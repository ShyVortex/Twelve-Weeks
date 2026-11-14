/**
 * @file IPC handlers for configuration, info, locale and window actions.
 */
'use strict';

const fs = require('fs');
const { dialog, shell } = require('electron');
const sysinfo = require('../../lib/sysinfo');
const { createRpcService } = require('../../lib/rpc/index');
const rpcService = require('../../lib/rpc/service');

/**
 * Register config/info/locale/window IPC handlers.
 * @param {Function} handle
 * @param {object} deps
 * @returns {void}
 */
function register(
  handle,
  { app, runtime, config, paths, mode, player, locale, log, getWindow, ban },
) {
  handle('cfg:get', async () => {
    let name = null;
    try {
      name = await player.resolveName();
    } catch {
      /* the name in use (Settings field shows it) */
    }
    return {
      ...config.values,
      token_id: undefined,
      loadout: undefined,
      sp_mode: mode.current(),
      resolved: {
        server: paths.serverAddress(),
        fileHost: paths.fileHost(),
        clientDir: paths.clientDir(),
        lang: locale.langNow(),
        name: name ? name.name : '',
        nameSource: name ? name.source : '',
      },
    };
  });

  handle('cfg:set', async (patch) => {
    config.applyPatch(patch);
    if ('custom_name' in (patch || {}) && config.values.custom_name)
      player.writeNameFile(config.values.custom_name);
    if ('lang' in (patch || {})) locale.setLang(locale.langNow());
    config.save();
    // the Discord Rich Presence switch takes effect at once: the old adapter closes its pipe (Discord drops its activity), the new one
    // (or the no-op one when switched off) is mounted; the renderer re-sends the current screen afterwards
    if ('rpc' in (patch || {})) {
      await Promise.race([rpcService.destroy().catch(() => {}), new Promise((r) => setTimeout(r, 1500))]);
      rpcService.mount(createRpcService(config, log, player));
    }
    return {
      resolved: {
        server: paths.serverAddress(),
        fileHost: paths.fileHost(),
        clientDir: paths.clientDir(),
      },
    };
  });

  handle('app:info', () => ({
    version: runtime.launcherVersion,
    buildDate: runtime.buildDate,
    hardware: sysinfo.hardware(),
    packaged: app.isPackaged,
    logDir: runtime.logDir,
    userData: runtime.userData,
    electron: process.versions.electron,
  }));

  handle('dir:pick', async (title) => {
    const picked = await dialog.showOpenDialog(getWindow(), {
      title: title || 'Select folder',
      properties: ['openDirectory', 'createDirectory'],
    });
    return picked.canceled ? { picked: false } : { picked: true, dir: picked.filePaths[0] };
  });

  handle('open:path', async (what) => {
    const target = {
      logs: runtime.logDir,
      game: config.values.game_dir,
      client: paths.clientDir(),
      data: runtime.userData,
    }[what];
    if (!target) throw new Error('Unknown folder');
    fs.mkdirSync(target, { recursive: true });
    const error = await shell.openPath(target);
    if (error) throw new Error(error);
    return {};
  });

  handle('app:log', (message) => {
    log(String(message).slice(0, 2000));
  });

  handle('open:url', (url) => {
    if (ban && ban.current().banned && /discord/i.test(String(url))) return; // no Discord links for a banned player
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
  });

  handle('win:ctl', (what) => {
    const window = getWindow();
    if (!window) return;
    if (what === 'min') window.minimize();
    else if (what === 'close') window.close();
  });
}

module.exports = { register };
