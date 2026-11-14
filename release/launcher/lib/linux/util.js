'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Check whether a path exists.
 * @param {string} p
 * @returns {boolean}
 */
const exists = (p) => {
  try {
    fs.accessSync(p);
    return true;
  } catch {
    return false;
  }
};

/**
 * Check whether a path is a directory.
 * @param {string} p
 * @returns {boolean}
 */
const isDir = (p) => {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
};

/**
 * Resolve a path to its real filesystem location.
 * @param {string} p
 * @returns {string}
 */
const real = (p) => {
  try {
    return fs.realpathSync(p);
  } catch {
    return p;
  }
};

/**
 * Read a text file, returning an empty string on failure.
 * @param {string} p
 * @returns {string}
 */
const readText = (p) => {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch {
    return '';
  }
};

/**
 * Wait for a number of milliseconds.
 * @param {number} ms
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Convert a POSIX path to a Wine-compatible Windows path.
 * @param {string} p
 * @returns {string}
 */
const winPath = (p) => 'Z:' + path.resolve(p).replace(/\//g, '\\');

module.exports = { exists, isDir, real, readText, sleep, winPath };
