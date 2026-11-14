/**
 * @file Locate the game, Steam libraries, executable metadata and build stamps.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const linux = require('../linux');
const { run, exists } = require('./util');

const STEAM_APP_ID = '2531310';
const EXE_TIMESTAMP = 0x687df976;
const EXE_IMAGE_SIZE = 0x9a68000;

/**
 * Return the platform Steam root used by the launcher.
 * @returns {string}
 */
async function steamPath() {
  if (process.platform === 'linux') return linux.steamRoots()[0] || null;
  const r = await run('reg', ['query', 'HKCU\\Software\\Valve\\Steam', '/v', 'SteamPath']);
  const m = /SteamPath\s+REG_SZ\s+(.+)/.exec(r.stdout);
  return m ? m[1].trim().replace(/\//g, '\\') : null;
}

/**
 * Parse Steam's libraryfolders.vdf into library paths.
 * @param {string} text
 * @returns {string[]}
 */
function parseLibraryFolders(text) {
  const out = [];
  const re = /"path"\s+"([^"]+)"/g;
  let m;
  while ((m = re.exec(text))) out.push(m[1].replace(/\\\\/g, '\\'));
  return out;
}

/**
 * Find candidate The Last of Us Part II install directories.
 * @returns {string[]}
 */
async function findGameDirs() {
  if (process.platform === 'linux') return linux.findGameDirs();
  const found = [];
  const add = (d) => {
    if (d && exists(path.join(d, 'tlou-ii.exe')) && !found.includes(d)) found.push(d);
  };
  const roots = [];
  const sp = await steamPath();
  if (sp) {
    const vdf = path.join(sp, 'steamapps', 'libraryfolders.vdf');
    if (exists(vdf)) {
      let text = '';
      try {
        text = fs.readFileSync(vdf, 'utf8');
      } catch {}
      // prefer the library that lists app 2531310 (its appmanifest names the install dir)
      for (const lib of parseLibraryFolders(text)) {
        const common = path.join(lib, 'steamapps', 'common');
        roots.push(common);
        const acf = path.join(lib, 'steamapps', `appmanifest_${STEAM_APP_ID}.acf`);
        if (exists(acf)) {
          try {
            const m = /"installdir"\s+"([^"]+)"/.exec(fs.readFileSync(acf, 'utf8'));
            if (m) add(path.join(common, m[1]));
          } catch {}
        }
      }
    }
  }
  const drives = [];
  for (let c = 67; c <= 90; c++) {
    const d = String.fromCharCode(c) + ':\\';
    if (exists(d)) drives.push(d);
  }
  for (const d of drives) {
    for (const sub of [
      'Games',
      'Program Files\\Epic Games',
      'Program Files (x86)\\Steam\\steamapps\\common',
      'SteamLibrary\\steamapps\\common',
      'Program Files\\Steam\\steamapps\\common',
    ])
      roots.push(path.join(d, sub));
  }
  for (const r of [...new Set(roots)]) {
    let ents = [];
    try {
      ents = fs.readdirSync(r, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of ents) if (e.isDirectory()) add(path.join(r, e.name));
  }
  return found;
}

/**
 * Check whether a directory contains the expected game executable.
 * @param {string} d
 * @returns {boolean}
 */
const isGameDir = (d) => !!d && exists(path.join(d, 'tlou-ii.exe'));

// Every hard-coded address of winmm.dll / t2r-ext.dll is for tlou-ii.exe 1.6.10721 (PE timestamp + image size, same constants as
// tools/ext/t2r_shared.h). t2r-ext.c has no guard of its own: on another build (a Steam update) it patches the wrong bytes and the game crashes
// or misbehaves with no message. known: true / false, or null when the exe is not a readable PE (a test stub): never blocks then.
/**
 * Read the executable build stamp.
 * @param {string} gameDir
 * @returns {string|number|null}
 */
function exeBuild(gameDir) {
  try {
    const fd = fs.openSync(path.join(gameDir, 'tlou-ii.exe'), 'r');
    try {
      const b = Buffer.alloc(4096);
      fs.readSync(fd, b, 0, 4096, 0);
      if (b.readUInt16LE(0) !== 0x5a4d) return { known: null };
      const nt = b.readUInt32LE(0x3c);
      if (nt + 24 + 60 > 4096 || b.readUInt32LE(nt) !== 0x4550) return { known: null };
      const ts = b.readUInt32LE(nt + 8),
        size = b.readUInt32LE(nt + 24 + 56);
      return {
        known: ts === EXE_TIMESTAMP && size === EXE_IMAGE_SIZE,
        ts,
        size,
      };
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return { known: null };
  }
}

module.exports = {
  STEAM_APP_ID,
  EXE_TIMESTAMP,
  EXE_IMAGE_SIZE,
  steamPath,
  parseLibraryFolders,
  findGameDirs,
  isGameDir,
  exeBuild,
};
