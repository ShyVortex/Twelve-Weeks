/**
 * @file Create and configure the main Electron window.
 */
'use strict';

const path = require('path');
const { BrowserWindow, dialog, shell } = require('electron');
const install = require('./install');

/**
 * Create and configure the main Electron window.
 * @param {{ rootDir: string, config: object, jobs: object, runtime: object, locale: object }} options
 * @returns {import('electron').BrowserWindow}
 */
function createMainWindow({ rootDir, config, jobs, runtime, locale }) {
  const I18N = locale.I18N;
  const window = new BrowserWindow({
    width: Math.max(1300, Math.min((config.values.win && config.values.win.w) || 1440, 3000)),
    height: Math.max(760, Math.min((config.values.win && config.values.win.h) || 860, 2000)),
    minWidth: 1300,
    minHeight: 760,
    frame: false,
    backgroundColor: '#070808',
    show: false,
    title: 'Twelve Weeks Launcher',
    icon: path.join(rootDir, 'assets', 'icon.png'),
    webPreferences: {
      autoplayPolicy: 'no-user-gesture-required',
      preload: path.join(rootDir, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });

  window.removeMenu();
  if (runtime.installRoot) {
    // taskbar pin / jump list: relaunch the fixed exe (never a versioned path) with the app's own icon
    try {
      window.setAppDetails({
        appId: install.AUMID,
        appIconPath: path.join(runtime.installRoot, 'icon.ico'),
        appIconIndex: 0,
        relaunchCommand: `"${process.execPath}"`,
        relaunchDisplayName: install.DISPLAY,
      });
    } catch {
      /* cosmetic */
    }
  }
  window.on('close', (event) => {
    if (!jobs.shouldConfirmClose() || window.__forceClose) return;
    const response = dialog.showMessageBoxSync(window, {
      type: 'question',
      buttons: [I18N.T('Keep working'), I18N.T('Quit anyway')],
      defaultId: 0,
      cancelId: 0,
      title: 'Twelve Weeks',
      message: I18N.T(
        jobs.kind === 'play'
          ? 'The game is still being prepared / started.'
          : 'An update is still running.',
      ),
      detail: I18N.T('Quitting now stops it; it starts over the next time.'),
    });
    if (response === 0) event.preventDefault();
    else window.__forceClose = true;
  });

  if (runtime.muted) window.webContents.setAudioMuted(true);
  window.loadFile(
    path.join(rootDir, 'src', 'index.html'),
    runtime.muted ? { query: { mute: '1' } } : undefined,
  );

  let resizeTimer = null;
  window.on('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (window && !window.isDestroyed() && !window.isMaximized() && !window.isMinimized()) {
        const [width, height] = window.getSize();
        config.values.win = { w: width, h: height };
        config.save();
      }
    }, 600);
  });

  window.once('ready-to-show', () => {
    if (!runtime.isScreenshot) window.show();
    else {
      window.setPosition(-6000, 100);
      window.showInactive();
    }
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event) => event.preventDefault());

  return window;
}

module.exports = { createMainWindow };
