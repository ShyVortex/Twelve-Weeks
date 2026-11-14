/**
 * @file Renderer notices, alerts, view switching and visual effects.
 *
 * The top-level wiring in this file (element listeners, view toggles) is installed as the script
 * loads; src/app.js only orchestrates startup. Keeping the wiring next to the helpers it drives
 * avoids a separate bootstrap layer for a small classic-script renderer.
 */
'use strict';

// One-line notices (also the hook for the clan feed): a dark gradient exactly as long as the sentence, fading in and out with it.
// One-line notices in the bottom-bar lane. One element = text + gradient, so they fade together: 1.2 s in (opacity + a 6 px slide, ease-out), held for
// 9 s + 90 ms per character, 1.2 s out (the node is removed on transitionend, never before), 3 s gap between toasts. A status message (toast()) that
// arrives while another is showing cross-fades it: the old one starts fading out while the new one fades in.
/**
 * One-line notice queue rendered in the bottom lane.
 */
const Notice = (() => {
  const GAP = 3000;
  const q = [];
  let running = false,
    hold = null;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const holdFor = (ms) =>
    new Promise((r) => {
      const t = setTimeout(r, ms);
      hold = () => {
        clearTimeout(t);
        r();
      };
    });
  function mount(text, kind) {
    const el = document.createElement('div');
    el.className = 'n ' + (kind || '');
    el.textContent = text;
    $('notice').appendChild(el);
    void el.offsetWidth;
    requestAnimationFrame(() => el.classList.add('on'));
    return el;
  }
  function unmount(el) {
    return new Promise((res) => {
      let done = false;
      const fin = () => {
        if (done) return;
        done = true;
        el.remove();
        res();
      };
      el.classList.remove('on');
      el.addEventListener('transitionend', (e) => {
        if (e.propertyName === 'opacity') fin();
      });
      setTimeout(fin, 1600);
    });
  }
  let cur = null;
  async function run() {
    if (running) return;
    running = true;
    while (q.length) {
      const it = q.shift(),
        el = mount(it.text, it.kind);
      cur = el;
      await sleep(1200); // fade in
      await holdFor(it.ms || 9000 + 90 * it.text.length); // hold (cut short only by a status message)
      hold = null;
      if (cur === el) {
        cur = null;
        await unmount(el);
      }
      it.done();
      if (q.length) await sleep(GAP);
    }
    running = false;
  }
  return {
    push(text, kind, ms, urgent) {
      return new Promise((done) => {
        const it = { text, kind, ms, done };
        if (urgent) {
          q.unshift(it);
          if (running && cur) {
            const old = cur;
            cur = null;
            unmount(old);
            if (hold) hold();
          }
        } else q.push(it);
        run();
      });
    },
  };
})();
window.notify = (text, ms) => Notice.push(text, '', ms, true);
// One blocked / denied sound and one alert panel for every refusal or error in the launcher (the game's menu-error wave, assets/sounds/error.wav).
// The panel (bottom-left, above the bottom rule) shows at once: the same alert while it is up just restarts its hold, a different one replaces it.
/**
 * Bottom-left alert panel shared by refusals, errors and server notices.
 */
