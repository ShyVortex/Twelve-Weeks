/**
 * @file Startup-crash loop detection based on failed game starts.
 */
'use strict';
// Startup-crash loop detection. The Play flow records every start that ended before a game window ever appeared (the game died on startup);
// a start that reached its window clears the record. N such failures within the window = a loop: the error text then points to "Report a bug"
// (which sends the logs and the newest crash dump) instead of just "press Play again".
const fs = require('fs');

const LIMIT = 3; // failed starts in a row that make a loop
const WINDOW_MS = 60 * 60 * 1000; // ...within an hour

/**
 * Read and parse the startup-health state file.
 * @param {string} file
 * @returns {object}
 */
function read(file) {
  try {
    const j = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(j.fails) ? j.fails.filter((t) => Number.isFinite(t)) : [];
  } catch {
    return [];
  }
}
/**
 * Persist the startup-health state file atomically.
 * @param {string} file
 * @param {object} st
 * @returns {void}
 */
function write(file, fails) {
  try {
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify({ fails }));
    fs.renameSync(tmp, file);
  } catch {
    /* best effort: tracking must never break Play */
  }
}
// -> { count, loop }
/**
 * Record a game start that failed before a window appeared.
 * @param {string} file
 * @param {number} [now]
 * @returns {object}
 */
function recordStartFailure(file, now = Date.now()) {
  if (!file) return { count: 0, loop: false };
  const fails = read(file).filter((t) => now - t < WINDOW_MS && t <= now);
  fails.push(now);
  const keep = fails.slice(-10);
  write(file, keep);
  return { count: keep.length, loop: keep.length >= LIMIT };
}
/**
 * Clear the startup-crash history after a successful start.
 * @param {string} file
 * @returns {void}
 */
function recordStartOk(file) {
  if (file) write(file, []);
}
/**
 * Read the current startup-crash state.
 * @param {string} file
 * @param {number} [now]
 * @returns {object}
 */
function state(file, now = Date.now()) {
  const n = file ? read(file).filter((t) => now - t < WINDOW_MS && t <= now).length : 0;
  return { count: n, loop: n >= LIMIT };
}
// next steps shown with every startup failure (after a Steam "verify game files" Steam runs a first-start step the launcher cannot see)
const NEXT_STEPS =
  'The game closed before it started. Next: start The Last of Us Part II once from your Steam library, finish any Steam window or dialog (install step, cloud sync, EULA) and wait until the game itself opens, then close it and press Play again. If it still happens, use REPORT A BUG in the menu.';
/**
 * Return a user-facing message for a crash loop.
 * @param {number} count
 * @returns {string}
 */
function loopMessage(count) {
  return `The game closed on startup ${count} times in a row. Another try will probably do the same. Next: start The Last of Us Part II once from your Steam library, finish any Steam window or dialog (install step, cloud sync, EULA) and wait until the game opens, then close it and press Play again. If it still happens, open REPORT A BUG in the menu and send it (it includes the logs and the newest crash dump), or press REPAIR INSTALL in Settings > Files first.`;
}

module.exports = {
  recordStartFailure,
  recordStartOk,
  state,
  loopMessage,
  NEXT_STEPS,
  LIMIT,
  WINDOW_MS,
};
