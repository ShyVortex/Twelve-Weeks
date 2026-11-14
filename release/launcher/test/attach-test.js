'use strict';
// node test/attach-test.js : report attachments (lib/attach.js) - magic-byte checks, count / size caps, screenshots inside the zip, clip upload
// streamed to a local mock server. Scratch folder only.
const fs = require('fs'), path = require('path'), http = require('http'), assert = require('assert');
const mkTmp = require('./tmp');
const att = require('../lib/attach');
const rpt = require('../lib/report');

(async () => {
  const tmp = mkTmp('f2att-');
  const w = (n, b) => { const f = path.join(tmp, n); fs.writeFileSync(f, b); return f; };
  const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64)]);
  const JPG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(64)]);
  const MP4 = Buffer.concat([Buffer.from([0, 0, 0, 0x18]), Buffer.from('ftypisom'), Buffer.alloc(80)]);
  const WEBM = Buffer.concat([Buffer.from([0x1a, 0x45, 0xdf, 0xa3, 0x93, 0x42, 0x82, 0x84]), Buffer.from('webm'), Buffer.alloc(80)]);

  // magic bytes decide, not the name
  assert.strictEqual(att.inspect(w('a.png', PNG)).item.ext, 'png');
  assert.strictEqual(att.inspect(w('b.png', JPG)).item.ext, 'jpg');          // a jpg named .png is a jpg
  assert.strictEqual(att.inspect(w('c.mp4', MP4)).item.kind, 'video');
  assert.strictEqual(att.inspect(w('d.mkv', WEBM)).item.ext, 'webm');
  for (const [n, b] of [['e.png', Buffer.from('<svg onload=1>')], ['f.mp4', Buffer.from('not a video at all')], ['g.png', Buffer.alloc(0)], ['h.exe', PNG], ['i.svg', PNG]]) assert.strictEqual(att.inspect(w(n, b)).ok, false, n);
  assert.strictEqual(att.inspect(path.join(tmp, 'nope.png')).ok, false);
  assert.strictEqual(att.inspect(tmp).ok, false);

  // counts: 5 screenshots, 2 clips
  const list = [];
  const imgs = []; for (let i = 0; i < 7; i++) imgs.push(w(`s${i}.png`, PNG));
  const rej = att.addAll(list, imgs);
  assert.strictEqual(list.length, 5); assert.strictEqual(rej.length, 2); assert.match(rej[0].reason, /At most 5/);
  assert.strictEqual(att.addAll(list, [imgs[0]]).length, 0); assert.strictEqual(list.length, 5, 'the same file twice is one');
  const r2 = att.addAll(list, [w('v1.mp4', MP4), w('v2.webm', WEBM), w('v3.mp4', MP4)]);
  assert.strictEqual(list.filter((x) => x.kind === 'video').length, 2); assert.match(r2[0].reason, /At most 2 clips/);

  // size caps (sparse files: no real disk use)
  const big = path.join(tmp, 'big.mp4'); fs.writeFileSync(big, MP4); fs.truncateSync(big, att.CLIP_MAX_EACH + 1);
  const rb = att.addAll([], [big]); assert.match(rb[0].reason, /Clip too big - trim it to under 200 MB/);
  const bigi = path.join(tmp, 'big.png'); fs.writeFileSync(bigi, PNG); fs.truncateSync(bigi, att.IMG_MAX_EACH + 1);
  assert.match(att.addAll([], [bigi])[0].reason, /under 8 MB/);
  const c1 = path.join(tmp, 'c1.mp4'), c2 = path.join(tmp, 'c2.mp4'); for (const f of [c1, c2]) { fs.writeFileSync(f, MP4); fs.truncateSync(f, 140 * 1024 * 1024); }
  const tl = []; const rt = att.addAll(tl, [c1, c2]); assert.strictEqual(tl.length, 1); assert.match(rt[0].reason, /250 MB/);

  // screenshots go into the zip as files/screenshot-N.<ext> and are listed with their size in meta.json
  const shots = att.screenshotEntries(list);
  assert.deepStrictEqual(shots.map((s) => s.name), ['screenshot-1.png', 'screenshot-2.png', 'screenshot-3.png', 'screenshot-4.png', 'screenshot-5.png']);
  const b = rpt.build([], { text: 'x' }, 'sys', shots);
  assert.ok(b.files.some((f) => f.name === 'screenshot-3.png' && f.size === PNG.length));
  assert.ok(b.zip.includes(Buffer.from('files/screenshot-5.png')));

  // clip upload: streamed (the mock never buffers more than it is sent), right headers, progress reported
  let got = 0, hdr = null, url = '';
  const srv = http.createServer((req, res) => { hdr = req.headers; url = req.url; req.on('data', (c) => { got += c.length; }); req.on('end', () => { res.setHeader('Content-Type', 'application/json'); res.end('{"ok":true,"name":"clip-1.mp4","size":' + got + '}'); }); });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const clip = path.join(tmp, 'real.mp4'); fs.writeFileSync(clip, Buffer.concat([MP4, Buffer.alloc(3 * 1024 * 1024, 5)]));
  let last = 0; const r = await att.uploadClip(`http://127.0.0.1:${srv.address().port}`, 'R-ABCD', 'k'.repeat(32), clip, (o, t) => { last = o; assert.ok(o <= t); });
  assert.strictEqual(r.status, 200); assert.strictEqual(got, fs.statSync(clip).size); assert.strictEqual(last, got);
  assert.strictEqual(hdr['content-length'], String(got)); assert.match(url, /^\/report-clip\?code=R-ABCD&key=k+$/);
  srv.close();
  console.log('attach-test ok');
})().catch((e) => { console.error(e); process.exit(1); });
