/**
 * @file Main configuration for the launcher
 */
'use strict';

const fs = require('fs');
const path = require('path');
const game = require('../lib/game');
const { isOutsideTemp } = require('./env');

const DEFAULTSETTINGS = {
  game_dir: '',
  token_id: '',
  custom_name: '',
  client_dir: '',
  p1_tester: false, // opt-in (or an empty t2r-playtest.txt in the game folder): the Part I download from the update server
  tlou1_dir: '', // The Last of Us Part I install (Part I maps are a DLC pulled from it)
  theme: 'wlf',
  effects: { grain: true, motion: true },
  background: 'seattle-falls',
  volume: 70,
  sounds: true,
  music: true,
  musicVolume: 35,
  debug_mode: false,
  sp_mode: false,
  loadout: null,
  loadout2: null,
  loadout_rev: undefined,
  loadout_game_rev: 0,
  win: null,
  lang: null,
  id_adopted: false,
  server_target: 'live', // 'live' | 'test' (Settings > Game > testing server switch)
  // Discord Rich Presence (lib/rpc, Settings > Game switch): provider 'discord' | null (off). rpc.discord.clientId may override the
  // built-in application id (lib/rpc/discord.js); it is not written by default, so a later change of the built-in id reaches every install.
  rpc: { provider: 'discord' },
};

/**
 * Create the persistent configuration store.
 * @param {{ runtime: object, log: Function }} options
 * @returns {object} Store with load/save/resolve helpers.
 */
function createConfigStore({ runtime, log }) {
  let values = { ...DEFAULTSETTINGS };

  function load() {
    try {
      values = {
        ...DEFAULTSETTINGS,
        ...JSON.parse(fs.readFileSync(runtime.cfgFile, 'utf8')),
      };
    } catch {
      values = { ...DEFAULTSETTINGS };
    }
    values.effects = { ...DEFAULTSETTINGS.effects, ...(values.effects || {}) };
    values.rpc = {
      ...DEFAULTSETTINGS.rpc,
      ...(values.rpc && typeof values.rpc === 'object' ? values.rpc : {}),
    };

    for (const key of ['server', 'file_host', 'channel']) delete values[key];
    if (values.server_target !== 'test') values.server_target = 'live';

    if (!/^[0-9a-f]{24}$/.test(values.token_id)) values.token_id = game.newTokenId();

    const tempPrefix = runtime.tmpDirLower;
    if (
      values.game_dir &&
      (!game.isGameDir(values.game_dir) ||
        values.game_dir.toLowerCase().startsWith(tempPrefix) ||
        /[\\/]appdata[\\/]local[\\/]temp[\\/]/i.test(values.game_dir)) &&
      !runtime.hasUserDataEnv
    ) {
      values.game_dir = '';
    }
    return values;
  }

  function save() {
    fs.mkdirSync(runtime.userData, { recursive: true });
    fs.writeFileSync(runtime.cfgFile, JSON.stringify(values, null, 2));
  }

  function adoptIdentity() {
    if (values.id_adopted || !game.isGameDir(values.game_dir)) return;
    let id = null;
    try {
      const token = JSON.parse(
        fs.readFileSync(path.join(values.game_dir, 'tlou-ii-mp.json'), 'utf8'),
      ).token;
      if (game.tokenName(token) !== null) id = token.slice(40);
    } catch {
      /* no existing identity */
    }
    if (id && /^[0-9a-f]{24}$/.test(id)) {
      values.token_id = id;
      log('Adopted the player id of the existing install.');
    }
    values.id_adopted = true;
    save();
  }

  function writesBlocked() {
    return runtime.isTest && isOutsideTemp(values.game_dir, runtime.tmpDir);
  }

  function applyPatch(patch) {
    for (const key of Object.keys(patch || {})) {
      if (!(key in DEFAULTSETTINGS) || key === 'token_id' || key === 'sp_mode') continue;
      if (key === 'server_target' && patch[key] !== 'live' && patch[key] !== 'test') continue;
      values[key] =
        key === 'effects' || key === 'rpc' ? { ...values[key], ...patch[key] } : patch[key];
    }
  }

  return {
    get values() {
      return values;
    },
    load,
    save,
    adoptIdentity,
    writesBlocked,
    applyPatch,
  };
}

module.exports = { createConfigStore, DEFAULTSETTINGS };
