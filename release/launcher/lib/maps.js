/**
 * @file Map catalog, Part I install validation and DLC (map pack) import for the MAPS tab.
 *
 * The launcher ships NO Part I-derived file. Part I maps are a DLC: the player points the launcher at their own
 * The Last of Us Part I install (validated here, read-only) and the maps are pulled from it into <game dir>\t2r-maps\
 * (the pack folder the mod's ext already scans, re/part1/map-packs.md section 2). Testers get the files sent
 * separately and import them into the same folder.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { exeFileVersion } = require('./pe-version');

/** Where a map comes from; the details panel shows name + source. Data-driven: add Part I maps to PART1 below. */
const PART2 = [
  {
    id: 'forest',
    place: 'Seattle',
    name: 'Forest',
    source: 'Twelve Weeks original (No Return Forest)',
  },
  {
    id: 'gas-station',
    place: 'Seattle',
    name: 'Gas Station',
    source: 'Twelve Weeks original (No Return Gas Station)',
  },
  {
    id: 'school',
    place: 'Seattle',
    name: 'School',
    source: 'Twelve Weeks original (No Return School)',
  },
  {
    id: 'shipyard',
    place: 'Seattle',
    name: 'Shipyard',
    source: 'Twelve Weeks original (No Return Shipyard)',
  },
  {
    id: 'resort',
    place: 'Santa Barbara',
    name: 'Resort',
    source: 'Twelve Weeks original (No Return Resort)',
  },
  {
    id: 'seraphite-camp',
    place: 'Seattle',
    name: 'Seraphite Camp',
    source: 'Twelve Weeks original (Seraphite Camp)',
  },
  {
    id: 'houses',
    place: 'Seattle',
    name: 'Houses',
    source: 'Twelve Weeks original (Jesse houses)',
  },
  {
    id: 'hospital',
    place: 'Seattle',
    name: 'Hospital',
    source: 'Ellie - Seattle Day 3, Find Nora (hospital street)',
  },
  {
    id: 'train-station',
    place: 'Santa Barbara',
    name: 'Train Station',
    source: 'Ellie - Santa Barbara (streets before the Rattler resort)',
  },
  {
    id: 'downtown',
    place: 'Seattle',
    name: 'Downtown',
    source: 'Ellie - Seattle Day 1 (downtown hub north)',
  },
  {
    id: 'jackson-suburbs',
    place: 'Jackson',
    name: 'Jackson Suburbs',
    source: 'Ellie and Dina - Jackson patrol (snowy suburb street)',
  },
  {
    id: 'outpost',
    place: 'Santa Barbara',
    name: 'Suburbs',
    source: 'Ellie - Santa Barbara (Rattler outpost suburbs)',
  },
  {
    id: 'wilds-houses',
    place: 'Santa Barbara',
    name: 'Hillside',
    source: 'Ellie - Santa Barbara (infected wilds, hillside houses)',
  },
  {
    id: 'capitol-shops',
    place: 'Seattle',
    name: 'Capitol Hill Shops',
    source: 'Ellie - Seattle Day 1 (Olive Street plaza)',
  },
  {
    id: 'into-the-city',
    place: 'Seattle',
    name: 'Convention Center',
    source: 'Ellie - Seattle Day 3 (Convention Center east wall)',
  },
  {
    id: 'overpass',
    place: 'Seattle',
    name: 'Overpass',
    source: 'Abby - Seattle Day 3 (Scar Island highway overpass)',
  },
  {
    id: 'chase',
    place: 'Seattle',
    name: 'Chase',
    source: 'Abby - Seattle Day 3 (Tommy sniper fight, indoor part)',
  },
  {
    id: 'jackson-market',
    place: 'Jackson',
    name: 'Supermarket',
    source: 'Ellie and Dina - Jackson patrol (snowy supermarket)',
  },
];

/** Part I maps (DLC). `pack` = id of the pack manifest in t2r-maps\ that makes the map available. */
const PART1 = [
  {
    id: 'p1-bookstore',
    place: 'Pittsburgh',
    name: 'Bookstore',
    source: 'The Last of Us Part I - Pittsburgh checkpoint bookstore',
    pack: 'part1-a',
  },
  {
    id: 'p1-plaza',
    place: 'Pittsburgh',
    name: 'Plaza',
    source: 'The Last of Us Part I - Pittsburgh financial district plaza',
    pack: 'part1-a',
  },
];

