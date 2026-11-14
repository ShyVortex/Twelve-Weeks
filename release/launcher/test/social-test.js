'use strict';
// node test/social-test.js : the FRIENDS / PARTY service end to end against a LOCAL copy of the game daemon (scratch port + scratch database, never the
// live one): two launchers send, accept and cancel friend requests, search by name, form a party (invite, join, ready, promote, kick, leave) through
// lib/daemon.js social() and the main-process wrapper (main/social.js), and the renderer module (src/social.js) draws the replies.
const fs = require('fs'), path = require('path'), assert = require('assert'), vm = require('vm'), { spawn } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon');
const game = require('../lib/game');
const { createSocial } = require('../main/social');

(async () => {
  const tmp = mkTmp('f2so-');
  const daemon = path.join(__dirname, '..', '..', '..', 'tools', 'daemon.py');
  const port = 17156, root = path.join(__dirname, '..', '..', '..');
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', daemon], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_DB: path.join(tmp, 't2r.db'), T2R_VERSION: 'test', T2R_HOST: '127.0.0.1' }, stdio: 'ignore' });
  try {
    let n = null;
    for (let i = 0; i < 30 && n === null; i++) { await new Promise((r) => setTimeout(r, 500)); n = await dm.onlineCount('127.0.0.1', port); }
    assert.ok(n !== null, 'daemon up');
    const A = game.nameToken('Anna', '0123456789abcdef01234567'), B = game.nameToken('Bert', 'fedcba987654321001234567'), C = game.nameToken('Cleo', 'aaaaaaaaaaaaaaaaaaaaaaaa');
    const call = (tok, sub, arg) => dm.social('127.0.0.1', port, tok, 'en', sub, arg);

    let r = await call(A, 'state');
    assert.strictEqual(r.ok, 1); assert.strictEqual(r.me.name, 'Anna'); assert.deepStrictEqual(r.friends, []);
    assert.strictEqual(await dm.social('127.0.0.1', port, A, 'en', 'nonsense'), null, 'unknown sub is not sent');
    await call(B, 'state'); await call(C, 'state');

    r = await call(A, 'search', 'ber');
    assert.deepStrictEqual(r.found.map((f) => f.name), ['Bert'], 'search finds the other launcher by name');
    r = await call(A, 'add', 'Bert');
    assert.strictEqual(r.ok, 1); assert.strictEqual(r.out.length, 1);
    r = await call(A, 'add', 'Bert'); assert.strictEqual(r.err, 'pending');
    r = await call(B, 'state'); assert.strictEqual(r.in.length, 1); assert.strictEqual(r.in[0].name, 'Anna');
    r = await call(B, 'accept', r.in[0].id);
    assert.strictEqual(r.ok, 1); assert.strictEqual(r.friends[0].name, 'Anna'); assert.strictEqual(r.friends[0].status, 'launcher', 'a launcher that polled is online');
    r = await call(A, 'state'); assert.strictEqual(r.friends[0].name, 'Bert'); assert.strictEqual(r.out.length, 0);

    // a request that is cancelled / declined
    r = await call(C, 'add', 'Anna'); assert.strictEqual(r.ok, 1);
    r = await call(A, 'state'); assert.strictEqual(r.in.length, 1);
    r = await call(A, 'remove', r.in[0].id); assert.strictEqual(r.in.length, 0);

    // the party: Anna leads, Bert joins
    r = await call(A, 'invite', 'garbage'); assert.strictEqual(r.ok, 0);
    r = await call(A, 'invite', r.friends[0].id); assert.strictEqual(r.ok, 1, 'invite a friend: ' + r.err);
    const annaId = r.me.id;
    r = await call(B, 'state'); assert.strictEqual(r.pinv.length, 1); assert.strictEqual(r.pinv[0].name, 'Anna');
    r = await call(B, 'join', annaId); assert.strictEqual(r.ok, 1, r.err);
    assert.strictEqual(r.party.members.length, 2); assert.strictEqual(r.party.members[0].leader, true); assert.strictEqual(r.party.meLeader, false);
    r = await call(B, 'ready', '1'); assert.ok(r.party.members.find((m) => m.me).ready);
    r = await call(B, 'kick', annaId); assert.strictEqual(r.err, 'notleader');
    r = await call(A, 'promote', r.party.members.find((m) => m.me).id); assert.strictEqual(r.party.meLeader, false, 'Bert leads now');
    r = await call(A, 'leave'); assert.strictEqual(r.party, null, 'a party of one is no party');

    // the main-process wrapper (token from the player name + config, address from paths) and the renderer module
    const svc = createSocial({
      config: { values: { token_id: '0123456789abcdef01234567' } },
      paths: { serverAddress: () => '127.0.0.1:' + port },
      player: { resolveName: async () => ({ name: 'Anna' }) },
      locale: { langNow: () => 'en' },
    });
    const g = await svc.get(); assert.strictEqual(g.social.me.name, 'Anna');
    await assert.rejects(async () => svc.act('wipe', ''), /Unknown friends action/);
    const act = await svc.act('add', 'Cleo'); assert.strictEqual(act.social.out[0].name, 'Cleo');

    // renderer: load src/social.js into a tiny fake DOM and draw the reply
    const els = {}; const el = (id) => (els[id] = els[id] || { id, hidden: false, innerHTML: '', children: [], firstChild: null, classList: { toggle() {} }, addEventListener() {}, dataset: {}, select() {} });
    const sandbox = {
      document: { getElementById: el, body: { classList: { contains: () => false } }, activeElement: null },
      f2: { social: async () => ({ ok: true, social: g.social }), socialAct: async () => ({ ok: true, social: g.social }) },
      T: (s, v) => (v ? s.replace(/\{(\w+)\}/g, (_, k) => v[k]) : s), Snd: { play() {} }, toast() {}, notify() {}, curView: 'friends', setTimeout, clearTimeout, navigator: {},
    };
    sandbox.window = sandbox;
    const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'social.js'), 'utf8');
    vm.runInNewContext(src + '\n;this.Social = Social;', sandbox);
    sandbox.Social.start(); await new Promise((r) => setTimeout(r, 100));
    assert.ok(sandbox.Social.last() && sandbox.Social.last().me.name === 'Anna', 'renderer loaded the state');
    console.log('social-test OK (friends, pending, party, wrapper, renderer)');
  } finally {
    p.kill(); await new Promise((r) => setTimeout(r, 400));
    ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* none */ } });
  }
  process.exit(0); // (the renderer module's poll timer would keep the loop alive)
})().catch((e) => { console.error(e); process.exit(1); });
