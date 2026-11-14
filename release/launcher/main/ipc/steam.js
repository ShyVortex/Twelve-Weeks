/**
 * @file IPC handlers for the ADD TO STEAM button (lib/steam-shortcut.js).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const install = require('../install');
const steam = require('../../lib/steam-shortcut');

/**
 * Register the Steam shortcut handlers.
 * @param {Function} handle
 * @param {object} deps
 * @returns {void}
 */
function register(handle, { app, log, rootDir }) {
  const dir = rootDir || path.join(__dirname, '..', '..');
  const target = () => {
    const root = install.installRoot();
    const exe = steam.launcherExe({
      root,
      rootExe: install.ROOT_NAME + '.exe',
      execPath: app.getPath('exe'),
    });
    const ico = path.join(root, 'icon.ico');
    return { exe, startDir: path.dirname(exe), icon: fs.existsSync(ico) ? ico : '' };
  };

  // what the button needs: is Steam there, is the shortcut already in it, is Steam running.
  // light = the idle re-check: shortcuts.vdf only, no process probe.
  handle('steam:state', async (light) => {
    const steamDir = await steam.findSteamDir();
    if (!steamDir) return { found: false, running: false, added: false };
    const added = steam.isAdded({ steamDir, exe: target().exe });
    return { found: true, added, running: light ? false : await steam.steamRunning() };
  });

  // Steam rewrites shortcuts.vdf when it exits: while it runs, the player agreed (restart) to have it asked to quit
  // (never killed) and started again afterwards.
  const whileSteamStopped = async (restart, job) => {
    const steamDir = await steam.findSteamDir();
    if (!steamDir) return { result: 'notfound' };
    const running = await steam.steamRunning();
    if (running) {
      if (!restart) return { result: 'running' };
      log('steam: asking Steam to quit');
      if (!(await steam.quitSteam({ steamDir }))) return { result: 'stuck' };
    }
    try {
      const r = job(steamDir);
      if (running) steam.startSteam(steamDir);
      return { ...r, restarted: running };
    } catch (e) {
      if (running) steam.startSteam(steamDir);
      if (e && e.code === 'no-user') return { result: 'nouser' };
      throw e;
    }
  };

  handle('steam:add', (restart) =>
    whileSteamStopped(restart, (steamDir) => {
      const r = steam.addToSteam({
        steamDir,
        ...target(),
        artDir: path.join(dir, 'assets', 'steam'),
        log,
      });
      return { result: r.created ? 'added' : 'updated' };
    }),
  );

  handle('steam:remove', (restart) =>
    whileSteamStopped(restart, (steamDir) => {
      steam.removeFromSteam({ steamDir, exe: target().exe, log });
      return { result: 'removed' };
    }),
  );
}

module.exports = { register };
