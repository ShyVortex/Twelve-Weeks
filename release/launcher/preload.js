/**
 * @file Sandboxed preload bridge exposing the f2 API to the renderer.
 */
'use strict';
const { contextBridge, ipcRenderer, webUtils } = require('electron');
// macro for returning an ipc invoker
const call =
  (channel) =>
  (...args) =>
    ipcRenderer.invoke(channel, ...args);
// macro for listening to ipc on
const on = (channel) => (callback) => {
  const handler = (_eventobj, arg) => callback(arg);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
};

contextBridge.exposeInMainWorld('f2', {
  getConfig: call('cfg:get'),
  setConfig: call('cfg:set'),
  info: call('app:info'),
  detectGame: call('game:detect'),
  pickGame: call('game:pick'),
  pickDir: call('dir:pick'),
  mapsState: call('maps:state'),
  mapsPickP1: call('maps:pick-p1'),
  mapsClearP1: call('maps:clear-p1'),
  mapsImport: call('maps:import'),
  mapsRemote: call('maps:remote'),
  mapsDownload: call('maps:download'),
  mapsConvert: call('maps:convert'),
  steamState: call('steam:state'),
  steamAdd: call('steam:add'),
  steamRemove: call('steam:remove'),
  checkState: call('state:check'),
  serverStatus: call('server:status'),
  playersRoster: call('players:roster'),
  news: call('news:get'),
  newsMedia: call('news:media'),
  clan: call('clan:get'),
  social: call('social:get'),
  socialAct: call('social:act'),
  playerName: call('player:name'),
  i18n: call('i18n:get'),
  clanFeed: call('clanfeed:get'),
  reportFiles: call('report:files'),
  sendReport: call('report:send'),
  reportPlayers: call('report:players'),
  reportPlayer: call('report:player'),
  onReportProgress: on('report-progress'),
  ban: call('ban:get'),
  update: call('update:run'),
  verify: call('update:verify'),
  cancel: call('update:cancel'),
  play: call('play:start'),
  playSp: call('play:sp'),
  spStatus: call('sp:status'),
  spSwitch: call('sp:switch'),
  reinstall: call('game:reinstall'),
  gameRunning: call('game:running'),
  steam: call('steam:status'),
  rest: call('launcher:rest'),
  rpcSet: call('rpc:set'),
  rpcGameEnded: call('rpc:game-ended'),
  updateLauncher: call('launcher:update'),
  log: call('app:log'),
  openPath: call('open:path'),
  openUrl: call('open:url'),
  win: call('win:ctl'),
  saveLoadout: call('loadout:save'),
  loadoutSync: call('loadout:sync'),
  attList: call('report:att-list'),
  attAdd: call('report:att-add'),
  attPick: call('report:att-pick'),
  attPaste: call('report:att-paste'),
  attRemove: call('report:att-remove'),
  // files dropped onto the window: the paths are read here (File objects do not cross the bridge)
  onDropFiles: (cb) => {
    document.addEventListener(
      'drop',
      (e) => {
        const fl = [...((e.dataTransfer && e.dataTransfer.files) || [])];
        if (!fl.length) return;
        e.preventDefault();
        const paths = fl
          .map((f) => {
            try {
              return webUtils.getPathForFile(f);
            } catch {
              return '';
            }
          })
          .filter(Boolean);
        if (paths.length) cb(paths);
      },
      true,
    );
  },
  onLog: on('log'),
  onProgress: on('progress'),
  onBusy: on('busy'),
});
