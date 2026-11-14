/**
 * @file Public facade for report collection, packaging, transport and system data.
 */
'use strict';

// REPORT A BUG: collect logs, scrub secrets, zip, POST to the update server (/report, API.md). Nothing here ever reads or sends the player's token
// file (tlou-ii-mp.json / t2r-client.json): text logs have every 64-hex run (the name token) and "token": "..." values replaced.
// Split into domain modules under lib/report/.
const { ZIP_CAP } = require('./report/constants');
const { zipBuild } = require('./report/zip');
const { scrub, scrubDump } = require('./report/scrub');
const { dumpInfo, binInfo, logIdent, stampMatchesBuild } = require('./report/artifacts');
const { collect } = require('./report/collect');
const { build } = require('./report/build');
const { werLocalDumps, systemInfo } = require('./report/system');
const {
  post,
  retryable,
  retryableStatus,
  queueList,
  enqueue,
  flushQueue,
} = require('./report/transport');

module.exports = {
  werLocalDumps,
  scrubDump,
  dumpInfo,
  binInfo,
  logIdent,
  stampMatchesBuild,
  collect,
  build,
  post,
  systemInfo,
  scrub,
  zipBuild,
  ZIP_CAP,
  enqueue,
  flushQueue,
  queueList,
  retryable,
  retryableStatus,
};
