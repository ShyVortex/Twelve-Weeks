'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { APP_ID, HELPER_APP_ID } = require('./constants');
const { exists, readText, winPath } = require('./util');
const { parseVdf, vget } = require('./vdf');
const { steamRoots, steamLibraries } = require('./steam');

/**
 * Build a sortable key for version-like names.
 * @param {string} s
 * @returns {Array<string|number>}
 */
const naturalKey = (s) =>
  String(s)
    .split(/(\d+)/)
    .map((t) => (/^\d+$/.test(t) ? parseInt(t, 10) : t));

/**
 * Compare version-like strings naturally.
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function naturalCmp(a, b) {
  const ka = naturalKey(a),
    kb = naturalKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const x = ka[i],
      y = kb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (x === y) continue;
    if (typeof x === 'number' && typeof y === 'number') return x < y ? -1 : 1;
    return String(x) < String(y) ? -1 : 1;
  }
  return 0;
}

/**
 * Scan Steam libraries for installed Proton builds.
 * @param {string[]} roots
 * @returns {{tools: object, names: string[]}}
 */
function discoverProtonTools(roots) {
  const tools = {};
  for (const lib of steamLibraries(roots)) {
    let ents = [];
    try {
      ents = fs.readdirSync(path.join(lib, 'steamapps', 'common'), {
        withFileTypes: true,
      });
    } catch {
      continue;
    }
    for (const e of ents) {
      const d = path.join(lib, 'steamapps', 'common', e.name);
      if (/^Proton/i.test(e.name) && exists(path.join(d, 'proton'))) tools[e.name] = d;
    }
  }
  for (const r of roots) {
    let ents = [];
    try {
      ents = fs.readdirSync(path.join(r, 'compatibilitytools.d'), {
        withFileTypes: true,
      });
    } catch {
      continue;
    }
    for (const e of ents) {
      const d = path.join(r, 'compatibilitytools.d', e.name);
      if (exists(path.join(d, 'proton'))) tools[e.name] = d;
    }
  }
  return { tools, names: Object.keys(tools) };
}

/**
 * Read the Proton name Steam has configured for the game.
 * @param {string[]} roots
 * @returns {string|null}
 */
function configuredProtonName(roots) {
  for (const r of roots) {
    const map = vget(
      parseVdf(readText(path.join(r, 'config', 'config.vdf'))),
      'InstallConfigStore',
      'Software',
      'Valve',
      'Steam',
      'CompatToolMapping',
    );
    if (!map) continue;
    const e = vget(map, APP_ID) || vget(map, '0');
    const nm = e && vget(e, 'name');
    if (nm) return nm;
  }
  return null;
}

/**
 * Pick a Proton path from the discovered tools according to Steam policy.
 * @param {object} tools
 * @param {string[]} names
 * @param {string|null} want
 * @returns {string|null}
 */
function selectProton(tools, names, want) {
  if (want) {
    const alias = {
      proton_experimental: 'Proton - Experimental',
      proton_hotfix: 'Proton Hotfix',
    };
    if (alias[want] && tools[alias[want]]) return tools[alias[want]];
    const m = /^proton_(\d+)$/.exec(want);
    if (m) {
      const hit = names
        .filter((n) => n.startsWith(`Proton ${m[1]}`))
        .sort(naturalCmp)
        .reverse()[0];
      if (hit) return tools[hit];
    }
    if (tools[want]) return tools[want];
  }
  if (tools['Proton - Experimental']) return tools['Proton - Experimental'];
  const plain = names.filter((n) => n.startsWith('Proton '));
  return tools[(plain.length ? plain : names).sort(naturalCmp).reverse()[0]];
}

/**
 * Locate a usable Proton runtime.
 * @param {string} [home]
 * @returns {string|null}
 */
function findProton(home = os.homedir()) {
  const roots = steamRoots(home);
  const { tools, names } = discoverProtonTools(roots);
  if (!names.length) return null;
  return selectProton(tools, names, configuredProtonName(roots));
}

/**
 * Build the environment for running a Windows tool under Proton.
 * @param {string} proton
 * @param {string} prefix
 * @param {string} [home]
 * @param {object} [base]
 * @returns {object}
 */
function protonEnv(proton, prefix, home = os.homedir(), base = process.env) {
  const root = steamRoots(home)[0] || path.join(home, '.steam', 'steam');
  const env = { ...base };
  for (const k of [
    'SteamOverlayGameId',
    'SteamClientLaunch',
    'STEAM_COMPAT_SHADER_PATH',
    'STEAM_COMPAT_INSTALL_PATH',
    'STEAM_COMPAT_LIBRARY_PATHS',
    'LD_PRELOAD',
    'LD_LIBRARY_PATH',
  ])
    delete env[k];
  return Object.assign(env, {
    STEAM_COMPAT_DATA_PATH: prefix,
    STEAM_COMPAT_CLIENT_INSTALL_PATH: root,
    SteamAppId: HELPER_APP_ID,
    SteamGameId: HELPER_APP_ID,
    STEAM_COMPAT_APP_ID: HELPER_APP_ID,
    WINEDEBUG: '-all',
  });
}

/**
 * Build the Steam helper argument list.
 * @param {{exe: string, nameFile: string, server: object, tokenFile: string, aliveFile: string, logFile: string}} options
 * @returns {string[]}
 */
function helperArgs({ exe, nameFile, server, tokenFile, aliveFile, logFile }) {
  return [
    exe,
    winPath(nameFile),
    'tlou-ii.exe',
    '--server',
    server,
    '--token',
    winPath(tokenFile),
    '--port',
    '7777',
    '--alive-file',
    winPath(aliveFile),
    '--log',
    winPath(logFile),
  ];
}

/**
 * Build the command that runs the slim-client tool under Proton.
 * @param {object} options
 * @returns {{cmd: string, args: string[], env: object, cwd: string}}
 */
function slimCommand({ clientDir, game, src, dat, dst, dataDir, deps = {} }) {
  const home = deps.home || os.homedir();
  const proton = findProton(home);
  if (!proton)
    throw new Error(
      'No Proton was found in your Steam folders: it is needed to rebuild the mod from your game files (the slim client). Install Proton Experimental in Steam, or ask the host for a full client.',
    );
  const exe = path.join(clientDir, 'slim', 't2r-slim.exe');
  const prefix = path.join(dataDir, 't2r-steam-prefix');
  fs.mkdirSync(prefix, { recursive: true });
  return {
    cmd: path.join(proton, 'proton'),
    args: ['run', exe, winPath(src), winPath(dat), winPath(game), winPath(dst)],
    env: protonEnv(proton, prefix, home),
    cwd: path.dirname(exe),
  };
}

module.exports = {
  naturalKey,
  naturalCmp,
  discoverProtonTools,
  configuredProtonName,
  selectProton,
  findProton,
  protonEnv,
  helperArgs,
  slimCommand,
};
