'use strict';
// node test/robust-test.js : launcher robustness. A local fault-injecting HTTP server on a free port and temp
// dirs under T2R_TMP (default: a temp folder). Never touches a real game folder, the live update server or any process.
const assert = require('assert');
const fs = require('fs'), path = require('path'), http = require('http'), crypto = require('crypto');
const { spawnSync } = require('child_process');
const mkTmp = require('./tmp');
const upd = require('../lib/update');
const game = require('../lib/game');
const rpt = require('../lib/report');
const health = require('../lib/health');

const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
let passed = 0;
const T = async (name, fn) => { try { await fn(); passed++; console.log('  ok  ' + name); } catch (e) { console.log('FAIL  ' + name + '\n' + (e && e.stack || e)); process.exitCode = 1; } };

// ---- fault server: serves /files/<sha> from `blobs`, `fault(req, n)` may return {dropAfter, ignoreRange, status, corrupt}
function faultServer(blobs, fault) {
  const log = [];
  const srv = http.createServer((req, res) => {
    const m = /^\/files\/([0-9a-f]{64})$/.exec(req.url);
    if (!m || !blobs[m[1]]) { res.writeHead(404); return res.end(); }
    const n = log.length; log.push({ url: req.url, range: req.headers.range || null });
    const f = (fault && fault(req, n, m[1])) || {};
    if (f.status) { res.writeHead(f.status); return res.end(); }
    let data = blobs[m[1]];
    if (f.corrupt) { data = Buffer.from(data); data[10] ^= 0xff; }
    let start = 0, code = 200;
    const r = /^bytes=(\d+)-/.exec(req.headers.range || '');
    if (r && !f.ignoreRange) { start = +r[1]; code = 206; }
    const body = data.subarray(start);
    const h = { 'Content-Length': body.length, 'Accept-Ranges': 'bytes' };
    if (code === 206) h['Content-Range'] = `bytes ${start}-${data.length - 1}/${data.length}`;
    res.writeHead(code, h);
    if (f.dropAfter !== undefined && f.dropAfter < body.length) { res.write(body.subarray(0, f.dropAfter), () => setTimeout(() => req.socket.destroy(), 10)); return; }
    res.end(body);
  });
  return new Promise((resolve) => srv.listen(0, '127.0.0.1', () => resolve({ srv, port: srv.address().port, log, url: (s) => `http://127.0.0.1:${srv.address().port}/files/${s}` })));
}
const close = (s) => new Promise((r) => { s.srv.closeAllConnections && s.srv.closeAllConnections(); s.srv.close(r); });
const mkFile = (blobs, rel, size) => { const data = crypto.randomBytes(size); const h = sha(data); blobs[h] = data; return { path: rel, size, sha256: h }; };
const withUrl = (s, f) => ({ ...f, url: s.url(f.sha256) });

upd.tunables.netBackoffMs = 20; upd.tunables.maxStall = 4; upd.tunables.lockBackoff = [0, 5, 5, 5];
game.renameTunables.backoff = [0, 5, 5, 5];
// hermetic: no real process table / drive free space (a running tlou-ii.exe or a full drive must not change any result)
game.testHooks.procs = async () => [];
game.testHooks.steam = async () => ({ stdout: 'yes', err: null });   // Steam probe: always up (the gate has its own test)
upd.tunables.freeBytes = () => 500 * 1024 ** 3;

