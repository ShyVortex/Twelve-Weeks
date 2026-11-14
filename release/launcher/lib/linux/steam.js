'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { APP_ID } = require('./constants');
const { exists, isDir, real, readText } = require('./util');
const { parseVdf, vget } = require('./vdf');

/**
 * Return candidate Steam installation roots.
 * @param {string} [home]
 * @returns {string[]}
 */
function steamRoots(home = os.homedir()) {
  const cands = [
    '.steam/steam',
    '.local/share/Steam',
    '.var/app/com.valvesoftware.Steam/.local/share/Steam',
    '.steam/root',
    'snap/steam/common/.local/share/Steam',
  ].map((p) => path.join(home, p));
  const out = [],
    seen = new Set();
  for (const c of cands) {
    if (!isDir(c)) continue;
    const r = real(c);
    if (seen.has(r)) continue;
    seen.add(r);
    out.push(c);
  }
  return out;
}

/**
 * Parse Steam library folders into absolute paths.
 * @param {string} text
 * @returns {string[]}
 */
function parseLibraryFolders(text) {
  const root = vget(parseVdf(text), 'libraryfolders') || {};
  const out = [];
  for (const k of Object.keys(root)) {
    const v = root[k];
    if (v && typeof v === 'object') {
      const p = vget(v, 'path');
      if (p) out.push(p);
    } else if (/^\d+$/.test(k) && typeof v === 'string') out.push(v);
  }
  return out;
}

/**
 * Expand Steam roots into library directories.
 * @param {string[]} roots
 * @returns {string[]}
 */
function steamLibraries(roots) {
  const libs = [],
    seen = new Set();
  const add = (p) => {
    const r = real(p);
    if (isDir(p) && !seen.has(r)) {
      seen.add(r);
      libs.push(p);
    }
  };
  for (const r of roots) {
    add(r);
    for (const p of parseLibraryFolders(readText(path.join(r, 'steamapps', 'libraryfolders.vdf'))))
      add(p);
  }
  return libs;
}

/**
 * Check whether a directory contains the game executable.
 * @param {string} d
 * @returns {boolean}
 */
const isGameDir = (d) => !!d && exists(path.join(d, 'tlou-ii.exe'));

/**
 * Find The Last of Us Part II directories in Steam libraries.
 * @param {string} [home]
 * @returns {string[]}
 */
function findGameDirs(home = os.homedir()) {
  const found = [],
    seen = new Set();
  const add = (d) => {
    if (isGameDir(d) && !seen.has(real(d))) {
      seen.add(real(d));
      found.push(d);
    }
  };
  const libs = steamLibraries(steamRoots(home));
  for (const lib of libs) {
    const acf = parseVdf(readText(path.join(lib, 'steamapps', `appmanifest_${APP_ID}.acf`)));
    const dir = vget(acf, 'AppState', 'installdir');
    if (dir) add(path.join(lib, 'steamapps', 'common', dir));
  }
  for (const lib of libs) {
    let ents = [];
    try {
      ents = fs.readdirSync(path.join(lib, 'steamapps', 'common'), {
        withFileTypes: true,
      });
    } catch {
      continue;
    }
    for (const e of ents)
      if (e.isDirectory() && /^The Last of Us Part II/i.test(e.name))
        add(path.join(lib, 'steamapps', 'common', e.name));
  }
  return found;
}

/**
 * Read the configured Steam launch options for the game.
 * @param {string} [home]
 * @returns {object}
 */
function launchOptions(home = os.homedir()) {
  const out = [];
  for (const r of steamRoots(home)) {
    let users = [];
    try {
      users = fs.readdirSync(path.join(r, 'userdata'));
    } catch {
      continue;
    }
    for (const u of users) {
      const cfg = parseVdf(readText(path.join(r, 'userdata', u, 'config', 'localconfig.vdf')));
      const lo = vget(
        cfg,
        'UserLocalConfigStore',
        'Software',
        'Valve',
        'Steam',
        'apps',
        APP_ID,
        'LaunchOptions',
      );
      if (lo) out.push(lo);
    }
  }
  return out;
}

module.exports = {
  steamRoots,
  parseLibraryFolders,
  steamLibraries,
  isGameDir,
  findGameDirs,
  launchOptions,
};
