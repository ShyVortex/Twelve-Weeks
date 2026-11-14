/**
 * @file File verification, resumable downloads and staged updates.
 */
'use strict';

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { pipeline } = require('stream/promises');
const { LOCK_CODES, SPACE_CODES, tunables, sleep, DECODERS } = require('./util');
const { explainError, ensureSpace } = require('./errors');
const { request } = require('./net');

/**
 * Write a file through a temporary path and atomic rename.
 * @param {string} file
 * @param {string} text
 * @returns {void}
 */
function writeFileAtomic(file, text) {
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, text);
  fs.renameSync(tmp, file);
}

/**
 * Hash a file while optionally reporting bytes read.
 * @param {string} file
 * @param {(bytes: number) => void} [onBytes]
 * @returns {Promise<string>}
 */
function sha256File(file, onBytes) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    const s = fs.createReadStream(file, { highWaterMark: 1 << 20 });
    s.on('data', (c) => {
      h.update(c);
      if (onBytes) onBytes(c.length);
    });
    s.on('error', reject);
    s.on('end', () => resolve(h.digest('hex')));
  });
}

/**
 * Load the size/mtime hash cache.
 * @param {string} cacheFile
 * @returns {object}
 */
function loadHashCache(cacheFile) {
  try {
    return JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
  } catch {
    return {};
  }
}

/**
 * Persist the hash cache, ignoring a locked or unwritable cache file.
 * @param {string} cacheFile
 * @param {object} cache
 * @returns {void}
 */
function saveHashCache(cacheFile, cache) {
  try {
    writeFileAtomic(cacheFile, JSON.stringify(cache));
  } catch {}
}

/**
 * Check one manifest entry against the local file and update the hash cache.
 * @param {object} f
 * @param {string} dir
 * @param {object} cache
 * @param {{full?: boolean, onHashed?: (bytes: number) => void}} [options]
 * @returns {Promise<boolean>}
 */
async function verifyFile(f, dir, cache, { full = false, onHashed } = {}) {
  const p = path.join(dir, f.path);
  let st = null;
  try {
    st = await fsp.stat(p);
  } catch {}
  if (!st || st.size !== f.size) return false;
  const c = cache[f.path];
  // the cache holds the LOCAL file's hash (matching or not): with an update pending, the 10 s re-check must not re-hash an unchanged 800 MB file
  if (!full && c && c.size === st.size && c.mtime === st.mtimeMs) return c.sha256 === f.sha256;
  let h;
  try {
    h = await sha256File(p, (n) => {
      if (onHashed) onHashed(n);
    });
  } catch {
    return false;
  } // a file that cannot be read (locked by an antivirus scan) is replaced rather than failing the whole check
  cache[f.path] = { size: st.size, mtime: st.mtimeMs, sha256: h };
  return h === f.sha256;
}

// Which files differ from the manifest? Uses a size+mtime hash cache so a normal check is instant.
/**
 * Compare a manifest against local files, using a size/mtime hash cache.
 * @param {object} manifest
 * @param {string} dir
 * @param {string} cacheFile
 * @param {{full?: boolean, onProgress?: Function}} [options]
 * @returns {Promise<object[]>}
 */
async function diffFiles(manifest, dir, cacheFile, { full = false, onProgress } = {}) {
  const cache = loadHashCache(cacheFile);
  const bad = [];
  const total = manifest.files.reduce((a, f) => a + f.size, 0);
  let hashed = 0;
  for (const f of manifest.files) {
    const ok = await verifyFile(f, dir, cache, {
      full,
      onHashed: (n) => {
        hashed += n;
        if (onProgress) onProgress({ phase: 'verify', done: hashed, total });
      },
    });
    if (!ok) bad.push(f);
  }
  saveHashCache(cacheFile, cache);
  return bad;
}

/**
 * Read the number of bytes already present in a partial file.
 * @param {string} part
 * @returns {Promise<number>}
 */
async function partSize(part) {
  try {
    return (await fsp.stat(part)).size;
  } catch {
    return 0;
  }
}

/**
 * Perform one ranged transfer attempt and append it to the part file.
 * @param {string} url
 * @param {string} part
 * @param {number} have
 * @param {{onBytes?: Function, signal?: AbortSignal, headers?: object}} [options]
 * @returns {Promise<void>}
 */
