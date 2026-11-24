/**
 * @file Renderer settings binding, thumbnails, config loading and language switching.
 */
'use strict';

// ---------------------------------------------------------------- settings wiring
/**
 * Wire settings controls to config persistence and UI updates.
 * @returns {void}
 */
function bindSettings() {
  const dbc = (el, fn, ms = 500) => {
    let t;
    el.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    });
  };
  dbc($('in-clientdir'), async () => {
    await save({ client_dir: $('in-clientdir').value.trim() });
    refresh();
  });
  dbc(
    $('in-name'),
    async () => {
      await save({ custom_name: $('in-name').value.trim() });
      renderState();
    },
    300,
  );
  const fx = (id, key) => {
    $(id).onchange = async () => {
      cfg.effects[key] = $(id).checked;
      await save({ effects: { [key]: $(id).checked } });
      applyLook();
    };
  };
  fx('fx-grain', 'grain');
  fx('fx-motion', 'motion');
  $$('#lang-pick .fopt').forEach((b) =>
    b.addEventListener('click', () => {
      if (b.dataset.lang !== I18N.lang) setLang(b.dataset.lang);
    }),
  );
  $('in-vol').oninput = () => {
    cfg.volume = +$('in-vol').value;
    $('vol-v').textContent = cfg.volume + '%';
    Snd.setVolume(cfg.volume);
  };
  $('in-vol').onchange = () => {
    save({ volume: cfg.volume });
    Snd.play('tick');
  };
  $$('#mus-set .fopt').forEach((b) =>
    b.addEventListener('click', async () => {
      if ((cfg.musicSet || 'grim') === b.dataset.set) return;
      cfg.musicSet = b.dataset.set;
      await save({ musicSet: cfg.musicSet });
      applyLook();
    }),
  );
  $('in-music').onchange = async () => {
    cfg.music = $('in-music').checked;
    await save({ music: cfg.music });
    applyLook();
  };
  $('in-mvol').oninput = () => {
    cfg.musicVolume = +$('in-mvol').value;
    $('mvol-v').textContent = cfg.musicVolume + '%';
    Mus.setVolume(cfg.musicVolume);
  };
  $('in-mvol').onchange = () => save({ musicVolume: cfg.musicVolume });
  $('in-discord').onchange = async () => {
    cfg.rpc = { ...(cfg.rpc || {}), provider: $('in-discord').checked ? 'discord' : null };
    await save({ rpc: { provider: cfg.rpc.provider } }); // main/ipc/config.js swaps the presence adapter at once
    if (cfg.rpc.provider) restorePresence();
  };
  $('in-debug').onchange = async () => {
    cfg.debug_mode = $('in-debug').checked;
    await save({ debug_mode: cfg.debug_mode });
  };
  $('in-sounds').onchange = async () => {
    cfg.sounds = $('in-sounds').checked;
    await save({ sounds: cfg.sounds });
    applyLook();
  };
  $$('#bg-mode .fopt').forEach((b) =>
    b.addEventListener('click', async () => {
      cfg.bgMode = b.dataset.mode;
      await save({ bgMode: cfg.bgMode });
      applyLook();
    }),
  );
  $('bg-block').addEventListener('click', () =>
    denied("OVERRIDDEN BY FACTION'S CHOICE", "Your clan's faction picks the backgrounds."),
  );
  $('b-server').onclick = switchServer;
  fillThumbs();
  Scenes.onSet(fillThumbs); // the picker always shows the set that applies (the faction's; neutral only before it is known)
}
// ---------------------------------------------------------------- live / testing server switch (Settings > Game)
/**
 * Show the confirmation dialog (veil + panel); resolves true on confirm, false on cancel / Escape.
 * @param {string} title
 * @param {string} text
 * @param {string} yes
 * @returns {Promise<boolean>}
 */
