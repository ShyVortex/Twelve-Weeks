// Block downloads (lib/update/blocks.js through files.downloadAll): only changed blocks are fetched, in parallel ranges; the result is
// byte-identical; a broken server falls back to the whole file. Runs against a local HTTP server with Range support.
'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const files = require('../lib/update/files');
const { tunables } = require('../lib/update/util');

tunables.netBackoffMs = 5;
const BS = 1 << 20;
const hex = (b) => crypto.createHash('sha256').update(b).digest('hex');
const blocks = (buf) => {
  const sha = [];
  for (let o = 0; o < buf.length; o += BS) sha.push(hex(buf.subarray(o, o + BS)).slice(0, 32));
  return { size: BS, sha };
};

let served = 0,
  maxParallel = 0,
  open = 0,
  rangeOk = true,
  corruptOnce = -1;
let body = Buffer.alloc(0);
const srv = http.createServer((req, res) => {
  const m = /bytes=(\d+)-(\d+)?/.exec(req.headers.range || '');
  if (!m || !rangeOk) {
    served += body.length;
    res.writeHead(200, { 'Content-Length': body.length });
    return res.end(body);
  }
  const a = +m[1],
    b = m[2] ? +m[2] + 1 : body.length;
  let chunk = Buffer.from(body.subarray(a, b));
  if (corruptOnce >= a && corruptOnce < b) {
    chunk[corruptOnce - a] ^= 0xff;
    corruptOnce = -1;
  }
  open++;
  maxParallel = Math.max(maxParallel, open);
  served += chunk.length;
  res.writeHead(206, { 'Content-Length': chunk.length, 'Content-Range': `bytes ${a}-${b - 1}/${body.length}` });
  setTimeout(() => {
    open--;
    res.end(chunk);
  }, 20);
});

async function run(name, fn) {
  try {
    await fn();
    console.log('  ok  ' + name);
  } catch (e) {
    console.log('FAIL  ' + name);
    console.log(e);
    process.exitCode = 1;
  }
}

(async () => {
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${srv.address().port}/files/x`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 't2r-blocks-'));
  const rel = 't2r-maps/main/t2r-data.bin';
  const dest = path.join(dir, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const oldBuf = crypto.randomBytes(40 * BS + 12345);
  const entry = (buf) => ({ path: rel, size: buf.length, sha256: hex(buf), url, blocks: blocks(buf) });
  const logs = [];
  const log = (l) => logs.push(l);

  await run('fresh download: all blocks fetched in parallel ranges, file identical', async () => {
    body = oldBuf;
    served = maxParallel = 0;
    await files.downloadAll([entry(oldBuf)], dir, { log });
    assert.ok(fs.readFileSync(dest).equals(oldBuf));
    assert.strictEqual(served, oldBuf.length);
    assert.ok(maxParallel >= 2, 'ranges ran in parallel: ' + maxParallel);
  });

  await run('update: only the changed blocks are downloaded (staged .new), unchanged ones are copied from the installed file', async () => {
    const nb = Buffer.from(oldBuf);
    crypto.randomBytes(BS).copy(nb, 3 * BS); // one block changed
    nb[20 * BS + 5] ^= 1; // a single byte in another block
    const tail = crypto.randomBytes(2 * BS);
    const newBuf = Buffer.concat([nb, tail]); // grown at the end
    body = newBuf;
    served = 0;
    await files.downloadAll([entry(newBuf)], dir, { stage: true, log });
    assert.ok(fs.readFileSync(dest + '.new').equals(newBuf));
    assert.ok(served <= 5 * BS + 12345, 'served ' + served);
    assert.ok(logs.some((l) => /already on disk/.test(l)), logs.join('\n'));
    fs.renameSync(dest + '.new', dest);
  });

  await run('a moved block is found anywhere in the installed file', async () => {
    const cur = fs.readFileSync(dest);
    const moved = Buffer.concat([cur.subarray(5 * BS, 6 * BS), cur.subarray(0, 5 * BS), cur.subarray(6 * BS)]);
    body = moved;
    served = 0;
    await files.downloadAll([entry(moved)], dir, { stage: true, log });
    assert.ok(fs.readFileSync(dest + '.new').equals(moved));
    assert.ok(served <= 2 * BS, 'served ' + served);
    fs.renameSync(dest + '.new', dest);
  });

  await run('an interrupted part file keeps its good blocks; a corrupted range is fetched again', async () => {
    const cur = fs.readFileSync(dest);
    const nb = crypto.randomBytes(cur.length);
    body = nb;
    const part = dest + '.new.part';
    const half = Buffer.from(nb.subarray(0, 10 * BS));
    fs.writeFileSync(part, half); // the plain downloader's prefix of an earlier run
    served = 0;
    corruptOnce = 15 * BS + 7;
    await files.downloadAll([entry(nb)], dir, { stage: true, log });
    assert.ok(fs.readFileSync(dest + '.new').equals(nb));
    assert.ok(served <= nb.length - 10 * BS + 2 * BS, 'served ' + served);
    fs.renameSync(dest + '.new', dest);
  });

  await run('server without Range: falls back to the plain whole-file download', async () => {
    const nb = crypto.randomBytes(3 * BS + 9);
    body = nb;
    rangeOk = false;
    await files.downloadAll([entry(nb)], dir, { stage: true, log });
    rangeOk = true;
    assert.ok(fs.readFileSync(dest + '.new').equals(nb));
    assert.ok(logs.some((l) => /block download failed/.test(l)));
  });

  srv.close();
  fs.rmSync(dir, { recursive: true, force: true });
  if (process.exitCode) console.log('blocks-test FAILED');
  else console.log('blocks-test ok');
})();
