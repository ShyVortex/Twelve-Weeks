/**
 * @file Resolve client, portable, user-data and generated-data paths.
 */
'use strict';

const path = require('path');
const game = require('../lib/game');
const upd = require('../lib/update');
const defaults = require('../defaults');
const install = require('./install');

/**
 * Resolve all launcher paths from the runtime and configuration.
 * @param {{ app: object, runtime: object, config: object }} options
 * @returns {object} Path helpers for client, portable, user-data and generated data.
 */
function createPaths({ app, runtime, config }) {
  function portableDir() {
    // installed layout: the folder the old portable exe sat in (its client\ folder), else the fixed root
    if (runtime.installRoot)
      return install.rememberedPortableDir(runtime.installRoot) || runtime.installRoot;
    return (
      process.env.PORTABLE_EXECUTABLE_DIR ||
      (process.env.APPIMAGE ? path.dirname(process.env.APPIMAGE) : path.dirname(process.execPath))
    );
  }

  function clientDir() {
    // a client folder that is the game folder is never used (the slim rebuild would overwrite the client's own winmm.dll: R-VW4C)
    if (
      config.values.client_dir &&
      !game.sameLocation(config.values.client_dir, config.values.game_dir)
    )
      return config.values.client_dir;
    const side = path.join(portableDir(), 'client');
    if (app.isPackaged && game.exists(path.join(side, 'winmm.dll'))) return side;
    return path.join(runtime.userData, 'client');
  }

  function serverAddress() {
    return defaults.server(config.values.server_target);
  }

  function fileHost() {
    return defaults.fileHost(config.values.server_target);
  }

  function channel() {
    return defaults.channel();
  }

  async function getManifest(host, retries = 0) {
    if (runtime.isLinux) {
      try {
        return await upd.fetchManifest(host, `${channel()}-linux`, { retries });
      } catch (e) {
        if (!/HTTP 404|no such channel/i.test(String(e.message))) throw e;
      }
    }
    return upd.fetchManifest(host, channel(), { retries });
  }

  return { portableDir, clientDir, serverAddress, fileHost, channel, getManifest };
}

module.exports = { createPaths };
