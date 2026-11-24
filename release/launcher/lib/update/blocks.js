/**
 * @file Block downloads: fetch only the blocks of a big file that are not already on disk, several HTTP Range requests at once.
 */
'use strict';

// A manifest entry may carry blocks = { size, sha: [first 16 bytes (hex) of the sha256 of each block] } (tools/update_server/publish.py).
// Why: the 2+ GB data pack came over ONE connection (players far from the server, e.g. Brazil -> Frankfurt, got a few MB/s), and every
// update fetched the whole file again even when most of it was unchanged. Here:
//   1. <dest>.part is kept at the full size; blocks in it that already match (an interrupted earlier run) are kept;
//   2. blocks the installed old copy (oldPath) already holds - at the same place or anywhere else in it - are copied from it;
//   3. the rest is fetched as Range requests of up to RANGE_MAX bytes, PARALLEL at once, each written at its offset and checked per block;
//   4. the whole file's sha256 must match the manifest before the part file is moved into place (the caller does the rename).
// Throws on failure; the caller falls back to the plain whole-file download.

const fs = require('fs');
const fsp = fs.promises;
const crypto = require('crypto');
const { request } = require('./net');
const { sleep, tunables } = require('./util');

const PARALLEL = 8;
const RANGE_MAX = 16 << 20;
const ROUNDS = 6;

const blockHash = (buf) => crypto.createHash('sha256').update(buf).digest('hex').slice(0, 32);

/**
 * Hash every whole block of a file. Missing file -> [].
 * @param {string} file
 * @param {number} bs
 * @param {AbortSignal} [signal]
 * @returns {Promise<string[]>}
 */
async function hashBlocks(file, bs, signal) {
  let fh;
  try {
    fh = await fsp.open(file, 'r');
  } catch {
    return [];
  }
  try {
    const size = (await fh.stat()).size;
    const out = [];
    const buf = Buffer.allocUnsafe(bs);
    for (let off = 0; off < size; off += bs) {
      if (signal && signal.aborted) throw new Error('cancelled');
      const n = Math.min(bs, size - off);
      const { bytesRead } = await fh.read(buf, 0, n, off);
      out.push(blockHash(buf.subarray(0, bytesRead)));
    }
    return out;
  } finally {
    await fh.close();
  }
}

/**
 * Fetch bytes [a, b) of url into fh at offset a. Resolves the number of bytes written.
 * @returns {Promise<number>}
 */
async function fetchRange(url, fh, a, b, { headers, signal, onBytes }) {
  const res = await request(url, {
    headers: { ...(headers || {}), Range: `bytes=${a}-${b - 1}` },
    timeout: 20000,
  });
  if (res.statusCode !== 206) {
    res.resume();
    throw new Error(`HTTP ${res.statusCode} for a block range`);
  }
  let pos = a;
  let chain = Promise.resolve();
  await new Promise((resolve, reject) => {
    let failed = false;
    const fail = (e) => {
      if (failed) return;
      failed = true;
      res.destroy();
      chain.then(
        () => reject(e),
        () => reject(e),
      );
    };
    const abort = () => fail(new Error('cancelled'));
    if (signal) signal.addEventListener('abort', abort, { once: true });
    res.on('data', (c) => {
      if (failed) return;
      if (pos + c.length > b) return fail(new Error('block range longer than asked'));
      const at = pos;
      pos += c.length;
      chain = chain.then(() => fh.write(c, 0, c.length, at));
      if (onBytes) onBytes(c.length);
    });
    res.on('error', fail);
    res.on('aborted', () => fail(new Error('connection lost')));
    res.on('end', () => {
      if (signal) signal.removeEventListener('abort', abort);
      chain.then(() => (failed ? null : resolve()), fail);
    });
  });
  return pos - a;
}

/**
 * Download f (manifest entry with f.blocks and f.url) into part, reusing what part and oldPath already hold.
 * @param {object} f
 * @param {string} part
 * @param {{oldPath?: string, onBytes?: Function, signal?: AbortSignal, headers?: object, log?: Function}} [opts]
 * @returns {Promise<{reused: number, copied: number, fetched: number}>}
 */
