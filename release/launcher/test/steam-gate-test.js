'use strict';
// node test/steam-gate-test.js : Play is blocked while Steam is not running (Windows); a failed probe never blocks; Linux is not gated.
const assert = require('assert');
const fs = require('fs'), path = require('path');
const mkTmp = require('./tmp');
const game = require('../lib/game');

let passed = 0;
const T = async (name, fn) => { try { await fn(); passed++; console.log('  ok  ' + name); } catch (e) { console.log('FAIL  ' + name + '\n' + (e && e.stack || e)); process.exitCode = 1; } };
const up = async () => ({ stdout: 'yes\r\n', err: null });
const down = async () => ({ stdout: '', err: null });
const broken = async () => ({ stdout: '', err: new Error('powershell.exe failed to start') });
game.testHooks.procs = async () => [];
const playOpts = () => ({ clientDir: mkTmp('sg-c-'), cfg: { game_dir: mkTmp('sg-g-'), token_id: 'x' }, server: '127.0.0.1:1', skipCheck: true, platform: 'win32', log() {} });

(async () => {
  await T('steam down -> gate blocks', async () => {
    game.testHooks.steam = down;
    assert.deepStrictEqual(await game.steamGate('win32'), { required: true, running: false });
  });
  await T('steam up -> gate allows', async () => {
    game.testHooks.steam = up;
    assert.deepStrictEqual(await game.steamGate('win32'), { required: true, running: true });
  });
  await T('probe error -> gate allows', async () => {
    game.testHooks.steam = broken;
    assert.strictEqual((await game.steamGate('win32')).running, true);
  });
  await T('Linux is never gated (Play starts Steam itself), even with the probe saying down', async () => {
    game.testHooks.steam = down;
    assert.deepStrictEqual(await game.steamGate('linux'), { required: false, running: true });
  });
  await T('Steam starts later -> the next poll enables Play (no restart)', async () => {
    let on = false;
    game.testHooks.steam = async () => (on ? up() : down());
    assert.strictEqual((await game.steamGate('win32')).running, false);
    assert.strictEqual((await game.steamGate('win32')).running, false);
    on = true;
    assert.strictEqual((await game.steamGate('win32')).running, true);
  });
  await T('play() refuses with the same message when Steam is down', async () => {
    game.testHooks.steam = down;
    await assert.rejects(game.play(playOpts()), (e) => e.message === game.STEAM_MSG && /Start Steam first - Twelve Weeks needs Steam running/.test(e.message));
  });
  await T('play() with Steam up gets past the gate (fails later on the game folder, not on Steam)', async () => {
    game.testHooks.steam = up;
    await assert.rejects(game.play(playOpts()), /tlou-ii\.exe was not found/);
  });
  await T('play() with a failed probe gets past the gate', async () => {
    game.testHooks.steam = broken;
    await assert.rejects(game.play(playOpts()), /tlou-ii\.exe was not found/);
  });
  await T('UI wiring: Polish text exists, renderer polls the gate and blocks the button', async () => {
    const pl = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'i18n', 'pl.json'), 'utf8'));
    assert.ok(pl[game.STEAM_MSG] && pl[game.STEAM_MSG] !== game.STEAM_MSG);
    const app = require('./srcs').text('app');   // src/app.js + src/app/*.js
    assert.ok(/setInterval\(pollSteam, \d+\)/.test(app) && /steamDown && gameState === 'idle'[\s\S]{0,120}label: 'START STEAM', disabled: true/.test(app) && /b\.disabled = view\.disabled/.test(app));
  });
  console.log(`steam-gate-test: ${passed} passed`);
})();
