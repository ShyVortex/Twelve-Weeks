/**
 * @file TEMPORARY playtester download of the prebuilt Part I Bookstore file set from our update server (MAPS tab, "Download from server").
 *
 * The files are exactly what the build stages for the map (converted level paks, audio, actor paks, render settings), as loose files with the
 * in-game paths. The server lists them at /part1-maps.json (tools/update_server/part1_maps.py) and serves /part1-files/<sha256>; the release
 * manifest never does. They land in <game dir>\t2r-maps\part1\<path> (the folder the mod's side-loader reads) and a marker files.json is written
 * LAST, only after every file is on disk with its listed size. Same layout as what the launcher-side converter (p1conv) writes from the player's
 * own Part I install (lib/maps-convert.js), which is the real, permanent route (re/launcher/part1-dlc.md).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const upd = require('./update');
const maps = require('./maps');

const NOT_AVAILABLE = 'Server maps are not available yet.';
const MAX_BYTES = 6 * 1024 ** 3;

/**
 * Fetch and validate the Part I file list from the update server.
 * @param {string} host update server base url
 * @returns {Promise<{pack: string, ver: number, total: number, files: {path: string, sha256: string, size: number, url: string}[]}>}
 */
async function fetchRemotePack(host) {
  if (!host) throw new Error('No file host configured (Settings > Files).');
  const root = upd.baseUrl(host);
  let m;
  try {
    m = await upd.getJson(`${root}/part1-maps.json`, 8000, { force: true });
  } catch (e) {
    if (/HTTP 404/.test(e.message)) throw new Error(NOT_AVAILABLE, { cause: e });
    throw upd.explainError(e);
  }
  if (m && Array.isArray(m.files) && !m.files.length) throw new Error(NOT_AVAILABLE);
  if (!m || !Array.isArray(m.files)) throw new Error('The server sent a broken Part I map list.');
  const seen = new Set();
  const files = m.files.map((f) => {
    if (
      !f ||
      !maps.isSafeRel(f.path) ||
      f.path === maps.FILES_MARKER ||
      seen.has(f.path) ||
      !/^[0-9a-f]{64}$/i.test(f.sha256 || '') ||
      !Number.isInteger(f.size) ||
      f.size < 0 ||
      f.size > MAX_BYTES
    )
      throw new Error('The server sent a broken Part I map list.');
    seen.add(f.path);
    const sha256 = f.sha256.toLowerCase();
    const url = new URL(f.url || `/part1-files/${sha256}`, root + '/');
    // the files come from the update server and nowhere else
    if (url.origin !== new URL(root).origin)
      throw new Error('The server sent a broken Part I map list.');
    return { path: f.path, sha256, size: f.size, url: url.toString() };
  });
  return {
    pack: String(m.pack || ''),
    ver: Number(m.ver) || 1,
    total: files.reduce((a, f) => a + f.size, 0),
    files,
  };
}

/**
 * Is this file already on disk, complete and identical (same size, same sha256)?
 * @param {string} dir
 * @param {{path: string, size: number, sha256: string}} f
 * @returns {Promise<boolean>}
 */
async function haveFile(dir, f) {
  try {
    const p = path.join(dir, ...f.path.split('/'));
    return fs.statSync(p).size === f.size && (await upd.sha256File(p)) === f.sha256;
  } catch {
    return false;
  }
}

/**
 * Download the file set into <game dir>\t2r-maps\part1\. Resumes half downloads, skips files that are already complete, verifies every sha256,
 * retries dropped connections, removes files an older pack had and this one does not, and writes the marker last.
 * @param {string} host
 * @param {string} gameDir
 * @param {{onProgress?: Function, signal?: AbortSignal, remote?: object}} [options]
 * @returns {Promise<{pack: string, files: number, downloaded: number, bytes: number}>}
 */
async function downloadRemotePack(host, gameDir, { onProgress, signal, remote } = {}) {
  if (!gameDir) throw new Error('Game folder not set.');
  const pack = remote || (await fetchRemotePack(host));
  const dir = maps.part1Dir(gameDir);
  fs.mkdirSync(dir, { recursive: true });
  const old = maps.readFilesMarker(gameDir);
  const todo = [];
  for (const f of pack.files) if (!(await haveFile(dir, f))) todo.push(f);
  const doneBefore = pack.files.filter((f) => !todo.includes(f)).reduce((a, f) => a + f.size, 0);
  const total = pack.total;
  // the set is "not installed" while its files change: the marker becomes files.json.pending, comes back if the run fails with the old set intact
  if (todo.length || (old && old.pack !== pack.pack)) maps.beginMarkerUpdate(gameDir);
  let ok = false;
  try {
    if (todo.length)
      await upd.downloadAll(todo, dir, {
        signal,
        concurrency: 3,
        onProgress: (p) => {
          if (!onProgress) return;
          const done = doneBefore + p.done;
          onProgress({
            done,
            total,
            speed: p.speed,
            eta: p.speed > 1 ? (total - done) / p.speed : null,
            files: pack.files.length,
            filesDone: pack.files.length - todo.length + (p.filesDone || 0),
          });
        },
      });
    // files of an older pack that this one no longer has (the old marker's paths were validated when it was read)
    if (old) {
      const keep = new Set(pack.files.map((f) => f.path));
      for (const f of old.files)
        if (!keep.has(f.path) && maps.isSafeRel(f.path))
          fs.rmSync(path.join(dir, ...f.path.split('/')), { force: true });
    }
    maps.writeFilesMarker(gameDir, pack);
    if (!maps.installedFileset(gameDir))
      throw new Error('The downloaded Part I map pack is incomplete. Try again later.');
    ok = true;
  } finally {
    maps.endMarkerUpdate(gameDir, ok);
  }
  return {
    pack: pack.pack,
    files: pack.files.length,
    downloaded: todo.length,
    bytes: todo.reduce((a, f) => a + f.size, 0),
  };
}

module.exports = { fetchRemotePack, downloadRemotePack };