async function downloadBlocks(f, part, { oldPath, onBytes, signal, headers, log } = {}) {
  const bs = f.blocks.size,
    want = f.blocks.sha,
    n = want.length;
  if (!bs || n !== Math.ceil(f.size / bs)) throw new Error('block list does not fit the file size');
  const blen = (i) => Math.min(bs, f.size - i * bs);
  // 1. what the part file already holds
  const have = new Array(n).fill(false);
  let st = null;
  try {
    st = await fsp.stat(part);
  } catch {}
  if (st && st.size === f.size) {
    const ph = await hashBlocks(part, bs, signal);
    for (let i = 0; i < n; i++) have[i] = ph[i] === want[i];
  } else if (st && st.size < f.size) {
    // a prefix from the plain resumable download: keep its whole blocks
    const ph = await hashBlocks(part, bs, signal);
    for (let i = 0; i < n && (i + 1) * bs <= st.size; i++) have[i] = ph[i] === want[i];
  }
  const fh = await fsp.open(part, st ? 'r+' : 'w+');
  let reused = 0,
    copied = 0,
    fetched = 0;
  try {
    await fh.truncate(f.size);
    for (let i = 0; i < n; i++)
      if (have[i]) {
        reused += blen(i);
        if (onBytes) onBytes(blen(i));
      }
    // 2. blocks the installed copy already has (same place first, then anywhere)
    if (oldPath && have.includes(false)) {
      const oh = await hashBlocks(oldPath, bs, signal);
      if (oh.length) {
        const where = new Map();
        oh.forEach((h, j) => {
          if (!where.has(h)) where.set(h, j);
        });
        const src = await fsp.open(oldPath, 'r');
        try {
          const buf = Buffer.allocUnsafe(bs);
          for (let i = 0; i < n; i++) {
            if (have[i]) continue;
            if (signal && signal.aborted) throw new Error('cancelled');
            const j = oh[i] === want[i] ? i : where.get(want[i]);
            if (j === undefined) continue;
            const { bytesRead } = await src.read(buf, 0, blen(i), j * bs);
            if (bytesRead !== blen(i) || blockHash(buf.subarray(0, bytesRead)) !== want[i])
              continue;
            await fh.write(buf, 0, bytesRead, i * bs);
            have[i] = true;
            copied += bytesRead;
            if (onBytes) onBytes(bytesRead);
          }
        } finally {
          await src.close();
        }
      }
    }
    // 3. fetch the rest, PARALLEL ranges at once; check every block, repeat the bad ones
    for (let round = 0; round < ROUNDS && have.includes(false); round++) {
      if (round) await sleep(Math.min(tunables.netBackoffMs * round, 8000));
      const ranges = [];
      for (let i = 0; i < n;) {
        if (have[i]) {
          i++;
          continue;
        }
        let j = i;
        while (j < n && !have[j] && (j - i + 1) * bs <= RANGE_MAX) j++;
        ranges.push([i, j]);
        i = j;
      }
      let lastErr = null;
      const run = async () => {
        while (ranges.length) {
          if (signal && signal.aborted) throw new Error('cancelled');
          const [i, j] = ranges.shift();
          const a = i * bs,
            b = Math.min(f.size, j * bs);
          let got = 0;
          try {
            got = await fetchRange(f.url, fh, a, b, { headers, signal, onBytes });
          } catch (e) {
            if (String(e.message) === 'cancelled') throw e;
            lastErr = e;
          }
          // check what arrived; a block that does not match is fetched again next round
          const buf = Buffer.allocUnsafe(bs);
          for (let k = i; k < j; k++) {
            if (k * bs >= a + got) break;
            const { bytesRead } = await fh.read(buf, 0, blen(k), k * bs);
            if (bytesRead === blen(k) && blockHash(buf.subarray(0, bytesRead)) === want[k]) {
              have[k] = true;
              fetched += blen(k);
            } else if (onBytes) onBytes(-Math.min(blen(k), a + got - k * bs));
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(PARALLEL, ranges.length) }, run));
      if (lastErr && log)
        log(`block download: ${lastErr.message} (round ${round + 1}, retrying the missing blocks)`);
    }
    if (have.includes(false))
      throw new Error(
        `${have.filter((x) => !x).length} block(s) of ${f.path} could not be downloaded`,
      );
  } finally {
    await fh.close();
  }
  return { reused, copied, fetched };
}

module.exports = { downloadBlocks, hashBlocks, blockHash, PARALLEL, RANGE_MAX };
