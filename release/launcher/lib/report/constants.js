/**
 * @file Shared limits and constants for report collection and transport.
 */
'use strict';

const TAIL = 20 * 1024 * 1024; // a log bigger than this is cut to its last 20 MB
const ZIP_CAP = 60 * 1024 * 1024; // whole report
const MATCH_RAW_CAP = 120 * 1024 * 1024; // per-match logs together, unpacked
const DUMP_MAX = 2; // older (stale) dumps, only when the player asks for them
const DUMP_ENTRY_MAX = 250 * 1024 * 1024; // the server refuses one unpacked file above 256 MB (report_store.MAX_ENTRY): a bigger dump is named in the report, not sent
const QUEUE_MAX_FILES = 5,
  QUEUE_MAX_BYTES = 150 * 1024 * 1024,
  QUEUE_MAX_AGE = 14 * 86400000;

module.exports = {
  TAIL,
  ZIP_CAP,
  MATCH_RAW_CAP,
  DUMP_MAX,
  DUMP_ENTRY_MAX,
  QUEUE_MAX_FILES,
  QUEUE_MAX_BYTES,
  QUEUE_MAX_AGE,
};
