'use strict';
// stand-in for `p1conv install` in tests: same JSON-lines protocol (tools/part1/p1conv.py). FAKE_MODE: ok | partial | error | crash | slow | junk | evilpath | nodat | needp1
// FAKE_ARGS: a file that gets {argv, seen = env FAKE_SEEN} of this run. Like p1conv: a successful run leaves <work>/part1dat-recipe.json; without --part1
// it needs that file (else PART1_NEEDED), and needp1 = an update that changed Part I files.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const unz = (x) => (typeof x === 'string' && x.startsWith('Z:') ? x.slice(2) : x); // (the tests' stand-in for Proton's winPath)
const a = process.argv.slice(2).map(unz);
const out = a[a.indexOf('--out') + 1];
if (!a.includes('--tlou2') || !a[a.indexOf('--tlou2') + 1]) { process.stdout.write(JSON.stringify({ event: 'error', message: 'no --tlou2' }) + String.fromCharCode(10)); process.exit(1); }
if (a[0] !== 'install' || !a.includes('--recipe') || !fs.existsSync(a[a.indexOf('--recipe') + 1]) || !a.includes('--work')) { process.stdout.write(JSON.stringify({ event: 'error', message: 'bad install arguments' }) + String.fromCharCode(10)); process.exit(1); }
const mode = process.env.FAKE_MODE || 'ok';
const say = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const work = a[a.indexOf('--work') + 1];
if (process.env.FAKE_ARGS) fs.writeFileSync(process.env.FAKE_ARGS, JSON.stringify({ argv: process.argv.slice(2), seen: process.env.FAKE_SEEN || '' }));
if (mode === 'needp1' || (!a.includes('--part1') && !fs.existsSync(path.join(work, 'part1dat-recipe.json')))) {
  say({ event: 'error', message: 'PART1_NEEDED: this update changes 3 Part I map files; the Part I install is needed to convert them again' });
  process.exit(1);
}
say({ event: 'hello', version: 1, map: 'p1-bookstore' });
if (mode === 'junk') process.stdout.write('this is not json\n');
say({ event: 'stage', name: 'levels', i: 1, n: 2 });
// install reports the one file it writes, part1.dat; the work files are not reported (they stay in --work)
const list = mode === 'evilpath' ? ['part1.dat', '../../evil.pak'] : mode === 'nodat' ? ['pak68/a.pak'] : ['part1.dat'];
say({ event: 'stage', name: 'p1-bookstore:levels', i: 2, n: 3 });
let n = 0;
for (const rel of list) {
  const p = path.join(out, ...rel.split('/'));
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const buf = Buffer.from('data-' + rel);
  fs.writeFileSync(p, buf);
  say({ event: 'progress', stage: 'levels', done: ++n, total: list.length, label: rel });
  say({ event: 'file', path: rel, size: buf.length, sha256: crypto.createHash('sha256').update(buf).digest('hex') });
  if (mode === 'crash') process.exit(3);
  if (mode === 'error') { say({ event: 'error', message: 'boom in the converter' }); process.exit(1); }
}
if (mode === 'ok' || mode === 'junk') { fs.mkdirSync(work, { recursive: true }); fs.writeFileSync(path.join(work, 'part1dat-recipe.json'), '{}'); }
if (mode === 'slow') setTimeout(() => say({ event: 'done', files: n, bytes: 1, partial: false, missing: [] }), 20000);
else say({ event: 'done', files: n, bytes: 1, partial: mode === 'partial', missing: mode === 'partial' ? ['bin/dc1/x.bin'] : [] });