async function transferRange(url, part, have, { onBytes, signal, headers } = {}) {
  const res = await request(url, {
    headers: {
      ...(headers || {}),
      ...(have ? { Range: `bytes=${have}-` } : {}),
    },
    timeout: 20000,
  });
  if (res.statusCode === 416) {
    res.resume();
    if (onBytes) onBytes(-have);
    await fsp.unlink(part).catch(() => {});
    throw new Error('HTTP 416 (the partial file no longer matches, starting it again)');
  }
  if (res.statusCode === 200 && have) {
    if (onBytes) onBytes(-have);
    have = 0;
    await fsp.unlink(part).catch(() => {});
  } // server ignored Range
  else if (res.statusCode !== 200 && res.statusCode !== 206) {
    res.resume();
    throw new Error(`HTTP ${res.statusCode}`);
  }
  const out = fs.createWriteStream(part, { flags: have ? 'a' : 'w' });
  await new Promise((resolve, reject) => {
    const abort = () => {
      res.destroy(new Error('cancelled'));
    };
    if (signal) signal.addEventListener('abort', abort, { once: true });
    let failed = false;
    const fail = (e) => {
      if (failed) return;
      failed = true;
      res.destroy();
      out.end(() => reject(e));
    }; // flush what arrived: it is resumed, not thrown away
    res.on('data', (c) => {
      if (onBytes) onBytes(c.length);
    });
    res.on('error', fail);
    res.on('aborted', () => fail(new Error('connection lost')));
    res.on('close', () => {
      if (!res.complete) fail(new Error('connection lost'));
    });
    out.on('error', (e) => {
      if (!failed) {
        failed = true;
        res.destroy();
        reject(e);
      }
    });
    out.on('finish', () => {
      if (!failed) resolve();
    });
    res.pipe(out);
  });
}

// Resumable ranged GET of `url` into `part` until it is `size` bytes (network retries inside; throws 'cancelled' on abort). Survives a server
// restart / dropped tunnel: every retry continues from the bytes on disk; only maxStall tries in a row WITHOUT a new byte end it.
/**
 * Download a URL into a part file with ranged resume and stall detection.
 * @param {string} url
 * @param {string} part
 * @param {number} size
 * @param {{onBytes?: Function, signal?: AbortSignal, headers?: object}} [options]
 * @returns {Promise<void>}
 */
async function fetchResumable(url, part, size, { onBytes, signal, headers } = {}) {
  let stall = 0,
    lastHave = -1,
    lastErr = null;
  for (let iter = 0; ; iter++) {
    if (signal && signal.aborted) throw new Error('cancelled');
    let have = await partSize(part);
    if (have > size) {
      await fsp.unlink(part).catch(() => {});
      if (onBytes) onBytes(-have);
      have = 0;
    }
    if (have >= size) return;
    if (iter > 0) {
      if (have > lastHave) stall = 0;
      else stall++;
      if (stall >= tunables.maxStall)
        throw lastErr || new Error('download stalled (no data from the server)');
      if (stall > 0) await sleep(Math.min(tunables.netBackoffMs * stall, 8000));
    }
    lastHave = have;
    try {
      await transferRange(url, part, have, { onBytes, signal, headers });
      lastErr = null;
    } catch (e) {
      if (String(e.message) === 'cancelled') throw e;
      if (SPACE_CODES.has(e.code) || LOCK_CODES.has(e.code) || e.code === 'EROFS')
        throw explainError(e, part); // local problems: retrying the network does not help
      lastErr = e;
    }
  }
}

// rename onto the final name, retrying while another program holds the destination (antivirus scan of the previous version, Steam helper).
// No copy fallback: a half-copied file under its final name is exactly what the verified-rename flow exists to avoid.
/**
 * Move a completed part file into its final destination.
 * @param {string} part
 * @param {string} dest
 * @returns {Promise<void>}
 */
async function moveInto(part, dest) {
  let last = null;
  for (let i = 0; i < tunables.lockBackoff.length; i++) {
    if (tunables.lockBackoff[i]) await sleep(tunables.lockBackoff[i]);
    try {
      await fsp.rename(part, dest);
      return;
    } catch (e) {
      last = e;
      if (!LOCK_CODES.has(e.code)) break;
    }
  }
  throw explainError(last, dest);
}

