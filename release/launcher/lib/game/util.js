/**
 * @file Process, filesystem and timeout helpers shared by the game module.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');
const upd = require('../update');

/**
 * Run a child process and capture its output.
 * @param {string} cmd
 * @param {string[]} args
 * @param {object} [opts]
 * @returns {Promise<object>}
 */
function run(cmd, args, opts = {}) {
  const { low, ...execOptions } = opts;
  return new Promise((resolve) => {
    const child = execFile(
      cmd,
      args,
      { windowsHide: true, timeout: 20000, ...execOptions },
      (err, stdout, stderr) =>
        resolve({
          err,
          stdout: String(stdout || ''),
          stderr: String(stderr || ''),
        }),
    );
    if (low && child && child.pid) {
      try {
        os.setPriority(child.pid, os.constants.priority.PRIORITY_BELOW_NORMAL);
      } catch {
        /* best effort */
      }
    }
  });
}

/**
 * Check whether a path exists.
 * @param {string} file
 * @returns {boolean}
 */
function exists(file) {
  try {
    fs.accessSync(file);
    return true;
  } catch {
    return false;
  }
}

/**
 * Read a UTF-8 file and trim surrounding whitespace.
 * @param {string} file
 * @returns {string}
 */
const readTrim = (file) => {
  try {
    return fs.readFileSync(file, 'utf8').trim();
  } catch {
    return '';
  }
};

/**
 * No-op progress callback.
 * @returns {void}
 */
const noProgress = () => {};

const RENAME_BACKOFF = [0, 250, 500, 1000, 2000, 4000];
const renameTunables = { backoff: RENAME_BACKOFF };

/**
 * Block the current thread for a short interval.
 * @param {number} ms
 * @returns {void}
 */
function sleepSync(ms) {
  if (ms > 0) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * Rename a path, retrying transient Windows locks.
 * @param {string} from
 * @param {string} to
 * @returns {void}
 */
function renameRetry(from, to) {
  let last = null;
  for (const ms of renameTunables.backoff) {
    sleepSync(ms);
    try {
      fs.renameSync(from, to);
      return;
    } catch (e) {
      last = e;
      if (!/^(EBUSY|EPERM|EACCES)$/.test(e.code || '')) break;
    }
  }
  try {
    fs.unlinkSync(from);
  } catch {
    /* already gone */
  }
  throw upd.explainError(last, to);
}

renameTunables.attemptMs = 30000;

/**
 * Reject a promise if it does not settle in time.
 * @param {Promise<unknown>} promise
 * @param {number} ms
 * @param {string} what
 * @returns {Promise<unknown>}
 */
async function withTimeout(promise, ms, what) {
  let timer;
  const cut = new Promise((_, reject) => {
    timer = setTimeout(
      () =>
        reject(
          Object.assign(
            new Error(
              `${what} did not finish within ${Math.round(ms / 1000)} s (an antivirus scan or another program is holding the file)`,
            ),
            { code: 'ETIMEDOUT' },
          ),
        ),
      ms,
    );
  });
  try {
    return await Promise.race([promise, cut]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Async variant of renameRetry.
 * @param {string} from
 * @param {string} to
 * @returns {Promise<void>}
 */
async function renameRetryAsync(from, to) {
  let last = null;
  for (const ms of renameTunables.backoff) {
    if (ms > 0) await new Promise((resolve) => setTimeout(resolve, ms));
    try {
      await withTimeout(
        fs.promises.rename(from, to),
        renameTunables.attemptMs,
        `Renaming ${path.basename(to)}`,
      );
      return;
    } catch (e) {
      last = e;
      if (e.code === 'ETIMEDOUT' || e.code === 'ENOENT') {
        if (!fs.existsSync(from) && fs.existsSync(to)) return;
      }
      if (!/^(EBUSY|EPERM|EACCES|ETIMEDOUT)$/.test(e.code || '')) break;
    }
  }
  try {
    fs.unlinkSync(from);
  } catch {
    /* already gone */
  }
  throw upd.explainError(last, to);
}

/**
 * Copy a file while reporting progress.
 * @param {string} src
 * @param {string} dst
 * @param {Function} [tick]
 * @returns {Promise<void>}
 */
function copyFileP(src, dst, tick) {
  const part = dst + '.t2r-new';
  const done = () => renameRetryAsync(part, dst);
  return new Promise((resolve, reject) => {
    const fail = (e) => {
      try {
        fs.unlinkSync(part);
      } catch {
        /* already gone */
      }
      reject(upd.explainError(e, dst));
    };
    const size = fs.statSync(src).size;
    if (size < 8 << 20) {
      fs.promises
        .copyFile(src, part)
        .then(() => {
          tick(size);
          return done();
        })
        .then(resolve, fail);
      return;
    }
    const reader = fs.createReadStream(src, { highWaterMark: 4 << 20 });
    const writer = fs.createWriteStream(part);
    let failed = false;
    const stop = (e) => {
      if (failed) return;
      failed = true;
      reader.destroy();
      writer.destroy();
      fail(e);
    };
    reader.on('data', (chunk) => tick(chunk.length));
    reader.on('error', stop);
    writer.on('error', stop);
    writer.on('finish', () => {
      if (failed) return;
      done().then(resolve, (e) => {
        failed = true;
        reject(e);
      });
    });
    reader.pipe(writer);
  });
}

/**
 * True when two paths are the same folder or file (case, trailing slashes, junctions, symlinks, hard links).
 * A client folder that is the game folder makes t2r-slim rebuild the client's own winmm.dll in place.
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
function sameLocation(a, b) {
  if (!a || !b) return false;
  const real = (p) => {
    try {
      return fs.realpathSync.native(p);
    } catch {
      return path.resolve(p);
    }
  };
  const norm = (p) => real(p).replace(/[/]+$/, '').toLowerCase();
  if (norm(a) === norm(b)) return true;
  try {
    const x = fs.statSync(a, { bigint: true }),
      y = fs.statSync(b, { bigint: true });
    return x.ino !== 0n && x.ino === y.ino && x.dev === y.dev;
  } catch {
    return false;
  }
}

module.exports = {
  sameLocation,
  run,
  exists,
  readTrim,
  noProgress,
  sleepSync,
  renameTunables,
  renameRetry,
  renameRetryAsync,
  withTimeout,
  copyFileP,
};
