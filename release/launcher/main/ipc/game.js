/**
 * @file IPC handlers for game detection, Play, update and SP/MP switching.
 */
'use strict';

const path = require('path');
const { dialog } = require('electron');
const game = require('../../lib/game');

/**
 * Register game, Play, update and SP/MP IPC handlers.
 * @param {Function} handle
 * @param {object} deps
 * @returns {void}
 */
function register(
  handle,
  { runtime, config, paths, player, status, mode, jobs, send, getWindow, log },
) {
  handle('game:detect', async () => {
    const dirs = await game.findGameDirs();
    if (!game.isGameDir(config.values.game_dir) && dirs.length) {
      config.values.game_dir =
        dirs.find((dir) => /Last of Us/i.test(path.basename(dir))) || dirs[0];
      config.save();
    }
    config.adoptIdentity();
    return {
      dirs,
      current: config.values.game_dir,
      ok: game.isGameDir(config.values.game_dir),
    };
  });

  handle('game:pick', async () => {
    const picked = await dialog.showOpenDialog(getWindow(), {
      title: 'Select the folder that contains tlou-ii.exe',
      properties: ['openDirectory'],
    });
    if (picked.canceled || !picked.filePaths[0]) return { picked: false };
    const dir = picked.filePaths[0];
    if (!game.isGameDir(dir)) throw new Error('tlou-ii.exe is not in that folder.');
    config.values.game_dir = dir;
    config.save();
    config.adoptIdentity();
    return { picked: true, dir };
  });

  handle('steam:status', async () => ({
    ...(await game.steamGate()),
    message: game.STEAM_MSG,
  }));
  handle('game:running', async () => ({ ...(await game.gameStatus()) }));
  handle('state:check', async () => ({ state: await status.checkState() }));
  handle('players:roster', async () => await status.roster());
  handle('server:status', async () => ({ status: await status.serverStatus() }));
  handle('player:name', async () => await player.resolveName());
  handle('sp:status', async () => mode.info());
  handle('sp:switch', (to) => jobs.switchMode(to === 'sp' ? 'sp' : 'mp'));

  handle('game:reinstall', async () => {
    if (!game.isGameDir(config.values.game_dir)) throw new Error('Game folder not set.');
    if (mode.current())
      throw new Error(
        'The launcher is in single-player mode: the mod is not installed. Press SWITCH TO MP first.',
      );
    if (process.env.F2_SHOT || process.env.F2_NO_GAME)
      throw new Error('Disabled in test / screenshot mode.');
    if (config.writesBlocked())
      throw new Error('Test mode: re-install only runs against a game folder inside the temp dir.');
    if (await game.gameRunning()) throw new Error('Close the game first.');
    config.adoptIdentity();
    await game.installMod(
      paths.clientDir(),
      config.values,
      log,
      (progress) => send('progress', progress),
      null,
      { userData: runtime.userData },
    );
    log('Mod files re-installed.');
    return {};
  });
}

module.exports = { register };
