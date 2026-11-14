'use strict';
// node test/daemon-test.js : asks a LOCAL copy of the game daemon (scratch port + scratch database, never the live one) for the online count (op 0x15)
// and the clan feed (op 0xB4).
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert'), { spawn } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon');
const game = require('../lib/game');

(async () => {
  const tmp = mkTmp('f2dm-');
  const daemon = path.join(__dirname, '..', '..', '..', 'tools', 'daemon.py');
  const port = 17155, root = path.join(__dirname, '..', '..', '..');
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', daemon], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_DB: path.join(tmp, 't2r.db'), T2R_VERSION: 'test' }, stdio: 'ignore' });
  try {
    let n = null;
    for (let i = 0; i < 30 && n === null; i++) { await new Promise((r) => setTimeout(r, 500)); n = await dm.onlineCount('127.0.0.1', port); }
    assert.ok(n !== null && n >= 1, 'online count ' + n);
    const tok = game.nameToken('Tester', '0123456789abcdef01234567');
    const lines = await dm.feedLines('127.0.0.1', port, tok);
    assert.ok(Array.isArray(lines), 'feed reply');     // a player without a clan gets n=0
    const pl = await dm.feedLines('127.0.0.1', port, tok, 'pl');       // the language byte (0xB4 [token][1] = Polish) is accepted
    assert.ok(Array.isArray(pl), 'feed reply in Polish');
    console.log('daemon-test OK online=' + n + ' feedLines=' + lines.length + ' (pl ' + pl.length + ')');
  } finally {
    p.kill(); await new Promise((r) => setTimeout(r, 400));
    ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* none */ } });   // the daemon logs next to itself
  }
})().catch((e) => { console.error(e); process.exit(1); });
