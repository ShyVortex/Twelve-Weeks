'use strict';
// stand-in for p1conv in tests: same JSON-lines protocol (tools/part1/p1conv.py). FAKE_MODE: ok | partial | error | crash | slow | junk
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const a = process.argv.slice(2);
const out = a[a.indexOf('--out') + 1];
if (!a.includes('--tlou2') || !a[a.indexOf('--tlou2') + 1]) { process.stdout.write(JSON.stringify({ event: 'error', message: 'no --tlou2' }) + String.fromCharCode(10)); process.exit(1); }
const mode = process.env.FAKE_MODE || 'ok';
const say = (o) => process.stdout.write(JSON.stringify(o) + '\n');
say({ event: 'hello', version: 1, map: 'p1-bookstore' });
if (mode === 'junk') process.stdout.write('this is not json\n');
say({ event: 'stage', name: 'levels', i: 1, n: 2 });
const list = mode === 'evilpath' ? ['pak68/a.pak', '../../evil.pak'] : ['pak68/a.pak', 'pak68/a-phys.pak', 'soundbank4/b.bnk'];
let n = 0;
for (const rel of list) {
  const p = path.join(out, ...rel.split('/'));
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const buf = Buffer.from('data-' + rel);
  fs.writeFileSync(p, buf);
  say({ event: 'progress', stage: 'levels', done: ++n, total: list.length, label: rel });
  say({ event: 'file', path: rel, size: buf.length, sha256: crypto.createHash('sha256').update(buf).digest('hex') });
  if (mode === 'crash' && n === 2) process.exit(3);
  if (mode === 'error' && n === 2) { say({ event: 'error', message: 'boom in the converter' }); process.exit(1); }
}
if (mode === 'slow') setTimeout(() => say({ event: 'done', files: n, bytes: 1, partial: false, missing: [] }), 20000);
else say({ event: 'done', files: n, bytes: 1, partial: mode === 'partial', missing: mode === 'partial' ? ['bin/dc1/x.bin'] : [] });
