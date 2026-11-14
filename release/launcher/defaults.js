/**
 * @file Built-in server/update-host defaults and environment overrides.
 */
'use strict';
// Built-in defaults: everybody uses the official server and the official update host, nothing to set up in the UI.
// Stamp at build time:  node scripts/stamp-defaults.js <game host:port> <http://update host:port>   (the two constants below are rewritten in place)
// Dev / testing only (never in the UI): env F2_SERVER=host:port, F2_FILE_HOST=http://host:port, F2_CHANNEL=beta.
const OFFICIAL_SERVER = 'play.twelve-weeks.com:7001';
// TODO: the update server (tools/update_server/server.py, local port 7002) needs its own TCP playit tunnel; put its public address here.
// Until it is reachable the launcher shows "update server unreachable" and Play still works with the installed client.
const OFFICIAL_FILE_HOST = 'http://play.twelve-weeks.com:7002';
// Testing server (Settings > Game > SWITCH TO TESTING SERVER): fixed pair, not touched by stamp-defaults.js.
const TEST_SERVER = 'play.twelve-weeks.com:7101';
const TEST_FILE_HOST = 'http://play.twelve-weeks.com:7102';
const OFFICIAL_CHANNEL = 'stable';

module.exports = {
  OFFICIAL_SERVER,
  OFFICIAL_FILE_HOST,
  OFFICIAL_CHANNEL,
  TEST_SERVER,
  TEST_FILE_HOST,
  // target: 'live' (default) or 'test'; the F2_* env overrides always win
  server: (target) =>
    (process.env.F2_SERVER || (target === 'test' ? TEST_SERVER : OFFICIAL_SERVER)).trim(),
  fileHost: (target) =>
    (process.env.F2_FILE_HOST || (target === 'test' ? TEST_FILE_HOST : OFFICIAL_FILE_HOST))
      .trim()
      .replace(/\/+$/, ''),
  channel: () => process.env.F2_CHANNEL || OFFICIAL_CHANNEL,
  appStart: () => Date.now(),
};
