/**
 * @file Single-player/multiplayer mode state shared by IPC and Play.
 */
'use strict';

const game = require('../lib/game');

/**
 * Create the shared SP/MP mode state.
 * @param {{ config: object, log: Function }} options
 * @returns {object} Mode API with read/switch/apply helpers.
 */
function createMode({ config, log }) {
  function current() {
    const active = game.spModeFor(config.values.game_dir, config.values.sp_mode);
    if (active !== !!config.values.sp_mode) {
      config.values.sp_mode = active;
      try {
        config.save();
      } catch (e) {
        log(`Could not save single-player mode: ${e.message}`);
      }
    }
    return active;
  }

  function sync() {
    return current();
  }

  function info() {
    const folder = config.values.game_dir ? game.spmode.disabledDir(config.values.game_dir) : '';
    return { sp: current(), folder, dirName: game.spmode.DIR_NAME };
  }

  return { current, sync, info };
}

module.exports = { createMode };
