// Dev harness: the launcher's real presence chain (presence.js + the Discord adapter) watching one game folder, without the UI.
// It logs every card Discord accepted (the SET_ACTIVITY reply) and clears the card when no tlou-ii.exe runs from that folder any more,
// as the launcher does when its game poll sees the game gone.
//   node dev/rpc-watch.js <game_dir> <log.jsonl> [max minutes]
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { createDiscordAdapter } = require('../lib/rpc/discord');
const service = require('../lib/rpc/service');
const presence = require('../lib/rpc/presence');

const dir = process.argv[2];
const out = process.argv[3];
const maxMs = (parseFloat(process.argv[4]) || 60) * 60000;
const log = (m) =>
  fs.appendFileSync(out, JSON.stringify({ t: new Date().toISOString(), ...m }) + '\n');

function gameUp() {
  try {
    const r = execFileSync(
      'powershell',
      [
        '-NoProfile',
        '-Command',
        '(Get-CimInstance Win32_Process -Filter "Name=\'tlou-ii.exe\'").ExecutablePath',
      ],
      {
        encoding: 'utf8',
        windowsHide: true,
      },
    );
    return r
      .split(/\r?\n/)
      .some(
        (p) =>
          p &&
          path.resolve(path.dirname(p.trim())).toLowerCase() === path.resolve(dir).toLowerCase(),
      );
  } catch {
    return false;
  }
}

(async () => {
  const adapter = createDiscordAdapter({
    config: { values: {} },
    log: (m) => log({ adapter: m }),
    player: {},
  });
  const set0 = adapter.setActivity;
  adapter.setActivity = async (a) => {
    log({ set: a });
    return set0(a);
  };
  service.mount(adapter);
  presence.init({ values: { game_dir: dir } });
  presence.started(dir);
  log({ started: dir });
  const t0 = Date.now();
  let seen = false,
    misses = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000));
    const up = gameUp();
    if (up) seen = true;
    // three misses in a row (15 s, like the launcher's game poll): one failed process query under memory load is not a closed game
    misses = up ? 0 : misses + 1;
    const gone = seen && misses >= 3;
    if (gone || Date.now() - t0 > maxMs) {
      await presence.ended();
      log({ ended: gone ? 'game closed' : 'time limit', cleared: true });
      await service.destroy();
      process.exit(0);
    }
  }
})().catch((e) => {
  log({ error: e.message });
  process.exit(1);
});
