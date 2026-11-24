'use strict';
// node test/devswitch-test.js : the launcher owns the switch files in the game folder; every Play removes developer / test
// switches (t2r-dev-*, t2r-debug-* except t2r-debug-mode.txt, test / probe names, -try / -dev endings) and keeps player state
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { isDevSwitch, removeDevSwitches, syncFeatureFlags } = require('../lib/game/install');

const KEEP = [
  't2r-ach-seen.txt', 't2r-customize.txt', 't2r-defaults-applied.txt', 't2r-ext-boot.txt', 't2r-faction-guns.txt',
  't2r-floor-bake.txt', 't2r-freecam.txt', 't2r-intro-seen.txt', 't2r-loadout-names.txt', 't2r-loadout.txt',
  't2r-melee-duel.txt', 't2r-menu-scene.txt', 't2r-name.txt', 't2r-notice.txt', 't2r-rpc-state.txt', 't2r-sens.txt',
  't2r-settings.txt', 't2r-skills.txt', 't2r-version.txt', 't2r-debug-mode.txt', 't2r-linux.txt', 't2r-installing.txt',
  'README.txt', 'remap.txt',
];
const GONE = [
  't2r-armortest.txt', 't2r-dev-give.txt', 't2r-dev-down-self.txt', 't2r-debug-coins.txt', 't2r-armorprobe.txt',
  't2r-uc4-arm-try.txt', 'T2R-DEV-SAY.TXT', 't2r-skill-dev.txt', 't2r-test-weapon.txt',
];
let n = 0;
const tests = [];
const ok = (name, fn) => tests.push([name, fn]);

ok('player state and launcher-owned files are never a dev switch', () => {
  for (const k of KEEP) assert.ok(!isDevSwitch(k), k);
});
ok('dev / test switch names are', () => {
  for (const g of GONE) assert.ok(isDevSwitch(g), g);
});
ok('Play sync removes the dev switches and keeps everything else', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'devsw-'));
  const game = path.join(tmp, 'game'), client = path.join(tmp, 'client');
  fs.mkdirSync(game); fs.mkdirSync(client);
  for (const f of [...KEEP, ...GONE]) fs.writeFileSync(path.join(game, f), 'on');
  fs.writeFileSync(path.join(client, 't2r-faction-guns.txt'), 'on');
  return syncFeatureFlags(client, game).then(() => {
    for (const g of GONE) assert.ok(!fs.existsSync(path.join(game, g)), g);
    for (const k of KEEP.filter((k) => k !== 't2r-melee-duel.txt')) assert.ok(fs.existsSync(path.join(game, k)), k);
    fs.rmSync(tmp, { recursive: true, force: true });
  });
});
ok('a missing game folder does not throw', () => {
  assert.deepStrictEqual(removeDevSwitches(path.join(os.tmpdir(), 'no-such-dir-devsw')), []);
});
(async () => {
  for (const [name, fn] of tests) { await fn(); n++; console.log('  ok  ' + name); }
  console.log('devswitch-test: ' + n + ' passed');
})().catch((e) => { console.error(e); process.exit(1); });
