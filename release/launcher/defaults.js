/**
 * @file Built-in server/update-host defaults and environment overrides.
 */
'use strict';
// Built-in defaults: everybody uses the official server and the official update host, nothing to set up in the UI.
// Stamp at build time:  node scripts/stamp-defaults.js <game host:port> <http://update host:port>   (the two constants below are rewritten in place)
// Dev / testing only (never in the UI): env F2_SERVER=host:port, F2_FILE_HOST=http://host:port, F2_CHANNEL=beta.
const OFFICIAL_SERVER = 'play.twelve-weeks.com:7001';
// The update server's two public addresses (0.1.46, lib/update/hosts.js): small requests go over HTTPS through Cloudflare, big files and
// clip uploads to fra1 directly (Cloudflare limits large files); each falls back to the other when a network filter blocks it (some ISP
// ActiveArmor blocked plain HTTP on :7002). While neither answers the launcher shows "update server unreachable" and Play still works.
const OFFICIAL_FILE_HOST = 'https://dl.twelve-weeks.com';
const OFFICIAL_DIRECT_HOST = 'http://play.twelve-weeks.com:7002';
// 0.1.49: the same server over HTTPS on 443, for filters that cut plain HTTP and the Cloudflare address
const OFFICIAL_TLS_HOST = 'https://play.twelve-weeks.com';
// 0.1.50: the same server by bare IP, the last try for filters that block the whole twelve-weeks.com domain
const OFFICIAL_IP_HOST = 'http://46.101.255.94:7002';
// Testing server (Settings > Game > SWITCH TO TESTING SERVER): fixed pair, not touched by stamp-defaults.js.
const TEST_SERVER = 'play.twelve-weeks.com:7101';
const TEST_FILE_HOST = 'http://play.twelve-weeks.com:7102';
const OFFICIAL_CHANNEL = 'stable';

module.exports = {
  OFFICIAL_SERVER,
  OFFICIAL_FILE_HOST,
  OFFICIAL_DIRECT_HOST,
  OFFICIAL_TLS_HOST,
  OFFICIAL_IP_HOST,
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
