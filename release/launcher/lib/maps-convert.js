/**
 * @file The Part I importer: run p1conv (tools/part1/p1conv.py, PyInstaller one-file) on the player's own Part I + Part II installs. This is
 * the only public route to the Part I maps (re/launcher/part1-dlc.md 10).
 *
 * The update server lists the importer for the current game data at /part1-importer.json: the converter binary per platform and the build's
 * recipe (part1-recipe.json: chunk layout, sizes and hashes, no Part I bytes). Both land in <userData>\p1conv\. `p1conv install` converts every
 * Part I map of the recipe and rebuilds <game dir>\t2r-maps\part1\part1.dat byte for byte (the file winmm maps behind the mod data); it prints
 * JSON lines on stdout (protocol: the docstring of p1conv.py). This module spawns it (no shell), turns the events into the launcher's progress,
 * kills it on cancel, and writes the files.json marker LAST, only when part1.dat is complete. Part I is only read.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const maps = require('./maps');
const upd = require('./update');

const PACK_PREFIX = 'part1-import-';
const PACK_ID = 'part1-a'; // (the older loose-file converter's marker id; mapsState still reads it)
const MAX_EXE = 512 * 1024 ** 2;
const MAX_RECIPE = 64 * 1024 ** 2;
const NO_IMPORTER = 'The Part I importer is not available for this game version yet.';

/**
 * <userData>\p1conv: the converter, the recipe, the work folder (converted files kept so the next build only re-writes part1.dat).
 * @param {string} userData
 * @returns {string}
 */
function importerDir(userData) {
  return path.join(userData || '', 'p1conv');
}

/** The converter is the Windows p1conv.exe on every platform: Linux runs it under Proton (Part I's archives are Oodle, decoded only by the
 * game's own oo2core_*_win64.dll), the same way as the slim tool and the Steam helper. */
function exeName() {
  return 'p1conv.exe';
}

/** An earlier import left its recipe in the work folder: p1conv can rebuild part1.dat from that part1.dat without Part I installed. */
function hasEarlierImport(workDir) {
  return !!workDir && fs.existsSync(path.join(workDir, 'part1dat-recipe.json'));
}

const PART1_NEEDED =
  'This update changes the Part I maps, so Part I is needed once more to convert them: install Part I, choose its folder here and press INSTALL FROM MY PART I.';

/**
 * Where the converter lives: F2_P1CONV (tests / dev), else <userData>\p1conv\p1conv(.exe) (downloaded by ensureImporter).
 * @param {string} userData
 * @returns {string} path, or '' when not installed
 */
function converterPath(userData) {
  const env = process.env.F2_P1CONV;
  if (env) return fs.existsSync(env) ? env : '';
  const p = path.join(importerDir(userData), exeName());
  return fs.existsSync(p) ? p : '';
}

/**
 * Fetch and validate /part1-importer.json: {build_id, recipe: {url, sha256, size}, converter: {win32|linux: {url, sha256, size}}}.
 * Every url must be on the update server itself.
 * @param {string} host update server base url
 * @returns {Promise<{buildId: string, recipe: object, converter: object}>}
 */
async function fetchImporter(host) {
  if (!host) throw new Error('No file host configured (Settings > Files).');
  const root = upd.baseUrl(host);
  let m;
  try {
    m = await upd.getJson(`${root}/part1-importer.json`, 8000, { force: true });
  } catch (e) {
    if (/HTTP 404/.test(e.message)) throw new Error(NO_IMPORTER, { cause: e });
    throw upd.explainError(e);
  }
  const file = (f, name, max) => {
    if (
      !f ||
      !/^[0-9a-f]{64}$/i.test(f.sha256 || '') ||
      !Number.isInteger(f.size) ||
      f.size <= 0 ||
      f.size > max
    )
      throw new Error('The server sent a broken Part I importer list.');
    const url = new URL(f.url || `/part1-files/${f.sha256.toLowerCase()}`, root + '/');
    // (both of the server's addresses count, lib/update/hosts.js sameServer; same rule as lib/maps-remote.js)
    if (!upd.hosts.sameServer(url.toString(), root))
      throw new Error('The server sent a broken Part I importer list.');
    return { path: name, sha256: f.sha256.toLowerCase(), size: f.size, url: url.toString() };
  };
  if (!m || !/^[0-9a-f]{32}$/i.test(m.build_id || '')) throw new Error(NO_IMPORTER);
  const conv = m.converter && m.converter.win32; // (Linux too: under Proton, see exeName)
  if (!conv) throw new Error(NO_IMPORTER);
  const buildId = m.build_id.toLowerCase();
  return {
    buildId,
    recipe: file(m.recipe, `part1-recipe-${buildId}.json`, MAX_RECIPE),
    converter: file(conv, exeName(), MAX_EXE),
  };
}

