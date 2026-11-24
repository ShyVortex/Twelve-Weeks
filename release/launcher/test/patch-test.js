'use strict';
// node test/patch-test.js : patch downloads (lib/update/patch.js, keystream.js, files.js downloadFile): the WASM keystream matches the
// reference, a patch rebuilds the target from an encrypted pack whose chunks moved, plain files patch too, a patch that does not fit or
// gives a wrong result falls back to the block download, malformed patch entries are dropped
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const zlib = require('zlib');
const { engine, ksByteRef } = require('../lib/update/keystream');
const { applyPatch, cleanPatches } = require('../lib/update/patch');
const { downloadFile } = require('../lib/update/files');
const { blockHash } = require('../lib/update/blocks');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 't2pt-'));
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
const rnd = (n, seed) => {
  const b = Buffer.alloc(n);
  let x = seed >>> 0 || 1;
  for (let i = 0; i < n; i++) {
    x ^= x << 13;
    x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    x >>>= 0;
    b[i] = x & 0xff;
  }
  return b;
};
// XOR b (file bytes [at, at + len)) with the keystream of view v, like the pack writer (whole qwords only)
const enc = (b, at, v) => {
  const e = engine();
  const lo = Math.max(at, v.off),
    hi = Math.min(at + b.length, v.off + Math.floor(v.len / 8) * 8);
  for (let p = lo; p < hi; ) {
    const n = Math.min(e.chunk, hi - p);
    b.copy(e.buf, 0, p - at, p - at + n);
    e.xor(n, v.pos + (p - v.off));
    e.buf.copy(b, p - at, 0, n);
    p += n;
  }
  return b;
};
function patchFile(src, dst, srcView, dstView, ops) {
  const parts = [];
  const h = Buffer.alloc(144);
  h.write('T2PT', 0, 'latin1');
  h.writeUInt32LE(1, 4);
  h.writeBigUInt64LE(BigInt(dst.length), 8);
  h.writeBigUInt64LE(BigInt(src.length), 16);
  Buffer.from(sha(src), 'hex').copy(h, 24);
  Buffer.from(sha(dst), 'hex').copy(h, 56);
  [srcView, dstView].forEach((v, i) => {
    h.writeBigUInt64LE(BigInt(v.off), 88 + i * 24);
    h.writeBigUInt64LE(BigInt(v.len), 96 + i * 24);
    h.writeBigUInt64LE(BigInt(v.pos), 104 + i * 24);
  });
  h.writeUInt32LE(ops.length, 136);
  parts.push(h);
  for (const op of ops) {
    const o = Buffer.alloc(op.kind === 0 ? 16 : 24);
    o.writeUInt32LE(op.kind, 0);
    o.writeBigUInt64LE(BigInt(op.len), 8);
    if (op.kind === 1) o.writeBigUInt64LE(BigInt(op.src), 16);
    if (op.kind === 0) parts.push(o, dst.subarray(op.at, op.at + op.len));
    if (op.kind === 1) parts.push(o);
    if (op.kind === 2) {
      const z = zlib.deflateSync(dst.subarray(op.at, op.at + op.len));
      o.writeBigUInt64LE(BigInt(z.length), 16);
      parts.push(o, z);
    }
  }
  return Buffer.concat(parts);
}

let n = 0;
const tests = [];
const ok = (name, fn) => tests.push([name, fn]);

ok('WASM keystream = reference, any start / length', () => {
  const e = engine();
  for (const [pos, len] of [[0, 64], [3, 1], [8001, 37], [5 * 2 ** 30 + 5, 19], [16, 7]]) {
    e.buf.fill(0, 0, len);
    e.xor(len, pos);
    for (let i = 0; i < len; i++) assert.strictEqual(e.buf[i], ksByteRef(pos + i), `pos ${pos + i}`);
  }
});

// a pack: 64-byte header, an encrypted view of chunks, a 16-byte trailer; the new one has the chunks moved, one changed, one new
const chunks = Array.from({ length: 12 }, (_, i) => rnd(3000 + i * 97, i + 1));
function pack(list, pos) {
  const plain = Buffer.concat(list);
  const v = { off: 64, len: plain.length, pos };
  const f = Buffer.concat([rnd(64, 99), Buffer.from(plain), rnd(16, 98)]);
  enc(f.subarray(64, 64 + plain.length), 64, v);
  const at = [];
  let o = 64;
  for (const c of list) {
    at.push(o);
    o += c.length;
  }
  return { f, v, at };
}

ok('pack patch: moved chunks are copied and re-encrypted, new bytes are RAW / RAWZ', async () => {
  const old = pack(chunks, 0);
  const nl = [rnd(500, 77), ...chunks.slice(0, 5), Buffer.alloc(4000, 7), ...chunks.slice(6)];
  const neu = pack(nl, 4096); // another stream position too (a part1.dat behind a grown data file)
  const ops = [{ kind: 0, at: 0, len: 64 + 500 }];
  for (let i = 0; i < 5; i++) ops.push({ kind: 1, src: old.at[i], len: chunks[i].length });
  ops.push({ kind: 2, at: neu.at[6], len: 4000 });
  for (let i = 6; i < 12; i++) ops.push({ kind: 1, src: old.at[i], len: chunks[i].length });
  ops.push({ kind: 0, at: neu.f.length - 16, len: 16 });
  const pf = path.join(tmp, 'p.t2pt'),
    of = path.join(tmp, 'old.bin'),
    out = path.join(tmp, 'out.bin');
  fs.writeFileSync(of, old.f);
  fs.writeFileSync(pf, patchFile(old.f, neu.f, old.v, neu.v, ops));
  await applyPatch(of, pf, out, { expectFrom: sha(old.f), expectTo: sha(neu.f) });
  assert.strictEqual(sha(fs.readFileSync(out)), sha(neu.f));
  await assert.rejects(applyPatch(of, pf, out, { expectFrom: '0'.repeat(64) }), /another source/);
});