// Compressed path: <dest>.z.part (Range on the compressed bytes) -> stream-decode into <dest>.part while hashing -> verify raw sha -> rename.
/**
 * Download and inflate a compressed manifest entry.
 * @param {object} f
 * @param {string} dest
 * @param {object} [options]
 * @returns {Promise<void>}
 */
async function downloadCompressed(f, dest, { onBytes, signal, headers } = {}) {
  const zpart = dest + '.z.part',
    part = dest + '.part';
  let lastErr = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    await fetchResumable(f.zurl, zpart, f.zsize, { onBytes, signal, headers });
    if ((await fsp.stat(zpart)).size !== f.zsize) {
      await fsp.unlink(zpart).catch(() => {});
      lastErr = new Error('compressed size mismatch');
      continue;
    }
    try {
      const h = crypto.createHash('sha256');
      const hasher = async function* (src) {
        for await (const c of src) {
          h.update(c);
          yield c;
        }
      };
      await pipeline(
        fs.createReadStream(zpart, { highWaterMark: 1 << 20 }),
        DECODERS[f.enc](),
        hasher,
        fs.createWriteStream(part),
      );
      if (h.digest('hex') !== f.sha256) throw new Error('checksum mismatch after decompression');
    } catch (e) {
      lastErr = e;
      await fsp.unlink(zpart).catch(() => {});
      await fsp.unlink(part).catch(() => {});
      continue;
    }
    await moveInto(part, dest);
    await fsp.unlink(zpart).catch(() => {});
    return;
  }
  throw lastErr || new Error('compressed download failed');
}

// Download one file resumably into <dest>.part, verify, move into place. With f.zurl the compressed twin is tried first and the raw url is
// the fallback. onTotal(delta) is told when the byte budget changes (compressed -> raw fallback).
/**
 * Download one manifest file to a destination.
 * @param {object} f
 * @param {string} dest
 * @param {object} [opts]
 * @returns {Promise<void>}
 */
function downloadFile(f, dest, opts = {}) {
  const { onBytes, onTotal, signal, headers } = opts;
  return (async () => {
    await fsp.mkdir(path.dirname(dest), { recursive: true });
    const part = dest + '.part';
    // a verified file from an interrupted earlier run (staged '.new', or the file itself): not downloaded again
    if (opts.reuse) {
      try {
        if ((await fsp.stat(dest)).size === f.size && (await sha256File(dest)) === f.sha256) {
          if (onBytes) onBytes(f.zurl ? f.zsize : f.size);
          return;
        }
      } catch {}
    }
    if (f.zurl) {
      let counted = 0;
      try {
        await downloadCompressed(f, dest, {
          signal,
          headers,
          onBytes: (n) => {
            counted += n;
            if (onBytes) onBytes(n);
          },
        });
        return;
      } catch (e) {
        if (String(e.message) === 'cancelled') throw e;
        await fsp.unlink(dest + '.z.part').catch(() => {});
        await fsp.unlink(part).catch(() => {});
        if (onBytes) onBytes(-counted);
        if (onTotal) onTotal(f.size - f.zsize);
      }
    }
    for (let attempt = 0; attempt < 4; attempt++) {
      await fetchResumable(f.url, part, f.size, { onBytes, signal, headers });
      const h = await sha256File(part);
      if (h === f.sha256) {
        await moveInto(part, dest);
        return;
      }
      await fsp.unlink(part).catch(() => {});
      if (attempt === 3) throw new Error(`Checksum mismatch for ${f.path}`);
    }
  })();
}

/**
 * Reserve enough free disk space for a download list and its largest twin.
 * @param {object[]} list
 * @param {string} dir
 * @param {string} sfx
 * @returns {Promise<void>}
 */
async function ensureDownloadSpace(list, dir, sfx) {
  // the disk must take the new files (plus the largest compressed twin in flight) before the first byte is fetched
  let need =
    list.reduce((a, f) => a + f.size, 0) +
    list.reduce((a, f) => Math.max(a, f.zurl ? f.zsize : 0), 0);
  for (const f of list)
    for (const x of ['', '.part', '.z.part']) {
      try {
        need -= (await fsp.stat(path.join(dir, f.path) + sfx + x)).size;
      } catch {}
    }
  ensureSpace(dir, need, 'the update');
}

