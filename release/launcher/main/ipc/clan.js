/**
 * @file IPC handlers for clan data.
 */
'use strict';

/**
 * Register clan IPC handlers.
 * @param {Function} handle
 * @param {{clan: object}} deps
 * @returns {void}
 */
function register(handle, { clan }) {
  handle('clan:get', () => clan.getClan());
  handle('clanfeed:get', (since, lang) => clan.getClanFeed(since, lang));
  handle('news:get', () => clan.getNews());
  handle('news:media', (src) => clan.getNewsMedia(src));
}

module.exports = { register };
