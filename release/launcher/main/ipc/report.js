/**
 * @file IPC handlers for report attachment and send operations.
 */
'use strict';

/**
 * Register report IPC handlers.
 * @param {Function} handle
 * @param {{report: object}} deps
 * @returns {void}
 */
function register(handle, { report }) {
  handle('report:files', (older) => report.files(older));
  handle('report:send', (form) => report.sendReport(form));
  handle('report:players', () => report.players());
  handle('report:player', (form) => report.reportPlayer(form));
  handle('report:att-list', () => report.list());
  handle('report:att-add', (paths) => report.add(paths));
  handle('report:att-pick', () => report.pick());
  handle('report:att-paste', (bytes) => report.paste(bytes));
  handle('report:att-remove', (id) => report.remove(id));
}

module.exports = { register };