/** The Part I PC version the conversion recipes are written for (exe string-table FileVersion). */
const PART1_VERSION = '1.1.4.0';
/** Archives the Part I maps are read from; all must be PSAR containers. world-hunter-city holds the Bookstore levels. */
const PART1_ARCHIVES = ['core.psarc', 'common.psarc', 'world-hunter-city.psarc'];
const PART1_EXES = ['tlou-i.exe', 'tlou-i-l.exe'];
const PACK_DIR = 't2r-maps';
/** Loose Part I file set (server download or p1conv): <game dir>	2r-maps\part1\<in-game path>, marker written LAST. */
const PART1_SUB = 'part1';
const FILES_MARKER = 'files.json';

/**
 * Check that a folder is a The Last of Us Part I (PC) install. Reads only; nothing is written.
 * @param {string} dir
 * @returns {{ok: boolean, reason?: string, exe?: string}}
 */
function validatePart1Dir(dir) {
  if (!dir || typeof dir !== 'string') return { ok: false, reason: 'No folder chosen.' };
  let exe = null;
  try {
    if (!fs.statSync(dir).isDirectory()) return { ok: false, reason: 'That is not a folder.' };
    exe = PART1_EXES.find((n) => fs.existsSync(path.join(dir, n)));
  } catch {
    return { ok: false, reason: 'That folder does not exist.' };
  }
  if (!exe) return { ok: false, reason: 'tlou-i.exe is not in that folder.' };
  const main = path.join(dir, 'build', 'pc', 'main');
  for (const n of [...PART1_ARCHIVES, 'pak68.txt']) {
    if (!fs.existsSync(path.join(main, n)))
      return {
        ok: false,
        reason: 'That folder looks incomplete: build\\pc\\main\\' + n + ' is missing.',
      };
  }
  for (const n of PART1_ARCHIVES) {
    try {
      const fd = fs.openSync(path.join(main, n), 'r');
      const head = Buffer.alloc(4);
      fs.readSync(fd, head, 0, 4, 0);
      fs.closeSync(fd);
      if (head.toString('latin1') !== 'PSAR')
        return { ok: false, reason: 'build\\pc\\main\\' + n + ' is not a Part I archive.' };
    } catch {
      return { ok: false, reason: 'Cannot read build\\pc\\main\\' + n + '.' };
    }
  }
  // the version the recipes are written for; an exe without readable version info is not rejected on that alone
  const version = exeFileVersion(path.join(dir, exe));
  if (version && version !== PART1_VERSION)
    return {
      ok: false,
      reason: 'Part I version {v} found, 1.1.4.0 required.',
      vars: { v: version },
    };
  return { ok: true, exe, version };
}

/**
 * Parse a pack manifest (t2r-maps\<anything>.txt, key=value lines, map= lines repeated).
 * @param {string} text
 * @returns {{id: string, ver: number, hash: string, file: string, size: number, maps: string[][]}|null}
 */
function parseManifest(text) {
  const m = { id: '', ver: 1, hash: '', file: '', size: -1, maps: [] };
  for (const line of String(text).split(/\r?\n/)) {
    const i = line.indexOf('=');
    if (i < 1) continue;
    const k = line.slice(0, i).trim();
    const v = line.slice(i + 1).trim();
    if (k === 'id') m.id = v;
    else if (k === 'ver') m.ver = parseInt(v, 10) || 1;
    else if (k === 'hash') m.hash = v.toLowerCase();
    else if (k === 'file') m.file = v;
    else if (k === 'size') m.size = parseInt(v, 10);
    else if (k === 'map') m.maps.push(v.split('|'));
  }
  if (!m.id || !/^[0-9a-f]{1,8}$/.test(m.hash) || !m.maps.length || !m.file) return null;
  if (/[\\/]/.test(m.file)) return null; // no path separators (map-packs.md)
  return m;
}

/**
 * List the installed packs of a game folder, with the same rule the ext uses: manifest parses and the archive
 * exists with exactly `size` bytes.
 * @param {string} gameDir
 * @returns {object[]}
 */