function askConfirm(title, text, yes) {
  return new Promise((resolve) => {
    const box = $('confirm'),
      y = $('cfm-yes'),
      n = $('cfm-no'),
      prev = document.activeElement;
    $('cfm-t').textContent = T(title);
    $('cfm-d').textContent = T(text);
    y.textContent = T(yes);
    box.hidden = false;
    n.focus(); // the safe answer is the default
    const done = (v) => {
      box.hidden = true;
      document.removeEventListener('keydown', key, true);
      y.onclick = n.onclick = null;
      if (prev && prev.focus) prev.focus();
      resolve(v);
    };
    const key = (e) => {
      if (e.key === 'Escape') done(false);
      else if (e.key === 'Tab') {
        e.preventDefault();
        (document.activeElement === y ? n : y).focus();
      } else if (
        e.key === 'ArrowLeft' ||
        e.key === 'ArrowRight' ||
        e.key === 'ArrowUp' ||
        e.key === 'ArrowDown'
      ) {
        e.preventDefault();
        (document.activeElement === y ? n : y).focus();
      } else return;
      e.stopPropagation();
    };
    document.addEventListener('keydown', key, true);
    y.onclick = () => done(true);
    n.onclick = () => done(false);
  });
}
/**
 * Redraw the server switch button/text and the TESTING SERVER tag from the saved target.
 * @returns {void}
 */
function renderServerTarget() {
  const test = cfg.server_target === 'test';
  $('b-server').textContent = T(test ? 'SWITCH TO LIVE SERVER' : 'SWITCH TO TESTING SERVER');
  $('server-msg').textContent = T(
    test ? 'You are on the testing server.' : 'You are on the live server.',
  );
  $('test-tag').hidden = !test;
}
/**
 * Ask, then switch between the live and the testing server and reload everything that depends on it.
 * @returns {Promise<void>}
 */
async function switchServer() {
  if (busy || lupBusy || gs.s === 'running' || gs.s === 'starting')
    return denied('CANNOT SWITCH NOW', 'Finish the running update or quit the game first.');
  const toTest = cfg.server_target !== 'test';
  const ok = await askConfirm(
    toTest ? 'SWITCH TO TESTING SERVER' : 'SWITCH TO LIVE SERVER',
    toTest
      ? "You're about to switch the launcher from the live server to the testing server. Testing builds can be unstable and progress there is separate. Are you sure?"
      : "You're about to switch the launcher from the testing server back to the live server. Are you sure?",
    'SWITCH',
  );
  if (!ok) return;
  await save({ server_target: toTest ? 'test' : 'live' });
  renderServerTarget();
  f2.log(`server target: ${cfg.server_target}`);
  // everything that came from the old server is dropped; the update check runs against the new file host (a different client build is downloaded by itself)
  cuTried = '';
  cuTold = '';
  newsOk = false;
  newsSig = '';
  await refresh();
  loadNews(true);
  loadClanSummary();
  toast(
    T(toTest ? 'Now using the testing server.' : 'Now using the live server.'),
    true,
    T('SERVER SWITCHED'),
  );
}
/**
 * Render the background thumbnails for the active scene set.
 * @returns {void}
 */
function fillThumbs() {
  $('bg-field').classList.toggle('locked', Scenes.setName() !== 'neutral');
  if (Scenes.setName() !== 'neutral') Scenes.setMode('rotate', null);
  $('bg-set').textContent = T(
    {
      wlf: 'WLF set (your clan)',
      sera: 'Seraphite set (your clan)',
      neutral: 'Neutral set (no clan yet)',
    }[Scenes.setName()],
  );
  $('thumbs').innerHTML = Scenes.list()
    .map(
      ([id, name]) =>
        `<button class="th" data-id="${id}" data-snd="click" title="${T(name)}" style="background-image:${Scenes.url(id)}"></button>`,
    )
    .join('');
  $$('#thumbs .th').forEach((t) =>
    t.addEventListener('click', async () => {
      cfg.bgMode = 'pick';
      cfg.background = t.dataset.id;
      await save({ bgMode: 'pick', background: cfg.background });
      applyLook();
    }),
  );
  $$('#thumbs .th').forEach((t) =>
    t.classList.toggle(
      'active',
      (cfg.bgMode || 'rotate') === 'pick' && t.dataset.id === cfg.background,
    ),
  );
}
/**
 * Populate settings controls from the current config/state.
 * @returns {void}
 */
