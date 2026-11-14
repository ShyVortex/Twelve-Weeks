'use strict';
// node test/clientupdate-test.js : a newly published client build is installed by itself when idle; with the game up the player is told to quit it first.
const assert = require('assert');
const P = require('../src/playstate');
const st = (n) => ({ toDownload: { files: n, bytes: 1 }, offline: false });
const idle = { s: 'idle' }, run = { s: 'running' };
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log('  ok  ' + n); } catch (e) { console.log('FAIL  ' + n + '\n' + e.stack); process.exitCode = 1; } };
t('idle + new build -> auto', () => assert.strictEqual(P.clientUpdateAction(st(3), idle, null, false), 'auto'));
t('game running -> quit-game, never auto', () => assert.strictEqual(P.clientUpdateAction(st(3), run, null, false), 'quit-game'));
t('game starting / preparing -> quit-game', () => { assert.strictEqual(P.clientUpdateAction(st(3), { s: 'starting' }, null, false), 'quit-game'); assert.strictEqual(P.clientUpdateAction(st(3), { s: 'preparing' }, null, false), 'quit-game'); });
t('up to date -> nothing', () => assert.strictEqual(P.clientUpdateAction(st(0), idle, null, false), null));
t('busy / single player / offline -> nothing', () => { assert.strictEqual(P.clientUpdateAction(st(3), idle, 'update', false), null); assert.strictEqual(P.clientUpdateAction(st(3), idle, null, true), null); assert.strictEqual(P.clientUpdateAction({ toDownload: { files: 3 }, offline: true }, idle, null, false), null); });
console.log(ok + ' passed');