function installedPacks(gameDir) {
  const dir = path.join(gameDir || '', PACK_DIR);
  let names = [];
  try {
    names = fs.readdirSync(dir).filter((n) => /\.txt$/i.test(n));
  } catch {
    return [];
  }
  const out = [];
  for (const n of names) {
    let man = null;
    try {
      man = parseManifest(fs.readFileSync(path.join(dir, n), 'utf8'));
    } catch {
      /* unreadable manifest = not installed */
    }
    if (!man) continue;
    let size = -2;
    try {
      size = fs.statSync(path.join(dir, man.file)).size;
    } catch {
      /* archive missing */
    }
    if (size === man.size) out.push({ ...man, manifest: n });
  }
  return out;
}

const SEG = '[A-Za-z0-9][A-Za-z0-9._+-]{0,79}';
const PATH_RE = new RegExp(`^(?:${SEG}/){0,5}${SEG}$`);
/**
 * Is this a plain forward-slash relative in-game path (no '..', no absolute path, no empty segment)?
 * @param {unknown} p
 * @returns {boolean}
 */
function isSafeRel(p) {
  return typeof p === 'string' && PATH_RE.test(p);
}

/**
 * Is the Part I download / converter opted in? An empty t2r-playtest.txt in the game folder or the p1_tester setting.
 * @param {{game_dir?: string, p1_tester?: boolean}} cfg
 * @returns {boolean}
 */
function p1Tester(cfg) {
  if (cfg && cfg.p1_tester === true) return true;
  try {
    return !!(cfg && cfg.game_dir) && fs.existsSync(path.join(cfg.game_dir, 't2r-playtest.txt'));
  } catch {
    return false;
  }
}

/**
 * Take the marker out of the way while the files change: it becomes files.json.pending (same folder), so "installed" is false during the run
 * but the old set's description survives a failed run.
 * @param {string} gameDir
 * @returns {void}
 */
function beginMarkerUpdate(gameDir) {
  const dir = part1Dir(gameDir);
  const m = path.join(dir, FILES_MARKER);
  const pend = path.join(dir, FILES_MARKER + '.pending');
  if (fs.existsSync(m)) fs.renameSync(m, pend);
}

/**
 * End a marker update (call it in a finally). The new marker is already written on success: the pending copy goes. On failure the old marker comes
 * back when the old set is still intact on disk (every file, listed size), else it stays gone.
 * @param {string} gameDir
 * @param {boolean} ok
 * @returns {void}
 */
function endMarkerUpdate(gameDir, ok) {
  const dir = part1Dir(gameDir);
  const m = path.join(dir, FILES_MARKER);
  const pend = path.join(dir, FILES_MARKER + '.pending');
  try {
    if (!fs.existsSync(pend)) return;
    if (!ok && !fs.existsSync(m)) {
      const old = readFilesMarker(gameDir, FILES_MARKER + '.pending');
      const intact =
        old &&
        old.files.every((f) => {
          try {
            return fs.statSync(path.join(dir, ...f.path.split('/'))).size === f.size;
          } catch {
            return false;
          }
        });
      if (intact) {
        fs.renameSync(pend, m);
        return;
      }
    }
    fs.rmSync(pend, { force: true });
  } catch {
    /* best effort: a stray .pending is harmless (never read as the marker) */
  }
}

/**
 * Folder of the loose Part I file set.
 * @param {string} gameDir
 * @returns {string}
 */
function hasPart1Dat(gameDir) {
  try {
    return !!gameDir && fs.statSync(path.join(part1Dir(gameDir), 'part1.dat')).size > 0;
  } catch {
    return false;
  }
}

/**
 * The build id the mod's winmm.dll expects at the end of part1.dat: 16 bytes at +0x68 of its '.t2rps' section (tools/features/p1_side_map.py,
 * descriptor magic 'P1SD'). null = no such section (not a side-file build) or the file cannot be read.
 * @param {string} dll
 * @returns {Buffer|null}
 */
