/**
 * @file RPC ownership signal shared by the launcher and the in-game mod.
 *
 * Both processes can set Discord presence, so they coordinate through one small
 * file in the game folder:
 *
 *   <game_dir>/t2r-rpc-owner.txt   ->   launcher | mod | off
 *
 *   launcher  the launcher may set presence (also the default when missing)
 *   mod       the mod owns presence; the launcher clears its own and stays silent
 *   off       nobody sets presence (vanilla game, or the mod turned its RPC off)
 *
 * The mod writes `mod` when its own RPC is ready and `off` when it stops. The
 * launcher writes `launcher` when it owns the menu (only over another value: a
 * missing file already means `launcher`). It never writes `mod`, and never
 * writes `off` either: a vanilla (single player) start leaves the game folder
 * untouched and the launcher just stays silent while that game runs.
 *
 * A missing or unreadable file means `launcher`, so old mods that know nothing
 * about this protocol keep working exactly as before.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const FILE = 't2r-rpc-owner.txt';
const VALUES = new Set(['launcher', 'mod', 'off']);

/**
 * Absolute path of the ownership file for a game folder.
 * @param {string|null} gameDir
 * @returns {string|null}
 */
function fileFor(gameDir) {
  return gameDir ? path.join(gameDir, FILE) : null;
}

/**
 * Read the current owner. Missing/unreadable/unknown values mean the launcher.
 * @param {string|null} gameDir
 * @returns {'launcher'|'mod'|'off'}
 */
function read(gameDir) {
  const file = fileFor(gameDir);
  if (!file) return 'launcher';
  try {
    const value = fs.readFileSync(file, 'utf8').trim().toLowerCase();
    return VALUES.has(value) ? value : 'launcher';
  } catch {
    return 'launcher';
  }
}

/**
 * Write the owner, skipping the write when it already holds that value.
 * Best effort: a missing/locked game folder must never break the launcher.
 * @param {string|null} gameDir
 * @param {'launcher'|'mod'|'off'} value
 * @returns {boolean}
 */
function write(gameDir, value) {
  const file = fileFor(gameDir);
  if (!file || !VALUES.has(value)) return false;
  if (read(gameDir) === value) return true;
  try {
    fs.writeFileSync(file, value + '\n');
    return true;
  } catch {
    return false;
  }
}

/**
 * Remove the ownership file (used by the mod on a clean exit).
 * @param {string|null} gameDir
 * @returns {void}
 */
function clear(gameDir) {
  const file = fileFor(gameDir);
  if (!file) return;
  try {
    fs.unlinkSync(file);
  } catch {
    /* already gone */
  }
}

module.exports = { FILE, fileFor, read, write, clear };
