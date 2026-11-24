/**
 * @file Game/Steam process inspection and the SP/MP switch bridge.
 */
'use strict';

const path = require('path');
const linux = require('../linux');
const spmode = require('../spmode');
const { run } = require('./util');
const { ctx, testHooks, startedPids } = require('./state');
const { verifyWinmm } = require('./dll');

/**
 * List running game processes.
 * @param {string} [plat]
 * @param {object} [ldeps]
 * @returns {Promise<Array<{id: number, window?: boolean}>>}
 */
async function psGameProcs(plat = ctx.plat, ldeps = ctx.deps) {
  // [{id, window}] for tlou-ii; window = has a main window
  if (testHooks.procs) return testHooks.procs();
  if (plat === 'linux')
    return linux.gameProcs(ldeps.procDir).map((p) => ({ id: p.pid, window: true }));
  const r = await run(
    'powershell.exe',
    [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      "Get-Process tlou-ii -ErrorAction SilentlyContinue | ForEach-Object { '{0} {1}' -f $_.Id, [int]($_.MainWindowHandle -ne 0) }",
    ],
    { low: true },
  );
  return r.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .map((l) => {
      const [id, w] = l.trim().split(' ');
      return { id: +id, window: w === '1' };
    });
}

/**
 * Terminate a process by pid.
 * @param {number} pid
 * @returns {void}
 */
async function killProc(pid) {
  if (startedPids.has(pid)) return; // this launcher started it in this session: never a "leftover"
  if (ctx.plat === 'linux') return; // Linux: never end a game process (Steam owns it; the leftover rule cannot produce one there anyway)
  await run('taskkill', ['/PID', String(pid), '/F']);
}
/**
 * Stop any Steam helper processes owned by the launcher.
 * @returns {void}
 */
async function killSteamHelpers(plat = ctx.plat, extra = ctx.extra || {}) {
  if (plat === 'linux') {
    if (extra.userData)
      linux.stopHelper(
        path.join(extra.userData, 'linux-state.json'),
        (extra.linuxDeps || {}).procDir,
      );
    return;
  }
  await run('powershell.exe', [
    '-NoProfile',
    '-NonInteractive',
    '-Command',
    'Get-Process t2r-steam -ErrorAction SilentlyContinue | Stop-Process -Force',
  ]);
}

// true while our Steam helper (t2r-steam.exe) runs (Windows; Linux keeps its own pid file, see linux.stopHelper). tests: testHooks.helper
/**
 * Check whether the Steam helper is running.
 * @returns {boolean}
 */
async function helperRunning() {
  if (testHooks.helper) return testHooks.helper();
  if (ctx.plat === 'linux') return false;
  const r = await run(
    'powershell.exe',
    [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      "if (Get-Process t2r-steam -ErrorAction SilentlyContinue) { 'yes' }",
    ],
    { low: true },
  );
  return /yes/.test(r.stdout);
}
// What a running game process is, for the "mod did not load" warning: exe path, command line, parent process and the winmm.dll it loaded.
// A player whose game opens the plain single-player menu with every mod file in place cannot be told apart from the launcher log alone
// (exe started by Steam instead of the launcher, a different exe, winmm.dll taken from System32 instead of the game folder, an antivirus block).
// Read-only. -> [{ pid, exe, cmd, ppid, parent, parentExe, winmm }] (winmm '' = no winmm.dll in the process, '?' = modules not readable).
const PROC_DETAILS_PS = [
  'Get-CimInstance Win32_Process -Filter "Name like \'tlou-ii%\'" | ForEach-Object {',
  '  $p = $_;',
  '  $par = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $p.ParentProcessId) -ErrorAction SilentlyContinue;',
  "  $w = '?';",
  "  try { $m = (Get-Process -Id $p.ProcessId -ErrorAction Stop).Modules | Where-Object { $_.ModuleName -eq 'winmm.dll' } | Select-Object -First 1; $w = if ($m) { $m.FileName } else { '' } } catch {}",
  '  @($p.ProcessId, $p.ExecutablePath, $p.CommandLine, $p.ParentProcessId, $par.Name, $par.ExecutablePath, $w) -join [char]9',
  '}',
].join(' ');
/**
 * Parse the PROC_DETAILS_PS output (one tab-separated line per process).
 * @param {string} stdout
 * @returns {Array<object>}
 */