/**
 * Count partial bytes already on disk for a download list.
 * @param {object[]} list
 * @param {string} dir
 * @param {string} sfx
 * @returns {Promise<number>}
 */
async function resumedBytes(list, dir, sfx) {
  let done = 0;
  for (const f of list) {
    try {
      done += f.zurl
        ? Math.min(f.zsize, (await fsp.stat(path.join(dir, f.path) + sfx + '.z.part')).size)
        : Math.min(f.size, (await fsp.stat(path.join(dir, f.path) + sfx + '.part')).size);
    } catch {}
  }
  return done;
}

/**
 * Create the throttled progress reporter for a download list.
 * @param {object[]} list
 * @param {number} total
 * @param {Function} [onProgress]
 * @returns {object}
 */
function createDownloadProgress(list, total, onProgress) {
  let done = 0,
    filesDone = 0,
    last = Date.now(),
    lastBytes = 0,
    speed = 0;
  return {
    addTotal: (d) => {
      total += d;
    },
    addDone: (n) => {
      done += n;
    },
    fileDone: () => {
      filesDone++;
    },
    tick: (file, force) => {
      const now = Date.now();
      if (!force && now - last < 150) return;
      const dt = (now - last) / 1000;
      if (dt > 0) speed = speed * 0.7 + ((done - lastBytes) / dt) * 0.3;
      last = now;
      lastBytes = done;
      if (onProgress)
        onProgress({
          done,
          total,
          speed,
          eta: speed > 1 ? (total - done) / speed : null,
          file,
          files: list.length,
          filesDone,
        });
    },
  };
}

/**
 * Run a worker over a shared queue with bounded concurrency.
 * @param {object[]} queue
 * @param {(item: object) => Promise<void>} worker
 * @param {number} concurrency
 * @returns {Promise<void>}
 */
async function runPool(queue, worker, concurrency) {
  let firstErr = null;
  const run = async () => {
    while (queue.length && !firstErr) {
      const item = queue.shift();
      try {
        await worker(item);
      } catch (e) {
        firstErr = firstErr || e;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, run));
  if (firstErr) throw firstErr;
}

// Download all files in `list` (4 in parallel). progress({done,total,speed,eta,file,files,filesDone})
// stage: files land as <path>.new (verified, complete) and are swapped in together by applyStaged(); without it each file is renamed into place.
/**
 * Download a list of manifest files with bounded concurrency.
 * @param {object[]} list
 * @param {string} dir
 * @param {{onProgress?: Function, signal?: AbortSignal, headers?: object, concurrency?: number, stage?: boolean}} [options]
 * @returns {Promise<void>}
 */
async function downloadAll(
  list,
  dir,
  { onProgress, signal, headers, concurrency = 4, stage = false } = {},
) {
  const sfx = stage ? '.new' : '';
  await ensureDownloadSpace(list, dir, sfx);
  const total = list.reduce((a, f) => a + (f.zurl ? f.zsize : f.size), 0); // compressed bytes where an entry has a compressed twin
  const progress = createDownloadProgress(list, total, onProgress);
  // resumed bytes already on disk count as done
  progress.addDone(await resumedBytes(list, dir, sfx));
  const queue = [...list].sort((a, b) => b.size - a.size);
  try {
    await runPool(
      queue,
      async (f) => {
        const dest = path.join(dir, f.path) + sfx;
        await downloadFile(f, dest, {
          signal,
          headers,
          reuse: stage,
          onTotal: progress.addTotal,
          onBytes: (n) => {
            progress.addDone(n);
            progress.tick(f.path);
          },
        });
        progress.fileDone();
        progress.tick(f.path, true);
      },
      concurrency,
    );
  } catch (e) {
    throw explainError(e, e.path || dir);
  }
}

module.exports = {
  writeFileAtomic,
  sha256File,
  diffFiles,
  fetchResumable,
  moveInto,
  downloadCompressed,
  downloadFile,
  downloadAll,
};
