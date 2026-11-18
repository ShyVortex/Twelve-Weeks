'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const childProcess = require('child_process');
const { exists, isDir, readText, sleep } = require('./util');
const { findProton, protonEnv, helperArgs } = require('./proton');

/**
 * Read the helper state file.
 * @param {string} file
 * @returns {object}
 */
function readState(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return {};
  }
}

/**
 * Write the helper state file.
 * @param {string} file
 * @param {object} st
 * @returns {void}
 */
function writeState(file, st) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(st));
  } catch {}
}

/**
 * Stop the Steam helper if it belongs to this launcher.
 * @param {string} stateFile
 * @param {string} [procDir]
 * @param {Function} [kill]
 * @returns {boolean}
 */
function stopHelper(stateFile, procDir = '/proc', kill = process.kill) {
  const pid = readState(stateFile).helper_pid;
  if (!pid) return false;
  let ours = false;
  try {
    ours = /t2r-steam/i.test(
      fs.readFileSync(path.join(procDir, String(pid), 'cmdline')).toString('latin1'),
    );
  } catch {}
  if (!ours) return false;
  try {
    kill(-pid, 'SIGTERM');
  } catch {
    try {
      kill(pid, 'SIGTERM');
    } catch {}
  }
  return true;
}

/**
 * Start the Steam helper under Proton.
 * @param {object} options
 * @returns {Promise<object>}
 */
async function startHelper({ clientDir, gameDir, dataDir, server, log, deps = {} }) {
  const spawn = deps.spawn || childProcess.spawn;
  const home = deps.home || os.homedir();
  const stateFile = path.join(dataDir, 'linux-state.json');
  stopHelper(stateFile, deps.procDir);
  const proton = findProton(home);
  if (!proton)
    return {
      pid: null,
      reason:
        'No Proton was found in your Steam folders (Flatpak Steam cannot be reached from here).',
    };
  const exe = path.join(clientDir, 'steam', 't2r-steam.exe');
  if (!exists(exe))
    return {
      pid: null,
      reason: `${exe} is missing (press REPAIR INSTALL in Settings > Files).`,
    };
  const prefix = path.join(dataDir, 't2r-steam-prefix');
  fs.mkdirSync(prefix, { recursive: true });
  const nameFile = path.join(dataDir, 't2r-steam-name.txt');
  const aliveFile = path.join(gameDir, 't2r-alive.txt');
  for (const f of [nameFile, aliveFile]) {
    try {
      fs.unlinkSync(f);
    } catch {}
  }
  const firstTime = !isDir(path.join(prefix, 'pfx'));
  const args = [
    'run',
    ...helperArgs({
      exe,
      nameFile,
      server,
      tokenFile: path.join(gameDir, 'tlou-ii-mp.json'),
      aliveFile,
      logFile: path.join(dataDir, 't2r-steam.log'),
    }),
  ];
  const out = fs.openSync(path.join(dataDir, 't2r-steam-proton.log'), 'w');
  let exited = null;
  let child;
  try {
    child = spawn(path.join(proton, 'proton'), args, {
      env: protonEnv(proton, prefix, home),
      cwd: path.dirname(exe),
      detached: true,
      stdio: ['ignore', out, out],
    });
  } catch (e) {
    return { pid: null, reason: `Proton could not be started (${e.message}).` };
  }
  child.on('exit', (code) => {
    exited = code === null ? -1 : code;
  });
  child.on('error', () => {
    exited = -2;
  });
  if (child.unref) child.unref();
  log(
    `Steam helper: ${path.basename(proton)} run ${path.basename(exe)}${firstTime ? ' (first start: Proton is creating its own prefix, up to a minute or two)' : ''}`,
  );
  const limit = (firstTime ? 120 : 25) * 1000;
  const t0 = Date.now();
  let reached = false;
  while (Date.now() - t0 < limit && exited === null) {
    if (exists(nameFile)) {
      reached = true;
      break;
    }
    await sleep(deps.pollMs || 500);
  }
  if (exited !== null && !reached)
    return {
      pid: null,
      reason: `Proton exited at once (code ${exited}); see ${path.join(dataDir, 't2r-steam-proton.log')}.`,
    };
  writeState(stateFile, { helper_pid: child.pid });
  let name = null;
  if (reached) {
    try {
      name = readText(nameFile).split(/\r?\n/)[0].trim() || null;
    } catch {}
  }
  return { pid: child.pid, name, reached };
}

module.exports = { readState, writeState, stopHelper, startHelper };
