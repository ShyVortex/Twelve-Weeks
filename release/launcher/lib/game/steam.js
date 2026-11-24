/**
 * @file Steam gate, helper lifecycle, player name and start-failure reporting.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const health = require('../health');
const { run, exists } = require('./util');
const { cleanName } = require('./identity');
const { testHooks } = require('./state');
const { killSteamHelpers } = require('./processes');

// ---------------------------------------------------------------- Steam helper (Start-SteamHelper)
/**
 * Start the Steam helper in its own prefix.
 * @param {string} clientDir
 * @param {object} cfg
 * @param {object} server
 * @param {Function} log
 * @returns {Promise<object>}
 */
async function startSteamHelper(clientDir, cfg, server, log, deps = {}) {
  const exe = path.join(clientDir, 'steam', 't2r-steam.exe');
  if (!exists(exe)) return null;
  const sleep = deps.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const probe = deps.steamRunning || steamRunning;
  const spawnHelper = deps.spawn || spawn;
  const killHelpers = deps.kill || killSteamHelpers;
  const out = path.join(os.tmpdir(), 't2r-steam-name.txt');
  const tok = path.join(cfg.game_dir, 'tlou-ii-mp.json');
  const logf = path.join(os.tmpdir(), 't2r-steam.log');
  // Steam that was started after the launcher (or only just now) is a running process long before it is logged in: the helper's Steam
  // init fails and it exits at once. That failure is never remembered: it is retried while Steam is up (a few times, ~25 s), so the helper
  // comes up as soon as Steam is ready, without restarting the launcher.
  for (let attempt = 1; attempt <= 4; attempt++) {
    await killHelpers();
    try {
      fs.unlinkSync(out);
    } catch {}
    try {
      fs.renameSync(logf, path.join(os.tmpdir(), 't2r-steam.prev.log'));
    } catch {} // keep the previous run's helper log (the helper opens its log with "w"): a report after a relaunch still has the match
    const child = spawnHelper(
      exe,
      [out, 'tlou-ii.exe', '--server', server, '--token', tok, '--port', '7777', '--log', logf],
      {
        cwd: path.dirname(exe),
        windowsHide: true,
        detached: true,
        stdio: 'ignore',
      },
    );
    let exited = false;
    let code = null;
    child.on('exit', (c) => {
      exited = true;
      code = c;
    });
    child.on('error', () => {
      exited = true;
    });
    child.unref();
    for (let i = 0; i < 40 && !exists(out) && !exited; i++) await sleep(250);
    await sleep(200);
    if (exists(out)) {
      const n = cleanName(fs.readFileSync(out, 'utf8').split(/\r?\n/)[0]);
      return n || null;
    }
    if (!exited) return null; // still waiting for Steam (the helper keeps going)
    // 0.1.51: the exit code says why (a one-line helper log alone said nothing): 2 = SteamAPI_Init failed, 3 = steam_api64.dll missing / not loadable
    const why =
      code === 2
        ? 'Steam init failed'
        : code === 3
          ? 'steam_api64.dll could not be loaded'
          : 'exit code ' + code;
    if (attempt === 4 || !(await probe())) {
      log(`Steam helper exited at once (${why}; details in t2r-steam.log) - giving up.`);
      return null; // Steam is gone, or four tries failed
    }
    log(
      `Steam helper exited at once (${why}; details in t2r-steam.log) - trying again (${attempt}/3).`,
    );
    await sleep(4000);
  }
  return null;
}

// The game ended before a window ever showed: counted; the third one in an hour gets the "send a report" text instead of "try again".
/**
 * Classify a failed game start for user-facing diagnostics.
 * @param {string} healthFile
 * @param {boolean} plain
 * @returns {object}
 */
function startFailure(healthFile, plain) {
  const h = health.recordStartFailure(healthFile);
  return h.loop ? health.loopMessage(h.count) : plain;
}

// tests only: testHooks.steam = async () => ({ stdout, err }) replaces the Steam process probe
const STEAM_MSG = 'Start Steam first - Twelve Weeks needs Steam running';
/**
 * Check whether Steam is currently running.
 * @returns {boolean}
 */
async function steamRunning() {
  const r = testHooks.steam
    ? await testHooks.steam()
    : await run(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          "if (Get-Process steam -ErrorAction SilentlyContinue) { 'yes' }",
        ],
        { low: true },
      );
  return /yes/.test(r.stdout) || !!r.err; // a failed probe is not "Steam is down"
}

// Windows: Play needs Steam running (matchmaking). Linux: Play starts the game through Steam itself (it launches Steam), nothing to gate.
// A failed probe counts as running (steamRunning), so it never blocks.
/**
 * Decide whether Play must be blocked until Steam starts.
 * @param {string} [plat]
 * @returns {object}
 */
async function steamGate(plat = process.platform) {
  if (plat === 'linux') return { required: false, running: true };
  return { required: true, running: await steamRunning() };
}

/**
 * Resolve the player name from config, the game or Steam.
 * @param {object} cfg
 * @param {object} steam
 * @param {string} [plat]
 * @returns {Promise<{ok: boolean, name?: string, source?: string}>}
 */
function playerName(cfg, steam, plat = process.platform) {
  // in-game name file > launcher-set name > Steam name > system user
  const nf = path.join(cfg.game_dir, 't2r-name.txt');
  if (exists(nf)) {
    const ln = cleanName(fs.readFileSync(nf, 'utf8').split(/\r?\n/)[0] || '');
    if (ln) return { name: ln, source: 'custom' };
  }
  if (cfg.custom_name) {
    const c = cleanName(cfg.custom_name);
    if (c) return { name: c, source: 'custom' };
  }
  if (steam) return { name: steam, source: 'steam' };
  return {
    name: cleanName(os.userInfo().username) || 'Player',
    source: plat === 'linux' ? 'system' : 'windows',
  };
}

module.exports = {
  startSteamHelper,
  startFailure,
  STEAM_MSG,
  steamRunning,
  steamGate,
  playerName,
};
