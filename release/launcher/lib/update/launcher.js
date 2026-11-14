/**
 * @file Self-update download, version comparison and deferred-swap journal.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { baseUrl } = require('./util');
const { request } = require('./net');
const { downloadFile } = require('./files');
const { journalPath } = require('./staging');

// Never update while the game runs: it holds the Steam helper's exe (client\steam\t2r-steam.exe) and the update would fail on that file halfway.
// status() -> { running, starting } (game.gameStatus). Resolves silently when idle; a failed poll never blocks.
/**
 * Refuse a launcher self-update while the game is running.
 * @param {object} status
 * @param {object} [opts]
 * @returns {void}
 */
async function refuseIfGameRunning(status, opts = {}) {
  let s = null;
  try {
    s = await status();
  } catch {
    return;
  }
  if (!s || !(s.running || s.starting)) return;
  const msg =
    'The game is running. Close it first, then update (the update replaces files the running game and its Steam helper use).';
  // a tlou-ii.exe without a window (zombie): the same "End it / Leave it" question Play asks, then the process is ended and the update goes on
  if (s.starting && !s.running && opts.confirmEnd && opts.procs && opts.kill) {
    let list = [];
    try {
      list = await opts.procs();
    } catch {}
    const ours = opts.ours || new Set();
    const pids = list.filter((p) => !p.window && !ours.has(p.id)).map((p) => p.id);
    if (pids.length && !list.some((p) => p.window) && (await opts.confirmEnd(pids))) {
      for (const id of pids) {
        if (opts.log)
          opts.log(
            `Ending a game process without a window (pid ${id}, confirmed) before the update.`,
          );
        await opts.kill(id);
      }
      let again = null;
      try {
        again = await status();
      } catch {
        return;
      }
      if (!again || !(again.running || again.starting)) return;
    }
  }
  throw new Error(msg);
}

// The swap batch needs to write next to the exe. Test that before the launcher quits (a locked / read-only / OneDrive folder would otherwise end in silence).
/**
 * Ensure the launcher can replace files next to a target.
 * @param {string} target
 * @returns {void}
 */
function assertWritableNextTo(target) {
  const probe = target + '.t2r-probe';
  try {
    fs.writeFileSync(probe, 'x');
    fs.renameSync(probe, probe + '2');
    fs.unlinkSync(probe + '2');
  } catch (e) {
    try {
      fs.unlinkSync(probe);
    } catch {}
    try {
      fs.unlinkSync(probe + '2');
    } catch {}
    const x = new Error(
      `The launcher cannot replace itself: the folder ${path.dirname(String(target))} does not allow changes (read-only, locked by OneDrive / an antivirus, or it needs administrator rights). Move the launcher to a normal folder such as your Desktop or Documents and start it from there, then update again.`,
    );
    x.cause = e;
    x.code = e && e.code;
    x.t2rExplained = true;
    throw x;
  }
}

// Launcher self-update (portable exe): download -> verify -> detached batch swaps the exe after we exit
/**
 * Download a new launcher payload to a temporary directory.
 * @param {object} info
 * @param {string} base
 * @param {string} tmpDir
 * @param {Function} onProgress
 * @param {AbortSignal} [signal]
 * @returns {Promise<string>}
 */
async function downloadLauncher(info, base, tmpDir, onProgress, signal) {
  const dest = path.join(tmpDir, 'TwelveWeeks-Launcher-new.exe');
  const url = new URL(info.url, baseUrl(base) + '/').toString();
  const f = {
    path: 'launcher',
    size: info.size || 0,
    sha256: String(info.sha256).toLowerCase(),
    url,
  };
  if (!f.size) {
    // size not given: HEAD-less, ask via a ranged GET of 1 byte is overkill; use Content-Length at fetch time
    const res = await request(url, { method: 'HEAD' });
    res.resume();
    f.size = parseInt(res.headers['content-length'] || '0', 10);
  }
  await downloadFile(f, dest, {
    signal,
    onBytes: (() => {
      let d = 0;
      return (n) => {
        d += n;
        onProgress && onProgress({ done: d, total: f.size });
      };
    })(),
  });
  return dest;
}

/**
 * Compare two dotted version strings.
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function cmpVersion(a, b) {
  const pa = String(a)
      .split(/[.\-+]/)
      .map((x) => parseInt(x, 10) || 0),
    pb = String(b)
      .split(/[.\-+]/)
      .map((x) => parseInt(x, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d < 0 ? -1 : 1;
  }
  return 0;
}

// An update that reached the end (every manifest file hash-checked or downloaded and swapped in) has no pending journal any more: a journal that
// names a file the newer manifest dropped would otherwise be 'missing' for ever and Play would refuse.
/**
 * Delete the deferred launcher-swap journal.
 * @param {string} dir
 * @returns {void}
 */
async function clearJournal(dir) {
  await fs.promises.unlink(journalPath(dir)).catch(() => {});
}
/**
 * Check whether a deferred launcher update is pending.
 * @param {string} dir
 * @returns {boolean}
 */
const hasPendingUpdate = (dir) => {
  try {
    return fs.existsSync(journalPath(dir));
  } catch {
    return false;
  }
};

module.exports = {
  refuseIfGameRunning,
  assertWritableNextTo,
  downloadLauncher,
  cmpVersion,
  clearJournal,
  hasPendingUpdate,
};
