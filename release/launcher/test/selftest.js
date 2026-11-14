'use strict';
// node test/selftest.js : unit checks of the ported install logic and the updater against the mock server.
const assert = require('assert');
const fs = require('fs');
const mkTmp = require('./tmp');
const os = require('os');
const path = require('path');
const game = require('../lib/game');
const upd = require('../lib/update');
const mock = require('./mock-server');
game.testHooks.steam = async () => ({ stdout: 'yes', err: null });   // hermetic: Steam is up

(async () => {
  // music sets: every track named in audio.js exists, 3 per theme
  const au = fs.readFileSync(path.join(__dirname, '..', 'src', 'audio.js'), 'utf8');
  for (const th of ['neutral', 'wlf', 'sera']) {
    const k = au.indexOf(th + ': ['); assert.ok(k >= 0, th);
    const m = [0, au.slice(k, au.indexOf(']', k))];
    const names = m[1].match(/'([^']+)'/g).map((x) => x.slice(1, -1));
    assert.strictEqual(names.length, 3, th);
    // assets/ is not in the public repository: check the files only where it is present
    const music = path.join(__dirname, '..', 'assets', 'music');
    if (fs.existsSync(music)) for (const n of names) assert.ok(fs.existsSync(path.join(music, n + '.ogg')), n);
  }
  // token format matches T2R-Play.ps1: "T2N:" + name + 0x00 + padding + 12-byte id
  const id = '0123456789abcdef01234567';
  const tok = game.nameToken('Joel', id);
  assert.strictEqual(tok.length, 64);
  assert.strictEqual(tok.slice(0, 8), '54324e3a');
  assert.strictEqual(game.tokenName(tok), 'Joel');
  assert.strictEqual(tok.slice(40), id);
  assert.strictEqual(game.cleanName('  Jöel\u00e9 Miller-Longname  '), 'Jel Miller-Long');

  // winmm patch round trip
  const dll = Buffer.alloc(0x60000);
  const XOR = 0x5A3C9E17;
  for (const o of [0x56402, 0x58725]) dll.writeUInt32LE((Buffer.from([127, 0, 0, 1]).readUInt32LE(0) ^ XOR) >>> 0, o);
  for (const o of [0x563F1, 0x58742]) dll.writeUInt16LE(7001, o);
  const tmp = mkTmp('f2t-');
  const f = path.join(tmp, 'winmm.dll'); fs.writeFileSync(f, dll);
  assert.deepStrictEqual(game.getDllTarget(dll), ['127.0.0.1', 7001]);
  assert.strictEqual(game.setDllTarget(f, '203.0.113.9', 15000), true);
  assert.deepStrictEqual(game.getDllTarget(fs.readFileSync(f)), ['203.0.113.9', 15000]);
  assert.strictEqual(game.setDllTarget(f, '203.0.113.9', 15000), false);
  const foreign = Buffer.alloc(0x60000); foreign.writeUInt16LE(5, 0x563F1);
  assert.throws(() => game.getDllTarget(foreign));
  // setDllTarget patches only the four sites in place: a foreign / short file is refused and left byte for byte as it was
  const ff = path.join(tmp, 'foreign.dll'); fs.writeFileSync(ff, foreign);
  assert.throws(() => game.setDllTarget(ff, '203.0.113.9', 15000));
  assert.ok(fs.readFileSync(ff).equals(foreign));
  const sf = path.join(tmp, 'short.dll'); fs.writeFileSync(sf, Buffer.alloc(100));
  assert.throws(() => game.setDllTarget(sf, '203.0.113.9', 15000));
  assert.strictEqual(fs.statSync(f).size, 0x60000);          // (still the same size after the in-place patch)
  // the exe build guard: fake PE headers, never the player's game
  const mkpe = (ts, size) => { const b = Buffer.alloc(4096); b.writeUInt16LE(0x5A4D, 0); b.writeUInt32LE(0x80, 0x3c); b.writeUInt32LE(0x4550, 0x80); b.writeUInt32LE(ts, 0x88); b.writeUInt32LE(size, 0x80 + 24 + 56); return b; };
  const gd = mkTmp('f2g-');
  fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), mkpe(game.EXE_TIMESTAMP, game.EXE_IMAGE_SIZE));
  assert.strictEqual(game.exeBuild(gd).known, true);
  fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), mkpe(game.EXE_TIMESTAMP + 1, game.EXE_IMAGE_SIZE));
  assert.strictEqual(game.exeBuild(gd).known, false);
  fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), 'not a PE');
  assert.strictEqual(game.exeBuild(gd).known, null);
  await assert.rejects(game.play({ clientDir: tmp, cfg: { game_dir: (fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), mkpe(1, 2)), gd), token_id: id, custom_name: '' }, server: '127.0.0.1:1', log() {} }), /not the version/);
  // antivirus guard: missing / truncated mod files are reported (and make the mod "not current", so it is installed again)
  const cd = mkTmp('f2c-'), gd2 = mkTmp('f2g2-');
  fs.writeFileSync(path.join(cd, 't2r-ext.dll'), Buffer.alloc(1000)); fs.writeFileSync(path.join(cd, 'version.txt'), 'v1\n');
  assert.deepStrictEqual(game.missingModFiles(cd, gd2), ['winmm.dll', 't2r-ext.dll']);
  fs.writeFileSync(path.join(gd2, 'winmm.dll'), Buffer.alloc(10)); fs.writeFileSync(path.join(gd2, 't2r-ext.dll'), Buffer.alloc(500)); fs.writeFileSync(path.join(gd2, 't2r-version.txt'), 'v1\n');
  assert.deepStrictEqual(game.missingModFiles(cd, gd2), ['t2r-ext.dll (damaged)']);
  assert.strictEqual(game.modCurrent(cd, { game_dir: gd2 }), false);
  fs.writeFileSync(path.join(gd2, 't2r-ext.dll'), Buffer.alloc(1000));
  assert.deepStrictEqual(game.missingModFiles(cd, gd2), []);
  assert.strictEqual(game.modCurrent(cd, { game_dir: gd2 }), true);
  for (const d of [gd, cd, gd2]) fs.rmSync(d, { recursive: true, force: true });

  assert.deepStrictEqual(game.parseServer('tcp://abc.joinmc.link:1234/'), { host: 'abc.joinmc.link', port: 1234 });
  assert.throws(() => game.parseServer('nope'));
  assert.deepStrictEqual(game.parseLibraryFolders('"path"\t\t"D:\\\\SteamLibrary"\n"path" "C:\\\\Steam"'), ['D:\\SteamLibrary', 'C:\\Steam']);

  // updater: fresh download, resume, verify/repair
  const { srv, files, port } = await mock.start(0);
  const base = `http://127.0.0.1:${port}`;
  const m = await upd.fetchManifest(base, 'stable');
  const dir = path.join(tmp, 'client'); fs.mkdirSync(dir);
  const cache = path.join(tmp, 'cache.json');
  let bad = await upd.diffFiles(m, dir, cache);
  assert.strictEqual(bad.length, files.length);
  // pre-seed a half-downloaded .part to prove Range resume
  const big = m.files.find((x) => x.path === 't2r-ext.dll');
  const bigSrc = files.find((x) => x.path === 't2r-ext.dll').buf;
  fs.mkdirSync(path.dirname(path.join(dir, big.path)), { recursive: true });
  fs.writeFileSync(path.join(dir, big.path) + '.part', bigSrc.subarray(0, 1_000_000));
  let last = null;
  await upd.downloadAll(bad, dir, { onProgress: (p) => { last = p; } });
  assert.strictEqual(last.filesDone, files.length);
  assert.ok(fs.readFileSync(path.join(dir, big.path)).equals(bigSrc));
  assert.strictEqual((await upd.diffFiles(m, dir, cache)).length, 0);
  fs.appendFileSync(path.join(dir, 'version.txt'), 'x');             // size change
  fs.writeFileSync(path.join(dir, 'server.txt'), Buffer.alloc(files.find((x) => x.path === 'server.txt').size, 65)); // same size, wrong bytes
  bad = await upd.diffFiles(m, dir, cache, { full: true });
  assert.deepStrictEqual(bad.map((x) => x.path).sort(), ['server.txt', 'version.txt']);
  await upd.downloadAll(bad, dir, {});
  assert.strictEqual((await upd.diffFiles(m, dir, cache, { full: true })).length, 0);
  assert.throws(() => upd.safeRel('../x'));
  assert.ok(upd.cmpVersion('0.1.0', '0.2.0') < 0 && upd.cmpVersion('1.0', '1.0.0') === 0);
  srv.close();

  // compressed transfer: mixed raw + gzip + brotli entries, resume on the compressed bytes, a damaged compressed blob falls back to raw
  {
    const z = await mock.start(0, null, { compress: true, corrupt: ['damaged.bin'] });
    const zb = `http://127.0.0.1:${z.port}`;
    const zm = await upd.fetchManifest(zb, 'stable');
    const ent = (p) => zm.files.find((x) => x.path === p);
    assert.strictEqual(ent('notes.txt').enc, 'br');
    assert.strictEqual(ent('pad.bin').enc, 'gzip');
    assert.ok(ent('notes.txt').zurl.endsWith('.br') && ent('pad.bin').zurl.endsWith('.gz'));
    assert.ok(ent('notes.txt').zsize < ent('notes.txt').size * 0.05);
    assert.strictEqual(ent('t2r-ext.dll').zurl, undefined);           // random bytes: raw only (mixed)
    const zdir = path.join(tmp, 'zclient'); fs.mkdirSync(zdir);
    const src = (p) => z.files.find((x) => x.path === p);
    const half = Math.floor(src('pad.bin').zsize / 2);
    fs.writeFileSync(path.join(zdir, 'pad.bin.z.part'), src('pad.bin').zbuf.subarray(0, half));   // resume mid compressed file
    const zbad = await upd.diffFiles(zm, zdir, path.join(tmp, 'zcache.json'));
    assert.strictEqual(zbad.length, zm.files.length);
    let zl = null, maxDone = 0;
    await upd.downloadAll(zbad, zdir, { onProgress: (p) => { zl = p; maxDone = Math.max(maxDone, p.done); } });
    for (const f of z.files) assert.ok(fs.readFileSync(path.join(zdir, f.path)).equals(f.buf), f.path);
    assert.strictEqual((await upd.diffFiles(zm, zdir, path.join(tmp, 'zcache.json'), { full: true })).length, 0);
    assert.strictEqual(zl.filesDone, z.files.length);
    assert.ok(zl.done === zl.total, `progress ${zl.done}/${zl.total}`);       // compressed bytes, adjusted for the raw fallback
    const expTotal = z.files.reduce((a, f) => a + (f.zsize && f.path !== 'damaged.bin' ? f.zsize : f.size), 0);   // compressed sizes, raw for mixed + fallback
    assert.strictEqual(zl.total, expTotal, 'total counts compressed bytes');
    const hits = z.reqLog.map((r) => r.url.split('/').pop());
    const pad = z.reqLog.filter((r) => r.url.endsWith(src('pad.bin').sha256 + '.gz'));
    assert.deepStrictEqual(pad.map((r) => r.range), [`bytes=${half}-`]);      // Range on the compressed file
    assert.ok(!hits.includes(src('pad.bin').sha256) && !hits.includes(src('notes.txt').sha256));   // those never touched the raw blob
    assert.ok(hits.includes(src('damaged.bin').sha256));                       // fallback to raw
    assert.ok(hits.includes(src('t2r-ext.dll').sha256));
    const left = []; (function walk(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) e.isDirectory() ? walk(path.join(d, e.name)) : /\.part$/.test(e.name) && left.push(e.name); })(zdir);
    assert.deepStrictEqual(left, []);                                           // no .part / .z.part leftovers
    z.srv.close();
  }
  // PLAY flow helpers (src/playstate.js): slim progress parsing, ETA, leftover-process rule, game-state machine
  {
    const PS = require('../src/playstate');
    assert.deepStrictEqual(PS.parseSlimLine('t2r-slim: progress 50 200'), { done: 50, total: 200 });
    assert.strictEqual(PS.parseSlimLine('t2r-slim: progress 300 200'), null);
    assert.strictEqual(PS.parseSlimLine('t2r-slim: rebuilt a/b'), null);
    assert.strictEqual(PS.eta(1, 100, 5000), null);                 // too early to say
    assert.strictEqual(PS.eta(50, 100, 30000), 30);
    assert.ok(PS.estimate(0) === 0 && PS.estimate(60000) > 0.5 && PS.estimate(1e9) <= 0.95);
    // a process this launcher started is never a leftover; a pre-existing windowless one is waited for 90 s, then asked about
    const L = (o) => PS.leftover({ graceMs: 90000, ...o });
    assert.strictEqual(L({ before: [], ours: [31644], now: [{ id: 31644, window: false }], waitedMs: 999999 }).action, 'none');
    assert.strictEqual(L({ before: [5], ours: [], now: [{ id: 5, window: false }], waitedMs: 12000 }).action, 'wait');
    assert.strictEqual(L({ before: [5], ours: [], now: [{ id: 5, window: false }], waitedMs: 95000 }).action, 'ask');
    assert.strictEqual(L({ before: [5], ours: [], now: [{ id: 5, window: true }], waitedMs: 1 }).action, 'running');
    assert.strictEqual(L({ before: [5], ours: [], now: [], waitedMs: 1 }).action, 'none');
    // state machine: polls never reset preparing; starting survives windowless polls; idle only after two empty polls
    let g = PS.gameState(null, { type: 'play-begin' });
    g = PS.gameState(g, { type: 'poll', running: false, starting: false }); assert.strictEqual(g.s, 'preparing');
    g = PS.gameState(g, { type: 'play-end', ok: true, windowUp: false }); assert.strictEqual(g.s, 'starting');
    for (let i = 0; i < 20; i++) g = PS.gameState(g, { type: 'poll', running: false, starting: true }); assert.strictEqual(g.s, 'starting');
    g = PS.gameState(g, { type: 'poll', running: true, starting: false }); assert.strictEqual(g.s, 'running');
    g = PS.gameState(g, { type: 'poll', running: false, starting: false }); assert.strictEqual(g.s, 'running');   // one empty poll: no flip
    g = PS.gameState(g, { type: 'poll', running: false, starting: true }); assert.strictEqual(g.s, 'running');
    g = PS.gameState(g, { type: 'poll', running: false, starting: false }); g = PS.gameState(g, { type: 'poll', running: false, starting: false }); assert.strictEqual(g.s, 'idle');
    assert.strictEqual(PS.gameState(PS.gameState(null, { type: 'play-begin' }), { type: 'play-end', ok: false }).s, 'idle');

    // waitForGameWindow: a cold boot with no window for 70 s is waited out, never ended
    let t = 0; const seen = [];
    const w = await game.waitForGameWindow({ procs: async () => [{ id: 9, window: t >= 70000 }], now: () => t, sleep: async (ms) => { t += ms; }, pollMs: 1500, progress: (p) => seen.push(p) });
    assert.strictEqual(w.windowUp, true); assert.ok(w.waitedMs >= 70000 && seen.length > 40 && seen[0].phase === 'play-window');
    t = 0; const wg = await game.waitForGameWindow({ procs: async () => [], now: () => t, sleep: async (ms) => { t += ms; }, pollMs: 1500 });
    assert.strictEqual(wg.exited, true);                           // no process at all for 6 polls after 10 s
    t = 0; const wt = await game.waitForGameWindow({ procs: async () => [{ id: 9, window: false }], now: () => t, sleep: async (ms) => { t += ms; }, pollMs: 1500, timeoutMs: 180000 });
    assert.deepStrictEqual([wt.windowUp, wt.exited], [false, false]);
    // Steam-restart grace (goneAfter Infinity): the game process is gone for 30 s, then Steam's restarted copy shows a window = windowUp; never 'exited'
    t = 0; const wr = await game.waitForGameWindow({ procs: async () => (t >= 30000 ? [{ id: 5, window: true }] : []), now: () => t, sleep: async (ms) => { t += ms; }, pollMs: 1500, timeoutMs: 60000, goneAfter: Infinity });
    assert.deepStrictEqual([wr.windowUp, wr.exited], [true, false]);
    t = 0; const wn = await game.waitForGameWindow({ procs: async () => [], now: () => t, sleep: async (ms) => { t += ms; }, pollMs: 1500, timeoutMs: 60000, goneAfter: Infinity });
    assert.deepStrictEqual([wn.windowUp, wn.exited], [false, false]);
    // runSlim reads "progress" lines from a child's stdout (a node script stands in for t2r-slim.exe)
    const fake = path.join(tmp, 'fakeslim.js');
    fs.writeFileSync(fake, "for (const p of [0, 10, 55, 100]) console.log('t2r-slim: progress ' + p * 10 + ' 1000'); console.log('t2r-slim: x written');");
    const got = []; const rs = await game.runSlim(process.execPath, [fake], { progress: (p) => got.push(p.done) });
    assert.strictEqual(rs.code, 0); assert.deepStrictEqual(got.filter((v, i, a) => a.indexOf(v) === i), [0, 10, 55, 100]);
  }
  console.log('selftest OK');
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
