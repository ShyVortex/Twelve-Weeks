/**
 * @file Launcher logger writing to launcher.log and the renderer log channel.
 */
'use strict';

const fs = require('fs');
const path = require('path');

/**
 *  A function that returns a logger callback for writing to launcher.log
 */
function createLogger({ logDir, send }) {
  return function log(message) {
    const line = `[${new Date().toISOString()}] ${message}`;
    try {
      fs.mkdirSync(logDir, { recursive: true });
      fs.appendFileSync(path.join(logDir, 'launcher.log'), line + '\n');
    } catch {
      /* logging must never break the launcher */
    }
    send('log', message);
  };
}

module.exports = { createLogger };
