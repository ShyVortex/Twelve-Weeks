/**
 * @file Shared update utilities: safe paths, sleep, byte formatting and error classification.
 */
'use strict';

const path = require('path');
const zlib = require('zlib');

/**
 * Validate and normalize a manifest-relative path.
 * @param {string} p
 * @returns {string}
 */
function safeRel(p) {
  // manifest paths are relative, forward slashes, no traversal
  const n = path.posix.normalize(String(p).replace(/\\/g, '/'));
  if (!n || n.startsWith('/') || n.startsWith('../') || n === '..' || /^[A-Za-z]:/.test(n))
    throw new Error(`Unsafe path in manifest: ${p}`);
  return n;
}

// ---- robustness helpers (launcher robustness)
// Delays are tunables so the tests can shrink them. lockBackoff: retries of a rename onto a file another program holds open (antivirus scan,
// the Steam helper, the game); netBackoffMs: first wait after a dropped connection (grows, capped at 8 s); maxStall: tries in a row without a
// single new byte before a download gives up (a tunnel that is down for ~30 s is survived, a dead server is not waited on for ever).
const tunables = {
  lockBackoff: [0, 250, 500, 1000, 2000, 4000],
  netBackoffMs: 800,
  maxStall: 6,
  freeBytes: null /* tests only: (dir) => bytes, replaces the real drive query */,
};
/**
 * Wait for a number of milliseconds.
 * @param {number} ms
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LOCK_CODES = new Set(['EBUSY', 'EPERM', 'EACCES', 'EMFILE', 'ENFILE', 'EAGAIN']);
const SPACE_CODES = new Set(['ENOSPC', 'EDQUOT']);
/**
 * Format a byte count as megabytes.
 * @param {number} n
 * @returns {string}
 */
const mb = (n) => `${Math.max(1, Math.round(n / 1048576))} MB`;
/**
 * Check whether an error is a retryable network error.
 * @param {unknown} e
 * @returns {boolean}
 */
const isNetErr = (e) =>
  /timeout|ECONN|ENOTFOUND|EHOSTUNREACH|ENETUNREACH|EAI_AGAIN/i.test(
    String((e && (e.code || e.message)) || e),
  );

/**
 * Normalize an update host base URL.
 * @param {string} b
 * @returns {string}
 */
function baseUrl(b) {
  return String(b).replace(/\/+$/, '');
}

// codecs decodable with Node's built-in zlib (no native addons); zstd is deliberately absent (Electron 33 = Node 20, no zlib zstd)
const DECODERS = {
  gzip: () => zlib.createGunzip(),
  br: () => zlib.createBrotliDecompress(),
};

module.exports = {
  safeRel,
  tunables,
  sleep,
  LOCK_CODES,
  SPACE_CODES,
  mb,
  isNetErr,
  baseUrl,
  DECODERS,
};