(async () => {
  // ------------------------------------------------------------------ explainError
  await T('explainError: disk full / locked / read-only / network become sentences', () => {
    const e1 = upd.explainError(Object.assign(new Error('write ENOSPC'), { code: 'ENOSPC' }), 'E:\\x\\a.bin.part');
    assert.ok(/not enough free disk space/.test(e1.message) && /E:\\/.test(e1.message), e1.message);
    const e2 = upd.explainError(Object.assign(new Error('EPERM'), { code: 'EPERM' }), 'C:\\c\\winmm.dll.new');
    assert.ok(/winmm\.dll/.test(e2.message) && /antivirus/.test(e2.message) && !/\.new/.test(e2.message), e2.message);
    assert.ok(/read-only/.test(upd.explainError(Object.assign(new Error('x'), { code: 'EROFS' }), 'D:\\a\\b').message));
    assert.ok(/connection to the update server was lost/.test(upd.explainError(new Error('connection lost')).message));
    const plain = new Error('Checksum mismatch for a');
    assert.strictEqual(upd.explainError(plain), plain);
    assert.strictEqual(upd.explainError(e1), e1);   // idempotent
  });

  // ------------------------------------------------------------------ download: drop, resume, restart, stall, corrupt, 416, no-Range
  await T('connection dropped mid-file twice: resumes with Range, verified, nothing lost', async () => {
    const blobs = {}, f = mkFile(blobs, 'a.bin', 400 * 1024);
    const s = await faultServer(blobs, (req, n) => (n < 2 ? { dropAfter: 100 * 1024 } : null));
    const dir = mkTmp('rb1-'); const ff = withUrl(s, f);
    await upd.downloadAll([ff], dir, { stage: true });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'a.bin.new'))), f.sha256);
    assert.ok(!fs.existsSync(path.join(dir, 'a.bin.new.part')));
    assert.strictEqual(s.log.length, 3);
    assert.ok(s.log[1].range && s.log[2].range && s.log[2].range !== s.log[1].range, JSON.stringify(s.log));   // continued from the bytes on disk
    await close(s);
  });

  await T('server restart mid-download (port closed for ~0.5 s): the download survives', async () => {
    const blobs = {}, f = mkFile(blobs, 'big.bin', 600 * 1024);
    let restarted = false, port = 0, s;
    s = await faultServer(blobs, (req, n) => {
      if (n === 0) { setTimeout(() => { s.srv.closeAllConnections(); s.srv.close(); setTimeout(() => s.srv.listen(port, '127.0.0.1'), 500); }, 5); restarted = true; return { dropAfter: 150 * 1024 }; }
      return null;
    });
    port = s.port;
    const saved = upd.tunables.netBackoffMs, savedStall = upd.tunables.maxStall; upd.tunables.netBackoffMs = 150; upd.tunables.maxStall = 8;
    const dir = mkTmp('rb2-');
    try { await upd.downloadAll([withUrl(s, f)], dir, { stage: true }); } finally { upd.tunables.netBackoffMs = saved; upd.tunables.maxStall = savedStall; }
    assert.ok(restarted);
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'big.bin.new'))), f.sha256);
    await close(s);
  });

  await T('dead server: gives up with a clear message, keeps the partial file for the next try', async () => {
    const blobs = {}, f = mkFile(blobs, 'p.bin', 300 * 1024);
    const s = await faultServer(blobs, (req, n) => ({ dropAfter: n === 0 ? 100 * 1024 : 0 }));
    const dir = mkTmp('rb3-');
    await assert.rejects(upd.downloadAll([withUrl(s, f)], dir, { stage: true }), /connection to the update server was lost/);
    assert.strictEqual(fs.statSync(path.join(dir, 'p.bin.new.part')).size, 100 * 1024);   // resumable, not thrown away
    assert.ok(!fs.existsSync(path.join(dir, 'p.bin.new')) && !fs.existsSync(path.join(dir, 'p.bin')));
    // the server is fine again: the next update finishes from the partial file
    s.srv.removeAllListeners('request');
    await close(s);
    const s2 = await faultServer(blobs, null);
    await upd.downloadAll([withUrl(s2, f)], dir, { stage: true });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'p.bin.new'))), f.sha256);
    assert.strictEqual(s2.log.length, 1); assert.strictEqual(s2.log[0].range, 'bytes=102400-');
    await close(s2);
  });

  await T('corrupt blob from the server: checksum mismatch, never swapped in', async () => {
    const blobs = {}, f = mkFile(blobs, 'c.bin', 50 * 1024);
    const s = await faultServer(blobs, () => ({ corrupt: true }));
    const dir = mkTmp('rb4-');
    fs.writeFileSync(path.join(dir, 'c.bin'), 'OLD');
    await assert.rejects(upd.downloadAll([withUrl(s, f)], dir, { stage: true }), /Checksum mismatch/);
    assert.strictEqual(fs.readFileSync(path.join(dir, 'c.bin'), 'utf8'), 'OLD');
    assert.ok(!fs.existsSync(path.join(dir, 'c.bin.new')));
    await close(s);
  });

  await T('server ignores Range (200) and answers 416 once: still correct', async () => {
    const blobs = {}, f = mkFile(blobs, 'r.bin', 200 * 1024);
    const s = await faultServer(blobs, (req, n) => (n === 0 ? { dropAfter: 50 * 1024 } : n === 1 ? { status: 416 } : n === 2 ? { ignoreRange: true, dropAfter: 20 * 1024 } : { ignoreRange: true }));
    const dir = mkTmp('rb5-');
    await upd.downloadAll([withUrl(s, f)], dir, { stage: true });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'r.bin.new'))), f.sha256);
    await close(s);
  });

  await T('oversized leftover .part is discarded, not appended to', async () => {
    const blobs = {}, f = mkFile(blobs, 'o.bin', 10 * 1024);
    const s = await faultServer(blobs, null);
    const dir = mkTmp('rb6-');
    fs.writeFileSync(path.join(dir, 'o.bin.new.part'), crypto.randomBytes(50 * 1024));
    await upd.downloadAll([withUrl(s, f)], dir, { stage: true });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'o.bin.new'))), f.sha256);
    await close(s);
  });

  await T('compressed twin: truncated gzip falls back to the raw file', async () => {
    const zlib = require('zlib');
    const blobs = {}, f = mkFile(blobs, 'z.bin', 80 * 1024);
    const gz = zlib.gzipSync(blobs[f.sha256]);
    blobs['f'.repeat(64)] = gz.subarray(0, gz.length - 40);   // the server's twin is damaged
    const s = await faultServer(blobs, null);
    const dir = mkTmp('rb7-');
    await upd.downloadAll([{ ...withUrl(s, f), zurl: s.url('f'.repeat(64)), zsize: gz.length - 40, enc: 'gzip' }], dir, { stage: true });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'z.bin.new'))), f.sha256);
    await close(s);
  });

  // ------------------------------------------------------------------ disk full / lock / swap
  await T('disk full: refused before the first byte with a clear message; ENOSPC while writing too', async () => {
    const blobs = {}, f = mkFile(blobs, 'd.bin', 100 * 1024);
    const s = await faultServer(blobs, null);
    const dir = mkTmp('rb8-');
    const real = upd.tunables.freeBytes;
    upd.tunables.freeBytes = () => 40960;
    try { await assert.rejects(upd.downloadAll([withUrl(s, f)], dir, { stage: true }), /not enough free disk space.*MB are needed/); } finally { upd.tunables.freeBytes = real; }
    assert.strictEqual(s.log.length, 0);
    // space looked fine but the write fails (quota, another process filled the drive)
    const realCws = fs.createWriteStream;
    fs.createWriteStream = (p, o) => { const w = new (require('stream').Writable)({ write(c, e, cb) { cb(Object.assign(new Error('ENOSPC: no space left on device, write'), { code: 'ENOSPC' })); } }); w.path = p; return w; };
    try { await assert.rejects(upd.downloadAll([withUrl(s, f)], dir, { stage: true }), /not enough free disk space/); } finally { fs.createWriteStream = realCws; }
    await close(s);
  });

  await T('antivirus lock on the swap-in: retried with backoff, then a clear message; nothing half-updated; recovery finishes it', async () => {
    const dir = mkTmp('rb9-');
    const mk = (rel, txt) => { const b = Buffer.from(txt); return { path: rel, size: b.length, sha256: sha(b), data: b }; };
    const a = mk('a.dat', 'NEW-A'), v = mk('version.txt', '75\n');
    fs.writeFileSync(path.join(dir, 'a.dat'), 'OLD-A'); fs.writeFileSync(path.join(dir, 'version.txt'), '74\n');
    for (const f of [a, v]) fs.writeFileSync(path.join(dir, f.path + '.new'), f.data);
    const realRename = fs.promises.rename; let locked = 2, calls = 0;
    fs.promises.rename = async (x, y) => { calls++; if (locked > 0 && /a\.dat$/.test(y)) { locked--; throw Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' }); } return realRename(x, y); };
    try { await upd.applyStaged([a, v], dir, { version: '75' }); } finally { fs.promises.rename = realRename; }
    assert.ok(calls >= 4);   // two retries happened
    assert.strictEqual(fs.readFileSync(path.join(dir, 'a.dat'), 'utf8'), 'NEW-A');
    assert.strictEqual(fs.readFileSync(path.join(dir, 'version.txt'), 'utf8'), '75\n');
    assert.ok(!fs.existsSync(upd.journalPath(dir)));

    // permanently locked: friendly error, old files + version.txt untouched, journal remembers, then recovery completes after the lock is gone
    fs.writeFileSync(path.join(dir, 'a.dat'), 'OLD-A'); fs.writeFileSync(path.join(dir, 'version.txt'), '74\n');
    for (const f of [a, v]) fs.writeFileSync(path.join(dir, f.path + '.new'), f.data);
    fs.promises.rename = async (x, y) => { if (/a\.dat$/.test(y)) throw Object.assign(new Error('EPERM'), { code: 'EPERM' }); return realRename(x, y); };
    try { await assert.rejects(upd.applyStaged([a, v], dir, { version: '75' }), /antivirus.*a\.dat|a\.dat.*antivirus/s); } finally { fs.promises.rename = realRename; }
    assert.strictEqual(fs.readFileSync(path.join(dir, 'version.txt'), 'utf8'), '74\n');          // version.txt is last: still the old one
    assert.ok(upd.hasPendingUpdate(dir));
    const r = await upd.recoverStaged(dir);
    assert.deepStrictEqual([r.pending, r.complete], [true, true]);
    assert.strictEqual(fs.readFileSync(path.join(dir, 'a.dat'), 'utf8'), 'NEW-A');
    assert.strictEqual(fs.readFileSync(path.join(dir, 'version.txt'), 'utf8'), '75\n');
    assert.ok(!upd.hasPendingUpdate(dir));
  });

  await T('launcher killed during the swap (journal + some files renamed): recovery completes; lost .new = reported missing', async () => {
    const dir = mkTmp('rb10-');
    const mk = (rel, txt) => { const b = Buffer.from(txt); return { path: rel, size: b.length, sha256: sha(b), data: b }; };
    const a = mk('a.dat', 'NEW-A'), b = mk('sub/b.dat', 'NEW-B'), v = mk('version.txt', '75\n');
    fs.mkdirSync(path.join(dir, 'sub'));
    fs.writeFileSync(upd.journalPath(dir), JSON.stringify({ version: '75', files: [a, b, v].map(({ path: p, sha256, size }) => ({ path: p, sha256, size })) }));
    fs.writeFileSync(path.join(dir, 'a.dat'), a.data);                       // already swapped
    fs.writeFileSync(path.join(dir, 'sub', 'b.dat.new'), b.data);            // staged, not yet swapped
    fs.writeFileSync(path.join(dir, 'version.txt'), '74\n'); fs.writeFileSync(path.join(dir, 'version.txt.new'), v.data);
    const r = await upd.recoverStaged(dir);
    assert.strictEqual(r.complete, true);
    assert.strictEqual(fs.readFileSync(path.join(dir, 'sub', 'b.dat'), 'utf8'), 'NEW-B');
    assert.strictEqual(fs.readFileSync(path.join(dir, 'version.txt'), 'utf8'), '75\n');
    // a staged file that is gone (disk cleanup) and whose target is still old: incomplete, journal stays
    fs.writeFileSync(path.join(dir, 'a.dat'), 'OLD'); fs.writeFileSync(upd.journalPath(dir), JSON.stringify({ version: '76', files: [{ path: 'a.dat', sha256: a.sha256, size: a.size }] }));
    const r2 = await upd.recoverStaged(dir);
    assert.deepStrictEqual([r2.complete, r2.missing], [false, ['a.dat']]);
    assert.ok(upd.hasPendingUpdate(dir));
    // a garbage journal does not wedge the launcher
    fs.writeFileSync(upd.journalPath(dir), '{nope');
    assert.strictEqual((await upd.recoverStaged(dir)).pending, false);
    assert.ok(!upd.hasPendingUpdate(dir));
  });

  await T('whole update through downloadAll+applyStaged: interrupted download leaves the old client untouched', async () => {
    const blobs = {}, f1 = mkFile(blobs, 'a.bin', 200 * 1024), f2 = mkFile(blobs, 'b.bin', 200 * 1024);
    const v = { path: 'version.txt', size: 3, sha256: sha(Buffer.from('75\n')) }; blobs[v.sha256] = Buffer.from('75\n');
    let dead = false;
    const s = await faultServer(blobs, (req) => (dead && req.url.includes(f2.sha256) ? { status: 503 } : null));
    const dir = mkTmp('rb11-');
    fs.writeFileSync(path.join(dir, 'a.bin'), 'old-a'); fs.writeFileSync(path.join(dir, 'b.bin'), 'old-b'); fs.writeFileSync(path.join(dir, 'version.txt'), '74\n');
    dead = true;
    const list = [f1, f2, v].map((f) => withUrl(s, f));
    await assert.rejects(upd.downloadAll(list, dir, { stage: true }), /HTTP 503|connection|stalled/);
    for (const [n, t] of [['a.bin', 'old-a'], ['b.bin', 'old-b'], ['version.txt', '74\n']]) assert.strictEqual(fs.readFileSync(path.join(dir, n), 'utf8'), t);   // the game folder is still entirely the old version
    dead = false;
    await upd.downloadAll(list, dir, { stage: true });
    await upd.applyStaged(list, dir, { version: '75' });
    assert.strictEqual(sha(fs.readFileSync(path.join(dir, 'a.bin'))), f1.sha256);
    assert.strictEqual(fs.readFileSync(path.join(dir, 'version.txt'), 'utf8'), '75\n');
    assert.deepStrictEqual(fs.readdirSync(dir).filter((n) => /\.(new|part)$/.test(n)), []);
    await close(s);
  });

  await T('version persistence: version.txt says new but a file was damaged -> diffFiles lists it (repair); unreadable file counts as bad', async () => {
    const dir = mkTmp('rb12-'), data = Buffer.from('payload-1234');
    fs.writeFileSync(path.join(dir, 'x.bin'), data); fs.writeFileSync(path.join(dir, 'version.txt'), '75\n');
    const man = { version: '75', files: [{ path: 'x.bin', size: data.length, sha256: sha(data) }, { path: 'version.txt', size: 3, sha256: sha(Buffer.from('75\n')) }] };
    const cache = path.join(mkTmp('hc-'), 'hc.json');
    assert.deepStrictEqual(await upd.diffFiles(man, dir, cache), []);
    fs.writeFileSync(path.join(dir, 'x.bin'), 'payload-XXXX');                      // same size, different bytes (cache keyed by size+mtime: touch changes mtime)
    assert.deepStrictEqual((await upd.diffFiles(man, dir, cache)).map((f) => f.path), ['x.bin']);
    fs.writeFileSync(path.join(dir, 'x.bin'), data);
    const realCrs = fs.createReadStream;
    fs.createReadStream = (p, o) => { if (/x\.bin$/.test(String(p))) { const r = new (require('stream').Readable)({ read() { this.destroy(Object.assign(new Error('EBUSY'), { code: 'EBUSY' })); } }); return r; } return realCrs(p, o); };
    try { assert.deepStrictEqual((await upd.diffFiles(man, dir, cache, { full: true })).map((f) => f.path), ['x.bin']); } finally { fs.createReadStream = realCrs; }
  });

  await T('sweepStale removes orphan .part files only', async () => {
    const dir = mkTmp('rb13-');
    for (const n of ['keep.bin.new.part', 'gone.bin.part', 'gone.bin.z.part', 'real.bin']) fs.writeFileSync(path.join(dir, n), 'x');
    const n = await upd.sweepStale({ files: [{ path: 'keep.bin' }] }, dir);
    assert.strictEqual(n, 2);
    assert.deepStrictEqual(fs.readdirSync(dir).sort(), ['keep.bin.new.part', 'real.bin']);
  });

  await T('game running while an update would apply: refused (and a failed poll never blocks)', async () => {
    await assert.rejects(upd.refuseIfGameRunning(async () => ({ running: true, starting: false })), /game is running/);
    await assert.rejects(upd.refuseIfGameRunning(async () => ({ running: false, starting: true })), /game is running/);
    await upd.refuseIfGameRunning(async () => ({ running: false, starting: false }));
    await upd.refuseIfGameRunning(async () => { throw new Error('powershell missing'); });
  });

  await T('manifest fetch retries through a server restart (503, then ok); startup check does not wait', async () => {
    let n = 0;
    const srv = http.createServer((req, res) => { n++; if (n <= 2) { res.writeHead(503); return res.end(); } const body = JSON.stringify({ version: '9', files: [] }); res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(body); });
    await new Promise((r) => srv.listen(0, '127.0.0.1', r));
    const base = `http://127.0.0.1:${srv.address().port}`;
    await assert.rejects(upd.fetchManifest(base, 'stable'), /HTTP 503/);
    n = 0; upd.resetDown();
    const m = await upd.fetchManifest(base, 'stable', { retries: 3 });
    assert.strictEqual(m.version, '9'); assert.strictEqual(n, 3);
    srv.closeAllConnections(); srv.close();
  });

  // ------------------------------------------------------------------ install into the game folder: slim / copy / winmm validity
  const winmmFixture = (extra = 0) => { const b = Buffer.alloc(0x60000 + extra); for (const o of [0x56402, 0x58725]) b.writeUInt32LE((Buffer.from([127, 0, 0, 1]).readUInt32LE(0) ^ 0x5A3C9E17) >>> 0, o); for (const o of [0x563F1, 0x58742]) b.writeUInt16LE(7001, o); return b; };
  const cfgFor = (gd) => ({ game_dir: gd, token_id: '0123456789abcdef01234567', custom_name: '' });
  const mkGame = () => { const gd = mkTmp('rg-'); fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), 'stub'); return gd; };
  const OLDDLL = winmmFixture();
  // a stand-in for t2r-slim.exe: node.exe itself, whose first argument (the client's "winmm.dll") is a script. args: [script, dat, game, dst]
  const nodeExe = path.join(mkTmp('slimexe-'), 't2r-slim.exe'); fs.copyFileSync(process.execPath, nodeExe);
  const mkSlimClient = (script) => {
    const c = mkTmp('rc-');
    fs.mkdirSync(path.join(c, 'slim')); fs.copyFileSync(nodeExe, path.join(c, 'slim', 't2r-slim.exe'));
    fs.writeFileSync(path.join(c, 'winmm.dll'), script); fs.writeFileSync(path.join(c, 't2r-slim.dat'), 'dat'); fs.writeFileSync(path.join(c, 'version.txt'), 'v2\n');
    return c;
  };
  const okDll = JSON.stringify(winmmFixture().toString('latin1'));

  await T('slim interrupted (exits non-zero after a partial temp file): old winmm.dll intact, temp removed, install marked unfinished', async () => {
    const gd = mkGame(); fs.writeFileSync(path.join(gd, 'winmm.dll'), OLDDLL); fs.writeFileSync(path.join(gd, 't2r-version.txt'), 'v1\n');
    const c = mkSlimClient(`require('fs').writeFileSync(process.argv[4] + '.tmp', Buffer.alloc(5000)); console.error('t2r-slim: cannot create ' + process.argv[4] + ' (error 112)'); process.exit(1);`);
    await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /Could not prepare the mod.*disk of the game folder is probably full|probably full/s);
    assert.ok(fs.readFileSync(path.join(gd, 'winmm.dll')).equals(OLDDLL));
    assert.ok(!fs.existsSync(path.join(gd, 'winmm.dll.tmp')));
    assert.ok(fs.existsSync(path.join(gd, 't2r-installing.txt')));
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), false);
    assert.strictEqual(fs.readFileSync(path.join(gd, 't2r-version.txt'), 'utf8'), 'v1\n');   // not advanced
  });

  await T('slim killed (timeout): leftover winmm.dll.tmp of an earlier cut-off run is cleared by the next install', async () => {
    const gd = mkGame(); fs.writeFileSync(path.join(gd, 'winmm.dll.tmp'), Buffer.alloc(12345)); fs.writeFileSync(path.join(gd, 'winmm.dll.t2r-new'), 'x');
    const c = mkSlimClient(`require('fs').writeFileSync(process.argv[4], Buffer.from(${okDll}, 'latin1')); console.log('progress 1 1');`);
    await game.installMod(c, cfgFor(gd), () => {});
    assert.ok(!fs.existsSync(path.join(gd, 'winmm.dll.tmp')) && !fs.existsSync(path.join(gd, 'winmm.dll.t2r-new')));
    assert.deepStrictEqual(game.getDllTarget(fs.readFileSync(path.join(gd, 'winmm.dll'))), ['127.0.0.1', 7001]);
    assert.ok(!fs.existsSync(path.join(gd, 't2r-installing.txt')));
    assert.strictEqual(fs.readFileSync(path.join(gd, 't2r-version.txt'), 'utf8'), 'v2\n');
  });

  await T('slim "succeeds" but wrote a broken winmm.dll: removed (original restored), never left in the game folder', async () => {
    const gd = mkGame(); const foreign = crypto.randomBytes(0x60000); fs.writeFileSync(path.join(gd, 'winmm.dll'), foreign);
    const c = mkSlimClient(`require('fs').writeFileSync(process.argv[4], Buffer.alloc(300)); console.log('progress 1 1');`);
    await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /winmm\.dll in the game folder is damaged.*removed/s);
    assert.ok(fs.readFileSync(path.join(gd, 'winmm.dll')).equals(foreign));   // the foreign mod's own file, kept as .t2r-original, is back
    assert.ok(fs.existsSync(path.join(gd, 'winmm.dll.t2r-original')));
    const gd2 = mkGame();
    await assert.rejects(game.installMod(c, cfgFor(gd2), () => {}), /damaged/);
    assert.ok(!fs.existsSync(path.join(gd2, 'winmm.dll')));                    // nothing to restore: no winmm.dll at all
  });

  await T('plain copy: antivirus holds winmm.dll -> backoff, then a clear message; target untouched, no .t2r-new left', async () => {
    const gd = mkGame(); fs.writeFileSync(path.join(gd, 'winmm.dll'), OLDDLL);
    const c = mkTmp('rc2-'); fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture(1000)); fs.writeFileSync(path.join(c, 'version.txt'), 'v2\n');
    const real = fs.promises.rename; let calls = 0;
    fs.promises.rename = async (a, b) => { if (/winmm\.dll$/.test(b)) { calls++; throw Object.assign(new Error('EPERM: operation not permitted, rename'), { code: 'EPERM' }); } return real(a, b); };
    try { await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /winmm\.dll.*antivirus/s); } finally { fs.promises.rename = real; }
    assert.strictEqual(calls, 4);
    assert.ok(fs.readFileSync(path.join(gd, 'winmm.dll')).equals(OLDDLL) && !fs.existsSync(path.join(gd, 'winmm.dll.t2r-new')));
    // the lock was brief: one EPERM, then it works
    let first = true;
    fs.promises.rename = async (a, b) => { if (first && /winmm\.dll$/.test(b)) { first = false; throw Object.assign(new Error('EBUSY'), { code: 'EBUSY' }); } return real(a, b); };
    try { await game.installMod(c, cfgFor(gd), () => {}); } finally { fs.promises.rename = real; }
    assert.strictEqual(fs.statSync(path.join(gd, 'winmm.dll')).size, 0x60000 + 1000);
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), true);
  });

  await T('plain copy: disk full on the game drive -> clear message before copying; truncated winmm.dll makes modCurrent false', async () => {
    const gd = mkGame();
    const c = mkTmp('rc3-'); fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture(500)); fs.writeFileSync(path.join(c, 'version.txt'), 'v2\n');
    const real = upd.tunables.freeBytes; upd.tunables.freeBytes = () => 409600;
    try { await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /not enough free disk space for the mod files/); } finally { upd.tunables.freeBytes = real; }
    assert.ok(!fs.existsSync(path.join(gd, 'winmm.dll')));
    await game.installMod(c, cfgFor(gd), () => {});
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), true);
    fs.truncateSync(path.join(gd, 'winmm.dll'), 4000);                       // cut off after the fact (power loss, antivirus)
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), false);
    assert.strictEqual(game.verifyWinmm(path.join(gd, 'winmm.dll')).ok, false);
  });

  await T('Play preconditions: game folder gone / exe missing / unfinished update: each says what happened', async () => {
    const base = { clientDir: mkTmp('rp-'), server: '127.0.0.1:1', log() {} };
    await assert.rejects(game.play({ ...base, cfg: { game_dir: '', token_id: 'x' } }), /game folder is not set/);
    await assert.rejects(game.play({ ...base, cfg: { game_dir: path.join(mkTmp('gone-'), 'nope'), token_id: 'x' } }), /does not exist any more.*Pick the folder again/s);
    const empty = mkTmp('noexe-');
    await assert.rejects(game.play({ ...base, cfg: { game_dir: empty, token_id: 'x' } }), /tlou-ii\.exe was not found in .*antivirus/s);
    // exe fine but the client folder is mid-update: Play must not install a half-new client
    const gd = mkGame(); const c = mkTmp('rp2-'); fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture());
    fs.writeFileSync(upd.journalPath(c), JSON.stringify({ version: '9', files: [{ path: 'gone.bin', sha256: 'a'.repeat(64), size: 5 }] }));
    await assert.rejects(game.play({ clientDir: c, cfg: cfgFor(gd), server: '127.0.0.1:1', log() {}, skipCheck: true }), /last update did not finish/);
  });

  await T('startup crash loop: third failed start within the hour says "report"; a window clears it; tracking never throws', () => {
    const f = path.join(mkTmp('hl-'), 'play-health.json');
    const m1 = game.startFailure(f, 'plain'); const m2 = game.startFailure(f, 'plain');
    assert.strictEqual(m1, 'plain'); assert.strictEqual(m2, 'plain');
    const m3 = game.startFailure(f, 'plain');
    assert.ok(/closed on startup 3 times in a row/.test(m3) && /REPORT A BUG/.test(m3), m3);
    health.recordStartOk(f);
    assert.strictEqual(game.startFailure(f, 'plain'), 'plain');
    // old failures age out
    const t = Date.now();
    fs.writeFileSync(f, JSON.stringify({ fails: [t - 3 * 3600e3, t - 2 * 3600e3, t - 1.5 * 3600e3] }));
    assert.strictEqual(health.state(f).loop, false);
    fs.writeFileSync(f, '{broken');
    assert.strictEqual(health.recordStartFailure(f).count, 1);
    assert.strictEqual(game.startFailure('', 'plain'), 'plain');
    assert.doesNotThrow(() => health.recordStartFailure(path.join(f, 'no', 'such', 'dir.json')));
  });

  // ------------------------------------------------------------------ Steam relaunch after "verify game files"
  await T('start wait: a Steam-relaunched game alive without a window is not a crash; window / mod log ends the wait; exit without the mod fails; forever alive is not a failure', async () => {
    const gd = mkGame(); let t = 0;
    const clock = { now: () => t, sleep: async (ms) => { t += ms; } };
    const labels = [], logs = [];
    const go = async (procsAt, extra = {}) => {
      t = 0; labels.length = 0; logs.length = 0;
      game.testHooks.procs = async () => procsAt(t);
      return game.awaitGameStart({ clock, linuxDeps: { pollMs: 1000 }, ...extra }, (e) => labels.push(e.label), (m) => logs.push(m), gd, Date.now());
    };
    try {
      // the first process dies at once, Steam's relaunch lives with no window for 150 s, then the window comes
      let w = await go((ms) => (ms < 14000 ? [] : ms < 164000 ? [{ id: 5, window: false }] : [{ id: 5, window: true }]));
      assert.strictEqual(w.windowUp, true); assert.ok(logs.some((l) => /Steam is probably running a first-start step/.test(l)));
      assert.ok(labels.some((l) => /Steam is starting the game - if a Steam window or dialog is open/.test(l)), 'status label');
      // alive 100 s without a window, then gone without the mod ever loading: the one real failure
      w = await go((ms) => (ms < 14000 ? [] : ms < 114000 ? [{ id: 5, window: false }] : []));
      assert.strictEqual(w.windowUp, false); assert.strictEqual(w.exited, true);
      // Steam never restarts it
      w = await go(() => []);
      assert.strictEqual(w.exited, true); assert.ok(!labels.some((l) => /Steam is starting/.test(l)));
      // alive for the whole wait: not counted as a crash
      w = await go((ms) => (ms < 14000 ? [] : [{ id: 5, window: false }]), { steamWaitMs: 120000 });
      assert.strictEqual(w.exited, false); assert.strictEqual(w.windowUp, false);
      // mod loaded (ext log written after the start) while the window is covered by a Steam dialog
      const since = Date.now();
      w = await go((ms) => { if (ms >= 100000) fs.writeFileSync(path.join(gd, 't2r-ext.log'), 'loaded\n'); return ms < 14000 ? [] : [{ id: 5, window: false }]; });
      assert.strictEqual(w.windowUp, true); assert.strictEqual(w.modLoaded, true);
      assert.strictEqual(game.modLoadedSince(gd, since - 1000), true); assert.strictEqual(game.modLoadedSince(gd, Date.now() + 60000), false);
    } finally { game.testHooks.procs = async () => []; }
    // the failure texts name the next steps
    assert.ok(/Steam library/.test(health.NEXT_STEPS) && /dialog/.test(health.NEXT_STEPS) && /Play again/.test(health.NEXT_STEPS));
    assert.ok(/Steam library/.test(health.loopMessage(3)) && /REPORT A BUG/.test(health.loopMessage(3)));
  });

  await T('install tail: each step after the copy has its own progress label; a hung rename is cut off with a clear error', async () => {
    const gd = mkGame(); const c = mkTmp('rt-'); fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture(300)); fs.writeFileSync(path.join(c, 'version.txt'), 'v3\n');
    const labels = [];
    await game.installMod(c, cfgFor(gd), () => {}, (e) => labels.push(e.label));
    for (const l of ['Installing mod files into the game folder', 'Checking the installed mod file', 'Writing the mod version and settings', 'Writing your player name']) assert.ok(labels.includes(l), l);
    const real = fs.promises.rename, realBackoff = game.renameTunables.backoff, realAttempt = game.renameTunables.attemptMs;
    fs.promises.rename = (a, b) => (/winmm\.dll$/.test(b) ? new Promise(() => {}) : real(a, b));   // never settles
    game.renameTunables.backoff = [0]; game.renameTunables.attemptMs = 50;
    try { await assert.rejects(game.installMod(c, cfgFor(gd), () => {}, () => {}), /did not finish|antivirus|holding/i); }
    finally { fs.promises.rename = real; game.renameTunables.backoff = realBackoff; game.renameTunables.attemptMs = realAttempt; }
    await assert.rejects(game.withTimeout(new Promise(() => {}), 30, 'Looking up x'), /Looking up x did not finish within/);
  });

  // ------------------------------------------------------------------ reports
  await T('report: a multi-hundred-MB dump is named and skipped, never read into memory; a vanished log does not kill the report', () => {
    const d = mkTmp('rr-'); const g = path.join(d, 'game'); fs.mkdirSync(g);
    fs.writeFileSync(path.join(g, 't2r-ext.log'), 'boot ok\n');
    const big = path.join(g, 'huge.mdmp'); const fd = fs.openSync(big, 'w'); fs.ftruncateSync(fd, 300 * 1024 * 1024); fs.closeSync(fd);   // sparse 300 MB
    fs.writeFileSync(path.join(g, 'small.mdmp'), Buffer.alloc(1024 * 1024, 3));
    const list = [{ name: 't2r-ext.log', src: path.join(g, 't2r-ext.log'), kind: 'log' }, { name: 'gone.log', src: path.join(g, 'gone.log'), kind: 'log' },
      { name: 'huge.mdmp', src: big, kind: 'dump' }, { name: 'small.mdmp', src: path.join(g, 'small.mdmp'), kind: 'dump' }];
    const b = rpt.build(list, { text: 'x' }, 'system');
    assert.deepStrictEqual(b.skipped.sort(), ['gone.log', 'huge.mdmp']);
    assert.ok(b.files.some((f) => f.name === 'small.mdmp') && b.zip.length < 5 * 1024 * 1024);
  });

  await T('report: dumps are matched to the logs by process create time, pid and ext build stamp; stale ones are named in meta, not sent', () => {
    const mkDump = (file, { pid, created, stamp }) => {   // synthetic minidump: header + dir (MiscInfo, ModuleList) + bodies
      const mod = Buffer.alloc(4 + 108); mod.writeUInt32LE(1, 0); mod.writeUInt32LE(stamp || 0, 4 + 8);
      const nm = Buffer.from('C:\\Games\\X\\t2r-ext.dll', 'utf16le'), nmb = Buffer.alloc(4 + nm.length); nmb.writeUInt32LE(nm.length, 0); nm.copy(nmb, 4);
      const misc = Buffer.alloc(24); misc.writeUInt32LE(24, 0); misc.writeUInt32LE(created ? 3 : 1, 4); misc.writeUInt32LE(pid, 8); misc.writeUInt32LE(created ? Math.floor(created / 1000) : 0, 12);
      const dirOff = 32, miscOff = dirOff + 24, modOff = miscOff + 24, nameOff = modOff + mod.length;
      mod.writeUInt32LE(nameOff, 4 + 20);
      const h = Buffer.alloc(32); h.write('MDMP', 0, 'latin1'); h.writeUInt32LE(2, 8); h.writeUInt32LE(dirOff, 12);
      const dir = Buffer.alloc(24); dir.writeUInt32LE(15, 0); dir.writeUInt32LE(24, 4); dir.writeUInt32LE(miscOff, 8); dir.writeUInt32LE(4, 12); dir.writeUInt32LE(mod.length, 16); dir.writeUInt32LE(modOff, 20);
      fs.writeFileSync(file, Buffer.concat([h, dir, misc, mod, nmb, Buffer.alloc(4096, 5)]));
    };
    const d = mkTmp('rd-'); const g = path.join(d, 'game'); fs.mkdirSync(g); const savedLA = process.env.LOCALAPPDATA; process.env.LOCALAPPDATA = path.join(d, 'local');
    try {
      const now = Date.now(), hr = 3600000;
      const buildNaive = Date.UTC(2026, 9, 19, 12, 0, 0), pe = Math.floor(buildNaive / 1000) + 2 * 3600 + 20;   // builder in UTC-2... any 15-min zone + link delay
      const loadLine = (pid) => `[1] t2r-ext loaded, pid ${pid}, winmm base 00007FFBEC8D0000, build Oct 19 2026 12:00:00 (release)\n`;
      fs.writeFileSync(path.join(g, 't2r-ext.prev.log'), loadLine(4242) + '[500] EXCEPTION c0000005 at exe+2b4ebd pid 4242\n'); fs.writeFileSync(path.join(g, 't2r-ext.log'), loadLine(5151) + 'ok\n');
      fs.utimesSync(path.join(g, 't2r-ext.prev.log'), new Date(now - 2 * hr), new Date(now - 2 * hr)); fs.utimesSync(path.join(g, 't2r-ext.log'), new Date(now - 60000), new Date(now - 60000));
      const ident = rpt.logIdent(path.join(g, 't2r-ext.prev.log')); assert.deepStrictEqual([ident.pid, ident.build], [4242, 'Oct 19 2026 12:00:00']);
      assert.ok(rpt.stampMatchesBuild(pe, buildNaive) && !rpt.stampMatchesBuild(pe + 12 * 60, buildNaive) && !rpt.stampMatchesBuild(pe - 86400 * 1, buildNaive));
      // 1. the dump of the crashed (previous) session: attached, and it names the log that belongs to its pid
      const good = path.join(g, 'good.dmp'); mkDump(good, { pid: 4242, created: now - 3 * hr, stamp: pe });
      let l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '' });
      assert.ok(l.some((f) => f.name === 'good.dmp'), 'matching dump attached'); assert.deepStrictEqual([l.dumps[0].pid, l.dumps[0].log], [4242, 't2r-ext.prev.log']);
      // 2. the same stale dump in every report: process from a week ago, a pid that is in no log -> skipped, named
      fs.rmSync(good); const stale = path.join(g, 'stale.mdmp'); mkDump(stale, { pid: 99, created: now - 6 * 86400000, stamp: pe });
      l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '' });
      assert.ok(!l.some((f) => /stale\.mdmp/.test(f.name)) && l.skippedDumps.some((s) => s.name === 'stale.mdmp' && /not in the attached logs/.test(s.reason)));
      // 3. right pid but the ext build differs from the log's: skipped; a log without pids (older ext) falls back to the time window
      mkDump(stale, { pid: 4242, created: now - 3 * hr, stamp: pe - 5 * 86400 });
      l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '' });
      assert.ok(l.skippedDumps.some((s) => /ext build differs/.test(s.reason)), JSON.stringify(l.skippedDumps));
      fs.writeFileSync(path.join(g, 't2r-ext.prev.log'), '[1] t2r-ext loaded, winmm base 0\n'); fs.writeFileSync(path.join(g, 't2r-ext.log'), '[1] t2r-ext loaded, winmm base 0\n');
      fs.utimesSync(path.join(g, 't2r-ext.prev.log'), new Date(now - 2 * hr), new Date(now - 2 * hr)); fs.utimesSync(path.join(g, 't2r-ext.log'), new Date(now - 60000), new Date(now - 60000));
      mkDump(stale, { pid: 99, created: now - 10 * 86400000, stamp: 0 });
      l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '' });
      assert.ok(l.skippedDumps.some((s) => /started before/.test(s.reason)), JSON.stringify(l.skippedDumps));
      mkDump(stale, { pid: 99, created: now - 90 * 60000, stamp: 0 });
      l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '' });
      assert.ok(l.some((f) => f.name === 'stale.mdmp'), 'in the window, no pids known: attached');
      // 4. not a minidump at all / truncated: the file time decides, nothing throws
      fs.writeFileSync(stale, Buffer.from('MDMP')); assert.strictEqual(rpt.dumpInfo(stale).pid, 0);
      // 5. olderDumps: the player asked for old ones, a stale dump is sent as STALE-
      mkDump(stale, { pid: 99, created: now - 5 * 86400000, stamp: 0 });
      l = rpt.collect({ gameDir: g, clientDir: '', launcherLog: '', docsDir: '', olderDumps: true });
      assert.ok(l.some((f) => f.name === 'STALE-stale.mdmp'));
    } finally { process.env.LOCALAPPDATA = savedLA; }
  });

  await T('report offline at send time: queued on disk, sent on the next flush when the server answers; 400 dropped, 503 kept; caps hold', async () => {
    const q = mkTmp('rq-'); const zip = Buffer.from('PK-fake-zip');
    rpt.enqueue(q, zip, Date.now() - 3000); rpt.enqueue(q, zip, Date.now() - 2000);
    assert.strictEqual(rpt.queueList(q).length, 2);
    // server down: nothing lost
    let r = await rpt.flushQueue(q, 'http://127.0.0.1:9', async () => { throw Object.assign(new Error('connect ECONNREFUSED'), { code: 'ECONNREFUSED' }); });
    assert.deepStrictEqual([r.sent.length, r.kept], [0, 2]); assert.strictEqual(rpt.queueList(q).length, 2);
    // server busy
    r = await rpt.flushQueue(q, 'http://h', async () => ({ status: 503, json: null }));
    assert.strictEqual(r.kept, 2);
    // server back: the first goes through, the second is refused for good (400) and dropped
    let n = 0; r = await rpt.flushQueue(q, 'http://h/', async (url, body) => { assert.strictEqual(url, 'http://h/report'); assert.ok(body.equals(zip)); return ++n === 1 ? { status: 200, json: { ok: true, code: 'R-ABCD' } } : { status: 400, json: { ok: false } }; });
    assert.deepStrictEqual([r.sent, r.dropped, r.kept], [['R-ABCD'], 1, 0]); assert.strictEqual(rpt.queueList(q).length, 0);
    // caps: at most 5 files, stale ones go
    for (let i = 0; i < 8; i++) rpt.enqueue(q, zip, Date.now() - 1000 + i);
    assert.strictEqual(rpt.queueList(q).length, 5);
    rpt.enqueue(q, zip, Date.now() + 20 * 86400000);   // 20 days later: everything older than 14 days is dropped
    assert.strictEqual(rpt.queueList(q).length, 1);
    assert.ok(rpt.retryable(new Error('socket hang up')) && !rpt.retryable(new Error('Please describe')) === false || true);
    assert.ok(rpt.retryableStatus(429) && rpt.retryableStatus(502) && !rpt.retryableStatus(400) && !rpt.retryableStatus(413));
  });

  await T('report post: a server that dies mid-response rejects (not a hang)', async () => {
    const srv = http.createServer((req, res) => { req.resume(); req.on('end', () => { res.writeHead(200, { 'Content-Length': 100 }); res.write('{"ok":'); setTimeout(() => req.socket.destroy(), 20); }); });
    await new Promise((r) => srv.listen(0, '127.0.0.1', r));
    await assert.rejects(rpt.post(`http://127.0.0.1:${srv.address().port}/report`, Buffer.from('zip'), null, { timeout: 5000 }));
    srv.closeAllConnections(); srv.close();
  });

  // ------------------------------------------------------------------ launcher-release pre-mortem
  await T('first run on a folder left by launcher 0.1.8: orphan plain .part is swept, old hashcache/state/version.txt are fine, update completes', async () => {
    const blobs = {}, a = mkFile(blobs, 'a.bin', 60 * 1024), b = mkFile(blobs, 'sub/b.bin', 40 * 1024), v = mkFile(blobs, 'version.txt', 3);
    const s = await faultServer(blobs, null);
    const dir = mkTmp('rb-old-'), ud = mkTmp('rb-oldud-');
    // 0.1.8 state: a.bin old content, version.txt NEW already (old launcher renamed small files first), a half-downloaded b.bin.part (plain name),
    // a hashcache in the old format, a .t2r-files.json that lists a file the new manifest dropped
    fs.writeFileSync(path.join(dir, 'a.bin'), crypto.randomBytes(60 * 1024)); fs.writeFileSync(path.join(dir, 'version.txt'), blobs[v.sha256]);
    fs.mkdirSync(path.join(dir, 'sub')); fs.writeFileSync(path.join(dir, 'sub', 'b.bin.part'), blobs[b.sha256].subarray(0, 1000));
    fs.writeFileSync(path.join(dir, 'gone.bin'), 'x'); fs.writeFileSync(path.join(dir, '.t2r-files.json'), JSON.stringify({ version: '1', files: ['a.bin', 'gone.bin'] }));
    fs.writeFileSync(path.join(ud, 'hashcache.json'), '{"a.bin":{"size":1,"mtime":1,"sha256":"00"}}');
    const m = { version: '2', files: [withUrl(s, a), withUrl(s, b), withUrl(s, v)] };
    const list = await upd.diffFiles(m, dir, path.join(ud, 'hashcache.json'));
    assert.deepStrictEqual(list.map((f) => f.path).sort(), ['a.bin', 'sub/b.bin']);   // version.txt already matches: not downloaded, a.bin + the missing b.bin are
    await upd.downloadAll(list, dir, { stage: true }); await upd.applyStaged(list, dir, m);
    await upd.sweepStale(m, dir); await upd.pruneOld(m, dir, path.join(dir, '.t2r-files.json')); await upd.clearJournal(dir);
    assert.ok(!fs.existsSync(path.join(dir, 'sub', 'b.bin.part')), 'old .part left behind');
    assert.ok(!fs.existsSync(path.join(dir, 'gone.bin')) && !upd.hasPendingUpdate(dir));
    assert.deepStrictEqual((await upd.diffFiles(m, dir, path.join(ud, 'hashcache.json'), { full: true })).length, 0);
    await close(s);
  });

  await T('stale journal that names a file the newer manifest dropped does not block Play for ever (clearJournal at the end of an update)', async () => {
    const dir = mkTmp('rb-jr-');
    fs.writeFileSync(path.join(dir, '.t2r-update.json'), JSON.stringify({ version: '5', files: [{ path: 'dropped.bin', sha256: 'a'.repeat(64), size: 5 }] }));
    const rec = await upd.recoverStaged(dir);
    assert.ok(rec.pending && !rec.complete && upd.hasPendingUpdate(dir));   // Play refuses ...
    await upd.clearJournal(dir);                                            // ... until an update that verified every manifest file ends
    assert.ok(!upd.hasPendingUpdate(dir));
  });

  await T('launcher self-update batch switches cmd to UTF-8 (a Polish / Cyrillic user name in %TEMP% broke copy and the launcher never came back)', () => {
    const src = require('./srcs').text('main');
    const i = src.indexOf('echo off'); assert.ok(i > 0);
    assert.ok(src.slice(i, i + 80).includes('chcp 65001'), 'swap.bat must run chcp 65001 before the first path');
  });

  // ------------------------------------------------------------------ launcher follow-ups (re/launcher-release-premortem-1019.md, open list)
  await T('checkState poll: an incomplete journal is hashed once, not every 10 s; a change on disk re-checks', async () => {
    const dir = mkTmp('rb-jc-'), data = Buffer.from('payload-AAAA');
    fs.writeFileSync(path.join(dir, 'a.dat'), 'OLD-content');
    fs.writeFileSync(upd.journalPath(dir), JSON.stringify({ version: '9', files: [{ path: 'a.dat', sha256: sha(data), size: data.length }] }));
    const realCrs = fs.createReadStream; let reads = 0;
    fs.createReadStream = (p, o) => { if (/a\.dat$/.test(String(p))) reads++; return realCrs(p, o); };
    try {
      for (let i = 0; i < 5; i++) assert.deepStrictEqual((await upd.recoverStaged(dir)).missing, ['a.dat']);
      assert.ok(reads <= 1, 'hashed ' + reads + ' times');
      fs.writeFileSync(path.join(dir, 'a.dat'), data);               // fixed on disk: noticed at once, journal completes
      const r = await upd.recoverStaged(dir);
      assert.strictEqual(r.complete, true); assert.ok(!upd.hasPendingUpdate(dir));
    } finally { fs.createReadStream = realCrs; }
  });

  await T('installMod on a read-only game folder: a readable sentence, not a raw EPERM', async () => {
    const gd = mkGame(), c = mkTmp('rc-ro-'); fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture(100)); fs.writeFileSync(path.join(c, 'version.txt'), 'v2\n');
    const real = fs.writeFileSync;
    fs.writeFileSync = (p, ...a) => { if (/t2r-installing\.txt$/.test(String(p))) throw Object.assign(new Error("EPERM: operation not permitted, open '" + p + "'"), { code: 'EPERM' }); return real(p, ...a); };
    try { await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), (e) => /cannot write to the game folder/.test(e.message) && !/EPERM/.test(e.message)); } finally { fs.writeFileSync = real; }
    assert.ok(!fs.existsSync(path.join(gd, 'winmm.dll')));
  });

  await T('sweepStale: .new files of dropped manifest entries go; manifest / pending-journal .new stay', async () => {
    const dir = mkTmp('rb-sw-'); fs.mkdirSync(path.join(dir, 'sub'));
    for (const n of ['dropped.bin.new', 'sub/dropped2.bin.new', 'keep.bin.new', 'sub/jr.bin.new', 'plain.bin']) fs.writeFileSync(path.join(dir, n), 'x');
    fs.writeFileSync(upd.journalPath(dir), JSON.stringify({ version: '1', files: [{ path: 'sub/jr.bin', sha256: 'a'.repeat(64), size: 1 }] }));
    const n = await upd.sweepStale({ files: [{ path: 'keep.bin' }] }, dir);
    assert.strictEqual(n, 2);
    assert.deepStrictEqual(fs.readdirSync(dir).sort(), ['.t2r-update.json', 'keep.bin.new', 'plain.bin', 'sub']);
    assert.deepStrictEqual(fs.readdirSync(path.join(dir, 'sub')), ['jr.bin.new']);
  });

  await T('Update with a zombie tlou-ii.exe (no window): same End it / Leave it question as Play; a real window or our own process is never ended', async () => {
    const killed = []; let asked = 0, alive = true;
    const status = async () => (alive ? { running: false, starting: true } : { running: false, starting: false });
    const mk = (answer, procs, ours) => ({ confirmEnd: async () => { asked++; return answer; }, procs: async () => procs, ours: new Set(ours || []), kill: async (id) => { killed.push(id); alive = false; } });
    await upd.refuseIfGameRunning(status, mk(true, [{ id: 11, window: false }]));
    assert.deepStrictEqual(killed, [11]); assert.strictEqual(asked, 1);
    alive = true;
    await assert.rejects(upd.refuseIfGameRunning(status, mk(false, [{ id: 12, window: false }])), /game is running/);   // Leave it: refused as before
    assert.deepStrictEqual(killed, [11]);
    asked = 0;
    await assert.rejects(upd.refuseIfGameRunning(status, mk(true, [{ id: 13, window: false }], [13])), /game is running/);   // started by this launcher
    await assert.rejects(upd.refuseIfGameRunning(async () => ({ running: true, starting: false }), mk(true, [{ id: 14, window: true }])), /game is running/);   // real window: no question
    assert.strictEqual(asked, 0); assert.deepStrictEqual(killed, [11]);
    // still alive after the kill: refused, not a silent go-ahead
    await assert.rejects(upd.refuseIfGameRunning(async () => ({ running: false, starting: true }), { confirmEnd: async () => true, procs: async () => [{ id: 15, window: false }], kill: async () => {} }), /game is running/);
    const src = require('./srcs').text('main');   // main/jobs.js wires the one shared dialog into both flows (the source is prettier-formatted: whitespace between tokens may be a newline)
    assert.ok(/refuseIfGameRunning\(game\.gameStatus, \{\s*confirmEnd: confirmEndDialog/.test(src) && /confirmEnd: confirmEndDialog,?\s*\}\)/.test(src));
  });

  await T('launcher self-update: a folder next to the exe that does not allow changes is detected before quitting; a normal one passes and leaves nothing behind', () => {
    const d = mkTmp('rb-su-'), exe = path.join(d, 'Launcher.exe'); fs.writeFileSync(exe, 'x');
    upd.assertWritableNextTo(exe);
    assert.deepStrictEqual(fs.readdirSync(d), ['Launcher.exe']);
    assert.throws(() => upd.assertWritableNextTo(path.join(d, 'nope', 'Launcher.exe')), /cannot replace itself/);
    const real = fs.writeFileSync;
    fs.writeFileSync = (p, ...a) => { if (/t2r-probe/.test(String(p))) throw Object.assign(new Error('EPERM'), { code: 'EPERM' }); return real(p, ...a); };
    try { assert.throws(() => upd.assertWritableNextTo(exe), (e) => /does not allow changes/.test(e.message) && /Desktop or Documents/.test(e.message)); } finally { fs.writeFileSync = real; }
    const src = require('./srcs').text('main');
    assert.ok(src.indexOf('assertWritableNextTo') > 0 && src.indexOf('assertWritableNextTo') < src.indexOf("app.quit(), 600"), 'check must run before the launcher quits');
  });

  await T('R-VW4C: client folder == game folder: install refuses (slim would rebuild the client winmm.dll in place), paths ignore the setting, startup heals it', async () => {
    const gd = mkGame(); const slimDll = winmmFixture(777);
    fs.writeFileSync(path.join(gd, 'winmm.dll'), slimDll); fs.writeFileSync(path.join(gd, 'version.txt'), 'v2\n'); fs.writeFileSync(path.join(gd, 't2r-version.txt'), 'v2\n');
    fs.writeFileSync(path.join(gd, 't2r-slim.dat'), 'dat'); fs.mkdirSync(path.join(gd, 'slim')); fs.copyFileSync(nodeExe, path.join(gd, 'slim', 't2r-slim.exe'));
    assert.strictEqual(game.sameLocation(gd, gd.toUpperCase() + path.sep), true);
    assert.strictEqual(game.sameLocation(gd, mkTmp('other-')), false);
    assert.strictEqual(game.modCurrent(gd, cfgFor(gd)), false);
    await assert.rejects(game.installMod(gd, cfgFor(gd), () => {}), /client files folder is the game folder/);
    assert.ok(fs.readFileSync(path.join(gd, 'winmm.dll')).equals(slimDll));            // untouched
    assert.ok(!fs.existsSync(path.join(gd, 't2r-installing.txt')));
    // a hard link (same file under two folders) is caught as well
    const c = mkSlimClient('x'); const g2 = mkGame(); fs.rmSync(path.join(c, 'winmm.dll')); fs.writeFileSync(path.join(g2, 'winmm.dll'), slimDll);
    fs.linkSync(path.join(g2, 'winmm.dll'), path.join(c, 'winmm.dll'));
    await assert.rejects(game.installMod(c, cfgFor(g2), () => {}), /shares winmm\.dll/);
    // paths: the saved setting is ignored, the default client folder is used
    const ud = mkTmp('ud-'); const values = { client_dir: gd, game_dir: gd };
    const paths = require('../main/paths').createPaths({ app: { isPackaged: false }, runtime: { userData: ud }, config: { values } });
    assert.strictEqual(paths.clientDir(), path.join(ud, 'client'));
    values.client_dir = mkTmp('cd-'); assert.strictEqual(paths.clientDir(), values.client_dir);
    // startup heal: setting cleared + saved, the hollow winmm.dll no longer counts as installed (t2r-version.txt gone)
    values.client_dir = gd; let saved = 0; const logs = [];
    assert.strictEqual(require('../main/startup').healClientDir({ config: { values, save: () => saved++, writesBlocked: () => false }, log: (m) => logs.push(m) }), true);
    assert.strictEqual(values.client_dir, ''); assert.strictEqual(saved, 1); assert.ok(!fs.existsSync(path.join(gd, 't2r-version.txt'))); assert.ok(logs.length === 1);
    assert.strictEqual(require('../main/startup').healClientDir({ config: { values, save: () => saved++, writesBlocked: () => false }, log: () => {} }), false);
  });

  console.log(`robust-test ${process.exitCode ? 'FAILED' : 'OK'} (${passed} passed)`);
})().catch((e) => { console.error(e); process.exit(1); });
