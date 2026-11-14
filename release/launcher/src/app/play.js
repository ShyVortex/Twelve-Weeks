/**
 * @file Renderer Play action and the surrounding game/progress event wiring.
 */
'use strict';

/**
 * Start the game flow through main and handle user-facing failures.
 * @returns {Promise<void>}
 */
async function doPlay() {
  if (banState.banned) {
    toast(banText(), false, T('YOU ARE BANNED'));
    return;
  }
  if (steamDown) {
    toast('Start Steam first - Twelve Weeks needs Steam running');
    return;
  }
  if (!state || !state.gameOk) {
    gotoSettings('game');
    const r = await f2.detectGame();
    if (r.ok) {
      await loadConfig();
      fillSettings();
      await refresh();
    }
    return;
  }
  if (!sp && !state.server) {
    gotoSettings('game');
    return;
  }
  if (!sp && state.offline && !state.installed) {
    await refresh();
    if (state.offline && !state.installed)
      toast(
        'Cannot reach the update server and no client is installed yet. Try again in a moment.',
      );
    return;
  }
  if (!sp && state.toDownload && state.toDownload.files > 0) {
    if (!(await doUpdate('update'))) return;
  } // single player: nothing is downloaded or installed, the client update waits for SWITCH TO MP
  // a launcher update waits for this moment (idle, before PLAY), once per version (a wrong manifest must not loop restarts); it restarts the launcher
  if (!sp && state.launcherUpdate && state.launcherUpdate.url) {
    let tried = null;
    try {
      tried = localStorage.getItem('f2-selfupd');
    } catch {}
    if (tried !== String(state.launcherUpdate.version)) {
      try {
        localStorage.setItem('f2-selfupd', String(state.launcherUpdate.version));
      } catch {}
      showProgress({
        phase: 'launcher-swap',
        label: 'Updating the launcher',
        unit: 'none',
        done: 0,
        total: 0,
      });
      const u = await f2.updateLauncher();
      if (u.ok) return; // the launcher restarts itself; press PLAY again then
      hideProgress(); // could not (not a packaged exe, offline ...): play with this version
    }
  }
  Snd.play('launch');
  gs = PlayState.gameState(gs, { type: 'play-begin' });
  renderButtons(); // the music keeps playing (ducked by the progress bar) until the game window is up
  const r = sp ? await f2.playSp() : await f2.play({ skipCheck: $('in-skipcheck').checked });
  hideProgress();
  if (!r.ok) {
    gs = PlayState.gameState(gs, { type: 'play-end', ok: false });
    renderButtons();
    toast(r.error);
    logline(r.error);
    await f2.rpcGameEnded().catch(() => {
      /* presence is cosmetic */
    });
    restorePresence();
    await refresh();
    Mus.setGame(false);
    Mus.setEnabled(cfg.music !== false);
    applyRest();
    return;
  }
  logline();
  gs = PlayState.gameState(gs, {
    type: 'play-end',
    ok: true,
    windowUp: !!r.windowUp,
  });
  Mus.setGame(gs.s === 'running');
  renderButtons();
  applyRest();
}
f2.onBusy((b) => {
  busy = b;
  renderButtons();
});
f2.onProgress((p) => {
  if (lupBusy) {
    const sub = $('loading').querySelector('.ld-sub');
    if (p.unit === 'bytes' && p.total)
      sub.textContent = T('{pct}%  {a} of {b}', {
        pct: ((100 * p.done) / p.total).toFixed(0),
        a: fmtBytes(p.done),
        b: fmtBytes(p.total),
      });
    return;
  }
  showProgress(p);
});
f2.onLog((m) => logline(m));
document.querySelector('[data-act=play]').onclick = () => {
  showView(null);
  doPlay();
};
$('mi-update').onclick = () => {
  showView(null);
  doUpdate('update');
};
$('f-update').onclick = () => doUpdate('update');
$('f-verify').onclick = () => doUpdate('verify');
$('f-repair').onclick = async () => {
  if (!state || !state.gameOk) return toast('Set the game folder first.');
  if (!(await doUpdate('verify'))) return;
  const r = await f2.reinstall();
  hideProgress();
  if (r.ok) toast('Client files verified and mod files re-installed into the game folder.', true);
  else toast(r.error);
};
$('f-cancel').onclick = () => f2.cancel();
$$('[data-open]').forEach((b) =>
  b.addEventListener('click', async () => {
    const r = await f2.openPath(b.dataset.open);
    if (!r.ok) toast(r.error);
  }),
);
$('b-detect').onclick = async () => {
  $('gamedir-msg').textContent = T('Searching...');
  const r = await f2.detectGame();
  await loadConfig();
  await refresh();
  fillSettings();
  gameMsg(r.ok ? T('{n} install(s) found.', { n: r.dirs.length }) : r.error);
};
$('b-pickgame').onclick = async () => {
  const r = await f2.pickGame();
  if (!r.ok) return gameMsg(r.error, true);
  if (r.picked) {
    await loadConfig();
    await refresh();
    fillSettings();
    gameMsg('Game folder set.');
  }
};
$('b-pickclient').onclick = async () => {
  const r = await f2.pickDir(T('Select the folder for the client files'));
  if (r.ok && r.picked) {
    $('in-clientdir').value = r.dir;
    await save({ client_dir: r.dir });
    refresh();
  }
};
/**
 * Show a game-folder status message.
 * @param {string} m
 * @param {boolean} [bad]
 * @returns {void}
 */
function gameMsg(m, bad) {
  const e = $('gamedir-msg');
  e.textContent = T(m);
  e.className = bad ? 'bad' : 'good';
}
$('b-launcher-update').onclick = async () => {
  const r = await f2.updateLauncher();
  if (!r.ok) toast(r.error);
};
