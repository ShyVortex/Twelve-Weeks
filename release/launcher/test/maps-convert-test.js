'use strict';
// node test/maps-convert-test.js : lib/maps-convert.js runs the converter protocol (a fake p1conv) on FAKE folders only
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const mkTmp = require('./tmp');
const maps = require('../lib/maps');
const conv = require('../lib/maps-convert');

const tmp = mkTmp('mapsconv-');
const w = (p, d) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, d); };
const p1 = path.join(tmp, 'p1');
w(path.join(p1, 'tlou-i.exe'), 'MZ');
for (const n of ['core', 'common', 'world-hunter-city']) w(path.join(p1, 'build', 'pc', 'main', n + '.psarc'), Buffer.from('PSAR....'));
w(path.join(p1, 'build', 'pc', 'main', 'pak68.txt'), 'x');
const fake = path.join(__dirname, 'fake-p1conv.js');
const run = (game, mode, extra = {}) => {
  process.env.FAKE_MODE = mode;
  return conv.convertFromInstall({ command: process.execPath, prefixArgs: [fake], part1Dir: p1, gameDir: game, ...extra });
};

(async () => {
  const g = path.join(tmp, 'game');
  const prog = [];
  const r = await run(g, 'ok', { onProgress: (p) => prog.push(p) });
  assert.strictEqual(r.files, 3);
  assert.deepStrictEqual(prog.map((p) => p.done), [1, 2, 3]);
  assert.strictEqual(prog[0].stage, 'levels');
  assert.ok(fs.existsSync(path.join(g, 't2r-maps', 'part1', 'pak68', 'a.pak')));
  assert.strictEqual(maps.installedFileset(g).files.length, 3);
  assert.strictEqual(maps.mapsState({ game_dir: g }).part1[0].installed, true);

  // a stray non-JSON line is ignored
  await run(path.join(tmp, 'g-junk'), 'junk');
  // partial result: no marker, an error the player can read
  const gp = path.join(tmp, 'g-partial');
  await assert.rejects(run(gp, 'partial'), /incomplete: 1 files missing/);
  assert.strictEqual(maps.installedFileset(gp), null);
  // converter error event / crash: no marker; an earlier marker is gone while files change
  const ge = path.join(tmp, 'g-err');
  await assert.rejects(run(ge, 'error'), /boom in the converter/);
  assert.strictEqual(maps.readFilesMarker(ge), null); // (nothing was installed before: nothing to restore)
  await assert.rejects(run(g, 'crash'), /stopped \(code 3\)/);
  assert.ok(maps.installedFileset(g), 'a failed run leaves the intact old set installed');
  // a failed run leaves an intact old set installed (marker restored), an unsafe path from the converter fails the run
  await run(path.join(tmp, 'g-keep'), 'ok');
  const gk = path.join(tmp, 'g-keep');
  assert.strictEqual(maps.installedFileset(gk).files.length, 3);
  await assert.rejects(run(gk, 'error'), /boom/);
  assert.strictEqual(maps.installedFileset(gk).files.length, 3, 'old marker restored after a failed run');
  assert.ok(!fs.existsSync(path.join(maps.part1Dir(gk), 'files.json.pending')));
  await assert.rejects(run(path.join(tmp, 'g-evil'), 'evilpath'), /unsafe file path/);
  assert.ok(!fs.existsSync(path.join(tmp, 'evil.pak')));
  // cancel kills the process
  const ac = new AbortController();
  const t0 = Date.now();
  const slow = run(path.join(tmp, 'g-slow'), 'slow', { signal: ac.signal, onProgress: () => ac.abort() });
  await assert.rejects(slow, /cancelled/);
  assert.ok(Date.now() - t0 < 15000, 'killed, not waited for');
  // not a Part I install / no converter
  await assert.rejects(conv.convertFromInstall({ exe: 'x', part1Dir: path.join(tmp, 'nope'), gameDir: g }), /does not exist/);
  await assert.rejects(conv.convertFromInstall({ part1Dir: p1, gameDir: g }), /not installed/);
  await assert.rejects(conv.convertFromInstall({ exe: path.join(tmp, 'missing.exe'), part1Dir: p1, gameDir: g }), /Cannot start/);
  // converterPath
  assert.strictEqual(conv.converterPath(path.join(tmp, 'ud')), '');
  w(path.join(tmp, 'ud', 'p1conv', process.platform === 'win32' ? 'p1conv.exe' : 'p1conv'), 'x');
  assert.ok(conv.converterPath(path.join(tmp, 'ud')));
  console.log('maps-convert-test ok');
})().catch((e) => { console.error(e); process.exit(1); });
