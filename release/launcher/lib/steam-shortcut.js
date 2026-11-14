/**
 * @file ADD TO STEAM: adds the launcher to Steam as a non-Steam game ("Twelve Weeks") with its library art.
 *
 * Steam keeps non-Steam games in userdata/<accountid>/config/shortcuts.vdf (BINARY VDF) and its art in userdata/<accountid>/config/grid/.
 * Steam rewrites shortcuts.vdf when it exits, so the file is only written while Steam is not running (the caller asks Steam to quit politely first).
 * Everything here takes its folders and process hooks as arguments so tests run on a fake Steam folder and never touch the real one.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile, spawn } = require('child_process');

const APP_NAME = 'Twelve Weeks';
const OUR_NAMES = ['twelve weeks', 'twelve weeks launcher'];
const BASE_ID = 76561197960265728n;
const BACKUP_SUFFIX = '.bak-twelveweeks';

// ---------------------------------------------------------------- crc32 / appid
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

/**
 * @param {Buffer|string} data
 * @returns {number} unsigned crc32 (same as Python zlib.crc32)
 */
function crc32(data) {
  const b = Buffer.isBuffer(data) ? data : Buffer.from(String(data), 'utf8');
  let c = 0xffffffff;
  for (let i = 0; i < b.length; i++) c = CRC_TABLE[(c ^ b[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/**
 * Steam's id of a non-Steam game: crc32(quoted exe + app name) with the top bit set. Unsigned (grid file names); the vdf stores it as int32.
 * @param {string} quotedExe
 * @param {string} appName
 * @returns {number}
 */
function shortcutAppId(quotedExe, appName) {
  return (crc32(quotedExe + appName) | 0x80000000) >>> 0;
}

// ---------------------------------------------------------------- binary vdf
// value types: 0 map (nested), 1 string, 2 int32, 3 float32, 4 pointer, 6 colour, 7 uint64, 10 int64; 8 ends a map.
// A map is read into an ordered list of { t, k, v } and written back identically, so entries Steam or the player made survive untouched.
const FIXED = { 2: 4, 3: 4, 4: 4, 6: 4, 7: 8, 10: 8 };

function readCStr(buf, pos) {
  const end = buf.indexOf(0, pos);
  if (end < 0) throw new Error('shortcuts.vdf: unterminated string');
  return [buf.toString('utf8', pos, end), end + 1];
}

function readMap(buf, pos) {
  const items = [];
  for (;;) {
    if (pos >= buf.length) throw new Error('shortcuts.vdf: truncated');
    const t = buf[pos++];
    if (t === 8) return [items, pos];
    let k, v;
    [k, pos] = readCStr(buf, pos);
    if (t === 0) [v, pos] = readMap(buf, pos);
    else if (t === 1) [v, pos] = readCStr(buf, pos);
    else if (FIXED[t]) {
      if (pos + FIXED[t] > buf.length) throw new Error('shortcuts.vdf: truncated');
      v = Buffer.from(buf.subarray(pos, pos + FIXED[t]));
      pos += FIXED[t];
    } else throw new Error('shortcuts.vdf: unknown value type ' + t);
    items.push({ t, k, v });
  }
}

/**
 * @param {Buffer|null} buf
 * @returns {Array} the root map items (an empty buffer = an empty root)
 */
function parseVdf(buf) {
  if (!buf || !buf.length) return [];
  const [root, end] = readMap(buf, 0);
  if (end < buf.length && buf.subarray(end).some((x) => x !== 0))
    throw new Error('shortcuts.vdf: trailing data');
  return root;
}

function writeMap(items, out) {
  for (const it of items) {
    out.push(Buffer.from([it.t]), Buffer.from(it.k + '\0', 'utf8'));
    if (it.t === 0) writeMap(it.v, out);
    else if (it.t === 1) out.push(Buffer.from(it.v + '\0', 'utf8'));
    else out.push(it.v);
  }
  out.push(Buffer.from([8]));
}

/**
 * @param {Array} root
 * @returns {Buffer}
 */
function serializeVdf(root) {
  const out = [];
  writeMap(root, out);
  return Buffer.concat(out);
}

const i32 = (n) => {
  const b = Buffer.alloc(4);
  b.writeInt32LE(n | 0);
  return b;
};
const lc = (s) => String(s).toLowerCase();
const field = (entry, key) => entry.v.find((f) => lc(f.k) === lc(key));
const strOf = (entry, key) => {
  const f = field(entry, key);
  return f && f.t === 1 ? f.v : '';
};
function setField(entry, key, t, v) {
  const f = field(entry, key);
  if (f) {
    f.t = t;
    f.v = v;
  } else entry.v.push({ t, k: key, v });
}
const setStr = (e, k, v) => setField(e, k, 1, v);
const setInt = (e, k, n) => setField(e, k, 2, i32(n));

const unquote = (s) =>
  String(s)
    .trim()
    .replace(/^"(.*)"$/, '$1');
const normPath = (s) => path.normalize(unquote(s).replace(/\//g, path.sep)).toLowerCase();
const quote = (s) => '"' + s + '"';

/**
 * Is this entry the launcher: same exe (quotes / slashes / case ignored) or a known launcher name.
 * @param {object} entry
 * @param {string} exe
 * @returns {boolean}
 */
function isOurs(entry, exe) {
  return (
    normPath(strOf(entry, 'Exe')) === normPath(exe) ||
    OUR_NAMES.includes(lc(strOf(entry, 'AppName')))
  );
}

/**
 * Adds or updates the launcher's entry in a parsed shortcuts root (an entry of the player's own is updated in place, never duplicated).
 * @param {Array} root
 * @param {{exe: string, startDir: string, icon: string}} o
 * @returns {{ appid: number, created: boolean, oldAppid: number|null, entry: object }}
 */
function upsertShortcut(root, { exe, startDir, icon }) {
  let sc = root.find((f) => f.t === 0 && lc(f.k) === 'shortcuts');
  if (!sc) {
    sc = { t: 0, k: 'shortcuts', v: [] };
    root.push(sc);
  }
  const qExe = quote(exe);
  let entry = sc.v.find((e) => e.t === 0 && isOurs(e, exe));
  let created = false,
    oldAppid = null,
    appid;
  if (!entry) {
    created = true;
    const next = sc.v.reduce((m, e) => (/^\d+$/.test(e.k) ? Math.max(m, +e.k + 1) : m), 0);
    entry = { t: 0, k: String(next), v: [] };
    sc.v.push(entry);
    appid = shortcutAppId(qExe, APP_NAME);
  } else {
    const f = field(entry, 'appid');
    if (f && f.t === 2) oldAppid = f.v.readUInt32LE(0);
    // exe and name unchanged: keep the id (and the art the player may already have under it); otherwise the id follows the new exe / name
    const same = strOf(entry, 'Exe') === qExe && strOf(entry, 'AppName') === APP_NAME;
    appid = same && oldAppid !== null ? oldAppid : shortcutAppId(qExe, APP_NAME);
  }
  setInt(entry, 'appid', appid);
  setStr(entry, 'AppName', APP_NAME);
  setStr(entry, 'Exe', qExe);
  setStr(entry, 'StartDir', quote(startDir));
  setStr(entry, 'icon', icon || '');
  if (!field(entry, 'ShortcutPath')) setStr(entry, 'ShortcutPath', '');
  if (!field(entry, 'LaunchOptions')) setStr(entry, 'LaunchOptions', '');
  if (!field(entry, 'IsHidden')) setInt(entry, 'IsHidden', 0);
  setInt(entry, 'AllowDesktopConfig', 1);
  setInt(entry, 'AllowOverlay', 1);
  setInt(entry, 'OpenVR', 0);
  if (!field(entry, 'Devkit')) setInt(entry, 'Devkit', 0);
  if (!field(entry, 'DevkitGameID')) setStr(entry, 'DevkitGameID', '');
  if (!field(entry, 'DevkitOverrideAppID')) setInt(entry, 'DevkitOverrideAppID', 0);
  if (!field(entry, 'LastPlayTime')) setInt(entry, 'LastPlayTime', 0);
  if (!field(entry, 'tags')) entry.v.push({ t: 0, k: 'tags', v: [] });
  return { appid, created, oldAppid, entry };
}

// ---------------------------------------------------------------- finding Steam and its users
function regSteamPath() {
  return new Promise((resolve) => {
    execFile(
      'reg',
      ['query', 'HKCU\\Software\\Valve\\Steam', '/v', 'SteamPath'],
      { windowsHide: true, timeout: 5000 },
      (err, out) => {
        const m = !err && /SteamPath\s+REG_SZ\s+(.+)/i.exec(String(out));
        resolve(m ? m[1].trim() : '');
      },
    );
  });
}

/**
 * @param {object} [env]
 * @param {string} [platform]
 * @returns {Promise<string>} Steam's folder, or '' (F2_STEAM_DIR overrides, for tests)
 */
async function findSteamDir(env = process.env, platform = process.platform) {
  if (env.F2_STEAM_DIR) return fs.existsSync(env.F2_STEAM_DIR) ? env.F2_STEAM_DIR : '';
  const cands = [];
  if (platform === 'win32') {
    cands.push(await regSteamPath());
    for (const v of ['ProgramFiles(x86)', 'ProgramFiles'])
      if (env[v]) cands.push(path.join(env[v], 'Steam'));
    cands.push('C:\\Program Files (x86)\\Steam');
  } else {
    const h = os.homedir();
    cands.push(
      path.join(h, '.steam', 'steam'),
      path.join(h, '.local', 'share', 'Steam'),
      path.join(h, '.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam'),
    );
  }
  for (const c of cands) if (c && fs.existsSync(path.join(c, 'userdata'))) return path.resolve(c);
  return '';
}

/**
 * @param {string} steamDir
 * @returns {string[]} the userdata/<accountid> folders to write: the most recent login, else every account that has a folder
 */
function steamUserDirs(steamDir) {
  const ud = path.join(steamDir, 'userdata');
  if (!fs.existsSync(ud)) return [];
  const have = new Set(fs.readdirSync(ud).filter((n) => /^\d+$/.test(n) && n !== '0'));
  let recent = [],
    all = [];
  try {
    const txt = fs.readFileSync(path.join(steamDir, 'config', 'loginusers.vdf'), 'utf8');
    for (const m of txt.matchAll(/"(\d{16,20})"\s*\{([^}]*)\}/g)) {
      const id = String(BigInt(m[1]) - BASE_ID);
      all.push(id);
      if (/"MostRecent"\s+"1"/i.test(m[2])) recent.push(id);
    }
  } catch {
    /* no loginusers.vdf: fall back to the folders */
  }
  recent = recent.filter((i) => have.has(i));
  all = all.filter((i) => have.has(i));
  const pick = recent.length ? recent : all.length ? all : [...have];
  return pick.map((i) => path.join(ud, i));
}

// ---------------------------------------------------------------- Steam process
function listProcesses(platform = process.platform) {
  return new Promise((resolve) => {
    const [cmd, args] =
      platform === 'win32'
        ? ['tasklist', ['/FI', 'IMAGENAME eq steam.exe', '/NH']]
        : ['pgrep', ['-x', 'steam']];
    execFile(cmd, args, { windowsHide: true, timeout: 8000 }, (err, out) =>
      resolve(String(out || '')),
    );
  });
}

/**
 * Is Steam running? Read-only: tasklist / pgrep output.
 * @param {string} [platform]
 * @param {Function} [list]
 * @returns {Promise<boolean>}
 */
async function steamRunning(platform = process.platform, list = listProcesses) {
  const out = await list(platform);
  return platform === 'win32' ? /^steam\.exe\s/im.test(out) : /^\d+\s*$/m.test(out);
}

const steamExe = (steamDir, platform = process.platform) =>
  platform === 'win32' ? path.join(steamDir, 'steam.exe') : path.join(steamDir, 'steam.sh');

/**
 * Asks Steam to quit (never a kill) and waits until it is gone.
 * @param {object} o
 * @returns {Promise<boolean>} true when it is gone
 */
async function quitSteam({
  steamDir,
  platform = process.platform,
  running = () => steamRunning(platform),
  ask,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  timeoutMs = 30000,
}) {
  (
    ask ||
    (() => {
      spawn(steamExe(steamDir, platform), ['-shutdown'], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
        cwd: steamDir,
      })
        .on('error', () => {})
        .unref();
    })
  )();
  for (let waited = 0; waited < timeoutMs; waited += 500) {
    if (!(await running())) return true;
    await sleep(500);
  }
  return !(await running());
}

/**
 * @param {string} steamDir
 * @param {string} [platform]
 * @returns {void}
 */
function startSteam(steamDir, platform = process.platform) {
  spawn(steamExe(steamDir, platform), [], { detached: true, stdio: 'ignore', cwd: steamDir })
    .on('error', () => {})
    .unref();
}

// ---------------------------------------------------------------- state / removal
const GRID_STEMS = (id) => [id + 'p', String(id), id + '_hero', id + '_logo'];
const GRID_EXTS = ['.png', '.jpg', '.jpeg', '.webp'];

/**
 * Is the launcher's shortcut in Steam for every target account? Reads shortcuts.vdf only (cheap; no process probe).
 * @param {{steamDir: string, exe: string}} o
 * @returns {boolean}
 */
function isAdded({ steamDir, exe }) {
  const users = steamUserDirs(steamDir);
  if (!users.length) return false;
  return users.every((u) => {
    try {
      const file = path.join(u, 'config', 'shortcuts.vdf');
      if (!fs.existsSync(file)) return false;
      const sc = parseVdf(fs.readFileSync(file)).find((f) => f.t === 0 && lc(f.k) === 'shortcuts');
      return !!sc && sc.v.some((e) => e.t === 0 && isOurs(e, exe));
    } catch {
      return false;
    }
  });
}

/**
 * Removes the launcher's entry (same match rule as the update path) and its four grid files; every other entry stays, renumbered 0..n-1.
 * @param {{steamDir: string, exe: string, log?: Function}} o
 * @returns {{ removed: number }}
 */
function removeFromSteam({ steamDir, exe, log = () => {} }) {
  let removed = 0;
  for (const u of steamUserDirs(steamDir)) {
    const cfg = path.join(u, 'config');
    const file = path.join(cfg, 'shortcuts.vdf');
    if (!fs.existsSync(file)) continue;
    const orig = fs.readFileSync(file);
    const root = parseVdf(orig);
    const sc = root.find((f) => f.t === 0 && lc(f.k) === 'shortcuts');
    if (!sc) continue;
    const gone = sc.v.filter((e) => e.t === 0 && isOurs(e, exe));
    if (!gone.length) continue;
    if (!fs.existsSync(file + BACKUP_SUFFIX)) fs.writeFileSync(file + BACKUP_SUFFIX, orig);
    sc.v = sc.v.filter((e) => !gone.includes(e));
    let i = 0;
    for (const e of sc.v) if (e.t === 0 && /^\d+$/.test(e.k)) e.k = String(i++);
    fs.writeFileSync(file + '.part', serializeVdf(root));
    fs.renameSync(file + '.part', file);
    for (const e of gone) {
      const f = field(e, 'appid');
      if (!f || f.t !== 2) continue;
      const id = f.v.readUInt32LE(0);
      for (const stem of GRID_STEMS(id))
        for (const x of GRID_EXTS) fs.rmSync(path.join(cfg, 'grid', stem + x), { force: true });
    }
    removed += gone.length;
    log('steam: removed ' + gone.length + ' shortcut(s) for account ' + path.basename(u));
  }
  return { removed };
}

// ---------------------------------------------------------------- the whole job
const ART = { cover: 'cover.jpg', wide: 'wide.jpg', hero: 'hero.jpg', logo: 'logo.png' };

/**
 * Writes the shortcut + art for every target account. Steam must not be running (the caller checks).
 * @param {object} o { steamDir, exe, startDir, icon, artDir, log }  artDir holds cover.jpg wide.jpg hero.jpg logo.png
 * @returns {{ users: number, created: number, updated: number, appid: number }}
 */
function addToSteam({ steamDir, exe, startDir, icon, artDir, log = () => {} }) {
  const users = steamUserDirs(steamDir);
  if (!users.length)
    throw Object.assign(new Error('No Steam account was found.'), { code: 'no-user' });
  let created = 0,
    updated = 0,
    appid = 0;
  for (const u of users) {
    const cfg = path.join(u, 'config');
    const file = path.join(cfg, 'shortcuts.vdf');
    fs.mkdirSync(cfg, { recursive: true });
    const orig = fs.existsSync(file) ? fs.readFileSync(file) : null;
    const root = parseVdf(orig); // throws on a file that cannot be read exactly: nothing is written then
    if (orig && !fs.existsSync(file + BACKUP_SUFFIX)) fs.writeFileSync(file + BACKUP_SUFFIX, orig);
    const r = upsertShortcut(root, { exe, startDir, icon });
    appid = r.appid;
    fs.writeFileSync(file + '.part', serializeVdf(root));
    fs.renameSync(file + '.part', file);
    r.created ? created++ : updated++;
    const grid = path.join(cfg, 'grid');
    fs.mkdirSync(grid, { recursive: true });
    const names = {
      cover: r.appid + 'p' + path.extname(ART.cover),
      wide: r.appid + path.extname(ART.wide),
      hero: r.appid + '_hero' + path.extname(ART.hero),
      logo: r.appid + '_logo' + path.extname(ART.logo),
    };
    for (const k of Object.keys(ART)) {
      const dest = path.join(grid, names[k]);
      // Steam picks the first art file it finds per kind: an older .png/.jpg of the same name would hide ours
      for (const x of ['.png', '.jpg', '.jpeg', '.webp']) {
        const other = dest.slice(0, dest.length - path.extname(dest).length) + x;
        if (other !== dest) fs.rmSync(other, { force: true });
      }
      fs.copyFileSync(path.join(artDir, ART[k]), dest);
    }
    log(
      'steam: ' +
        (r.created ? 'added' : 'updated') +
        ' shortcut ' +
        r.appid +
        ' for account ' +
        path.basename(u),
    );
  }
  return { users: users.length, created, updated, appid };
}

/**
 * The exe a Steam entry must start: the AppImage, else the portable exe the player runs, else the installed runtime exe (stable path), else this process.
 * @param {object} o { env, root, rootExe, execPath, exists }
 * @returns {string}
 */
function launcherExe({
  env = process.env,
  root = '',
  rootExe = '',
  execPath = process.execPath,
  exists = fs.existsSync,
} = {}) {
  if (env.APPIMAGE && exists(env.APPIMAGE)) return env.APPIMAGE;
  if (env.PORTABLE_EXECUTABLE_FILE && exists(env.PORTABLE_EXECUTABLE_FILE))
    return env.PORTABLE_EXECUTABLE_FILE;
  const installed = root && rootExe ? path.join(root, rootExe) : '';
  if (installed && exists(installed)) return installed;
  return execPath;
}

module.exports = {
  launcherExe,
  APP_NAME,
  crc32,
  shortcutAppId,
  parseVdf,
  serializeVdf,
  upsertShortcut,
  isOurs,
  findSteamDir,
  steamUserDirs,
  steamRunning,
  quitSteam,
  startSteam,
  addToSteam,
  isAdded,
  removeFromSteam,
};