ok('plain file patch (no keystream): copies + literals', async () => {
  const a = rnd(50000, 5);
  const b = Buffer.concat([a.subarray(10000, 30000), rnd(333, 6), a.subarray(0, 10000)]);
  const v0 = { off: 0, len: 0, pos: 0 };
  const ops = [{ kind: 1, src: 10000, len: 20000 }, { kind: 0, at: 20000, len: 333 }, { kind: 1, src: 0, len: 10000 }];
  const pf = path.join(tmp, 'f.t2pt'),
    of = path.join(tmp, 'a.bin'),
    out = path.join(tmp, 'b.bin');
  fs.writeFileSync(of, a);
  fs.writeFileSync(pf, patchFile(a, b, v0, v0, ops));
  await applyPatch(of, pf, out);
  assert.ok(fs.readFileSync(out).equals(b));
  // a truncated patch throws
  fs.writeFileSync(pf, patchFile(a, b, v0, v0, ops).subarray(0, 200));
  await assert.rejects(applyPatch(of, pf, out));
});

// downloadFile against a local server: the patch path, its fallback to the block download
function serve(blobs) {
  const hits = [];
  const srv = http.createServer((req, res) => {
    const s = req.url.split('?')[0].split('/').pop();
    hits.push(s.slice(0, 8));
    const b = blobs[s];
    if (!b) {
      res.writeHead(404);
      return res.end();
    }
    const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
    if (m) {
      const a = +m[1],
        e = m[2] ? +m[2] : b.length - 1;
      res.writeHead(206, { 'Content-Length': e - a + 1, 'Content-Range': `bytes ${a}-${e}/${b.length}` });
      return res.end(b.subarray(a, e + 1));
    }
    res.writeHead(200, { 'Content-Length': b.length });
    res.end(b);
  });
  return new Promise((r) => srv.listen(0, '127.0.0.1', () => r({ srv, hits, base: `http://127.0.0.1:${srv.address().port}` })));
}
const BS = 4096;
const entryFor = (buf, base, patches) => ({
  path: 'x.bin',
  sha256: sha(buf),
  size: buf.length,
  url: `${base}/files/${sha(buf)}?sid=1`,
  blocks: { size: BS, sha: Array.from({ length: Math.ceil(buf.length / BS) }, (_, i) => blockHash(buf.subarray(i * BS, (i + 1) * BS))) },
  patches,
});

ok('downloadFile: a fitting patch is all that is downloaded; a bad one falls back to the blocks; no fit = blocks', async () => {
  const a = rnd(60000, 11);
  const b = Buffer.concat([rnd(100, 12), a]); // everything moved by 100 bytes: no block matches
  const v0 = { off: 0, len: 0, pos: 0 };
  const good = patchFile(a, b, v0, v0, [{ kind: 0, at: 0, len: 100 }, { kind: 1, src: 0, len: 60000 }]);
  const bad = Buffer.from(good);
  bad[144 + 16 + 20] ^= 1; // inside the RAW bytes (after the header and the first op header): valid patch file, wrong result
  const s = await serve({ [sha(b)]: b, [sha(good)]: good, [sha(bad)]: bad });
  const oldPath = path.join(tmp, 'x.bin');
  try {
    for (const [name, p, wantPatchOnly] of [
      ['good', { from: sha(a), sha256: sha(good), size: good.length }, true],
      ['bad', { from: sha(a), sha256: sha(bad), size: bad.length }, false],
      ['other source', { from: 'f'.repeat(64), sha256: sha(good), size: good.length }, false],
    ]) {
      fs.writeFileSync(oldPath, a);
      s.hits.length = 0;
      const dest = oldPath + '.new';
      const logs = [];
      let counted = 0;
      await downloadFile(entryFor(b, s.base, [p]), dest, { oldPath, log: (l) => logs.push(l), onBytes: (k) => (counted += k) });
      assert.strictEqual(sha(fs.readFileSync(dest)), sha(b), name);
      assert.strictEqual(s.hits.includes(sha(b).slice(0, 8)), !wantPatchOnly, `${name}: ${s.hits}`);
      assert.strictEqual(counted, b.length, `${name}: progress ends at the file size (${counted})`);
      for (const left of ['.part', '.patch', '.patch.part']) assert.ok(!fs.existsSync(dest + left), `${name}: ${left} left behind`);
      fs.unlinkSync(dest);
    }
  } finally {
    s.srv.close();
  }
});

ok('malformed patch entries are dropped, good ones kept', () => {
  const h = 'a'.repeat(64);
  const f = { size: 1000, patches: [{ from: h, sha256: h, size: 10 }, { from: 'x', sha256: h, size: 10 }, { from: h, sha256: h, size: 5000 }, null] };
  cleanPatches(f);
  assert.deepStrictEqual(f.patches, [{ from: h, sha256: h, size: 10 }]);
  const g = { size: 1000, patches: 'nope' };
  cleanPatches(g);
  assert.ok(!('patches' in g));
});

(async () => {
  for (const [name, fn] of tests) {
    await fn();
    n++;
    console.log('  ok  ' + name);
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log('patch-test: ' + n + ' passed');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