/**
 * Download the converter and this build's recipe into <userData>\p1conv\ (skipped when already there with the same sha256).
 * @param {string} host
 * @param {string} userData
 * @param {{signal?: AbortSignal, onProgress?: Function, importer?: object}} [options]
 * @returns {Promise<{exe: string, recipe: string, buildId: string}>}
 */
async function ensureImporter(host, userData, { signal, onProgress, importer } = {}) {
  const imp = importer || (await fetchImporter(host));
  const dir = importerDir(userData);
  fs.mkdirSync(dir, { recursive: true });
  const todo = [];
  for (const f of [imp.converter, imp.recipe]) {
    const p = path.join(dir, f.path);
    let ok = false;
    try {
      ok = fs.statSync(p).size === f.size && (await upd.sha256File(p)) === f.sha256;
    } catch {
      /* missing */
    }
    if (!ok) todo.push(f);
  }
  if (todo.length) await upd.downloadAll(todo, dir, { signal, concurrency: 2, onProgress });
  const exe = path.join(dir, imp.converter.path);
  return { exe, recipe: path.join(dir, imp.recipe.path), buildId: imp.buildId };
}

/**
 * Spawn the converter and read its JSON lines.
 * @param {{command: string, args: string[], onEvent?: Function, signal?: AbortSignal, cwd?: string, env?: object}} o
 * @returns {Promise<{done: object|null, events: number}>}
 */
function runProtocol({ command, args, onEvent, signal, cwd, env }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: env || process.env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let buf = '',
      done = null,
      err = null,
      events = 0,
      tail = '';
    // the whole tree: p1conv install runs `p1conv convert` children (PyInstaller: bootloader + python each), and killing only the
    // top process left a convert running on after CANCEL, writing into the work folder next to the next run's converter
    const onAbort = () => {
      try {
        if (process.platform === 'win32' && child.pid)
          spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
            windowsHide: true,
            stdio: 'ignore',
          }).on('error', () => child.kill());
        else child.kill();
      } catch {
        /* already gone */
      }
    };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }
    const line = (ln) => {
      if (!ln.trim()) return;
      let ev;
      try {
        ev = JSON.parse(ln);
      } catch {
        return; // not protocol (a stray print): ignored
      }
      if (!ev || typeof ev.event !== 'string') return;
      events++;
      if (ev.event === 'done') done = ev;
      if (ev.event === 'error') err = String(ev.message || 'conversion failed');
      try {
        if (onEvent) onEvent(ev);
      } catch (e) {
        err = err || e.message; // a handler refused the event (unsafe path): stop the converter, fail the run
        onAbort();
      }
    };
    child.stdout.on('data', (d) => {
      buf += d.toString('utf8');
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        line(buf.slice(0, i));
        buf = buf.slice(i + 1);
      }
    });
    child.stderr.on('data', (d) => {
      tail = (tail + d.toString('utf8')).slice(-2000);
    });
    child.on('error', (e) => reject(new Error(`Cannot start the Part I converter: ${e.message}`)));
    child.on('close', (code) => {
      if (buf.trim()) line(buf);
      if (signal && signal.aborted) return reject(new Error('cancelled'));
      if (err) return reject(new Error(err));
      if (code !== 0)
        return reject(
          new Error(
            `The Part I converter stopped (code ${code}). ${tail.trim().split('\n').pop() || ''}`.trim(),
          ),
        );
      resolve({ done, events });
    });
  });
}

/**
 * Import: convert the Part I install with the build's recipe into <game dir>\t2r-maps\part1\part1.dat and write the marker.
 * Part I may be missing when an earlier import exists (hasEarlierImport): p1conv then rebuilds part1.dat from the earlier one, and says
 * PART1_NEEDED only when the update changed Part I files.
 * Linux: command = <proton>/proton, prefixArgs = ['run', exe], env = its Proton env, pathArg = winPath (the converter sees Windows paths).
 * @param {{exe: string, recipe: string, buildId?: string, workDir: string, part1Dir: string, gameDir: string, onProgress?: Function, signal?: AbortSignal, extraArgs?: string[], command?: string, prefixArgs?: string[], env?: object, pathArg?: Function}} o
 * @returns {Promise<{pack: string, files: number, bytes: number}>}
 */
