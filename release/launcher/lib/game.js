/**
 * @file Public facade for game discovery, installation, Steam integration and Play.
 */
'use strict';

// Game folder detection, mod install and game start. A faithful port of
// release/client/T2R-Play.ps1, split into domain modules under lib/game/.
const spmode = require('./spmode');

const { cleanName, newTokenId, nameToken, tokenName } = require('./game/identity');
const {
  EXE_TIMESTAMP,
  EXE_IMAGE_SIZE,
  steamPath,
  parseLibraryFolders,
  findGameDirs,
  isGameDir,
  exeBuild,
} = require('./game/discovery');
const { run, exists, readTrim, renameTunables, withTimeout, sameLocation } = require('./game/util');
const { getDllTarget, setDllTarget, verifyWinmm } = require('./game/dll');
const { parseServer, resolveServer, probeServer } = require('./game/server');
const { runSlim, installMod, missingModFiles, modCurrent } = require('./game/install');
const {
  psGameProcs,
  killProc,
  helperRunning,
  spDisable,
  spEnable,
  spTopUp,
  spModeFor,
  gameRunning,
  gameStatus,
} = require('./game/processes');
const { startFailure, STEAM_MSG, steamRunning, steamGate } = require('./game/steam');
const {
  playSingleplayer,
  modLoadedSince,
  awaitGameStart,
  waitForGameWindow,
  play,
} = require('./game/play');
const { testHooks, startedPids } = require('./game/state');

module.exports = {
  sameLocation,
  spDisable,
  spEnable,
  spTopUp,
  spModeFor,
  playSingleplayer,
  helperRunning,
  spmode,
  steamPathPublic: steamPath,
  cleanName,
  newTokenId,
  nameToken,
  tokenName,
  findGameDirs,
  isGameDir,
  parseLibraryFolders,
  getDllTarget,
  setDllTarget,
  verifyWinmm,
  renameTunables,
  startFailure,
  parseServer,
  resolveServer,
  probeServer,
  installMod,
  modCurrent,
  steamRunning,
  steamGate,
  STEAM_MSG,
  gameRunning,
  gameStatus,
  killProc,
  waitForGameWindow,
  runSlim,
  psGameProcs,
  testHooks,
  startedPids,
  play,
  awaitGameStart,
  modLoadedSince,
  withTimeout,
  readTrim,
  exists,
  run,
  exeBuild,
  missingModFiles,
  EXE_TIMESTAMP,
  EXE_IMAGE_SIZE,
};
