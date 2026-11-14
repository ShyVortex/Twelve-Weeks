'use strict';

const path = require('path');
const os = require('os');
const { APP_ID } = require('./constants');
const { exists, sleep } = require('./util');
const { steamRoots } = require('./steam');
const { gameProcs } = require('./processes');

/**
 * Resolve an executable on PATH synchronously.
 * @param {string} cmd
 * @param {string} pathEnv
 * @returns {string|null}
 */
function whichSync(cmd, pathEnv = process.env.PATH || '') {
  for (const d of pathEnv.split(path.delimiter)) {
    if (d && exists(path.join(d, cmd))) return path.join(d, cmd);
  }
  return null;
}

/**
 * Order the possible ways to launch the game through Steam.
 * @param {string} url
 * @param {{flatpakRoot: boolean, flatpakOnly: boolean}} flags
 * @returns {{cmd: string, args: string[]}[]}
 */
function steamLaunchCandidates(url, { flatpakRoot, flatpakOnly }) {
  const candidates = [];
  if (!flatpakOnly) candidates.push({ cmd: 'steam', args: [url] });
  if (flatpakRoot)
    candidates.push({ cmd: 'flatpak', args: ['run', 'com.valvesoftware.Steam', url] });
  if (flatpakOnly) candidates.push({ cmd: 'steam', args: [url] });
  candidates.push({ cmd: 'xdg-open', args: [url] });
  return candidates;
}

/**
 * Build the Steam launch command for the game.
 * @param {string} [home]
 * @param {string} [pathEnv]
 * @returns {{cmd: string, args: string[]}}
 */
function steamLaunchCommand(home = os.homedir(), pathEnv = process.env.PATH || '') {
  const url = `steam://rungameid/${APP_ID}`;
  const roots = steamRoots(home);
  const flatpakRoot = roots.some((r) => r.includes('com.valvesoftware.Steam'));
  const flatpakOnly = roots.length > 0 && roots.every((r) => r.includes('com.valvesoftware.Steam'));
  const candidates = steamLaunchCandidates(url, { flatpakRoot, flatpakOnly });
  for (const c of candidates) if (c.cmd === 'xdg-open' || whichSync(c.cmd, pathEnv)) return c;
  return candidates[candidates.length - 1];
}

/**
 * Wait briefly for the game process to appear.
 * @param {string} procDir
 * @param {number} ms
 * @returns {Promise<boolean>}
 */
async function waitForGame(procDir, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (gameProcs(procDir).length) return true;
    await sleep(1000);
  }
  return false;
}

module.exports = { whichSync, steamLaunchCandidates, steamLaunchCommand, waitForGame };
