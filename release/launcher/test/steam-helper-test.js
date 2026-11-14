'use strict';
// node test/steam-helper-test.js : the Steam helper start retries while Steam is up but not ready (Steam started after the launcher); a failure is never remembered.
const fs = require('fs'),
  os = require('os'),
  path = require('path'),
  assert = require('assert'),
  { EventEmitter } = require('events');
const { startSteamHelper } = require('../lib/game/steam');

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'f2-helper-'));
  fs.mkdirSync(path.join(dir, 'steam'));
  fs.writeFileSync(path.join(dir, 'steam', 't2r-steam.exe'), 'x');
  const out = path.join(os.tmpdir(), 't2r-steam-name.txt');
  const mk = (failures, steamUp = true) => {
    let n = 0,
      kills = 0;
    const deps = {
      sleep: () => new Promise((r) => setImmediate(r)),
      steamRunning: async () => steamUp,
      kill: async () => kills++,
      spawn: () => {
        const c = new EventEmitter();
        c.unref = () => {};
        n++;
        if (n <= failures) setImmediate(() => c.emit('exit', 1)); // Steam not ready: the helper dies at once
        else fs.writeFileSync(out, 'Tester\n');
        return c;
      },
    };
    return { deps, count: () => [n, kills] };
  };
  const cfg = { game_dir: dir };
  const log = () => {};
  // ready at once
  let t = mk(0);
  assert.strictEqual(await startSteamHelper(dir, cfg, 's:1', log, t.deps), 'Tester');
  assert.deepStrictEqual(t.count(), [1, 1]);
  // Steam only comes up during the 3rd start: still works without a restart of anything
  t = mk(2);
  assert.strictEqual(await startSteamHelper(dir, cfg, 's:1', log, t.deps), 'Tester');
  assert.deepStrictEqual(t.count(), [3, 3]);
  // Steam gone: no retry loop
  t = mk(9, false);
  assert.strictEqual(await startSteamHelper(dir, cfg, 's:1', log, t.deps), null);
  assert.strictEqual(t.count()[0], 1);
  // never ready: gives up after 4 starts
  t = mk(9);
  assert.strictEqual(await startSteamHelper(dir, cfg, 's:1', log, t.deps), null);
  assert.strictEqual(t.count()[0], 4);
  try {
    fs.unlinkSync(out);
  } catch {}
  console.log('steam-helper-test OK');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
