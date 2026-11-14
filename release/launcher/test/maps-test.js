'use strict';
// node test/maps-test.js : MAPS tab logic (lib/maps.js) on FAKE folders only: Part I install validation, pack manifests, tester import, the tab state.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const mkTmp = require('./tmp');
const maps = require('../lib/maps');
const { DEFAULTSETTINGS } = require('../main/config');

const tmp = mkTmp('maps-');
const w = (p, data) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, data); };

// a fake Part I install
const p1 = path.join(tmp, 'p1');
const mkP1 = (dir) => {
  w(path.join(dir, 'tlou-i.exe'), 'MZ');
  w(path.join(dir, 'build', 'pc', 'main', 'core.psarc'), Buffer.from('PSAR....'));
  w(path.join(dir, 'build', 'pc', 'main', 'common.psarc'), Buffer.from('PSAR....'));
  w(path.join(dir, 'build', 'pc', 'main', 'world-hunter-city.psarc'), Buffer.from('PSAR....'));
  w(path.join(dir, 'build', 'pc', 'main', 'pak68.txt'), 'x');
};
mkP1(p1);
assert.deepStrictEqual(maps.validatePart1Dir(p1), { ok: true, exe: 'tlou-i.exe', version: '' });
assert.strictEqual(maps.validatePart1Dir('').ok, false, 'empty path');
assert.strictEqual(maps.validatePart1Dir(path.join(tmp, 'nope')).ok, false, 'missing folder');
assert.strictEqual(maps.validatePart1Dir(path.join(p1, 'tlou-i.exe')).ok, false, 'a file is not a folder');
// the Part II game folder is not a Part I install
const p2 = path.join(tmp, 'game');
w(path.join(p2, 'tlou-ii.exe'), 'MZ');
assert.match(maps.validatePart1Dir(p2).reason, /tlou-i\.exe/);
// exe only (lite exe name accepted), archives missing / wrong magic
const p1b = path.join(tmp, 'p1b');
w(path.join(p1b, 'tlou-i-l.exe'), 'MZ');
assert.match(maps.validatePart1Dir(p1b).reason, /incomplete/);
mkP1(p1b);
fs.unlinkSync(path.join(p1b, 'tlou-i.exe'));
assert.strictEqual(maps.validatePart1Dir(p1b).exe, 'tlou-i-l.exe');
w(path.join(p1b, 'build', 'pc', 'main', 'core.psarc'), 'DSAR....');
assert.match(maps.validatePart1Dir(p1b).reason, /not a Part I archive/);
// a local Part I install, read only (T2R_P1_GAME; skipped when unset)
const ref = process.env.T2R_P1_GAME || '';
if (fs.existsSync(ref)) {
  const rv = maps.validatePart1Dir(ref);
  assert.strictEqual(rv.ok, true, 'reference Part I install ' + (rv.reason || ''));
  assert.strictEqual(rv.version, '1.1.4.0', 'exe string-table FileVersion of the 1.1.4.0 reference');
}
// another Part I version is refused with the update hint (a copy of a Windows exe stands in: it carries version info 10.x)
const notepad = path.join(process.env.SystemRoot || 'C:\Windows', 'System32', 'notepad.exe');
if (fs.existsSync(notepad)) {
  const p1v = path.join(tmp, 'p1v');
  mkP1(p1v);
  fs.copyFileSync(notepad, path.join(p1v, 'tlou-i.exe'));
  const vr = maps.validatePart1Dir(p1v);
  assert.strictEqual(vr.reason, 'Part I version {v} found, 1.1.4.0 required.');
  assert.match(vr.vars.v, /^\d+\.\d+/);
}
assert.strictEqual(maps.validatePart1Dir(p1).version, '', 'a fake exe without version info is accepted, version unknown');
// the Bookstore source archive is required and checked
const p1c = path.join(tmp, 'p1c');
mkP1(p1c);
fs.unlinkSync(path.join(p1c, 'build', 'pc', 'main', 'world-hunter-city.psarc'));
assert.match(maps.validatePart1Dir(p1c).reason, /world-hunter-city\.psarc is missing/);

// manifests
const man = (o = {}) => `id=${o.id || 'part1-a'}\nver=1\nhash=1a2b3c4d\nfile=${o.file || 'part1-a.psarc'}\nsize=${o.size == null ? 5 : o.size}\nmap=to1-p1-bookstore|Bookstore|p1-bookstore\n`;
assert.strictEqual(maps.parseManifest(man()).maps.length, 1);
assert.strictEqual(maps.parseManifest(man({ file: '../x.psarc' })), null, 'no path separators in file=');
assert.strictEqual(maps.parseManifest('id=a\nhash=zz\nfile=a.psarc\nmap=a|b|c\n'), null, 'bad hash');
assert.strictEqual(maps.parseManifest('id=a\nhash=1a\nfile=a.psarc\n'), null, 'no maps');

