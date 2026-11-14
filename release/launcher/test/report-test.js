'use strict';
// node test/report-test.js : builds a report from a SCRATCH game folder, checks secrets are scrubbed, and (if python is available) posts it to a local
// update server on a scratch port. Never touches a real game folder or the live daemon.
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert'), { spawn, execFileSync } = require('child_process');
const mkTmp = require('./tmp');
const rpt = require('../lib/report');

(async () => {
  const tmp = mkTmp('f2rep-'); process.env.LOCALAPPDATA = path.join(tmp, 'local');   // hermetic: no real crash dumps
  const game = path.join(tmp, 'game'); fs.mkdirSync(game);
  const token = '54324e3a' + 'ab'.repeat(28);
  fs.writeFileSync(path.join(game, 't2r-ext.log'), `boot ok\nlogin token ${token}\n{"token":"${token}"}\n`);
  fs.writeFileSync(path.join(game, 't2r-ext.prev.log'), 'previous\n');
  fs.writeFileSync(path.join(game, 't2r-version.txt'), 'abc123\n');
  fs.writeFileSync(path.join(game, 'tlou-ii-mp.json'), JSON.stringify({ token }));       // must never be listed
  fs.writeFileSync(path.join(game, 'crash.mdmp'), Buffer.alloc(3 * 1024 * 1024, 7));
  fs.mkdirSync(path.join(tmp, 'docs', 'The Last of Us Part II'), { recursive: true }); const old = path.join(tmp, 'docs', 'The Last of Us Part II', 'old.mdmp'); fs.writeFileSync(old, Buffer.alloc(1000, 1)); fs.utimesSync(old, new Date(Date.now() - 30 * 86400000), new Date(Date.now() - 30 * 86400000));
  const sdir = path.join(tmp, 'steamtmp'); fs.mkdirSync(sdir);   // the Steam helper's logs: current + previous run
  fs.writeFileSync(path.join(sdir, 't2r-steam.log'), `peer slot 1: state 3 ping 205 ms in 0 pkt/s token ${token}\n`); fs.writeFileSync(path.join(sdir, 't2r-steam.prev.log'), 'old run\n');
  const list = rpt.collect({ gameDir: game, clientDir: '', launcherLog: '', docsDir: path.join(tmp, 'docs'), olderDumps: false, steamLogDir: sdir });
  const names = list.map((f) => f.name);
  assert.ok(names.includes('t2r-ext.log') && names.includes('t2r-ext.prev.log') && names.includes('crash.mdmp'), names.join());
  { // per-match logs (ext logs/t2r-match-*.log): newest 3 by default, 8 for 'earlier' answers, scrubbed like every log
    const ml = path.join(game, 'logs'); fs.mkdirSync(ml);
    for (let i = 1; i <= 5; i++) { const f = path.join(ml, `t2r-match-2026101${i}-120000-hospital.log`); fs.writeFileSync(f, `match ${i} token ${token}
`); const t = new Date(Date.now() - (6 - i) * 3600000); fs.utimesSync(f, t, t); }
    const ln = (o) => rpt.collect({ gameDir: game, clientDir: '', launcherLog: '', docsDir: '', olderDumps: false, steamLogDir: sdir, ...o }).map((f) => f.name).filter((n) => /^t2r-match-/.test(n));
    assert.deepStrictEqual(ln({}), ['t2r-match-20261015-120000-hospital.log', 't2r-match-20261014-120000-hospital.log', 't2r-match-20261013-120000-hospital.log'], 'newest 3 by default');
    assert.strictEqual(ln({ matchLogs: 8 }).length, 5); assert.strictEqual(ln({ matchLogs: 0 }).length, 0);
    const b = rpt.build(rpt.collect({ gameDir: game, clientDir: '', launcherLog: '', docsDir: '', olderDumps: false, steamLogDir: sdir }), {}, 'sys'); assert.ok(b.files.some((f) => /^t2r-match-/.test(f.name)));
  }
  assert.ok(!names.some((n) => /tlou-ii-mp\.json|client\.json/i.test(n)));
  assert.ok(names.includes('t2r-steam.log') && names.includes('t2r-steam.prev.log'), 'the Steam helper logs ride along: ' + names.join());
  assert.ok(!names.includes('old.mdmp'), 'an older dump needs the toggle');
  // ---- both dumps of ONE crash (game .mdmp + WER .dmp), never another process, WER first, token blanked in the copy, registry state mocked
  {
    const mk = (pid, body) => { const b = Buffer.alloc(4096 + (body ? body.length : 0)); b.write('MDMP', 0, 'latin1'); b.writeUInt32LE(1, 8); b.writeUInt32LE(32, 12);
      b.writeUInt32LE(15, 32); b.writeUInt32LE(24, 36); b.writeUInt32LE(64, 40); b.writeUInt32LE(3, 64 + 4); b.writeUInt32LE(pid, 64 + 8); b.writeUInt32LE(Math.floor(Date.now() / 1000) - 60, 64 + 12);
      if (body) body.copy(b, 4096); return b; };
    const g2 = path.join(tmp, 'game2'), docs2 = path.join(tmp, 'docs2', 'The Last of Us Part II'), cd = path.join(process.env.LOCALAPPDATA, 'CrashDumps');
    fs.mkdirSync(g2); fs.mkdirSync(docs2, { recursive: true }); fs.mkdirSync(cd, { recursive: true });
    fs.writeFileSync(path.join(g2, 't2r-ext.log'), 't2r-ext loaded, pid 4242, winmm base 0x1000 (x)\nplaying\n');
    const tok = 'cd'.repeat(32), body = Buffer.concat([Buffer.from('xx' + tok + 'yy', 'latin1'), Buffer.from(tok, 'utf16le')]);
    fs.writeFileSync(path.join(docs2, 'game.mdmp'), mk(4242));               // the game's own dump of pid 4242
    fs.writeFileSync(path.join(g2, 'game.mdmp'), mk(4242));                  // its copy next to the exe: sent once
    fs.writeFileSync(path.join(cd, 'tlou-ii.exe.4242.dmp'), mk(4242, body)); // WER's dump of the same crash
    fs.writeFileSync(path.join(cd, 'tlou-ii.exe.999.dmp'), mk(999));         // another process: never attached
    const l2 = rpt.collect({ gameDir: g2, clientDir: '', launcherLog: '', docsDir: path.join(tmp, 'docs2'), olderDumps: false, steamLogDir: sdir });
    const dn = l2.filter((f) => f.kind === 'dump').map((f) => f.name);
    assert.deepStrictEqual(dn, ['tlou-ii.exe.4242.dmp', 'game.mdmp'], 'WER first, game dump second, one copy, no other pid: ' + dn.join());
    assert.ok(l2.skippedDumps.some((d) => /999/.test(d.name)) && l2.skippedDumps.some((d) => /copy/.test(d.reason)), JSON.stringify(l2.skippedDumps));
    const b2 = rpt.build(l2, { text: 't' }, 'sys\n'), z = b2.zip.toString('latin1');
    assert.ok(!z.includes(tok), 'zip is deflated; checked on the unpacked copy below');
    const sd = Buffer.from(body); assert.strictEqual(rpt.scrubDump(sd), 2); assert.ok(!sd.includes(Buffer.from(tok)) && !sd.includes(Buffer.from(tok, 'utf16le')) && sd.length === body.length);
    assert.ok(b2.files.some((f) => f.name === 'tlou-ii.exe.4242.dmp') && b2.files.some((f) => f.name === 'game.mdmp'));
    assert.ok(fs.readFileSync(path.join(cd, 'tlou-ii.exe.4242.dmp')).includes(Buffer.from(tok)), 'the file on disk is never modified');
    // size pressure: the WER dump that does not fit is skipped, the small game dump still goes
    const big = rpt.collect({ gameDir: g2, clientDir: '', launcherLog: '', docsDir: path.join(tmp, 'docs2'), olderDumps: false, steamLogDir: sdir });
    big.find((f) => f.name === 'tlou-ii.exe.4242.dmp').src = path.join(tmp, 'nowhere.dmp');
    assert.ok(rpt.build(big, { text: 't' }, 's').files.some((f) => f.name === 'game.mdmp'));
    // ---- the ext's own crash file t2r-crash-<pid>-1.bin (tools/ext/crashbin.h): attached by pid + create time + build like a dump, otherwise named in the meta
    {
      const bin = (pid, build, ageMs) => { const b = Buffer.alloc(128 + 4096, 3); b.fill(0, 0, 128); b.write('T2RCBIN1', 0, 'latin1'); b.writeUInt32LE(1, 8); b.writeUInt32LE(128, 12); b.writeUInt32LE(pid, 16);
        b.writeBigUInt64LE(BigInt(Math.round((Date.now() - ageMs + 11644473600000) * 1e4)), 24); b.writeUInt32LE(0xC0000005, 32); b.write(build, 96, 'latin1'); return b; };
      const g3 = path.join(tmp, 'game3'); fs.mkdirSync(g3);
      fs.writeFileSync(path.join(g3, 't2r-ext.log'), 't2r-ext loaded, pid 5151, winmm base 0x1000, build Oct  9 2026 12:34:56 (release)\nplaying\n');
      fs.writeFileSync(path.join(g3, 't2r-crash-5151-1.bin'), bin(5151, 'Oct  9 2026 12:34:56 (release)', 60000));   // __DATE__ pads the day: "Oct  9"
      fs.writeFileSync(path.join(g3, 't2r-crash-777-1.bin'), bin(777, 'Oct  9 2026 12:34:56 (release)', 60000));    // another process
      fs.writeFileSync(path.join(g3, 't2r-crash-5151-2.bin'), bin(5151, 'Oct  8 2026 01:02:03 (release)', 60000));   // same pid, other build
      fs.writeFileSync(path.join(g3, 't2r-crash-9999-1.bin'), Buffer.from('not a crash file'));
      fs.utimesSync(path.join(g3, 't2r-crash-777-1.bin'), new Date(Date.now() - 5000), new Date(Date.now() - 5000));
      const l3 = rpt.collect({ gameDir: g3, clientDir: '', launcherLog: '', docsDir: '', olderDumps: false, steamLogDir: sdir });
      const dn3 = l3.filter((f) => f.kind === 'dump').map((f) => f.name);
      assert.deepStrictEqual(dn3, ['t2r-crash-5151-1.bin'], 'only the crash file of the logged process and build: ' + dn3.join());
      const why = (n) => (l3.skippedDumps.find((d) => d.name === n) || {}).reason || '';
      assert.ok(/not in the attached logs/.test(why('t2r-crash-777-1.bin')) && /build differs/.test(why('t2r-crash-5151-2.bin')) && /bad header/.test(why('t2r-crash-9999-1.bin')), JSON.stringify(l3.skippedDumps));
      assert.ok(l3.dumps.some((d) => d.writer === 'ext' && d.pid === 5151 && d.sent_as === 't2r-crash-5151-1.bin'));
      assert.ok(rpt.build(l3, { text: 't' }, 's').files.some((f) => f.name === 't2r-crash-5151-1.bin'), 'goes into the zip');
      assert.strictEqual(rpt.binInfo(path.join(g3, 't2r-crash-5151-1.bin')).pid, 5151);
      // with a dump of the same process both go (dump first)
      const cd3 = path.join(process.env.LOCALAPPDATA, 'CrashDumps');
      fs.writeFileSync(path.join(cd3, 'tlou-ii.exe.5151.dmp'), mk(5151));
      assert.deepStrictEqual(rpt.collect({ gameDir: g3, clientDir: '', launcherLog: '', docsDir: '', olderDumps: false, steamLogDir: sdir }).filter((f) => f.kind === 'dump').map((f) => f.name), ['tlou-ii.exe.5151.dmp', 't2r-crash-5151-1.bin']);
      fs.rmSync(path.join(cd3, 'tlou-ii.exe.5151.dmp'), { force: true });
    }
    // registry state: mocked reg.exe output, the real registry is never read here
    const B = String.fromCharCode(92), K = ['HKEY_LOCAL_MACHINE', 'SOFTWARE', 'Microsoft', 'Windows', 'Windows Error Reporting', 'LocalDumps'].join(B), NL = String.fromCharCode(13, 10);
    assert.ok(/^not configured/.test(rpt.werLocalDumps(() => '')));
    assert.ok(/DumpType 2.*C:.d.*per-exe/.test(rpt.werLocalDumps(() => K + NL + NL + K + B + 'tlou-ii.exe' + NL + '    DumpFolder    REG_EXPAND_SZ    C:' + B + 'd' + NL + '    DumpType    REG_DWORD    2' + NL)), 'per-exe');
    assert.ok(/global key/.test(rpt.werLocalDumps(() => K + NL + '    DumpType    REG_DWORD    1' + NL + NL + K + B + 'Other.exe' + NL)), 'global');
    assert.ok(rpt.systemInfo({ wer: 'configured x', launcherVersion: '0' }).includes('wer-localdumps configured x'));
  }
  const none = rpt.collect({ gameDir: path.join(tmp, 'empty'), clientDir: '', launcherLog: '', docsDir: '' });
  assert.strictEqual(none[0].kind, 'missing');   // t2r-ext.log missing -> a warning row, not silence
  const meta = { text: 'it crashed after the match', when: 'Just now', name: 'Tester', version: 'abc123', steamId: '7656119800000000' };
  const b = rpt.build(list, meta, rpt.systemInfo({ ...meta, nameSource: 'test', launcherVersion: '0' }));
  const zipPath = path.join(tmp, 'report.zip'); fs.writeFileSync(zipPath, b.zip);
  const raw = b.zip.toString('latin1');
  assert.ok(!raw.includes(token));
  // python side: the server's own validator must accept it, with the log scrubbed
  const root = path.join(tmp, 'reports');
  const py = path.join(__dirname, '..', '..', '..', 'tools', 'update_server');
  let out;
  try { out = execFileSync('python', ['-I', '-c', `import sys; sys.path.insert(0, r'${py}'); import report_store, json; r = report_store.save_report(r'${root}', open(r'${zipPath}', 'rb').read(), '127.0.0.1'); print(json.dumps(r))`], { encoding: 'utf8' }); }
  catch (e) { console.log('python not available, skipped the server check:', e.message.split('\n')[0]); console.log('report-test OK (zip only)'); return; }
  const dir = JSON.parse(out).dir;
  const log = fs.readFileSync(path.join(dir, 'files', 't2r-ext.log'), 'utf8');
  assert.ok(log.includes('<token-removed>') && !log.includes(token) && log.includes('<removed>'), log);
  assert.ok(fs.existsSync(path.join(dir, 'files', 'crash.mdmp')) && fs.existsSync(path.join(dir, 'files', 'system.txt')));
  const meta2 = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json'), 'utf8'));
  assert.strictEqual(meta2.steamId, '7656119800000000'); assert.ok(meta2.code.startsWith('R-'));
  // end to end: the launcher's own POST against a local update server (scratch port + scratch data dir)
  const srv = spawn('python', ['-I', path.join(py, 'server.py'), '--data', path.join(tmp, 'srvdata'), '--host', '127.0.0.1', '--port', '15396'], { stdio: 'ignore' });
  try {
    let r = null;
    for (let i = 0; i < 20 && !r; i++) { await new Promise((x) => setTimeout(x, 300)); try { r = await rpt.post('http://127.0.0.1:15396/report', b.zip); } catch { /* not up yet */ } }
    assert.ok(r && r.status === 200 && r.json.ok && /^R-/.test(r.json.code), JSON.stringify(r));
    const stored = fs.readdirSync(path.join(tmp, 'srvdata', 'reports')).filter((d) => d.includes(r.json.code));
    assert.strictEqual(stored.length, 1);
    console.log('report-test OK (zip, scrub, server validator, HTTP POST)', r.json.code, b.zip.length, 'bytes');
  } finally { srv.kill(); }
})().catch((e) => { console.error(e); process.exit(1); });