const Alert = (() => {
  let key = '',
    timer = 0,
    el = null;
  const ICON = { denied: 'none', error: 'none', warning: 'info', info: 'info' };
  const esc2 = (s) =>
    String(s).replace(
      /[&<>"]/g,
      (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m],
    );
  function show(type, title, desc) {
    title = T(title);
    desc = T(desc);
    el = el || $('alert');
    const k = type + '|' + title + '|' + desc;
    if (k !== key) {
      key = k;
      el.className = 'alert ' + type + (el.classList.contains('on') ? ' on' : '');
      el.innerHTML = `<i style="background-image:url('../assets/icons/${ICON[type] || 'none'}.png')"></i><div><b>${esc2(title)}</b><span>${esc2(desc)}</span></div>`;
    }
    void el.offsetWidth;
    el.classList.add('on');
    $('app').classList.add('alert-on');
    clearTimeout(timer);
    timer = setTimeout(
      () => {
        el.classList.remove('on');
        $('app').classList.remove('alert-on');
        key = '';
      },
      Math.min(10000, 4500 + 45 * desc.length),
    );
  }
  return { show, key: () => key };
})();
// ---------------------------------------------------------------- server notices (daemon op 0xBA / status.json): alert panel, each id once per session
// u update available | r planned restart (live countdown, re-shown at 5 / 2 / 1 min) | s shutting down | t free text from the host
/**
 * Server notice/restart countdown controller.
 */
const Notices = (() => {
  const seen = new Set(),
    restarts = new Map(); // restarts: id -> { endsAt, text, lvl }
  const STEPS = [300, 120, 60];
  let live = null; // { id, until }: the countdown being drawn
  const left = (r) => Math.max(0, Math.round(r.endsAt - Date.now() / 1000));
  const lvlOf = (s) => STEPS.filter((t) => s <= t).length;
  function restartText(r) {
    const s = left(r),
      t =
        s >= 60
          ? T('Server restarting in {n} min.', { n: Math.ceil(s / 60) })
          : T('Server restarting in {n} s.', { n: s });
    return r.text ? t + ' ' + T(r.text) : t;
  }
  function showRestart(id) {
    const r = restarts.get(id);
    if (r) {
      Snd.play('error');
      live = { id, until: Date.now() + 10000 };
      Alert.show('warning', 'SERVER RESTART', restartText(r));
    }
  }
  function update(st) {
    if (!st) return;
    const list = Array.isArray(st.notices) ? st.notices : [];
    // free text / restart reason: the daemon's 0xBA reply is already in this launcher's language; the status.json fallback carries text_pl (the admin's Polish form)
    const txt = (n) =>
      (typeof I18N !== 'undefined' && I18N.lang === 'pl' && n.text_pl) || n.text || '';
    // 'u' (update available) is an in-game notice for players in a match; the launcher shows updates on its own UPDATE row, so it is ignored here
    const ids = new Set();
    for (const n of list) {
      if (n.kind === 'r') {
        ids.add(n.id);
        const endsAt = n.endsAt || Date.now() / 1000 + (n.param || 0);
        if (!restarts.has(n.id)) {
          restarts.set(n.id, {
            endsAt,
            text: txt(n),
            lvl: lvlOf(Math.max(0, Math.round(endsAt - Date.now() / 1000))),
          });
          showRestart(n.id);
        } else restarts.get(n.id).endsAt = endsAt;
      } else if ((n.kind === 's' || n.kind === 't') && !seen.has('n' + n.id)) {
        seen.add('n' + n.id);
        Snd.play('error');
        if (n.kind === 's')
          Alert.show('warning', 'SERVER SHUTTING DOWN', 'Server is shutting down.');
        else Alert.show('warning', 'SERVER NOTICE', txt(n));
      }
    }
    for (const id of [...restarts.keys()]) if (!ids.has(id)) restarts.delete(id); // cancelled or done
  }
  setInterval(() => {
    // 1 s: the live countdown, and the 5 / 2 / 1 min re-shows between two polls
    for (const [id, r] of restarts) {
      const l = lvlOf(left(r));
      if (l > r.lvl) {
        r.lvl = l;
        showRestart(id);
      }
    }
    if (
      live &&
      Date.now() < live.until &&
      Alert.key().startsWith('warning|' + T('SERVER RESTART') + '|')
    ) {
      const r = restarts.get(live.id);
      if (r) Alert.show('warning', 'SERVER RESTART', restartText(r));
      else live = null;
    }
  }, 1000);
  return { update };
})();
/**
 * Show a refusal/error alert and play the error sound.
 * @param {string} title
 * @param {string} [desc]
 * @returns {void}
 */
function denied(title, desc) {
  Snd.play('error');
  Alert.show('denied', title, desc || '');
}
/**
 * Show a status/result alert.
 * @param {string} msg
 * @param {boolean} [good]
 * @param {string} [title]
 * @returns {void}
 */
function toast(msg, good, title) {
  if (good) Alert.show('info', title || 'DONE', msg);
  else {
    Snd.play('error');
    Alert.show('error', title || 'SOMETHING WENT WRONG', msg);
  }
}
/**
 * Route a status message to the notice lane.
 * @returns {void}
 */
function logline() {
  /* one place for status messages: the notice lane */
}

// ---------------------------------------------------------------- screens
/**
 * Switch the visible launcher view.
 * @param {string|null} v
 * @returns {void}
 */
$('discord').addEventListener('click', () => {
  if (banState.banned) return; // (no Discord for a banned player; the button is hidden too)
  f2.openUrl('https://discord.gg/wmVgW2wxge');
});
$('discord').addEventListener('mouseenter', () => Snd.play('hover'));
/* global askConfirm */
// ADD TO STEAM: adds the launcher to Steam as a non-Steam game (main/ipc/steam.js). Steam rewrites its shortcut list on exit, so a running Steam is
// restarted (politely) after a confirm. Once the shortcut exists the button is a small box (logo + check) that grows to STEAM ADDED on hover;
// a click offers to remove it again. The state is re-read every 10 s (shortcuts.vdf only).
let steamAdded = false;
function steamErr(r) {
  if (r.result === 'notfound')
    Alert.show('error', 'STEAM NOT FOUND', 'Steam could not be found on this computer.');
  else if (r.result === 'nouser')
    Alert.show(
      'error',
      'NO STEAM ACCOUNT',
      'No Steam account was found. Log in to Steam once, then try again.',
    );
  else
    Alert.show(
      'error',
      'STEAM DID NOT CLOSE',
      'Close Steam yourself, then press ADD TO STEAM again.',
    );
}
function drawSteamBtn(added) {
  steamAdded = added;
  const b = $('steamadd');
  b.classList.toggle('added', added);
  $('steamadd-t').textContent = T(added ? 'STEAM ADDED' : 'ADD TO STEAM');
  b.title = T(
    added
      ? 'Remove Twelve Weeks from your Steam library'
      : 'Add Twelve Weeks to your Steam library',
  );
}
async function checkSteamBtn() {
  if ($('steamadd').disabled) return;
  try {
    const st = await f2.steamState(true);
    if (st.ok && !$('steamadd').disabled) drawSteamBtn(!!st.added);
  } catch {
    /* next check */
  }
}
$('steamadd').addEventListener('mouseenter', () => Snd.play('hover'));
$('steamadd').addEventListener('click', async () => {
  const b = $('steamadd');
  if (b.disabled) return;
  b.disabled = true;
  const remove = steamAdded;
  const bad = (r) =>
    Alert.show('error', remove ? 'COULD NOT REMOVE FROM STEAM' : 'COULD NOT ADD TO STEAM', r.error);
  try {
    if (
      remove &&
      !(await askConfirm(
        'REMOVE FROM STEAM',
        'Remove TWELVE WEEKS from your Steam library?',
        'REMOVE',
      ))
    )
      return;
    const st = await f2.steamState();
    if (!st.ok) return bad(st);
    if (!st.found)
      return Alert.show('error', 'STEAM NOT FOUND', 'Steam could not be found on this computer.');
    let restart = false;
    if (st.running) {
      restart = await askConfirm(
        remove ? 'REMOVE FROM STEAM' : 'ADD TO STEAM',
        remove
          ? 'Steam must restart to remove TWELVE WEEKS from your library. Restart Steam now?'
          : 'Steam must restart to show TWELVE WEEKS in your library. Restart Steam now?',
        'RESTART STEAM',
      );
      if (!restart)
        return window.notify(
          T(
            'Nothing was changed. Steam has to restart for the entry to show up; press ADD TO STEAM again when you are ready.',
          ),
        );
      window.notify(
        T(
          remove
            ? 'Closing Steam, removing TWELVE WEEKS...'
            : 'Closing Steam, adding TWELVE WEEKS...',
        ),
      );
    }
    const r = await (remove ? f2.steamRemove(restart) : f2.steamAdd(restart));
    if (!r.ok) return bad(r);
    if (r.result === 'added') window.notify(T('TWELVE WEEKS was added to your Steam library.'));
    else if (r.result === 'updated')
      window.notify(T('TWELVE WEEKS was updated in your Steam library.'));
    else if (r.result === 'removed')
      window.notify(T('TWELVE WEEKS was removed from your Steam library.'));
    else steamErr(r);
    if (['added', 'updated'].includes(r.result)) drawSteamBtn(true);
    else if (r.result === 'removed') drawSteamBtn(false);
  } finally {
    b.disabled = false;
  }
});
checkSteamBtn();
setInterval(checkSteamBtn, 10000);

// Rich Presence per screen (Discord, lib/rpc; OmegaMan): add an entry here to give a screen its own status.
// Every view without one (and closing all views) falls back to the main menu.
const PRESENCE = {
  idle: { details: 'In main menu', state: 'Ready' },
  news: { details: 'Reading news', state: 'Curious' },
  clan: { details: 'Checking clan', state: 'Gregarious' },
  loadout: { details: 'Checking loadout', state: 'Itchy' },
  loadoutEdit: { details: 'Editing loadout', state: 'Tinkering' },
  friends: { details: 'Adding a friend', state: 'Friendly' },
};
let lastPresence = null;
/**
 * Presence key for the current screen: a top-level view, or the loadout sub-page.
 * @returns {string}
 */
function presenceKey() {
  if (curView === 'loadout') return Loadout.mode() === 'edit' ? 'loadoutEdit' : 'loadout';
  return curView || 'idle';
}
/**
 * Publish the launcher's presence for the current screen. Never overrides the
 * game's presence: the Play flow sets its own once the game window is up.
 * @param {boolean} [force] Re-send even when the screen did not change.
 * @returns {void}
 */
function updatePresence(force) {
  const key = presenceKey();
  if (!force && key === lastPresence) return; // no redundant Discord updates
  if (gs.s !== 'idle') return; // the game owns presence while it runs
  lastPresence = key;
  f2.rpcSet(PRESENCE[key] || PRESENCE.idle).catch(() => {
    /* presence is cosmetic: a failure must never break navigation */
  });
}
/**
 * Re-publish the current screen after the game released presence, even when the
 * screen key did not change (the launcher's activity was cleared in between).
 * @returns {void}
 */
function restorePresence() {
  lastPresence = null;
  updatePresence(true);
}
Loadout.onModeChange(() => updatePresence()); // EDIT / BACK / reset inside GEAR UP

function showView(v) {
  curView = v;
  $$('.mi[data-view]').forEach((t) => t.classList.toggle('active', t.dataset.view === v));
  $$('.view').forEach((s) => s.classList.toggle('active', s.id === 'v-' + v));
  $('app').classList.toggle('has-view', !!v);
  $('app').dataset.view = v || '';
  if (v === 'news') {
    $('news-pip').hidden = true;
    loadNews(!newsOk);
    markNewsSeen();
  }
  if (v === 'clan') Clan.load();
  if (v === 'friends') Social.open();
  if (v === 'report') Report.open();
  if (v === 'loadout') Loadout.reset();
  updatePresence();
}
window.f2show = (v) => showView(v); // (dev screenshot hook: sets a view instead of toggling it)

// ---------------------------------------------------------------- STATUS panel: collapsed by default, problem rows stay visible
(function statusPanel() {
  const rows = $('st-rows');
  const btn = $('st-more');
  const apply = (open, remember) => {
    rows.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    $('st-more-t').textContent = T(open ? 'LESS' : 'MORE');
    if (remember) {
      try {
        localStorage.setItem('f2-status-open', open ? '1' : '0');
      } catch {
        /* optional */
      }
    }
  };
  let open = false;
  try {
    open = localStorage.getItem('f2-status-open') === '1';
  } catch {
    /* optional */
  }
  apply(open, false);
  btn.addEventListener('click', () => apply(!rows.classList.contains('open'), true));
  $('row-nw').addEventListener('click', () => showView('news'));
})();
$$('.mi[data-view]').forEach((t) =>
  t.addEventListener('click', () => showView(curView === t.dataset.view ? null : t.dataset.view)),
);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && curView) {
    Snd.play('back');
    showView(null);
  }
});
$$('.sub').forEach((b) =>
  b.addEventListener('click', () => {
    $$('.sub').forEach((x) => x.classList.toggle('active', x === b));
    $$('.pane').forEach((p) => p.classList.toggle('active', p.id === 's-' + b.dataset.sub));
  }),
);
$('tb-min').onclick = () => f2.win('min');
$('tb-close').onclick = () => f2.win('close');
document.querySelector('[data-act=quit]').onclick = () => setTimeout(() => f2.win('close'), 250);

