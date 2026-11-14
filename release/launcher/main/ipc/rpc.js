/**
 * @file IPC handlers for Rich Presence updates coming from the renderer.
 */
'use strict';

const presence = require('../../lib/rpc/presence');

/**
 * Register Rich Presence IPC handlers.
 * @param {Function} handle
 * @returns {void}
 */
function register(handle) {
  // The renderer only sends display strings: keep them short and ignore anything else.
  // `presence.menu` decides whether the launcher may show them right now (the
  // mod or a vanilla game may own presence instead).
  handle('rpc:set', (activity) => {
    if (!activity || typeof activity !== 'object') return {};
    const clip = (s) => (typeof s === 'string' ? s.slice(0, 128) : '');
    return presence.menu({
      details: clip(activity.details),
      state: clip(activity.state),
    });
  });

  // The game stopped (or a launch failed): take presence back and clear the
  // stale in-game activity. The renderer re-sets the current screen afterwards.
  handle('rpc:game-ended', () => presence.ended());
}

module.exports = { register };