function parseProcDetails(stdout) {
  return String(stdout || '')
    .split(/\r?\n/)
    .filter((l) => l.trim())
    .map((l) => {
      const [pid, exe, cmd, ppid, parent, parentExe, winmm] = l.replace(/\r$/, '').split('\t');
      return {
        pid: +pid,
        exe: exe || '',
        cmd: cmd || '',
        ppid: +ppid || 0,
        parent: parent || '',
        parentExe: parentExe || '',
        winmm: winmm === undefined ? '?' : winmm,
      };
    })
    .filter((p) => p.pid > 0);
}
/**
 * Describe every running tlou-ii*.exe process (Windows only; [] elsewhere or on error).
 * @returns {Promise<Array<object>>}
 */
async function gameProcDetails() {
  if (testHooks.procDetails) return testHooks.procDetails();
  if (ctx.plat === 'linux') return [];
  try {
    const r = await run(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', PROC_DETAILS_PS],
      {
        low: true,
      },
    );
    return parseProcDetails(r.stdout);
  } catch {
    return [];
  }
}

// SWITCH TO SP / MP (lib/spmode.js) with this module's process probes and winmm check
/**
 * Build the dependency bundle used by the SP/MP switch.
 * @returns {object}
 */
const spDeps = () => ({
  verifyWinmm: (f) => verifyWinmm(f, 0),
  procs: () => psGameProcs(),
  helper: helperRunning,
  helperWaitMs: testHooks.helperWaitMs,
});
/**
 * Disable the mod for single-player.
 * @param {string} gameDir
 * @returns {Promise<object>}
 */
const spDisable = (gameDir) => spmode.disable(gameDir, spDeps());
/**
 * Re-enable the mod for multiplayer.
 * @param {string} gameDir
 * @returns {Promise<object>}
 */
const spEnable = (gameDir) => spmode.enable(gameDir, spDeps());
/**
 * Move base-mod leftovers of an install already in SP mode into the disabled folder.
 * @param {string} gameDir
 * @param {boolean} [noProcs] skip the running-game check (the caller already did it)
 * @returns {Promise<{moved: number, files: string[]}>}
 */
const spTopUp = (gameDir, noProcs) =>
  spmode.topUp(gameDir, noProcs ? Object.assign(spDeps(), { procs: null }) : spDeps());
/**
 * Return the effective SP/MP mode for a game directory.
 * @param {string} gameDir
 * @param {boolean} flag
 * @returns {string}
 */
const spModeFor = (gameDir, flag) => spmode.modeFor(gameDir, flag, (f) => verifyWinmm(f, 0));

/**
 * Report whether the game is running or starting.
 * @returns {Promise<{running: boolean, starting: boolean}>}
 */
async function gameRunning() {
  return (await psGameProcs()).some((p) => p.window);
}
// { running: a game window exists, starting: a tlou-ii process exists but no window yet (a cold boot shows none for a minute or more) }
/**
 * Return the full game-process status snapshot.
 * @returns {Promise<object>}
 */
async function gameStatus() {
  const p = await psGameProcs();
  return {
    running: p.some((x) => x.window),
    starting: p.length > 0 && !p.some((x) => x.window),
  };
}

module.exports = {
  psGameProcs,
  gameProcDetails,
  parseProcDetails,
  killProc,
  killSteamHelpers,
  helperRunning,
  spDeps,
  spDisable,
  spEnable,
  spTopUp,
  spModeFor,
  gameRunning,
  gameStatus,
};