async function convertFromInstall({
  exe,
  recipe,
  buildId = '',
  workDir,
  part1Dir,
  gameDir,
  onProgress,
  signal,
  extraArgs = [],
  command,
  prefixArgs = [],
  env,
  pathArg = (p) => p,
  log,
}) {
  if (!gameDir) throw new Error('Game folder not set.');
  const check = maps.validatePart1Dir(part1Dir);
  if (!check.ok && !hasEarlierImport(workDir)) throw new Error(check.reason);
  if (!exe && !command) throw new Error('The Part I converter is not installed.');
  if (!recipe || !fs.existsSync(recipe)) throw new Error(NO_IMPORTER);
  const out = maps.part1Dir(gameDir);
  fs.mkdirSync(out, { recursive: true });
  maps.beginMarkerUpdate(gameDir); // not installed while the files change (files.json.pending; restored if the run fails with the old set intact)
  let ok = false;
  try {
    const files = [];
    let stage = '';
    // (reports: "stuck at Checking for updates") the bar shows the WHOLE run: stage i of n plus the share of the current stage, from the first
    // stage event on (the first stages - check, index, texindex - send no progress events and run for minutes on a first import)
    let stageI = 0,
      stageN = 0;
    const say = (m) => {
      try {
        if (log) log(`Part I converter: ${m}`);
      } catch {}
    };
    const r = await runProtocol({
      command: command || exe,
      args: [
        ...prefixArgs,
        'install',
        ...(check.ok ? ['--part1', pathArg(part1Dir)] : []),
        '--tlou2',
        pathArg(gameDir),
        '--recipe',
        pathArg(recipe),
        '--out',
        pathArg(out),
        '--work',
        pathArg(workDir),
        ...extraArgs,
      ],
      signal,
      env,
      onEvent: (ev) => {
        if (ev.event === 'stage') {
          stage = ev.name;
          if (Number.isInteger(ev.n) && ev.n > 0) {
            stageN = ev.n;
            stageI = Math.max(stageI, Math.min(ev.i | 0, ev.n));
          }
          say(`stage ${ev.name} (${ev.i}/${ev.n})`);
          if (onProgress && stageN) onProgress({ done: stageI, total: stageN, stage });
        }
        if (ev.event === 'log' || ev.event === 'error' || ev.event === 'hello')
          say(ev.message || JSON.stringify(ev));
        if (ev.event === 'file') {
          if (!maps.isSafeRel(ev.path) || ev.path === maps.FILES_MARKER)
            throw new Error('The Part I converter reported an unsafe file path.');
          files.push({ path: ev.path, size: ev.size, sha256: ev.sha256 });
        }
        // no label: the job's own translated "Converting Part I maps" stays on the bar (ev.label is a pak file name)
        if (onProgress && ev.event === 'progress') {
          const part = ev.total > 0 ? Math.min(1, Math.max(0, ev.done / ev.total)) : 0;
          if (stageN)
            onProgress({
              done: Math.min(stageN, stageI + part),
              total: stageN,
              file: ev.label,
              stage: ev.stage || stage,
            });
          else
            onProgress({
              done: ev.done,
              total: ev.total,
              file: ev.label,
              stage: ev.stage || stage,
            });
        }
      },
    }).catch((e) => {
      throw /^PART1_NEEDED/.test(e.message) ? new Error(PART1_NEEDED, { cause: e }) : e;
    });
    if (!r.done) throw new Error('The Part I converter ended without a result.');
    if (r.done.partial)
      throw new Error(
        'The Part I conversion is incomplete: ' + (r.done.missing || []).length + ' files missing.',
      );
    // every reported file must exist on disk with the reported size before the marker says "installed"
    for (const f of files) {
      let sz = -1;
      try {
        sz = fs.statSync(path.join(out, ...f.path.split('/'))).size;
      } catch {
        /* missing */
      }
      if (sz !== f.size) throw new Error('The Part I converter wrote a damaged file: ' + f.path);
    }
    if (!files.some((f) => f.path === 'part1.dat'))
      throw new Error('The Part I converter ended without writing part1.dat.');
    const pack = buildId ? PACK_PREFIX + buildId.slice(0, 12) : PACK_ID;
    maps.writeFilesMarker(gameDir, { pack, ver: 1, files });
    ok = true;
    return { pack, files: files.length, bytes: files.reduce((a, f) => a + f.size, 0) };
  } finally {
    maps.endMarkerUpdate(gameDir, ok);
  }
}

module.exports = {
  converterPath,
  importerDir,
  fetchImporter,
  ensureImporter,
  runProtocol,
  convertFromInstall,
  hasEarlierImport,
  PACK_ID,
  NO_IMPORTER,
  PART1_NEEDED,
};
