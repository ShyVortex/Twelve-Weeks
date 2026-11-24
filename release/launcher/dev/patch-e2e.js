'use strict';
// node dev/patch-e2e.js <work dir> <case>   (real-file proof, not part of npm test: needs the 2 GB pack files)
// Serves blobs over a local HTTP server with Range (like the update server), then runs lib/update/files.js downloadFile exactly as an
// update does. <work dir>/e2e/cases.json: { "<case>": { entry: <manifest entry>, dest, oldPath, blobs: { sha: file } } }
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { downloadFile } = require('../lib/update/files');

const [work, name] = process.argv.slice(2);
const c = JSON.parse(fs.readFileSync(path.join(work, 'e2e', 'cases.json'), 'utf8'))[name];
const served = { bytes: 0, requests: [] };
const srv = http.createServer((req, res) => {
  const sha = req.url.split('?')[0].split('/').pop();
  const file = c.blobs[sha];
  if (!file) {
    res.writeHead(404);
    return res.end();
  }
  const size = fs.statSync(file).size;
  let a = 0,
    b = size - 1,
    code = 200;
  const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
  if (m) {
    a = +m[1];
    b = m[2] ? +m[2] : size - 1;
    code = 206;
  }
  served.requests.push(sha.slice(0, 8));
  res.writeHead(code, {
    'Content-Length': b - a + 1,
    ...(code === 206 ? { 'Content-Range': `bytes ${a}-${b}/${size}` } : {}),
  });
  const s = fs.createReadStream(file, { start: a, end: b });
  s.on('data', (d) => (served.bytes += d.length));
  s.pipe(res);
});
srv.listen(0, '127.0.0.1', async () => {
  const f = {
    ...c.entry,
    url: `http://127.0.0.1:${srv.address().port}/files/${c.entry.sha256}?sid=1`,
  };
  const t0 = Date.now();
  const logs = [];
  try {
    await downloadFile(f, c.dest, { oldPath: c.oldPath, log: (l) => logs.push(l) });
    const h = crypto.createHash('sha256');
    await new Promise((r, j) =>
      fs
        .createReadStream(c.dest, { highWaterMark: 8 << 20 })
        .on('data', (d) => h.update(d))
        .on('end', r)
        .on('error', j),
    );
    const sha = h.digest('hex');
    console.log(
      JSON.stringify({
        case: name,
        ok: sha === c.entry.sha256,
        sha,
        served_bytes: served.bytes,
        requests: served.requests.length,
        first_requests: [...new Set(served.requests)],
        seconds: Math.round((Date.now() - t0) / 1000),
        log: logs,
      }),
    );
  } catch (e) {
    console.log(JSON.stringify({ case: name, ok: false, error: e.message, log: logs }));
  }
  srv.close();
});
