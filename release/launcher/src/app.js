/**
 * @file Renderer entry point: performs startup orchestration after all classic scripts load.
 *
 * The renderer uses classic-script globals plus the index.html load order instead of ES modules:
 * this file runs last and may call any helper defined by an earlier src/app/*.js file. When adding
 * a file, register it in src/index.html before app.js and document the globals it publishes.
 */
'use strict';

// ---------------------------------------------------------------- init
/**
 * Start the renderer: load configuration and translations, bind UI, then run
 * the initial data refreshes under the startup overlay and install the polls.
 * @returns {Promise<void>}
 */
(async function init() {
  const t0 = performance.now();
  const cap = (p, ms) =>
    Promise.race([Promise.resolve(p).catch(() => null), new Promise((r) => setTimeout(r, ms))]); // never stuck: every startup task is done, failed or capped
  const overlay = $('loading');
  const hideOverlay = () => {
    if (lupBusy || banState.banned) return; // (a banned player keeps the ban screen) // (the end of startup hid the launcher-update overlay while the update downloaded, so the player saw nothing and closed it)
    if (!overlay.classList.contains('gone')) {
      overlay.classList.add('gone');
      window.__loadDone = true;
      f2.log('startup data loaded in ' + Math.round(performance.now() - t0) + ' ms');
    }
  };
  setTimeout(hideOverlay, 12000); // hard cap
  Snd.bind();
  startBanWatch(); // the ban screen first: a stored ban shows before anything else loads
  await loadConfig();
  await initLang();
  startGrain();
  bindSettings();
  bindMaps();
  fillSettings();
  applyLook();
  loadAbout();
  Loadout.init(cfg.loadout2, async (d) => {
    const r = await f2.saveLoadout(d);
    if (r && r.ok) Loadout.setStatus(r.status);
  });
  Mus.start(); // may start under the overlay
  // everything at once: game folder, update check + server status, news, clan (needs the game folder for the name file), feed
  const detect = f2.detectGame().then(() => loadConfig());
  const spReady = detect.then(() => loadSpStatus()); // the mode first: SP never asks for the clan
  spReady.then(() => syncLoadout());
  const tasks = [detect, refresh(), loadNews(), spReady.then(() => loadClanSummary())];
  Feed.start();
  await cap(Promise.allSettled(tasks), 11500);
  fillSettings();
  applyLook();
  hideOverlay();
  Social.start(); // friends + party: the badge on FRIENDS and the 'online' mark for the friends (not in SP mode)
  // periodic polls only change what really changed (text in place, no DOM rebuild), and never touch the state the Play flow owns
  let restN = 0;
  setInterval(async () => {
    if (busy === 'play') return;
    if (gs.s === 'running' && ++restN % 3) return; // each poll starts a powershell.exe: every 15 s (not 5) while the game runs
    const r = await f2.gameRunning();
    if (busy === 'play') return;
    const n = PlayState.gameState(gs, {
      type: 'poll',
      running: !!r.running,
      starting: !!r.starting,
    });
    const prev = gs.s;
    const changed = n.s !== gs.s;
    gs = n;
    if (changed) {
      Mus.setGame(gs.s === 'running');
      renderButtons();
      // the game (and the mod inside it) released presence: show the current screen again
      if ((prev === 'running' || prev === 'starting') && gs.s === 'idle')
        f2
          .rpcGameEnded()
          .then(restorePresence)
          .catch(() => {
            /* presence is cosmetic */
          });
    }
    applyRest();
  }, 5000);
  setInterval(syncLoadout, 3000);
  // game -> launcher: a name changed in-game (t2r-name.txt) shows here without reopening the launcher
  setInterval(async () => {
    if (busy === 'play') return;
    try {
      const r = await f2.playerName();
      if (!r.ok) return;
      updateName();
      if (document.activeElement !== $('in-name')) $('in-name').value = r.name;
    } catch (_) {
      /* next poll */
    }
  }, 3000);
  setInterval(() => loadNews(true), 120000); // news: re-read every 2 min (a failed first read, a newly published entry)
  setTimeout(() => {
    if (!newsOk) loadNews();
  }, 15000);
  renderSteam();
  pollSteam();
  setInterval(pollSteam, 4000);
  // A launcher left open never saw a newly published launcher / client (the manifest was read only at start) - re-check while idle
  setInterval(() => {
    if (!busy && gs.s === 'idle') refresh();
  }, 10000); // every 10 s while the game is not running
  setInterval(() => {
    if (!busy && gs.s === 'running') refresh();
  }, 60000); // game running: only to tell the player a newer build is out (autoClientUpdate)
  setInterval(async () => {
    if (!busy) {
      const st = await f2.serverStatus();
      if (st.ok) {
        status = st.status;
        renderStatus();
        Notices.update(st.status);
      }
      Players.tick(); // test feature: panel open -> refresh its list on this same cadence
    }
  }, 30000);
})();
