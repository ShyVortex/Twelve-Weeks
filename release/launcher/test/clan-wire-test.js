'use strict';
// node test/clan-wire-test.js : seeds a clan in a SCRATCH database, runs a LOCAL daemon copy on a scratch port, reads it over the read-only ops 0xE0 / 0xE8,
// parses it with lib/clanwire.js and compares with tools/update_server/clan_view.py (the same database). Never the live daemon.
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert'), { spawn, execFileSync } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon'), cw = require('../lib/clanwire'), game = require('../lib/game');
const root = path.join(__dirname, '..', '..', '..');
const data = new Function(fs.readFileSync(path.join(__dirname, '..', 'src', 'gamedata.js'), 'utf8') + '\nreturn GAMEDATA;')();

// pure parser check on a known reply
const sample = 'v=1 fac=1 st=1 day=17 h=12 hu=2 s=1 need=15 wk=3 lday=16 lparts=1310 lsup=26 lneed=14 lgain=1 ldied=0 lhungry=0 lsick=0 lheal=1 lleft=0 ev=0 evn=0 levk=0 levn=0 levl=0 levg=0 levt=0 mx=18 rw=4 rl=2 ag1=3 ag2=6 ag3=9';
const meta = 'v=1 bc1=2 bc2=0 bc3=1 bc4=0 bc5=0 bc6=0 bc7=1 bp=0 ba=0 bn=3 mi=1 mp=7 ml=1 mz=15 mg1=3 mg2=6 mg3=9 mev=1';
const c0 = cw.fromWire(sample, meta, data);
assert.strictEqual(c0.week, 3); assert.strictEqual(c0.dayOfWeek, 4); assert.strictEqual(c0.event.kind, 'attack'); assert.strictEqual(c0.event.dayOfEvent, 3);
assert.strictEqual(c0.mission.name, 'Down Enemies'); assert.deepStrictEqual(c0.mission.goals, [3, 6, 9]); assert.strictEqual(c0.boosters.find((b) => b.id === 1).count, 2);
assert.strictEqual(cw.fromWire('', null, data), null);

(async () => {
  const tmp = mkTmp('f2cw-');
  const db = path.join(tmp, 't2r.db'), tid = '0123456789abcdef01234567', port = 17156;
  execFileSync('python', ['-I', '-c', `import sys, json, sqlite3; sys.path.insert(0, r'${root}/tools'); import clan; c = sqlite3.connect(r'${db}'); clan.choose_side(c, '${tid}', clan.WLF); cl = clan.load(c, '${tid}'); cl.update(day=17, healthy=12, hungry=2, sick=1, weeks_total=3, runs_won=4, runs_lost=2, last_result=json.dumps({"day": 16, "parts": 1310, "supplies": 26, "needed": 14, "gained": 1, "died": 0})); clan.save(c, '${tid}', cl); clan.mission_choose(c, '${tid}', 1); c.commit(); c.close()`]);
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', path.join(root, 'tools', 'daemon.py')], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_DB: db, T2R_VERSION: 'test' }, stdio: 'ignore' });
  try {
    const tok = game.nameToken('Tester', tid);
    let t = { state: null };
    for (let i = 0; i < 30 && !t.state; i++) { await new Promise((r) => setTimeout(r, 500)); t = await dm.clanTexts('127.0.0.1', port, tok); }
    const c = cw.fromWire(t.state, t.meta, data);
    assert.ok(c, 'no clan reply');
    const py = JSON.parse(execFileSync('python', ['-I', '-c', `import sys, json; sys.path.insert(0, r'${root}/tools/update_server'); import clan_view; print(json.dumps(clan_view.view(r'${db}', '${tid}')))`], { encoding: 'utf8' }));
    for (const k of ['hasClan', 'faction', 'factionName', 'status', 'daysDone', 'size', 'healthy', 'hungry', 'sick', 'needed', 'maxSize', 'runsWon', 'runsLost', 'week', 'dayOfWeek', 'boosterNext']) assert.deepStrictEqual(c[k], py[k], k);
    assert.deepStrictEqual(c.event, py.event); assert.deepStrictEqual(c.mission, py.mission); assert.deepStrictEqual(c.lastMatch, py.lastMatch); assert.deepStrictEqual(c.boosters, py.boosters);
    // a fresh install (unknown token) finds the account's clan through the steamid hint, read only; without the hint there is no clan
    const SID = '76561198000000042', fresh = game.nameToken('Fresh', 'c3853f30aabbccddeeff0011');
    execFileSync('python', ['-I', '-c', `import sys, sqlite3; sys.path.insert(0, r'${root}/tools'); import clan; c = sqlite3.connect(r'${db}'); clan.choose_side(c, 's:${SID}', clan.SERAPHITES); cl = clan.load(c, 's:${SID}'); cl.update(day=47); clan.save(c, 's:${SID}', cl); c.commit(); c.close()`]);
    const noHint = cw.fromWire((await dm.clanTexts('127.0.0.1', port, fresh)).state, null, data), withHint = await dm.clanTexts('127.0.0.1', port, fresh, SID);
    const hc = cw.fromWire(withHint.state, withHint.meta, data);
    assert.ok(noHint && !noHint.hasClan, 'no hint: no clan'); assert.ok(hc && hc.hasClan && hc.status === 'alive' && hc.daysDone === 47 && hc.factionName === 'SERAPHITES', 'hint: the account clan');
    console.log('clan-wire-test OK: daemon ops 0xE0/0xE8 match clan_view.py (' + c.factionName + ' week ' + c.week + ' day ' + c.dayOfWeek + ', mission ' + c.mission.name + ')');
  } finally {
    p.kill();
    await new Promise((r) => setTimeout(r, 400));
    ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* not written */ } });   // the daemon logs next to itself: remove what this test created
  }
})().catch((e) => { console.error(e); process.exit(1); });