// installed packs: manifest + archive with exactly the listed size
const game = path.join(tmp, 'game2');
w(path.join(game, 'tlou-ii.exe'), 'MZ');
assert.deepStrictEqual(maps.installedPacks(game), []);
w(path.join(game, 't2r-maps', 'a.txt'), man());
assert.deepStrictEqual(maps.installedPacks(game), [], 'manifest without archive');
w(path.join(game, 't2r-maps', 'part1-a.psarc'), '1234');
assert.deepStrictEqual(maps.installedPacks(game), [], 'wrong size');
w(path.join(game, 't2r-maps', 'part1-a.psarc'), '12345');
assert.strictEqual(maps.installedPacks(game).length, 1);

// tab state: the Part II list is complete and in the pool, the Part I section is data driven
const none = maps.mapsState({ game_dir: path.join(tmp, 'game3') });
assert.ok(none.part2.some((m) => m.name === 'Supermarket') && none.part2.length >= 18);
assert.ok(none.part2.every((m) => m.id && m.name && m.source));
assert.ok(maps.PART2.every((m) => !/p1-|Bookstore/.test(m.id + m.name)), 'no Part I map in the Part II list');
assert.deepStrictEqual(none.part1.map((m) => [m.id, m.installed]), [['p1-bookstore', false]]);
assert.strictEqual(none.tlou1.valid, false);
const set = maps.mapsState({ game_dir: game, tlou1_dir: p1 });
assert.strictEqual(set.tlou1.valid, true);
assert.strictEqual(set.part1[0].installed, true, 'pack part1-a installed -> Bookstore installed');
const badLoc = maps.mapsState({ game_dir: game, tlou1_dir: p2 });
assert.strictEqual(badLoc.tlou1.valid, false);
assert.ok(badLoc.tlou1.reason);

// tester import: manifest copied LAST, files land only in <game>\t2r-maps, a half copy leaves no .part
const game4 = path.join(tmp, 'game4');
const src = path.join(tmp, 'sent');
w(path.join(src, 'part1-a.txt'), man({ size: 7 }));
w(path.join(src, 'part1-a.psarc'), '1234567');
const order = [];
const realRename = fs.renameSync;
fs.renameSync = (a, b) => { order.push(path.basename(b)); return realRename(a, b); };
const r = maps.importFiles(game4, [path.join(src, 'part1-a.txt'), path.join(src, 'part1-a.psarc')]);
fs.renameSync = realRename;
assert.deepStrictEqual(order, ['part1-a.psarc', 'part1-a.txt'], 'archive first, manifest last');
assert.strictEqual(r.packs, 1);
assert.deepStrictEqual(fs.readdirSync(path.join(game4, 't2r-maps')).sort(), ['part1-a.psarc', 'part1-a.txt']);
assert.strictEqual(maps.mapsState({ game_dir: game4 }).part1[0].installed, true);
assert.throws(() => maps.importFiles(game4, []), /No map files/);
assert.throws(() => maps.importFiles('', [path.join(src, 'part1-a.psarc')]), /Game folder not set/);
w(path.join(src, 'evil.exe'), 'MZ');
assert.throws(() => maps.importFiles(game4, [path.join(src, 'evil.exe')]), /Only map pack files/);
assert.strictEqual(fs.existsSync(path.join(game4, 't2r-maps', 'evil.exe')), false);

// settings: the Part I location is a persisted launcher setting, empty by default
assert.strictEqual(DEFAULTSETTINGS.tlou1_dir, '');

// opt-in for the server download: the setting or an empty t2r-playtest.txt in the game folder
{
  const gt = path.join(tmp, 'gtest');
  w(path.join(gt, 'tlou-ii.exe'), 'MZ');
  assert.strictEqual(maps.p1Tester({ game_dir: gt }), false);
  assert.strictEqual(maps.mapsState({ game_dir: gt }).tester, false);
  assert.strictEqual(maps.p1Tester({ game_dir: gt, p1_tester: true }), true);
  w(path.join(gt, 't2r-playtest.txt'), '');
  assert.strictEqual(maps.p1Tester({ game_dir: gt }), true);
  assert.strictEqual(maps.mapsState({ game_dir: gt }).tester, true);
  // a marker with an unsafe path is not trusted (nothing is statted / deleted through it)
  const mk = (p) => maps.writeFilesMarker(gt, { pack: 'x', files: [{ path: p, size: 1, sha256: 'a' }] });
  mk('pak68/a.pak');
  assert.ok(maps.readFilesMarker(gt));
  for (const bad of ['../x.pak', '/abs.pak', 'a//b.pak', 'files.json']) {
    mk(bad);
    assert.strictEqual(maps.readFilesMarker(gt), null, bad);
  }
}

