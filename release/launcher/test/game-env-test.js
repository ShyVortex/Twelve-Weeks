'use strict';
// The game must not inherit the Steam shortcut's environment (SteamAppId / SteamGameId of the launcher's shortcut).
const assert = require('assert');
const { gameEnv } = require('../lib/game/play');
const env = gameEnv({ PATH: 'C:/x', SteamAppId: '0', SteamGameId: '10758096580427317248', SteamOverlayGameId: '1', SteamClientLaunch: '1', SteamEnv: '1', USERPROFILE: 'u', STEAM_COMPAT_DATA_PATH: 'p' });
assert.deepStrictEqual(env, { PATH: 'C:/x', USERPROFILE: 'u' });
console.log('game-env-test ok');
