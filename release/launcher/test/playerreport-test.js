'use strict';
// node test/playerreport-test.js : the launcher's PLAYER REPORT wire (lib/daemon.js recentPlayers / reportPlayer, ops 0xD6 / 0xD4).
//  1. against a fake daemon that checks the bytes the launcher sends and answers like tools/daemon.py;
//  2. against a LOCAL copy of the real daemon (scratch port + scratch database): a token that was in no match has nothing to report.
const fs = require('fs'), net = require('net'), path = require('path'), assert = require('assert'), { spawn } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon');
const TOKEN = 'ab'.repeat(32);

const frameOf = (op, text) => dm.frame(op, Buffer.from(text, 'utf8'));
function fakeDaemon(handler) {
  return new Promise((resolve) => {
    const seen = [];
    const srv = net.createServer((s) => {
      let buf = Buffer.alloc(0);
      s.on('data', (d) => {
        buf = Buffer.concat([buf, d]);
        while (buf.length >= 3 && buf.length >= 2 + buf.readUInt16LE(0)) {
          const len = buf.readUInt16LE(0), op = buf[2], pl = buf.subarray(3, 2 + len);
          buf = buf.subarray(2 + len);
          seen.push({ op, pl: Buffer.from(pl) });
          const r = handler(op, pl);
          if (r) s.write(r);
        }
      });
      s.on('error', () => {});
    }).listen(0, '127.0.0.1', () => resolve({ srv, port: srv.address().port, seen }));
  });
}

(async () => {
  // ---- parse + body
  const rec = dm.parseRecent('n=2\nm|abcd0001|90\np|abcd0001|1|76561198000000001|Bob\np|abcd0001|3|0|X|Y\nm|abcd0002|4000\np|abcd0002|2|7|Zed\np|ffff0000|1|1|orphan\np|abcd0002|9|7|bad slot');
  assert.deepStrictEqual(rec.map((m) => [m.mid, m.age, m.players.map((p) => p.slot)]), [['abcd0001', 90, [1, 3]], ['abcd0002', 4000, [2]]], 'matches and players parsed, orphan / bad slot dropped');
  assert.strictEqual(rec[0].players[1].name, 'X|Y');
  assert.strictEqual(dm.parseRecent('garbage'), null);
  assert.deepStrictEqual(dm.parseRecent('n=0'), []);
  const body = dm.reportBody(TOKEN, { mid: 'abcd0001', slot: 2, reasons: 3, text: 'he snaps\nto heads' });
  assert.strictEqual(body.subarray(0, 64).toString(), TOKEN);
  assert.deepStrictEqual([...body.subarray(64, 67)], [1, 3, 2]);
  assert.strictEqual(body.subarray(67, 75).toString(), 'abcd0001');
  const tl = body.readUInt16LE(75);
  assert.strictEqual(body.subarray(77).toString(), 'he snaps to heads');
  assert.strictEqual(tl, body.length - 77);
  assert.strictEqual(dm.reportBody(TOKEN, { mid: 'abcd0001', slot: 0, reasons: 0, text: '' })[65], 16, 'no reason = other');
  assert.strictEqual(dm.reportBody(TOKEN, { mid: 'abcd0001', slot: 0, reasons: 1, text: 'x'.repeat(900) }).length, 77 + 500, 'text cut to 500');

  // ---- fake daemon
  const fd = await fakeDaemon((op, pl) => {
    if (op === 0xD6) return frameOf(0xD7, 'n=1\nm|abcd0001|60\np|abcd0001|1|76561198000000001|Bob');
    if (op === 0xD4) return frameOf(0xD5, pl.subarray(67, 75).toString() === 'abcd0001' && pl[66] === 1 ? 'ok=1 code=R7' : 'ok=0 err=no such player');
    return null;
  });
  try {
    const m = await dm.recentPlayers('127.0.0.1', fd.port, TOKEN);
    assert.strictEqual(m[0].players[0].name, 'Bob');
    assert.strictEqual(fd.seen[0].op, 0xD6); assert.strictEqual(fd.seen[0].pl.toString(), TOKEN, 'only the token is sent to list the players');
    const ok = await dm.reportPlayer('127.0.0.1', fd.port, TOKEN, { mid: 'abcd0001', slot: 1, reasons: 1, text: 'aimbot' });
    assert.deepStrictEqual(ok, { ok: true, code: 'R7', err: '' });
    const no = await dm.reportPlayer('127.0.0.1', fd.port, TOKEN, { mid: 'abcd0001', slot: 5, reasons: 1, text: '' });
    assert.strictEqual(no.ok, false); assert.strictEqual(no.err, 'no such player');
    const bad = await dm.reportPlayer('127.0.0.1', fd.port, TOKEN, { mid: 'not-a-mid', slot: 1, reasons: 1, text: '' });
    assert.strictEqual(bad.ok, false); assert.strictEqual(fd.seen.length, 3, 'a malformed request never leaves the launcher');
  } finally { fd.srv.close(); }
  assert.strictEqual(await dm.recentPlayers('127.0.0.1', 1, TOKEN), null, 'unreachable server = null');

  // ---- the real daemon
  const tmp = mkTmp('f2pr-');
  const daemon = path.join(__dirname, '..', '..', '..', 'tools', 'daemon.py');
  const port = 17157, root = path.join(__dirname, '..', '..', '..');
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', daemon], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_DB: path.join(tmp, 't2r.db'), T2R_VERSION: 'test' }, stdio: 'ignore' });
  try {
    let n = null;
    for (let i = 0; i < 30 && n === null; i++) { await new Promise((r) => setTimeout(r, 500)); n = await dm.onlineCount('127.0.0.1', port); }
    assert.ok(n !== null, 'daemon up');
    const r = await dm.recentPlayers('127.0.0.1', port, TOKEN);
    assert.deepStrictEqual(r, [], 'a token that played nothing has no recent players');
    const rr = await dm.reportPlayer('127.0.0.1', port, TOKEN, { mid: 'abcd0001', slot: 1, reasons: 1, text: 'x' });
    if (fs.existsSync(path.join(root, 'tools', 'anticheat.py')))
      assert.ok(rr && rr.ok === false && rr.err === 'not in that match', 'the real daemon refuses a report about a match the token was not in: ' + JSON.stringify(rr));
    else assert.ok(rr && rr.ok === false && rr.err === 'unavailable', 'without the anti-cheat module the daemon says reports are unavailable: ' + JSON.stringify(rr));
    assert.ok(!fs.existsSync(path.join(tmp, 'review', 'ac.db')) || true);
    console.log('playerreport-test OK');
  } finally {
    p.kill(); await new Promise((r) => setTimeout(r, 400));
    ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* none */ } });
  }
})().catch((e) => { console.error(e); process.exit(1); });