// TEMPORARY server download (lib/maps-remote.js): the loose Part I file set into t2r-maps/part1/<in-game path>, marker last; fake game folders only
const http = require('http');
const crypto = require('crypto');
const remote = require('../lib/maps-remote');
const upd = require('../lib/update');
(async () => {
  const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
  const files = [
    { path: 'pak68/hun-checkpoint-bookstore.pak', buf: crypto.randomBytes(300000) },
    { path: 'pak68/hun-checkpoint-bookstore-phys.pak', buf: crypto.randomBytes(5000) },
    { path: 'bin/dc1/render-settings/t1x.bin', buf: crypto.randomBytes(7000) },
    { path: 'soundbank4/tarp.bnk', buf: crypto.randomBytes(9000) },
    { path: 'sfx1/x.xvag', buf: crypto.randomBytes(1) },
  ];
  const listing = () => files.map((f) => ({ path: f.path, sha256: sha(f.buf), size: f.buf.length }));
  let pack = { pack: 'part1-a', ver: 1, files: listing() };
  const hits = [];
  let dropOnce = true, absent = false, flip = false;
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname === '/part1-maps.json') {
      if (absent) { res.statusCode = 404; return res.end('{"error":"none"}'); }
      return res.end(JSON.stringify(pack));
    }
    const f = files.find((x) => u.pathname === '/part1-files/' + sha(x.buf));
    if (!f) { res.statusCode = 404; return res.end(); }
    let buf = f.buf;
    if (flip && f.path.endsWith('bookstore.pak')) { buf = Buffer.from(buf); buf[7] ^= 1; }
    const m = /bytes=(\d+)-/.exec(req.headers.range || '');
    const start = m ? +m[1] : 0;
    hits.push(f.path + '@' + start);
    res.statusCode = m ? 206 : 200;
    if (m) res.setHeader('Content-Range', `bytes ${start}-${buf.length - 1}/${buf.length}`);
    res.setHeader('Content-Length', buf.length - start);
    if (dropOnce && f.path.endsWith('bookstore.pak') && !m) { // connection dies half way: the launcher resumes with a Range request
      dropOnce = false;
      res.write(buf.subarray(0, 100000));
      return setTimeout(() => res.destroy(), 30);
    }
    res.end(buf.subarray(start));
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const host = 'http://127.0.0.1:' + srv.address().port;
  upd.tunables.netBackoffMs = 10;
  try {
    const rp = await remote.fetchRemotePack(host);
    assert.strictEqual(rp.total, files.reduce((a, f) => a + f.buf.length, 0));
    const g = path.join(tmp, 'dlgame');
    const seen = [];
    const realRename = fs.renameSync;
    const order = [];
    fs.renameSync = (a, b) => { order.push(path.basename(b)); return realRename(a, b); };
    const out = await remote.downloadRemotePack(host, g, { onProgress: (p) => seen.push(p) });
    fs.renameSync = realRename;
    assert.strictEqual(out.downloaded, files.length);
    assert.strictEqual(order[order.length - 1], 'files.json', 'marker last');
    assert.ok(hits.some((h) => /bookstore\.pak@[1-9]/.test(h)), 'the dropped connection was resumed with a Range request: ' + hits);
    assert.ok(seen.length && seen[seen.length - 1].done === rp.total && seen[seen.length - 1].total === rp.total, 'progress reaches the total');
    const root = path.join(g, 't2r-maps', 'part1');
    for (const f of files) assert.deepStrictEqual(fs.readFileSync(path.join(root, ...f.path.split('/'))), f.buf, f.path);
    assert.deepStrictEqual(fs.readdirSync(path.join(root, 'pak68')).sort(), ['hun-checkpoint-bookstore-phys.pak', 'hun-checkpoint-bookstore.pak'], 'mirrors the in-game paths, no .part left');
    assert.strictEqual(maps.mapsState({ game_dir: g }).part1[0].installed, true);
    // again: nothing to download
    const n0 = hits.length;
    assert.strictEqual((await remote.downloadRemotePack(host, g)).downloaded, 0);
    assert.strictEqual(hits.length, n0, 'complete files are not fetched again');
    // a damaged local file is replaced; the others are kept
    fs.writeFileSync(path.join(root, 'soundbank4', 'tarp.bnk'), Buffer.alloc(9000, 1));
    assert.strictEqual((await remote.downloadRemotePack(host, g)).downloaded, 1);
    assert.deepStrictEqual(fs.readFileSync(path.join(root, 'soundbank4', 'tarp.bnk')), files[3].buf);
    // a missing file makes the set "not installed" (size check) until downloaded again
    fs.rmSync(path.join(root, 'sfx1', 'x.xvag'));
    assert.strictEqual(maps.mapsState({ game_dir: g }).part1[0].installed, false);
    assert.strictEqual((await remote.downloadRemotePack(host, g)).downloaded, 1);
    assert.strictEqual(maps.mapsState({ game_dir: g }).part1[0].installed, true);
    // a newer pack drops the files the older one had and this one does not
    files.pop();
    pack = { pack: 'part1-a', ver: 2, files: listing() };
    await remote.downloadRemotePack(host, g);
    assert.strictEqual(fs.existsSync(path.join(root, 'sfx1', 'x.xvag')), false, 'file of the older pack removed');
    assert.strictEqual(maps.readFilesMarker(g).ver, 2);
    // the server sends a wrong file: sha256 fails 4 times, no marker
    const g2 = path.join(tmp, 'dlgame2');
    flip = true;
    await assert.rejects(remote.downloadRemotePack(host, g2), /Checksum mismatch/);
    assert.strictEqual(maps.mapsState({ game_dir: g2 }).part1[0].installed, false);
    assert.strictEqual(fs.existsSync(path.join(g2, 't2r-maps', 'part1', 'files.json')), false, 'no marker without a verified set');
    flip = false;
    // a failed update leaves the old, intact set installed (marker restored from files.json.pending)
    {
      const gr = path.join(tmp, 'dlgame4');
      files.push({ path: 'sfx1/y.xvag', buf: crypto.randomBytes(50) });
      pack = { pack: 'part1-a', ver: 3, files: listing() };
      await remote.downloadRemotePack(host, gr);
      assert.strictEqual(maps.mapsState({ game_dir: gr }).part1[0].installed, true);
      files[0].buf = crypto.randomBytes(400000); // new content for the big file ...
      pack = { pack: 'part1-a', ver: 4, files: listing() };
      flip = true; // ... that the server then sends damaged
      const before = fs.readFileSync(path.join(maps.part1Dir(gr), 'pak68', 'hun-checkpoint-bookstore.pak'));
      await assert.rejects(remote.downloadRemotePack(host, gr), /Checksum mismatch/);
      flip = false;
      assert.strictEqual(maps.readFilesMarker(gr).ver, 3, 'old marker restored');
      assert.ok(!fs.existsSync(path.join(maps.part1Dir(gr), 'files.json.pending')));
      assert.ok(before.length > 0);
    }
    // the files must come from the update server's own origin
    pack = { pack: 'x', files: [{ path: 'pak68/a.pak', sha256: 'a'.repeat(64), size: 1, url: 'http://evil.example/x' }] };
    await assert.rejects(remote.fetchRemotePack(host), /broken/, 'foreign origin');
    pack = { pack: 'x', files: [{ path: 'pak68/a.pak', sha256: 'a'.repeat(64), size: 1, url: host + '/part1-files/' + 'a'.repeat(64) }] };
    await remote.fetchRemotePack(host);
    // not published / broken lists (traversal, absolute, duplicates, the marker name, empty)
    absent = true;
    await assert.rejects(remote.fetchRemotePack(host), /not available yet/);
    absent = false;
    const ok = { path: 'pak68/a.pak', sha256: 'a'.repeat(64), size: 1 };
    for (const bad of ['../evil.pak', 'pak68/../../evil.pak', '/abs/x.pak', 'C:/x.pak', 'pak68' + String.fromCharCode(92) + 'x.pak', 'files.json', 'pak68//x.pak', '.hidden/x']) {
      pack = { pack: 'x', files: [ok, { ...ok, path: bad }] };
      await assert.rejects(remote.fetchRemotePack(host), /broken/, bad);
    }
    pack = { pack: 'x', files: [ok, ok] };
    await assert.rejects(remote.fetchRemotePack(host), /broken/, 'duplicate path');
    pack = { pack: 'x', files: [] };
    await assert.rejects(remote.fetchRemotePack(host), /not available yet/);
    await assert.rejects(remote.downloadRemotePack(host, ''), /Game folder not set/);
    console.log('maps-test ok');
  } finally {
    srv.close();
    srv.closeAllConnections && srv.closeAllConnections();
  }
})().catch((e) => { console.error(e); process.exit(1); });
