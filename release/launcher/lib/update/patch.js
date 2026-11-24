/**
 * @file Apply a T2PT patch (tools/update_server/make_patch.py) to the installed copy of a pack file.
 *
 * The pack files are one stream XOR'd with a position-keyed keystream, so a chunk that only moved differs in every byte. The patch says
 * which byte ranges of the new file are old bytes (COPY: read from the installed file, decrypt at the old stream position, encrypt at the
 * new one) and which are new (RAW: written as they are; RAWZ: zlib-compressed). Plain files (t2r-ext.dll ...) have empty views: COPY is
 * then a plain byte copy. Only the RAW bytes are downloaded. The caller verifies the result's sha256
 * against the manifest before it replaces anything; any problem throws and the caller falls back to the block download.
 */
'use strict';

const fsp = require('fs').promises;
const zlib = require('zlib');
const { engine } = require('./keystream');

const MAGIC = 'T2PT';
const HDR = 144;
const RAW = 0,
  COPY = 1,
  RAWZ = 2;

/**
 * @param {Buffer} b
 * @returns {object}
 */
function parseHeader(b) {
  if (b.length < HDR || b.toString('latin1', 0, 4) !== MAGIC) throw new Error('not a patch file');
  if (b.readUInt32LE(4) !== 1)
    throw new Error(`patch version ${b.readUInt32LE(4)} is not supported`);
  const u = (o) => {
    const v = b.readBigUInt64LE(o);
    if (v > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('patch header value out of range');
    return Number(v);
  };
  const view = (o) => ({ off: u(o), len: u(o + 8), pos: u(o + 16) });
  const h = {
    dstSize: u(8),
    srcSize: u(16),
    from: b.toString('hex', 24, 56),
    to: b.toString('hex', 56, 88),
    src: view(88),
    dst: view(112),
    ops: b.readUInt32LE(136),
  };
  for (const v of [h.src, h.dst]) if (v.pos % 8) throw new Error('patch view not qword aligned');
  return h;
}

// XOR buf[0, n) - file bytes [at, at + n) of a file with view v - with the keystream where those bytes are encrypted
function xorView(eng, n, at, v) {
  const lo = Math.max(at, v.off),
    hi = Math.min(at + n, v.off + Math.floor(v.len / 8) * 8);
  if (hi <= lo) return;
  // pieces are split at the view edges (applyPatch), so an encrypted part always starts at the piece's start
  if (lo !== at) throw new Error('internal: piece crosses a view edge');
  eng.xor(hi - lo, v.pos + (lo - v.off));
}

/**
 * Build `out` from the installed file `oldPath` and the patch file. Resolves the number of bytes written.
 * @param {string} oldPath
 * @param {string} patchPath
 * @param {string} out
 * @param {{signal?: AbortSignal, onBytes?: Function, expectFrom?: string, expectTo?: string}} [opts]
 * @returns {Promise<number>}
 */
async function applyPatch(oldPath, patchPath, out, { signal, onBytes, expectFrom, expectTo } = {}) {
  const eng = engine();
  const pf = await fsp.open(patchPath, 'r');
  let sf = null,
    of = null;
  try {
    const hb = Buffer.alloc(HDR);
    if ((await pf.read(hb, 0, HDR, 0)).bytesRead !== HDR) throw new Error('patch file too short');
    const h = parseHeader(hb);
    if (expectFrom && h.from !== expectFrom) throw new Error('patch is for another source file');
    if (expectTo && h.to !== expectTo) throw new Error('patch is for another target file');
    const psize = (await pf.stat()).size;
    sf = await fsp.open(oldPath, 'r');
    if ((await sf.stat()).size !== h.srcSize)
      throw new Error('installed file has another size than the patch expects');
    of = await fsp.open(out, 'w');
    let pp = HDR,
      dpos = 0;
    const ob = Buffer.alloc(24);
    // the view edges of the target / source: a COPY piece never crosses one, so a piece is either all in or all out of the
    // encrypted part on each side (xorView then always starts at the piece's own start)
    const edges = (v) => [v.off, v.off + Math.floor(v.len / 8) * 8];
    const [de0, de1] = edges(h.dst),
      [se0, se1] = edges(h.src);
    for (let i = 0; i < h.ops; i++) {
      if (signal && signal.aborted) throw new Error('cancelled');
      if ((await pf.read(ob, 0, 16, pp)).bytesRead !== 16) throw new Error('patch file truncated');
      const kind = ob.readUInt32LE(0);
      const len = Number(ob.readBigUInt64LE(8));
      pp += 16;
      if (!Number.isSafeInteger(len) || len <= 0 || dpos + len > h.dstSize)
        throw new Error('bad patch op');
      if (kind === RAW) {
        if (pp + len > psize) throw new Error('patch file truncated');
        for (let done = 0; done < len;) {
          const n = Math.min(eng.chunk, len - done);
          const { bytesRead } = await pf.read(eng.buf, 0, n, pp + done);
          if (bytesRead !== n) throw new Error('patch file truncated');
          await of.write(eng.buf, 0, n, dpos + done);
          done += n;
          if (onBytes) onBytes(n);
        }
        pp += len;
      } else if (kind === COPY) {
        if ((await pf.read(ob, 16, 8, pp)).bytesRead !== 8) throw new Error('patch file truncated');
        const src = Number(ob.readBigUInt64LE(16));
        pp += 8;
        if (!Number.isSafeInteger(src) || src + len > h.srcSize) throw new Error('bad patch op');
        for (let done = 0; done < len;) {
          const s = src + done,
            d = dpos + done;
          let n = Math.min(eng.chunk, len - done);
          for (const e of [de0, de1]) if (d < e && d + n > e) n = e - d;
          for (const e of [se0, se1]) if (s < e && s + n > e) n = e - s;
          const { bytesRead } = await sf.read(eng.buf, 0, n, s);
          if (bytesRead !== n) throw new Error('installed file shorter than expected');
          xorView(eng, n, s, h.src); // decrypt at the old position
          xorView(eng, n, d, h.dst); // encrypt at the new one
          await of.write(eng.buf, 0, n, d);
          done += n;
          if (onBytes) onBytes(n);
        }
      } else if (kind === RAWZ) {
        // a zlib-compressed literal piece (make_patch.py: at most 4 MiB, only when it saves space)
        if (len > eng.chunk || (await pf.read(ob, 16, 8, pp)).bytesRead !== 8)
          throw new Error('bad patch op');
        const zlen = Number(ob.readBigUInt64LE(16));
        pp += 8;
        if (
          !Number.isSafeInteger(zlen) ||
          zlen <= 0 ||
          zlen > len + (len >> 6) + 1024 ||
          pp + zlen > psize
        )
          throw new Error(`bad compressed piece in the patch (${zlen} bytes for ${len})`);
        const zb = Buffer.allocUnsafe(zlen);
        if ((await pf.read(zb, 0, zlen, pp)).bytesRead !== zlen)
          throw new Error('patch file truncated');
        const raw = zlib.inflateSync(zb, { maxOutputLength: len });
        if (raw.length !== len) throw new Error('bad compressed piece in the patch');
        await of.write(raw, 0, len, dpos);
        pp += zlen;
        if (onBytes) onBytes(len);
      } else throw new Error(`unknown patch op ${kind}`);
      dpos += len;
    }
    if (dpos !== h.dstSize) throw new Error('patch does not cover the whole file');
    if (pp !== psize) throw new Error('patch file has trailing bytes');
    await of.truncate(h.dstSize);
    return dpos;
  } finally {
    await pf.close();
    if (sf) await sf.close();
    if (of) await of.close();
  }
}

/**
 * Read only the header of a patch file.
 * @param {string} patchPath
 * @returns {Promise<object>}
 */
async function readPatchHeader(patchPath) {
  const pf = await fsp.open(patchPath, 'r');
  try {
    const hb = Buffer.alloc(HDR);
    await pf.read(hb, 0, HDR, 0);
    return parseHeader(hb);
  } finally {
    await pf.close();
  }
}

/**
 * Keep only well-formed patch entries (from / sha256 = 64 hex, 0 < size < file size); none left -> the field is removed.
 * @param {object} f
 * @returns {void}
 */
function cleanPatches(f) {
  const hex = (s) => typeof s === 'string' && /^[0-9a-f]{64}$/.test(s);
  const ps = Array.isArray(f.patches)
    ? f.patches.filter(
        (p) =>
          p &&
          hex(p.from) &&
          hex(p.sha256) &&
          Number.isSafeInteger(p.size) &&
          p.size > 0 &&
          p.size < f.size,
      )
    : [];
  if (ps.length) f.patches = ps.map((p) => ({ from: p.from, sha256: p.sha256, size: p.size }));
  else delete f.patches;
}

module.exports = { applyPatch, readPatchHeader, parseHeader, cleanPatches };
