/**
 * @file Keeps the last good update/server answer over short failures on a flaky link.
 */
'use strict';
// A flaky link to the update server / game server (e.g. "update server unreachable" -> "up to date" -> "unreachable" every 10 s, the
// player count flipping between a dash and a number: one check in three timed out through the tunnel relay) must not flip what the player
// sees. The last GOOD answer is kept and shown while the next failures stay under `maxFails` in a row and the good one is not older than
// `maxAgeMs`; a real outage (3 failures in a row, or nothing good for 2 minutes) still shows as offline. Pure, no timers: the caller feeds it.
/**
 * Create a sticky holder for the last good answer.
 * @param {{maxFails?: number, maxAgeMs?: number, now?: Function}} [options]
 * @returns {{ok: Function, fail: Function, last: Function, fails: number, reset: Function}}
 */
function makeSticky({ maxFails = 3, maxAgeMs = 120000, now = Date.now } = {}) {
  let good = null,
    goodAt = 0,
    fails = 0;
  return {
    ok(v) {
      good = v;
      goodAt = now();
      fails = 0;
    },
    // a failed check: the value to show instead (the last good one) or null = show the failure
    fail() {
      fails++;
      if (good !== null && fails < maxFails && now() - goodAt <= maxAgeMs) return good;
      return null;
    },
    last() {
      return good;
    },
    get fails() {
      return fails;
    },
    reset() {
      good = null;
      goodAt = 0;
      fails = 0;
    },
  };
}
module.exports = { makeSticky };
