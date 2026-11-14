/**
 * @file Shared mutable state and test hooks for the game module.
 */
'use strict';

const startedPids = new Set();

const testHooks = {
  procs: null,
  steam: null,
  helper: null,
  spawn: null,
  helperWaitMs: undefined,
};

const ctx = { plat: process.platform, deps: {}, extra: {} };

module.exports = { startedPids, testHooks, ctx };
