'use strict';
// node test/maps-convert-test.js : lib/maps-convert.js runs the importer protocol (a fake `p1conv install`) on FAKE folders only
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const mkTmp = require('./tmp');
const maps = require('../lib/maps');
const upd = require('../lib/update');
const conv = require('../lib/maps-convert');

const tmp = mkTmp('mapsconv-');
const w = (p, d) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, d); };
const p1 = path.join(tmp, 'p1');
w(path.join(p1, 'tlou-i.exe'), 'MZ');
for (const n of ['core', 'common', 'world-hunter-city']) w(path.join(p1, 'build', 'pc', 'main', n + '.psarc'), Buffer.from('PSAR....'));
w(path.join(p1, 'build', 'pc', 'main', 'pak68.txt'), 'x');
const recipe = path.join(tmp, 'part1-recipe.json');
w(recipe, '{}');
const BID = '0d43cfbf9d073263481bbb7b12ea79e8';
const fake = path.join(__dirname, 'fake-p1conv.js');
const run = (game, mode, extra = {}) => {
  process.env.FAKE_MODE = mode;
  return conv.convertFromInstall({
    command: process.execPath, prefixArgs: [fake], part1Dir: p1, gameDir: game, recipe, buildId: BID, workDir: path.join(tmp, 'work'), ...extra,
  });
};

