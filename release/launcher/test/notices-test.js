'use strict';
// node test/notices-test.js : a LOCAL throwaway daemon (scratch game port + scratch admin port + scratch database, never the live one);
// notices are created through its admin listener (POST /notice, /shutdown) and read back with the launcher's op 0xBA client.
const fs = require('fs'), os = require('os'), path = require('path'), http = require('http'), assert = require('assert'), { spawn } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon'), game = require('../lib/game');

const post = (port, secret, p, body) => new Promise((res, rej) => {
  const b = JSON.stringify(body || {});
  const r = http.request({ host: '127.0.0.1', port, path: p, method: 'POST', headers: { 'X-Admin-Secret': secret, 'Content-Length': Buffer.byteLength(b) } }, (x) => { let d = ''; x.on('data', (c) => (d += c)); x.on('end', () => res(JSON.parse(d))); });
  r.on('error', rej); r.end(b);
});

(async () => {
  const tmp = mkTmp('f2nt-');
  const root = path.join(__dirname, '..', '..', '..'), daemon = path.join(root, 'tools', 'daemon.py');
  const port = 17156, admin = 17157;
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', daemon], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_ADMIN_PORT: String(admin), T2R_HOST: '127.0.0.1', T2R_DB: path.join(tmp, 't2r.db'), T2R_VERSION: 'test' }, stdio: 'ignore' });
  try {
    let n = null;
    for (let i = 0; i < 30 && n === null; i++) { await new Promise((r) => setTimeout(r, 500)); n = await dm.onlineCount('127.0.0.1', port); }
    assert.ok(n !== null, 'daemon up');
    let secret = '';
    for (let i = 0; i < 20 && !secret; i++) { try { secret = fs.readFileSync(path.join(tmp, 'admin-secret.txt'), 'utf8').trim(); } catch { await new Promise((r) => setTimeout(r, 300)); } }
    assert.ok(secret.length >= 16, 'admin secret');
    const tok = game.nameToken('Tester', '0123456789abcdef01234567');
    assert.deepStrictEqual(await dm.notices('127.0.0.1', port, tok, 'en'), [], 'no notices at first');
    assert.ok((await post(admin, secret, '/notice', { text: 'Maintenance tonight at 22:00', minutes: 5 })).ok);
    const sh = await post(admin, secret, '/shutdown', { minutes: 5, reason: 'patch', restart: true });
    assert.ok(sh.ok, 'shutdown scheduled');
    const l = await dm.notices('127.0.0.1', port, tok, 'pl');
    const r = l.find((x) => x.kind === 'r'), t = l.find((x) => x.kind === 't');
    assert.ok(r && r.param > 280 && r.param <= 300 && r.text === 'patch', 'restart notice ' + JSON.stringify(r));
    assert.ok(t && t.text === 'Maintenance tonight at 22:00' && t.id > 0, 'text notice ' + JSON.stringify(t));
    assert.ok((await post(admin, secret, '/shutdown/cancel')).ok);
    assert.ok(!(await dm.notices('127.0.0.1', port, tok, 'en')).some((x) => x.kind === 'r'), 'cancelled restart is gone');
    console.log('notices-test OK: ' + JSON.stringify(l));
  } finally {
    p.kill(); await new Promise((r) => setTimeout(r, 400));
    ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* none */ } });
  }
})().catch((e) => { console.error(e); process.exit(1); });
