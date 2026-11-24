/**
 * @file IPC handlers for the MAPS tab: Part I location, DLC state and tester import.
 */
'use strict';

const path = require('path');
const { dialog } = require('electron');
const maps = require('../../lib/maps');
const mapsRemote = require('../../lib/maps-remote');
const mapsConvert = require('../../lib/maps-convert');

/**
 * Register the MAPS handlers.
 * @param {Function} handle
 * @param {object} deps
 * @returns {void}
 */
function register(handle, { config, getWindow, jobs, paths, runtime, player }) {
  const sids = async () => (player ? await player.readSteamIds() : []);
  // may this PC download the server pack? true / false (the server said no: 404) / null (not known: offline, server down - asked again)
  let p1Server = null;
  const serverPack = async () => {
    if (p1Server !== null) return p1Server;
    try {
      await mapsRemote.fetchRemotePack(paths.fileHost(), await sids());
      p1Server = true;
    } catch (e) {
      if (/not available yet/i.test((e && e.message) || '')) p1Server = false;
    }
    return p1Server;
  };
  // does the update server list the Part I importer for this game data? (same caching as serverPack; null = not known, asked again)
  let p1Importer = null;
  const importer = async () => {
    if (p1Importer !== null) return p1Importer;
    try {
      await mapsConvert.fetchImporter(paths.fileHost());
      p1Importer = true;
    } catch (e) {
      if (/not available/i.test((e && e.message) || '')) p1Importer = false;
    }
    return p1Importer;
  };
  const state = () => ({
    ...maps.mapsState(config.values, { clientDir: paths.clientDir() }),
    converter: !!mapsConvert.converterPath(runtime && runtime.userData) || p1Importer === true,
    // an earlier import: INSTALL FROM MY PART I works without Part I installed (part1.dat is rebuilt from the earlier one)
    reimport: mapsConvert.hasEarlierImport(
      path.join(mapsConvert.importerDir(runtime && runtime.userData), 'work'),
    ),
  });
  handle('maps:state', async () => {
    const [pack] = await Promise.all([serverPack(), importer()]);
    return { state: { ...state(), serverPack: pack } };
  });

  // pick the Part I folder; only a validated install is saved
  handle('maps:pick-p1', async () => {
    const picked = await dialog.showOpenDialog(getWindow(), {
      title: 'Select the folder that contains tlou-i.exe',
      properties: ['openDirectory'],
    });
    if (picked.canceled || !picked.filePaths[0]) return { picked: false };
    const check = maps.validatePart1Dir(picked.filePaths[0]);
    if (!check.ok) throw Object.assign(new Error(check.reason), { vars: check.vars });
    config.values.tlou1_dir = picked.filePaths[0];
    config.save();
    return { picked: true, state: state() };
  });

  handle('maps:clear-p1', async () => {
    config.values.tlou1_dir = '';
    config.save();
    return { state: state() };
  });

  // TEMPORARY playtester pack: what the server offers (size) / the download itself (progress goes out as 'progress' events)
  handle('maps:remote', async () => {
    const r = await mapsRemote.fetchRemotePack(paths.fileHost(), await sids());
    return { remote: { pack: r.pack, ver: r.ver, total: r.total, files: r.files.length } };
  });

  handle('maps:convert', async () => {
    const r = await jobs.runMapsConvert();
    return { ...r, state: state() };
  });

  handle('maps:download', async () => {
    const r = await jobs.runMapsDownload(await sids());
    return { ...r, state: state() };
  });

  // tester path: the dev sends the map files, the tester picks them here
  handle('maps:import', async () => {
    const picked = await dialog.showOpenDialog(getWindow(), {
      title: 'Select the map files',
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'Map pack files', extensions: ['psarc', 'pak', 'txt'] }],
    });
    if (picked.canceled || !picked.filePaths.length) return { picked: false };
    const r = maps.importFiles(config.values.game_dir, picked.filePaths);
    return { picked: true, ...r, state: state() };
  });
}

module.exports = { register };
