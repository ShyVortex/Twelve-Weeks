'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Read the process table.
 * @param {string} [procDir]
 * @returns {Array<{pid: number, cmd: string}>}
 */
function procList(procDir = '/proc') {
  const out = [];
  let ents = [];
  try {
    ents = fs.readdirSync(procDir);
  } catch {
    return out;
  }
  for (const e of ents) {
    if (!/^\d+$/.test(e)) continue;
    let cmd = '';
    try {
      cmd = fs
        .readFileSync(path.join(procDir, e, 'cmdline'))
        .toString('latin1')
        .replace(/\0/g, ' ')
        .trim();
    } catch {
      continue;
    }
    out.push({ pid: +e, cmd });
  }
  return out;
}

/**
 * List processes belonging to the game.
 * @param {string} [procDir]
 * @param {number} [self]
 * @returns {object[]}
 */
function gameProcs(procDir = '/proc', self = process.pid) {
  return procList(procDir).filter(
    (p) => p.pid !== self && /tlou-ii\.exe/i.test(p.cmd) && !/t2r-steam|t2r-slim/i.test(p.cmd),
  );
}

/**
 * List processes belonging to the Steam helper.
 * @param {string} [procDir]
 * @returns {object[]}
 */
function helperProcs(procDir = '/proc') {
  return procList(procDir).filter((p) => /t2r-steam/i.test(p.cmd));
}

module.exports = { procList, gameProcs, helperProcs };