function winmmPart1Id(dll) {
  let fd;
  try {
    fd = fs.openSync(dll, 'r');
    const rd = (pos, n) => {
      const b = Buffer.alloc(n);
      return fs.readSync(fd, b, 0, n, pos) === n ? b : null;
    };
    const dos = rd(0, 64);
    if (!dos || dos.toString('latin1', 0, 2) !== 'MZ') return null;
    const nt = dos.readUInt32LE(0x3c);
    const fh = rd(nt, 24);
    if (!fh || fh.toString('latin1', 0, 4) !== 'PE\0\0') return null;
    const nsec = fh.readUInt16LE(6);
    const sec0 = nt + 24 + fh.readUInt16LE(20);
    for (let i = 0; i < nsec && i < 96; i++) {
      const sh = rd(sec0 + i * 40, 40);
      if (!sh) return null;
      if (sh.toString('latin1', 0, 6) !== '.t2rps' || sh[6] !== 0) continue;
      const raw = sh.readUInt32LE(20);
      const d = rd(raw, 0x78);
      if (!d || d.readUInt32LE(0) !== 0x44533150) return null;
      return d.subarray(0x68, 0x78);
    }
    return null;
  } catch {
    return null;
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

/**
 * The build id a part1.dat carries: its last 16 bytes. null = no file / too small.
 * @param {string} gameDir
 * @returns {Buffer|null}
 */
function part1DatId(gameDir) {
  let fd;
  try {
    const p = path.join(part1Dir(gameDir), 'part1.dat');
    const n = fs.statSync(p).size;
    if (n < 16) return null;
    fd = fs.openSync(p, 'r');
    const b = Buffer.alloc(16);
    return fs.readSync(fd, b, 0, 16, n - 16) === 16 ? b : null;
  } catch {
    return null;
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

/**
 * Does the part1.dat in the game folder belong to the installed mod build? An older build's part1.dat (players kept an old build's when the next one dropped
 * it from the client) is refused by winmm, so it must not count as installed. true / false; null = not known (no side-file winmm found).
 * The client folder's winmm.dll is the build being played after the next sync, so it wins over the game folder's copy.
 * @param {string} gameDir
 * @param {string} [clientDir]
 * @returns {boolean|null}
 */
function part1Current(gameDir, clientDir) {
  const dat = part1DatId(gameDir);
  for (const d of [clientDir, gameDir]) {
    if (!d) continue;
    const want = winmmPart1Id(path.join(d, 'winmm.dll'));
    if (want) return !!dat && dat.equals(want);
  }
  return null;
}

function part1Dir(gameDir) {
  return path.join(gameDir || '', PACK_DIR, PART1_SUB);
}

/**
 * Read the file-set marker ({pack, ver, files:[{path,size,sha256}]}) or null.
 * @param {string} gameDir
 * @returns {{pack: string, ver: number, files: {path: string, size: number, sha256: string}[]}|null}
 */
function readFilesMarker(gameDir, name = FILES_MARKER) {
  try {
    const m = JSON.parse(fs.readFileSync(path.join(part1Dir(gameDir), name), 'utf8'));
    if (!m || !Array.isArray(m.files) || !m.files.length || typeof m.pack !== 'string') return null;
    // a marker is only trusted when every path in it is a plain in-game relative path (the file set is deleted / statted by these)
    if (
      !m.files.every(
        (f) => f && isSafeRel(f.path) && f.path !== FILES_MARKER && Number.isInteger(f.size),
      )
    )
      return null;
    return { pack: m.pack, ver: Number(m.ver) || 1, files: m.files };
  } catch {
    return null;
  }
}

/**
 * Write the marker atomically. Call it last: its presence says the whole set is on disk.
 * @param {string} gameDir
 * @param {{pack: string, ver?: number, files: {path: string, size: number, sha256: string}[]}} set
 * @returns {void}
 */
function writeFilesMarker(gameDir, set) {
  const dir = part1Dir(gameDir);
  fs.mkdirSync(dir, { recursive: true });
  const body = JSON.stringify(
    {
      pack: set.pack,
      ver: set.ver || 1,
      files: set.files.map((f) => ({ path: f.path, size: f.size, sha256: f.sha256 })),
    },
    null,
    1,
  );
  const target = path.join(dir, FILES_MARKER);
  fs.writeFileSync(target + '.part', body);
  fs.renameSync(target + '.part', target);
}

/**
 * The installed loose file set: marker present and every listed file on disk with its listed size (cheap; hashes are checked when written).
 * @param {string} gameDir
 * @returns {{pack: string, ver: number, files: object[]}|null}
 */
function installedFileset(gameDir) {
  const m = readFilesMarker(gameDir);
  if (!m) return null;
  for (const f of m.files) {
    try {
      if (fs.statSync(path.join(part1Dir(gameDir), ...String(f.path).split('/'))).size !== f.size)
        return null;
    } catch {
      return null;
    }
  }
  return m;
}

/**
 * The state the MAPS tab shows.
 * @param {{game_dir?: string, tlou1_dir?: string}} cfg
 * @param {{clientDir?: string}} [opts] clientDir = the client folder (its winmm.dll names the part1.dat build it needs)
 * @returns {object}
 */
function mapsState(cfg, { clientDir } = {}) {
  const p1 = cfg.tlou1_dir ? validatePart1Dir(cfg.tlou1_dir) : { ok: false, reason: '' };
  const packs = cfg.game_dir ? installedPacks(cfg.game_dir) : [];
  const have = new Set(packs.map((p) => p.id));
  const set = cfg.game_dir ? installedFileset(cfg.game_dir) : null;
  if (set) have.add(set.pack);
  // the Part I file set (server download 'part1-<build>', converter 'part1-a') or a part1.dat in the game folder: Bookstore + Plaza are there,
  // unless that part1.dat is another build's (winmm turns the Part I maps off for it): then they are missing and the download is offered again
  const cur = cfg.game_dir ? part1Current(cfg.game_dir, clientDir) : null;
  if (cur === false) have.delete('part1-a');
  else if ((set && /^part1-/.test(set.pack)) || hasPart1Dat(cfg.game_dir)) have.add('part1-a');
  return {
    part2: PART2,
    part1: PART1.map((m) => ({ ...m, installed: have.has(m.pack) })),
    part1Stale: cur === false && hasPart1Dat(cfg.game_dir),
    tester: p1Tester(cfg),
    tlou1: { dir: cfg.tlou1_dir || '', valid: p1.ok, reason: p1.ok ? '' : p1.reason || '' },
    packDir: cfg.game_dir ? path.join(cfg.game_dir, PACK_DIR) : '',
    packs: packs.map((p) => ({ id: p.id, ver: p.ver, maps: p.maps.length })),
  };
}

/**
 * Tester import: copy the files the dev sent into <game dir>\t2r-maps\. Manifests (.txt) are copied LAST, after the
 * archives are complete, so a half-copied pack never counts. Only plain file names are accepted.
 * @param {string} gameDir
 * @param {string[]} files absolute paths
 * @returns {{copied: string[], packs: number}}
 */
function importFiles(gameDir, files) {
  if (!gameDir) throw new Error('Game folder not set.');
  const list = (files || []).filter((f) => typeof f === 'string' && f);
  if (!list.length) throw new Error('No map files chosen.');
  const bad = list.filter((f) => !/\.(psarc|pak|txt)$/i.test(f));
  if (bad.length) throw new Error('Only map pack files (.psarc, .pak, .txt) can be imported.');
  for (const f of list)
    if (!fs.statSync(f).isFile()) throw new Error('Not a file: ' + path.basename(f));
  const dest = path.join(gameDir, PACK_DIR);
  fs.mkdirSync(dest, { recursive: true });
  const data = list.filter((f) => !/\.txt$/i.test(f));
  const manifests = list.filter((f) => /\.txt$/i.test(f));
  const copied = [];
  for (const f of [...data, ...manifests]) {
    const target = path.join(dest, path.basename(f));
    const tmp = target + '.part';
    fs.copyFileSync(f, tmp);
    fs.renameSync(tmp, target);
    copied.push(path.basename(f));
  }
  return { copied, packs: installedPacks(gameDir).length };
}

module.exports = {
  PART1,
  PART1_VERSION,
  PART2,
  PACK_DIR,
  FILES_MARKER,
  isSafeRel,
  p1Tester,
  beginMarkerUpdate,
  endMarkerUpdate,
  part1Dir,
  part1Current,
  winmmPart1Id,
  readFilesMarker,
  writeFilesMarker,
  installedFileset,
  validatePart1Dir,
  parseManifest,
  installedPacks,
  mapsState,
  importFiles,
};