(async () => {
  const g = path.join(tmp, 'game');
  const prog = [];
  const logs = [];
  const r = await run(g, 'ok', { onProgress: (p) => prog.push(p), log: (m) => logs.push(m) });
  assert.strictEqual(r.files, 1);
  assert.strictEqual(r.pack, 'part1-import-' + BID.slice(0, 12));
  // stage events move the bar too (whole run = stage i of n + the share of the stage), so it never sits on "Checking for updates"
  assert.deepStrictEqual(prog.map((p) => [p.done, p.total]), [[1, 2], [2, 3], [3, 3]]);
  assert.strictEqual(prog[0].stage, 'levels');
  assert.strictEqual(prog[2].stage, 'levels');
  assert.ok(logs.some((m) => /stage p1-bookstore:levels \(2\/3\)/.test(m)), 'stages go to the launcher log');
  assert.ok(fs.existsSync(path.join(g, 't2r-maps', 'part1', 'part1.dat')));
  assert.strictEqual(maps.installedFileset(g).files.length, 1);
  assert.strictEqual(maps.mapsState({ game_dir: g }).part1[0].installed, true);

  // a stray non-JSON line is ignored
  await run(path.join(tmp, 'g-junk'), 'junk');
  // partial result: no marker, an error the player can read
  const gp = path.join(tmp, 'g-partial');
  await assert.rejects(run(gp, 'partial'), /incomplete: 1 files missing/);
  assert.strictEqual(maps.installedFileset(gp), null);
  // a run that never writes part1.dat does not count as installed
  const gn = path.join(tmp, 'g-nodat');
  await assert.rejects(run(gn, 'nodat'), /without writing part1.dat/);
  assert.strictEqual(maps.readFilesMarker(gn), null);
  // converter error event / crash: no marker; an earlier marker is gone while files change
  const ge = path.join(tmp, 'g-err');
  await assert.rejects(run(ge, 'error'), /boom in the converter/);
  assert.strictEqual(maps.readFilesMarker(ge), null); // (nothing was installed before: nothing to restore)
  await assert.rejects(run(g, 'crash'), /stopped \(code 3\)/);
  assert.ok(maps.installedFileset(g), 'a failed run leaves the intact old set installed');
  const gk = path.join(tmp, 'g-keep');
  await run(gk, 'ok');
  await assert.rejects(run(gk, 'error'), /boom/);
  assert.strictEqual(maps.installedFileset(gk).files.length, 1, 'old marker restored after a failed run');
  assert.ok(!fs.existsSync(path.join(maps.part1Dir(gk), 'files.json.pending')));
  await assert.rejects(run(path.join(tmp, 'g-evil'), 'evilpath'), /unsafe file path/);
  assert.ok(!fs.existsSync(path.join(tmp, 'evil.pak')));
  // cancel kills the process
  const ac = new AbortController();
  const t0 = Date.now();
  const slow = run(path.join(tmp, 'g-slow'), 'slow', { signal: ac.signal, onProgress: () => ac.abort() });
  await assert.rejects(slow, /cancelled/);
  assert.ok(Date.now() - t0 < 15000, 'killed, not waited for');
  // Part I uninstalled after an import: the run goes on without --part1 (p1conv rebuilds part1.dat from the earlier one)
  const gu = path.join(tmp, 'g-uninst');
  const wu = path.join(tmp, 'work-uninst');
  const argsFile = path.join(tmp, 'args.json');
  process.env.FAKE_ARGS = argsFile;
  await assert.rejects(run(gu, 'ok', { part1Dir: path.join(tmp, 'gone'), workDir: wu }), /does not exist/); // never imported: Part I needed
  await run(gu, 'ok', { workDir: wu });
  assert.ok(conv.hasEarlierImport(wu));
  assert.ok(JSON.parse(fs.readFileSync(argsFile, 'utf8')).argv.includes('--part1'));
  const ru = await run(gu, 'ok', { part1Dir: path.join(tmp, 'gone'), workDir: wu });
  assert.strictEqual(ru.files, 1);
  assert.ok(!JSON.parse(fs.readFileSync(argsFile, 'utf8')).argv.includes('--part1'), 'no --part1 for a folder that is gone');
  // the update changed Part I files: the player is told to install Part I again
  await assert.rejects(run(gu, 'needp1', { part1Dir: path.join(tmp, 'gone'), workDir: wu }), (e) => e.message === conv.PART1_NEEDED);
  assert.strictEqual(maps.installedFileset(gu).files.length, 1, 'the earlier set stays installed');
  // Linux wrapping: paths through pathArg, the given env reaches the converter
  await run(gu, 'ok', { workDir: wu, pathArg: (p) => 'Z:' + p, env: { ...process.env, FAKE_MODE: 'ok', FAKE_SEEN: 'proton-env' } });
  const seen = JSON.parse(fs.readFileSync(argsFile, 'utf8'));
  assert.strictEqual(seen.seen, 'proton-env');
  assert.ok(seen.argv[seen.argv.indexOf('--recipe') + 1].startsWith('Z:'));
  delete process.env.FAKE_ARGS;
  // not a Part I install / no converter / no recipe
  await assert.rejects(conv.convertFromInstall({ exe: 'x', recipe, part1Dir: path.join(tmp, 'nope'), gameDir: g }), /does not exist/);
  await assert.rejects(conv.convertFromInstall({ part1Dir: p1, recipe, gameDir: g }), /not installed/);
  await assert.rejects(conv.convertFromInstall({ exe: 'x', part1Dir: p1, gameDir: g }), /not available for this game version/);
  await assert.rejects(
    conv.convertFromInstall({ exe: path.join(tmp, 'missing.exe'), recipe, workDir: tmp, part1Dir: p1, gameDir: g }), /Cannot start/);
  // converterPath
  assert.strictEqual(conv.converterPath(path.join(tmp, 'ud')), '');
  w(path.join(tmp, 'ud', 'p1conv', 'p1conv.exe'), 'x'); // (the Windows converter on every platform: Linux runs it under Proton)
  assert.ok(conv.converterPath(path.join(tmp, 'ud')));

  // the importer list: validated, same-origin urls only, 404 = not available
  const H = 'https://files.example.test';
  const sha = 'a'.repeat(64);
  const plat = 'win32';
  const good = { build_id: BID, recipe: { sha256: sha, size: 10 }, converter: { [plat]: { sha256: sha, size: 20, url: '/p1conv/x' } } };
  let answer = good;
  upd.getJson = async (url) => {
    assert.ok(url.endsWith('/part1-importer.json'), url);
    if (answer === 404) throw new Error('HTTP 404');
    return answer;
  };
  const imp = await conv.fetchImporter(H);
  assert.strictEqual(imp.buildId, BID);
  assert.strictEqual(imp.recipe.path, `part1-recipe-${BID}.json`);
  assert.ok(imp.recipe.url.endsWith('/part1-files/' + sha));
  assert.ok(imp.converter.url.startsWith(new URL(upd.baseUrl(H)).origin));
  answer = 404;
  await assert.rejects(conv.fetchImporter(H), /not available for this game version/);
  answer = { ...good, converter: { [plat]: { sha256: sha, size: 20, url: 'https://elsewhere.test/p1conv.exe' } } };
  await assert.rejects(conv.fetchImporter(H), /broken Part I importer list/);
  answer = { ...good, recipe: { sha256: 'xyz', size: 10 } };
  await assert.rejects(conv.fetchImporter(H), /broken Part I importer list/);
  answer = { ...good, converter: {} };
  await assert.rejects(conv.fetchImporter(H), /not available for this game version/);
  answer = { ...good, converter: { linux: { sha256: sha, size: 20, url: '/p1conv/x' } } }; // (no native Linux converter: Part I needs Oodle)
  await assert.rejects(conv.fetchImporter(H), /not available for this game version/);
  answer = { ...good, build_id: 'nope' };
  await assert.rejects(conv.fetchImporter(H), /not available for this game version/);
  console.log('maps-convert-test ok');
})().catch((e) => { console.error(e); process.exit(1); });
