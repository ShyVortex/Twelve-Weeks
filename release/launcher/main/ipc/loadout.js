/**
 * @file IPC handlers for loadout read/write and synchronization.
 */
'use strict';

const game = require('../../lib/game');
const lof = require('../../lib/loadoutfile');
const gameData = require('../gamedata');

/**
 * Register loadout IPC handlers.
 * @param {Function} handle
 * @param {{config: object, mode: object, log: Function}} deps
 * @returns {void}
 */
function register(handle, { config, mode, log }) {
  const loadoutDir = () =>
    game.isGameDir(config.values.game_dir) && !mode.current() ? config.values.game_dir : '';
  let loadoutError;

  const writeLoadout = (loadout) => {
    const dir = loadoutDir();
    const data = gameData();
    if (!dir || config.writesBlocked()) return false;
    const rev = lof.nextRev(config.values.loadout_rev);
    const { over } = lof.writeLauncher(data, dir, loadout, rev);
    config.values.loadout_rev = rev;
    config.save();
    log(`Loadouts written for the game (rev ${rev}).`);
    if (over.length)
      log(
        `Custom loadout(s) ${over.join(', ')} over ${data.lpMax} Loadout Points - the game keeps those as they were.`,
      );
    return true;
  };

  handle('loadout:save', async (loadout) => {
    config.values.loadout2 = loadout;
    config.save();
    let status = 'nogame';
    try {
      if (writeLoadout(loadout)) status = 'pending';
    } catch (e) {
      log(`Loadout file not written: ${e.message}`);
      status = 'error';
    }
    return { status };
  });

  handle('loadout:sync', async () => {
    const dir = loadoutDir();
    const data = gameData();
    if (!data.weapons) return { status: 'nogame', adopt: null };
    const state = lof.syncStep(data, dir, config.values);
    if (state.error !== loadoutError) {
      loadoutError = state.error;
      if (state.error)
        log(
          `Game loadout file t2r-loadout.json is ${state.error} - keeping the launcher's own copy until the game rewrites it.`,
        );
    }
    let status = state.status;
    if (state.write) {
      try {
        if (!writeLoadout(config.values.loadout2)) status = 'nogame';
      } catch (e) {
        log(`Loadout file not written: ${e.message}`);
        status = 'error';
      }
    }
    if (state.adopt) {
      config.values.loadout2 = state.adopt;
      if (config.values.loadout_rev === undefined) config.values.loadout_rev = 0;
    }
    if (state.adopt || Object.keys(state.patch).length) {
      Object.assign(config.values, state.patch);
      config.save();
    }
    if (state.adopt && state.problems.length) log(`Game loadouts: ${state.problems.join('; ')}`);
    return { status, adopt: state.adopt };
  });
}

module.exports = { register };
