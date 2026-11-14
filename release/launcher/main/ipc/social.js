/**
 * @file IPC handlers for friends and party.
 */
'use strict';

/**
 * Register friends/party IPC handlers.
 * @param {Function} handle
 * @param {{social: object}} deps
 * @returns {void}
 */
function register(handle, { social }) {
  handle('social:get', () => social.get());
  handle('social:act', (sub, arg) => social.act(sub, arg));
}

module.exports = { register };
