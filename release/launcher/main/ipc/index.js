/**
 * @file Register all IPC handlers with their main-process dependencies.
 */
'use strict';

const { ipcMain } = require('electron');
const configIpc = require('./config');
const gameIpc = require('./game');
const reportIpc = require('./report');
const clanIpc = require('./clan');
const socialIpc = require('./social');
const updateIpc = require('./update');
const loadoutIpc = require('./loadout');
const mapsIpc = require('./maps');
const steamIpc = require('./steam');
const rpcIpc = require('./rpc');

/**
 * Register every IPC handler with its main-process dependencies.
 * @param {object} dependencies
 * @returns {void}
 */
function registerIpc(dependencies) {
  const { locale, log } = dependencies;
  const I18N = locale.I18N;
  const strings = locale.load();

  ipcMain.handle('i18n:get', () => strings);

  const handle = (channel, fn) =>
    ipcMain.handle(channel, async (_event, ...args) => {
      try {
        return { ok: true, ...(await fn(...args)) };
      } catch (e) {
        log(`ERROR: ${e.message}`);
        return { ok: false, error: I18N.T(e.message, e.vars) };
      }
    });

  configIpc.register(handle, dependencies);
  gameIpc.register(handle, dependencies);
  reportIpc.register(handle, dependencies);
  clanIpc.register(handle, dependencies);
  socialIpc.register(handle, dependencies);
  updateIpc.register(handle, dependencies);
  loadoutIpc.register(handle, dependencies);
  mapsIpc.register(handle, dependencies);
  steamIpc.register(handle, dependencies);
  rpcIpc.register(handle);
}

module.exports = { registerIpc };
