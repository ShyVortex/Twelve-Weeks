/**
 * @file Run p1conv (tools/part1/p1conv.py, PyInstaller one-file) on the player's own Part I install: the real, permanent route to the Part I maps.
 *
 * The converter writes the Part I Bookstore file set under the in-game paths into <game dir>\t2r-maps\part1\ (same layout and same bytes as the
 * server pack of lib/maps-remote.js) and prints JSON lines on stdout (protocol: the docstring of p1conv.py). This module spawns it (no shell),
 * turns the events into the launcher's progress, kills it on cancel, and writes the files.json marker LAST, only when the converter says the set is
 * complete. Part I is only read.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const maps = require('./maps');

const PACK_ID = 'part1-a';

/**
 * Where the converter lives: F2_P1CONV (tests / dev), else <userData>\p1conv\p1conv.exe (downloaded with the launcher's blobs).
 * @param {string} userData
 * @returns {string} path, or '' when not installed
 */
function converterPath(userData) {
  const env = process.env.F2_P1CONV;
  if (env) return fs.existsSync(env) ? env : '';
  const p = path.join(
    userData || '',
    'p1conv',
    process.platform === 'win32' ? 'p1conv.exe' : 'p1conv',
  );
  return fs.existsSync(p) ? p : '';
}

/**
 * Spawn the converter and read its JSON lines.
 * @param {{command: string, args: string[], onEvent?: Function, signal?: AbortSignal, cwd?: string}} o
 * @returns {Promise<{done: object|null, events: number}>}
 */
function runProtocol({ command, args, onEvent, signal, cwd }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let buf = '',
      done = null,
      err = null,
      events = 0,
      tail = '';
    const onAbort = () => {
      try {
        child.kill();
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
 * Convert the Part I install into <game dir>\t2r-maps\part1\ and write the marker.
 * @param {{exe: string, part1Dir: string, gameDir: string, onProgress?: Function, signal?: AbortSignal, extraArgs?: string[], command?: string, prefixArgs?: string[]}} o
 * @returns {Promise<{pack: string, files: number, bytes: number}>}
 */
async function convertFromInstall({
  exe,
  part1Dir,
  gameDir,
  onProgress,
  signal,
  extraArgs = [],
  command,
  prefixArgs = [],
}) {
  if (!gameDir) throw new Error('Game folder not set.');
  const check = maps.validatePart1Dir(part1Dir);
  if (!check.ok) throw new Error(check.reason);
  if (!exe && !command) throw new Error('The Part I converter is not installed.');
  const out = maps.part1Dir(gameDir);
  fs.mkdirSync(out, { recursive: true });
  maps.beginMarkerUpdate(gameDir); // not installed while the files change (files.json.pending; restored if the run fails with the old set intact)
  let ok = false;
  try {
    const files = [];
    let stage = '';
    const r = await runProtocol({
      command: command || exe,
      args: [
        ...prefixArgs,
        'convert',
        '--part1',
        part1Dir,
        '--tlou2',
        gameDir,
        '--out',
        out,
        ...extraArgs,
      ],
      signal,
      onEvent: (ev) => {
        if (ev.event === 'stage') stage = ev.name;
        if (ev.event === 'file') {
          if (!maps.isSafeRel(ev.path) || ev.path === maps.FILES_MARKER)
            throw new Error('The Part I converter reported an unsafe file path.');
          files.push({ path: ev.path, size: ev.size, sha256: ev.sha256 });
        }
        if (onProgress && ev.event === 'progress')
          onProgress({ done: ev.done, total: ev.total, label: ev.label, stage: ev.stage || stage });
      },
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
    maps.writeFilesMarker(gameDir, { pack: PACK_ID, ver: 1, files });
    ok = true;
    return { pack: PACK_ID, files: files.length, bytes: files.reduce((a, f) => a + f.size, 0) };
  } finally {
    maps.endMarkerUpdate(gameDir, ok);
  }
}

module.exports = { converterPath, runProtocol, convertFromInstall, PACK_ID };
