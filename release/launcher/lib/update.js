/**
 * @file Public facade for manifests, downloads, staging and launcher updates.
 */
'use strict';

// Manifest-based client updater: per-file sha256, resumable ranged downloads, verify / repair.
// Protocol: see release/launcher/API.md. Split into domain modules under lib/update/.
const { safeRel, tunables, isNetErr, baseUrl } = require('./update/util');
const { explainError, ensureSpace, freeBytes } = require('./update/errors');
const { resetDown, getJson, getBuffer, fetchManifest } = require('./update/net');
const hosts = require('./update/hosts');
const {
  writeFileAtomic,
  sha256File,
  diffFiles,
  downloadAll,
  downloadFile,
} = require('./update/files');
const {
  journalPath,
  pruneOld,
  applyStaged,
  recoverStaged,
  sweepStale,
} = require('./update/staging');
const {
  refuseIfGameRunning,
  assertWritableNextTo,
  downloadLauncher,
  cmpVersion,
  clearJournal,
  hasPendingUpdate,
} = require('./update/launcher');

module.exports = {
  hosts,
  assertWritableNextTo,
  clearJournal,
  hasPendingUpdate,
  tunables,
  explainError,
  ensureSpace,
  freeBytes,
  applyStaged,
  recoverStaged,
  sweepStale,
  refuseIfGameRunning,
  journalPath,
  writeFileAtomic,
  isNetErr,
  resetDown,
  getJson,
  getBuffer,
  fetchManifest,
  diffFiles,
  downloadAll,
  downloadFile,
  pruneOld,
  downloadLauncher,
  sha256File,
  cmpVersion,
  safeRel,
  baseUrl,
};
