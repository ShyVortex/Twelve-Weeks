/**
 * @file Linux/Steam Deck support: Proton discovery, Wine registry, process inspection and launch.
 */
'use strict';
// Linux (Steam + Proton / Steam Deck) support of the launcher: the counterpart of release/client/t2r-linux.py, with the one-time Steam
// launch option automated. The implementation lives in lib/linux/*; this module keeps the public surface used by lib/game.js.
//
// How a Linux session works:
//  1. the client files go into the game folder exactly like on Windows (a slim client is rebuilt by t2r-slim.exe run under Proton);
//  2. the Steam helper (t2r-steam.exe, the genuine Valve steam_api64.dll) runs through `proton run` in ITS OWN prefix OUTSIDE the game's
//     Steam launch, with SteamAppId=480 (a process inside the game's launch tree is TLOU2 to Steam whatever its environment says, and
//     Steam P2P only connects between Spacewar helpers) - the ext then touches <game>/t2r-alive.txt every 5 s and the helper follows it;
//  3. winmm.dll must load in place of the system one: Wine wants a native,builtin override. t2r-linux.py asked the player for the launch option
//     WINEDLLOVERRIDES="winmm=n,b" %command%; the launcher writes the same override into the game's Proton prefix registry instead
//     (HKCU\Software\Wine\DllOverrides, compatdata/2531310/pfx/user.reg) while the game is closed, so no launch option is needed;
//  4. the game is started through Steam (steam://rungameid/2531310), never directly.

const { APP_ID } = require('./linux/constants');
const { parseVdf, vget } = require('./linux/vdf');
const {
  steamRoots,
  parseLibraryFolders,
  steamLibraries,
  findGameDirs,
  isGameDir,
  launchOptions,
} = require('./linux/steam');
const { findProton, naturalCmp, protonEnv, helperArgs, slimCommand } = require('./linux/proton');
const { procList, gameProcs, helperProcs } = require('./linux/processes');
const { patchUserReg, userRegFor, findUserReg, prepareGamePrefix, REG_EDITS } = require('./linux/registry');
const { readState, writeState, stopHelper, startHelper } = require('./linux/helper');
const { winPath } = require('./linux/util');
const { steamLaunchCommand, whichSync, waitForGame } = require('./linux/launch');

module.exports = {
  APP_ID,
  parseVdf,
  vget,
  steamRoots,
  parseLibraryFolders,
  steamLibraries,
  findGameDirs,
  isGameDir,
  findProton,
  naturalCmp,
  winPath,
  protonEnv,
  helperArgs,
  procList,
  gameProcs,
  helperProcs,
  patchUserReg,
  userRegFor,
  findUserReg,
  prepareGamePrefix,
  launchOptions,
  stopHelper,
  startHelper,
  slimCommand,
  steamLaunchCommand,
  whichSync,
  waitForGame,
  readState,
  writeState,
  REG_EDITS,
};
