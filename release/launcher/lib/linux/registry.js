'use strict';

const fs = require('fs');
const path = require('path');
const { APP_ID } = require('./constants');
const { exists } = require('./util');
const { gameProcs } = require('./processes');

/**
 * Find a registry section header and the line where it ends.
 * @param {string[]} lines
 * @param {Function} strip
 * @param {string} section
 * @returns {{hi: number, end: number}}
 */
function regSectionRange(lines, strip, section) {
  const head = '[' + section.replace(/\\/g, '\\\\').toLowerCase() + ']';
  const hi = lines.findIndex((l) => strip(l).toLowerCase().startsWith(head));
  if (hi < 0) return { hi: -1, end: -1 };
  let end = lines.length;
  for (let j = hi + 1; j < lines.length; j++)
    if (strip(lines[j]).startsWith('[')) {
      end = j;
      break;
    }
  return { hi, end };
}

/**
 * Find the index of a key inside a registry section.
 * @param {string[]} lines
 * @param {Function} strip
 * @param {string} name
 * @param {number} hi
 * @param {number} end
 * @returns {number}
 */
function regValueIndex(lines, strip, name, hi, end) {
  const key = `"${name}"=`.toLowerCase();
  for (let j = hi + 1; j < end; j++) if (strip(lines[j]).toLowerCase().startsWith(key)) return j;
  return -1;
}

/**
 * Find where a new key should be inserted inside a registry section.
 * @param {string[]} lines
 * @param {Function} strip
 * @param {number} hi
 * @param {number} end
 * @returns {number}
 */
function regInsertIndex(lines, strip, hi, end) {
  let at = hi + 1;
  while (at < end && (strip(lines[at]).startsWith('#') || strip(lines[at]).startsWith(';'))) at++;
  return at;
}

/**
 * Apply key/value edits to a Wine user.reg file.
 * @param {string} text
 * @param {{section: string, name: string, value: string}[]} edits
 * @param {number} [now]
 * @returns {string}
 */
function patchUserReg(text, edits, now = Math.floor(Date.now() / 1000)) {
  const lines = text.split('\n');
  const eol = text.includes('\r\n') ? '\r' : '';
  const strip = (l) => l.replace(/\r$/, '');
  for (const e of edits) {
    const want = `"${e.name}"=${e.value}`;
    const { hi, end } = regSectionRange(lines, strip, e.section);
    if (hi < 0) {
      if (lines.length && strip(lines[lines.length - 1]) === '') lines.pop();
      lines.push('', `[${e.section.replace(/\\/g, '\\\\')}] ${now}`, `#time=0`, want, '');
      continue;
    }
    const vi = regValueIndex(lines, strip, e.name, hi, end);
    if (vi >= 0) {
      lines[vi] = want + eol;
      continue;
    }
    lines.splice(regInsertIndex(lines, strip, hi, end), 0, want + eol);
  }
  return lines.join('\n');
}

/**
 * Resolve the Wine user.reg path for a game directory.
 * @param {string} gameDir
 * @returns {string|null}
 */
function userRegFor(gameDir) {
  const common = path.dirname(gameDir);
  if (path.basename(common) !== 'common') return null;
  return path.join(path.dirname(common), 'compatdata', APP_ID, 'pfx', 'user.reg');
}

const REG_EDITS = [
  {
    section: 'Software\\Wine\\DllOverrides',
    name: 'winmm',
    value: '"native,builtin"',
  },
  {
    section: 'Software\\Naughty Dog\\The Last of Us Part II',
    name: 'ShowLauncher',
    value: 'dword:00000000',
  },
];

/**
 * Ensure the Proton prefix has the required registry overrides.
 * @param {string} gameDir
 * @param {{procDir?: string}} [options]
 * @returns {object} { ok, changed } or { ok: false, reason }
 */
function prepareGamePrefix(gameDir, { procDir = '/proc' } = {}) {
  const reg = userRegFor(gameDir);
  if (!reg)
    return {
      ok: false,
      reason:
        'The game folder is not inside a Steam library (steamapps/common), so its Proton prefix cannot be found.',
    };
  if (!exists(reg)) {
    return {
      ok: false,
      reason:
        'The game has never been started through Steam on this computer, so its Proton prefix does not exist yet. Start The Last of Us Part II once from Steam (until its menu), close it, then press PLAY again.',
    };
  }
  if (gameProcs(procDir).length)
    return {
      ok: false,
      reason: 'The game is running: close it before the launcher changes its Proton prefix.',
    };
  const old = fs.readFileSync(reg, 'utf8');
  const next = patchUserReg(old, REG_EDITS);
  if (next === old) return { ok: true, changed: false };
  const bak = reg + '.t2r-backup';
  if (!exists(bak)) fs.copyFileSync(reg, bak);
  const tmp = reg + '.t2r-new';
  fs.writeFileSync(tmp, next);
  fs.renameSync(tmp, reg);
  return { ok: true, changed: true };
}

module.exports = {
  regSectionRange,
  regValueIndex,
  regInsertIndex,
  patchUserReg,
  userRegFor,
  REG_EDITS,
  prepareGamePrefix,
};
