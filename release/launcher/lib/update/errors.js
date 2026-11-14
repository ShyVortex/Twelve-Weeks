/**
 * @file Human-readable update errors and free-space checks.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { LOCK_CODES, SPACE_CODES, tunables, mb, isNetErr } = require('./util');

// Turns a raw fs / network error into a sentence the player can act on. The original error stays on .cause (and its code on .code).
/**
 * Convert low-level update errors into user-facing text.
 * @param {unknown} e
 * @param {string} where
 * @returns {string}
 */
function explainError(e, where) {
  if (!e) return new Error('Unknown error');
  if (e.t2rExplained) return e;
  const code = e.code || '';
  const msg = String(e.message || e);
  const file = where ? path.basename(String(where).replace(/\.(part|new|z\.part)$/, '')) : '';
  let text = null;
  if (SPACE_CODES.has(code) || /ENOSPC|no space left|not enough space/i.test(msg))
    text = where
      ? `There is not enough free disk space on the drive of ${path.parse(path.resolve(String(where))).root || where} for the update. Free some space and press Update again; the download continues where it stopped.`
      : 'There is not enough free disk space for the update. Free some space and press Update again; the download continues where it stopped.';
  else if (LOCK_CODES.has(code))
    text = `Windows would not let the launcher replace ${file || 'a file'}: another program has it open (the game, the Steam helper or an antivirus scan). Close the game, wait a minute (or add the launcher's client folder to your antivirus exclusions) and press Update again.`;
  else if (code === 'EROFS')
    text = where
      ? `The folder is read-only (${path.dirname(String(where))}). Choose another client folder in Settings > Files.`
      : 'The folder is read-only. Choose another client folder in Settings > Files.';
  else if (
    isNetErr(e) ||
    /connection lost|socket hang up|aborted|stalled|EPIPE|ECONNRESET/i.test(msg)
  )
    text =
      'The connection to the update server was lost (the server may be restarting). Check your internet connection and press Update again; the download continues where it stopped.';
  if (!text) return e;
  const out = new Error(text);
  out.cause = e;
  out.code = code;
  out.t2rExplained = true;
  return out;
}

// Free bytes on the drive of `dir` (null = unknown). fs.statfsSync needs Node 18.15+ (Electron 33 ships Node 20).
/**
 * Return free bytes for the volume containing a path.
 * @param {string} dir
 * @returns {number}
 */
function freeBytes(dir) {
  if (tunables.freeBytes) return tunables.freeBytes(dir);
  try {
    let d = path.resolve(dir);
    while (!fs.existsSync(d) && path.dirname(d) !== d) d = path.dirname(d);
    const s = fs.statfsSync(d);
    return Number(s.bavail) * Number(s.bsize);
  } catch {
    return null;
  }
}
// Throws a clear error when the drive of `dir` cannot take `needed` more bytes (with a little slack). Unknown free space never blocks.
/**
 * Throw a readable error when the target volume lacks space.
 * @param {string} dir
 * @param {number} needed
 * @param {string} [what]
 * @returns {void}
 */
function ensureSpace(dir, needed, what = 'the update') {
  const free = freeBytes(dir);
  if (free === null || needed <= 0) return;
  if (free < needed + 64 * 1048576) {
    const drive = path.parse(path.resolve(dir)).root || dir;
    const e = new Error(
      what === 'the update'
        ? `There is not enough free disk space for the update: about ${mb(needed)} are needed on the drive of ${drive}, ${mb(free)} are free. Free some space and try again; the download continues where it stopped.`
        : `There is not enough free disk space for the mod files: about ${mb(needed)} are needed on the drive of ${drive}, ${mb(free)} are free. Free some space and try again.`,
    );
    e.code = 'ENOSPC';
    e.t2rExplained = true;
    throw e;
  }
}

module.exports = { explainError, freeBytes, ensureSpace };
