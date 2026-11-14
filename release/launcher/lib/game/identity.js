/**
 * @file Player-name normalization and token identity helpers.
 */
'use strict';

const crypto = require('crypto');

/**
 * Normalize a player name for display and file use.
 * @param {string} name
 * @returns {string}
 */
function cleanName(name) {
  let value = String(name || '')
    .replace(/[^\x20-\x7E]/g, '')
    .trim();
  if (value.length > 15) value = value.slice(0, 15).trim();
  return value;
}

/**
 * Create a fresh player token id.
 * @returns {string}
 */
function newTokenId() {
  return crypto.randomBytes(12).toString('hex');
}

/**
 * Derive the 64-byte identity token from a player name and id.
 * @param {string} name
 * @param {string} idHex
 * @returns {string}
 */
function nameToken(name, idHex) {
  const raw = Buffer.alloc(32);
  raw.write('T2N:', 0, 'ascii');
  Buffer.from(name, 'utf8').subarray(0, 15).copy(raw, 4);
  Buffer.from(idHex, 'hex').copy(raw, 20);
  return raw.toString('hex');
}

/**
 * Recover the display name from a player token.
 * @param {string} token
 * @returns {string}
 */
function tokenName(token) {
  if (!/^[0-9a-fA-F]{64}$/.test(token || '')) return null;
  const buffer = Buffer.from(token, 'hex');
  if (buffer.toString('ascii', 0, 4) !== 'T2N:') return null;
  const end = buffer.indexOf(0, 4);
  return end < 0 ? null : buffer.toString('utf8', 4, end);
}

module.exports = { cleanName, newTokenId, nameToken, tokenName };
