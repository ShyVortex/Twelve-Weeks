/**
 * @file Ownership-aware presence facade.
 *
 * Sits in front of the RPC service and decides whether the launcher may set
 * presence right now, or must stay silent because the mod (or the vanilla game)
 * owns it. See ./owner.js for the signal file contract.
 */
'use strict';

const rpcService = require('./service');
const owner = require('./owner');
const ingame = require('./ingame');
const I18N = require('../../src/i18n-core');

const POLL_MS = 3000;
// Discord takes about 5 activity updates per 20 s; stay well under it: a changed
// card goes out at most every UPDATE_MS, a new screen (match start, death, post
// match) after FLOW_MS.
const UPDATE_MS = 15000;
const FLOW_MS = 4000;

let config = null;
let gameDir = null;
let gameRunning = false;
let handedOff = false;
let timer = null;
// in-game card: what was sent last and when, and the launch time (older state files are leftovers)
let live = { sig: null, st: null, at: 0, since: 0 };

/**
 * Remember the config store so the current game folder is always available.
 * @param {object} cfg
 * @returns {void}
 */
function init(cfg) {
  config = cfg;
}

/**
 * Game folder the ownership file lives in.
 * @returns {string|null}
 */
function dir() {
  return gameDir || (config && config.values.game_dir) || null;
}

function stopWatch() {
  if (timer) clearInterval(timer);
  timer = null;
}

/**
 * While the game runs, watch the owner file: when the mod claims it, clear the
 * launcher's activity once and stay silent.
 * @returns {Promise<void>}
 */
async function checkOwner() {
  if (!gameRunning) return;
  if (owner.read(dir()) === 'launcher') {
    handedOff = false;
    await checkIngame();
    return;
  }
  if (!handedOff) {
    handedOff = true;
    await rpcService.clear();
  }
}

/**
 * The mod's state file -> the in-game card, rate limited. Nothing is sent while the
 * file is missing (old ext, still at the boat screen): the launch card stays.
 * @param {number} [now]
 * @returns {Promise<void>}
 */
async function checkIngame(now) {
  const t = now || Date.now();
  const s = ingame.read(dir(), live.since, t);
  if (!s) return;
  const a = ingame.build(s, I18N.T);
  // menus / lobby count from the launch; a match from its own start (t0 in the state file)
  if (!a.timestamps && live.since) a.timestamps = { start: Math.floor(live.since / 1000) };
  const sig = ingame.signature(a);
  if (sig === live.sig) return;
  const gap = t - live.at;
  if (gap < (s.st !== live.st ? FLOW_MS : UPDATE_MS)) return; // the next poll sends it
  live = { sig, st: s.st, at: t, since: live.since };
  await rpcService.setActivity(a);
}

/** @returns {boolean} the mod's in-game card is showing */
function ingameShowing() {
  return !!live.sig;
}

function startWatch() {
  if (timer) return;
  timer = setInterval(() => {
    checkOwner().catch(() => {
      /* presence must never break the game flow */
    });
  }, POLL_MS);
  if (timer.unref) timer.unref();
}

/**
 * Menu/UI presence (main menu, news, loadout, ...). Ignored while the game runs
 * and while the mod owns presence.
 * @param {import('./noop.js').RpcActivity} activity
 * @returns {Promise<void>}
 */
async function menu(activity) {
  if (gameRunning) return; // the game owns the screen
  // Outside a game session `off`/`launcher` are the only meaningful values and
  // both mean "the launcher may show the menu": a stale `off` left by a crash
  // must not silence the launcher forever. `mod` is still respected, because the
  // game may have been started outside the launcher.
  if (owner.read(dir()) === 'mod') {
    if (!handedOff) {
      handedOff = true;
      await rpcService.clear();
    }
    return;
  }
  handedOff = false;
  owner.write(dir(), 'launcher');
  await rpcService.setActivity(activity);
}

/**
 * Multiplayer launch: show the launcher's in-game status until the mod claims
 * ownership, at which point the watcher clears it.
 * @param {import('./noop.js').RpcActivity} activity
 * @returns {Promise<void>}
 */
async function game(activity) {
  if (owner.read(dir()) !== 'launcher') {
    handedOff = true;
    await rpcService.clear();
    return;
  }
  handedOff = false;
  if (ingameShowing()) return; // the game's own card is already up
  await rpcService.setActivity(activity);
}

/**
 * Vanilla launch (single player): hand presence to the game immediately.
 * @returns {Promise<void>}
 */
async function vanilla() {
  // PLAY SINGLEPLAYER never writes into the game folder (lib/game/play.js), so no `off` is written here: the launcher only clears its
  // own activity and stays silent until ended() (menu() is ignored while the game runs).
  handedOff = true;
  await rpcService.clear();
}

/**
 * Mark the game as running and start watching the ownership file.
 * @param {string} [dirPath]
 * @returns {void}
 */
function started(dirPath) {
  if (dirPath) gameDir = dirPath;
  gameRunning = true;
  handedOff = false;
  live = { sig: null, st: null, at: 0, since: Date.now() };
  startWatch();
}

/**
 * Game exited (or a launch failed): stop watching, give ownership back to the
 * launcher and clear the stale in-game activity. The renderer re-sets the
 * current screen afterwards.
 * @returns {Promise<void>}
 */
async function ended() {
  const current = dir();
  gameRunning = false;
  gameDir = null;
  stopWatch();
  handedOff = false;
  live = { sig: null, st: null, at: 0, since: 0 };
  owner.write(current, 'launcher');
  await rpcService.clear();
}

/**
 * Stop watching without touching presence (launcher quit).
 * @returns {void}
 */
function stop() {
  gameRunning = false;
  gameDir = null;
  stopWatch();
}

module.exports = {
  init,
  menu,
  game,
  vanilla,
  started,
  ended,
  stop,
  checkIngame,
  _live: () => live,
};
