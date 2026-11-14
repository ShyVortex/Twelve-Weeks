/**
 * @file Staged update application, journals and stale-file cleanup.
 */
'use strict';

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const { safeRel } = require('./util');
const { writeFileAtomic, sha256File, moveInto } = require('./files');

// Remove files that the old install had but the manifest dropped (only files we manage: listed in the previous state file)
/**
 * Remove files that are no longer present in the manifest.
 * @param {object} manifest
 * @param {string} dir
 * @param {string} stateFile
 * @returns {void}
 */
async function pruneOld(manifest, dir, stateFile) {
  let prev = [];
  try {
    prev = JSON.parse(fs.readFileSync(stateFile, 'utf8')).files || [];
  } catch {}
  const keep = new Set(manifest.files.map((f) => f.path));
  for (const p of prev)
    if (!keep.has(p)) {
      try {
        await fsp.unlink(path.join(dir, safeRel(p)));
      } catch {}
    }
  writeFileAtomic(stateFile, JSON.stringify({ version: manifest.version, files: [...keep] }));
}

// ---- staged swap-in. downloadAll({stage:true}) leaves every changed file as <path>.new (each one hash-verified before it got that name, so a .new
// that exists is complete and good). applyStaged() then renames them all into place in one quick pass, version.txt LAST, under a journal
// (.t2r-update.json). A launcher killed in the middle leaves the journal behind: recoverStaged() finishes (or reports) it on the next start, and
// play refuses while it exists, so the mod is never installed from a half-new client folder.
const JOURNAL = '.t2r-update.json';
/**
 * Return the update journal path for a directory.
 * @param {string} dir
 * @returns {string}
 */
const journalPath = (dir) => path.join(dir, JOURNAL);
/**
 * Atomically apply staged staged-file entries.
 * @param {object[]} list
 * @param {string} dir
 * @param {object} manifest
 * @returns {Promise<{applied: number}>}
 */
async function applyStaged(list, dir, manifest) {
  const files = list.map((f) => ({
    path: f.path,
    sha256: f.sha256,
    size: f.size,
  }));
  if (!files.length) return { applied: 0 };
  // version.txt (the "installed version" the launcher and the Play flow read) goes last
  files.sort((a, b) => (a.path === 'version.txt') - (b.path === 'version.txt'));
  writeFileAtomic(
    journalPath(dir),
    JSON.stringify({ version: manifest && manifest.version, files }),
  );
  for (const f of files) {
    const dest = path.join(dir, f.path);
    await fsp.mkdir(path.dirname(dest), { recursive: true });
    await moveInto(dest + '.new', dest);
  }
  await fsp.unlink(journalPath(dir)).catch(() => {});
  return { applied: files.length };
}
// Completes an interrupted applyStaged(). { pending: false } = nothing to do; { pending: true, complete: bool, missing: [paths] }.
const _recCache = new Map(); // dir -> { sig, res }: an incomplete journal is not re-hashed every 10 s while nothing on disk changed
/**
 * Compute a signature for the update journal.
 * @param {object} manifest
 * @param {object[]} applied
 * @returns {string}
 */
async function journalSig(dir, j) {
  const parts = [];
  try {
    parts.push((await fsp.stat(journalPath(dir))).mtimeMs);
  } catch {
    parts.push('x');
  }
  for (const f of j.files || []) {
    let rel;
    try {
      rel = safeRel(f.path);
    } catch {
      continue;
    }
    const dest = path.join(dir, rel);
    for (const p of [dest, dest + '.new']) {
      try {
        const st = await fsp.stat(p);
        parts.push(st.size + ':' + st.mtimeMs);
      } catch {
        parts.push('-');
      }
    }
  }
  return parts.join('|');
}
/**
 * Recover an interrupted staged update from its journal.
 * @param {string} dir
 * @returns {Promise<object>}
 */
async function recoverStaged(dir) {
  let j;
  try {
    j = JSON.parse(fs.readFileSync(journalPath(dir), 'utf8'));
  } catch (e) {
    if (e.code === 'ENOENT') return { pending: false };
    try {
      fs.unlinkSync(journalPath(dir));
    } catch {}
    return { pending: false };
  }
  const sig = await journalSig(dir, j),
    hit = _recCache.get(dir);
  if (hit && hit.sig === sig) return hit.res;
  const missing = [];
  for (const f of j.files || []) {
    let rel;
    try {
      rel = safeRel(f.path);
    } catch {
      continue;
    }
    const dest = path.join(dir, rel);
    let staged = false;
    try {
      staged = (await fsp.stat(dest + '.new')).size === f.size;
    } catch {}
    if (staged) {
      try {
        await moveInto(dest + '.new', dest);
        continue;
      } catch (e) {
        missing.push(rel);
        continue;
      }
    }
    let ok = false;
    try {
      ok = (await fsp.stat(dest)).size === f.size && (await sha256File(dest)) === f.sha256;
    } catch {}
    if (!ok) missing.push(rel);
  }
  if (!missing.length) {
    _recCache.delete(dir);
    await fsp.unlink(journalPath(dir)).catch(() => {});
    return { pending: true, complete: true, missing };
  }
  const res = { pending: true, complete: false, missing };
  _recCache.set(dir, { sig: await journalSig(dir, j), res });
  return res;
}
// leftovers of interrupted downloads that no manifest entry will ever resume (a file dropped from the manifest, an older build's .part)
/**
 * Delete stale staging artifacts after a successful update.
 * @param {object} manifest
 * @param {string} dir
 * @returns {void}
 */
async function sweepStale(manifest, dir) {
  const want = new Set();
  for (const f of manifest.files)
    for (const y of ['.part', '.z.part']) want.add(f.path + '.new' + y); // a plain <file>.part is an older launcher's (this one stages into .new): never resumed, can be hundreds of MB
  const keepNew = new Set(); // a .new that a pending journal still has to swap in is never swept
  const fwd = (p) => String(p).split('\\').join('/');
  try {
    for (const f of JSON.parse(fs.readFileSync(journalPath(dir), 'utf8')).files || [])
      keepNew.add(fwd(f.path) + '.new');
  } catch {}
  for (const f of manifest.files) keepNew.add(fwd(f.path) + '.new');
  let n = 0;
  const walk = async (d, rel) => {
    let ents;
    try {
      ents = await fsp.readdir(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of ents) {
      const r = rel ? rel + '/' + e.name : e.name;
      if (e.isDirectory()) {
        await walk(path.join(d, e.name), r);
        continue;
      }
      if (
        (/\.(part|z\.part)$/.test(e.name) && !want.has(r)) ||
        (/\.new$/.test(e.name) && !keepNew.has(r))
      ) {
        try {
          await fsp.unlink(path.join(d, e.name));
          n++;
        } catch {}
      }
    }
  };
  await walk(dir, '');
  return n;
}

module.exports = { journalPath, pruneOld, applyStaged, recoverStaged, sweepStale };