// ---------------------------------------------------------------- look
/**
 * Apply theme, effects, audio and background settings.
 * @returns {void}
 */
function applyLook() {
  document.body.classList.toggle('no-grain', !cfg.effects.grain);
  document.body.classList.toggle(
    'motion',
    cfg.effects.motion !== false && !matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  Scenes.setMode(
    Scenes.setName() === 'neutral' ? cfg.bgMode || 'rotate' : 'rotate',
    cfg.background,
  ); // a known faction decides the backgrounds
  const blocked = Scenes.setName() !== 'neutral';
  $('bg-field').classList.toggle('locked', blocked);
  Snd.setVolume(cfg.volume);
  Snd.setEnabled(cfg.sounds);
  Mus.setVolume(cfg.musicVolume == null ? 35 : cfg.musicVolume);
  Mus.setEnabled(cfg.music !== false);
  $$('#thumbs .th').forEach((t) =>
    t.classList.toggle(
      'active',
      (cfg.bgMode || 'rotate') === 'pick' && t.dataset.id === cfg.background,
    ),
  );
  $$('#bg-mode .fopt').forEach((b) =>
    b.classList.toggle('active', b.dataset.mode === (cfg.bgMode || 'rotate')),
  );
}
/**
 * Draw the static grain texture once.
 * @returns {void}
 */
function startGrain() {
  // one static frame: no per-frame flicker
  const c = $('grain'),
    g = c.getContext('2d');
  c.width = 256;
  c.height = 256;
  const img = g.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() * 255;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}
// while the game runs the launcher rests (see main.js 'launcher:rest'): no CSS animation, no UI / feed sounds, throttled page
/**
 * Toggle the reduced-activity state while the game runs.
 * @returns {void}
 */
function applyRest() {
  const on = gs.s === 'running' || gs.s === 'starting';
  const run = gs.s === 'running';
  if (document.body.classList.contains('game-on') === on && applyRest.run === run) return;
  applyRest.run = run;
  document.body.classList.toggle('game-on', on);
  try {
    f2.rest(run ? 'run' : on);
  } catch {} // 'run' = the game window is up: main also minimizes the launcher
}
