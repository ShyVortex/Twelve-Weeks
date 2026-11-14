/**
 * @file IPC handlers for update progress and cancellation.
 */
'use strict';

/**
 * Register update IPC handlers.
 * @param {Function} handle
 * @param {{jobs: object, getWindow: Function}} deps
 * @returns {void}
 */
function register(handle, { jobs, getWindow, ban }) {
  handle('ban:get', () => (ban ? ban.current() : { banned: false, reason: '' }));
  handle('update:run', () => jobs.runUpdate());
  handle('update:verify', () => jobs.runUpdate({ full: true }));
  handle('update:cancel', () => jobs.cancel());
  handle('play:start', (options) => jobs.runPlay(options));
  handle('play:sp', () => jobs.runPlaySp());
  handle('launcher:update', () => jobs.selfUpdate());

  handle('launcher:rest', (on) => {
    const window = getWindow();
    try {
      if (
        window &&
        !window.isDestroyed() &&
        typeof window.webContents.setBackgroundThrottling === 'function'
      )
        window.webContents.setBackgroundThrottling(!!on);
      if (on === 'run' && window && !window.isDestroyed() && !window.isMinimized())
        window.minimize();
    } catch {
      /* the window may be closing */
    }
    return {};
  });
}

module.exports = { register };