function fillSettings() {
  $('in-gamedir').value = state ? state.gameDir : cfg.game_dir || '';
  $('in-clientdir').value = cfg.client_dir || '';
  $('in-clientdir').placeholder = cfg.resolved.clientDir;
  // the field shows the name in use (in-game name file, custom name, Steam name ...), never empty; not overwritten while being typed in
  if (document.activeElement !== $('in-name'))
    $('in-name').value = (cfg.resolved && cfg.resolved.name) || cfg.custom_name || '';
  $('in-debug').checked = !!cfg.debug_mode;
  $('in-discord').checked = !!(cfg.rpc && cfg.rpc.provider === 'discord');
  renderServerTarget();
  $('fx-grain').checked = cfg.effects.grain;
  $('fx-motion').checked = cfg.effects.motion !== false;
  $('in-vol').value = cfg.volume;
  $('vol-v').textContent = cfg.volume + '%';
  $('in-sounds').checked = cfg.sounds;
  $('in-music').checked = cfg.music !== false;
  $('in-mvol').value = cfg.musicVolume == null ? 35 : cfg.musicVolume;
  $('mvol-v').textContent = $('in-mvol').value + '%';
}
/**
 * Load the resolved configuration from main.
 * @returns {Promise<void>}
 */
async function loadConfig() {
  cfg = await f2.getConfig();
}
// GEAR UP follows the game: its t2r-loadout.json is the truth, a saved edit goes to the game as a launcher file (main.js loadout:sync)
/**
 * Reconcile the loadout with the game-owned file.
 * @returns {Promise<void>}
 */
async function syncLoadout() {
  try {
    const r = await f2.loadoutSync();
    if (r && r.ok) {
      Loadout.setStatus(r.status);
      if (r.adopt) Loadout.adopt(r.adopt);
    }
  } catch (_) {}
}

// ---------------------------------------------------------------- language (English / Polish / Spanish: src/i18n/languages.js), live
let STR = null;
/**
 * Load translations and apply the saved language.
 * @returns {Promise<void>}
 */
async function initLang() {
  L10N.scan(); // remember the English markup before anything rewrites it
  STR = await f2.i18n();
  // one table per language (main/locale.js): a language never overwrites another one's entries
  for (const [code, table] of Object.entries((STR && STR.langs) || {})) I18N.load(table, code);
  setLang(cfg.resolved.lang, true);
}
/**
 * Switch the renderer language and refresh translated UI.
 * @param {string} l
 * @param {boolean} [silent]
 * @returns {void}
 */
function setLang(l, silent) {
  I18N.setLang(l);
  document.documentElement.lang = l;
  cfg.lang = l;
  cfg.resolved.lang = l;
  L10N.apply();
  $$('#lang-pick .fopt').forEach((b) => b.classList.toggle('active', b.dataset.lang === l));
  if (!silent) {
    save({ lang: l });
  }
  if (state) renderState();
  if (status) renderStatus();
  renderButtons();
  renderServerTarget();
  updateName();
  fillThumbs();
  loadAbout();
  if (typeof Report !== 'undefined' && Report.fillMaps) Report.fillMaps();
  Loadout.rerender();
  Clan.rerender();
  Social.rerender();
  if (typeof Feed !== 'undefined' && Feed.setLang) Feed.setLang(l); // feed language: daemon op 0xB4 lang byte + /clanfeed.json?lang= (main.js getClanFeed), ticker pool TICKER_PL
  if (curView === 'report') {
    const e = $('rp-dumps');
    if (e) e.dispatchEvent(new Event('change'));
  }
  const sum = Clan.last();
  if (sum) Clan.summary(sum);
  if (newsOk) {
    newsSig = '';
    loadNews(true);
  } // news list re-renders in the new language (pl copy)
}
