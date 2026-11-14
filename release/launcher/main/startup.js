/**
 * @file Startup work on the game folder: recover interrupted SP/MP switches, top up SP mode.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const game = require('../lib/game');

/**
 * Undo an interrupted SP/MP switch when the launcher starts.
 * @param {{ config: object, log: Function }} options
 * @returns {void}
 */
function recoverInterruptedWork({ config, log }) {
  if (game.isGameDir(config.values.game_dir) && !config.writesBlocked()) {
    try {
      const recovered = game.spmode.recover(config.values.game_dir);
      if (recovered.recovered) log('An unfinished SWITCH TO SP / MP was undone.');
      else if (recovered.failed)
        log(`Unfinished switch could not be undone: ${recovered.failed.join('; ')}`);
    } catch (e) {
      log(`Could not recover single-player mode: ${e.message}`);
    }
  }
}

/**
 * Park base-mod leftovers of an install that is already in SP mode; no waiting, no error shown.
 * @param {{ config: object, log: Function }} options
 * @returns {Promise<void>}
 */
async function topUpSingleplayer({ config, log }) {
  if (!game.isGameDir(config.values.game_dir) || config.writesBlocked()) return;
  try {
    const topped = await game.spTopUp(config.values.game_dir);
    if (topped.moved)
      log(
        `SP mode: ${topped.moved} leftover base-mod entries moved to ${game.spmode.disabledDir(config.values.game_dir)} (${topped.files.join(', ')})`,
      );
  } catch (e) {
    log(`SP top-up: ${e.message}`);
  }
}

/**
 * A saved client folder that IS the game folder: t2r-slim rebuilt the client's winmm.dll in place on every install, so each start
 * downloaded the slim file over the game's winmm.dll again (hash differs) and the mod never loaded. Clear the setting and force one rebuild.
 * @param {{ config: object, log: Function }} options
 * @returns {boolean} true when the setting was cleared
 */
function healClientDir({ config, log }) {
  const v = config.values;
  if (!v.client_dir || !v.game_dir || config.writesBlocked()) return false;
  if (!game.sameLocation(v.client_dir, v.game_dir)) return false;
  log(
    `Client folder setting pointed at the game folder (${v.client_dir}): reset to the default; the mod is rebuilt on the next Play.`,
  );
  v.client_dir = '';
  try {
    config.save();
  } catch (e) {
    log(`Could not save the settings: ${e.message}`);
  }
  try {
    fs.unlinkSync(path.join(v.game_dir, 't2r-version.txt')); // the winmm.dll there is the hollow slim file: not "current"
  } catch {}
  return true;
}

module.exports = { recoverInterruptedWork, topUpSingleplayer, healClientDir };
