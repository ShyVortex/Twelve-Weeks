/**
 * @file Renderer sound effects and music playback.
 */
'use strict';
// Menu sounds: TLOU2's own gbl-menu bank waves (assets/sounds/<name>.wav, see README). Swappable by file name.
const MUTED = /[?&]mute=1/.test(location.search); // automated runs: nothing is ever played or even loaded
/**
 * Sound-effect player for UI interactions.
 */
const Snd = (() => {
  const gain = {
    feed: 0.2,
    hover: 0.22,
    click: 0.5,
    tab: 0.4,
    confirm: 0.45,
    back: 0.4,
    error: 0.45,
    toggle: 0.4,
    tick: 0.3,
    launch: 0.5,
  };
  const pool = {},
    alias = { feed: 'tick' }; // feed: the soft tick for the clan feed toasts
  let volume = 0.7,
    enabled = true,
    lastHover = 0;
  for (const n of Object.keys(gain)) {
    if (MUTED) break;
    const a = new Audio(`../assets/sounds/${alias[n] || n}.wav`);
    a.preload = 'auto';
    pool[n] = a;
  }
  function play(n) {
    if (MUTED || !enabled || !pool[n] || volume <= 0 || document.body.classList.contains('game-on'))
      return;
    if (n === 'hover') {
      const now = performance.now();
      if (now - lastHover < 110) return;
      lastHover = now;
    }
    const a = pool[n].cloneNode();
    a.volume = Math.min(1, volume * gain[n]);
    a.play().catch(() => {});
  }
  function bind() {
    document.addEventListener('click', (e) => {
      const el = e.target.closest('[data-snd]');
      if (el && !el.disabled) play(el.dataset.snd);
    });
    document.addEventListener('mouseover', (e) => {
      const el = e.target.closest('.mi,.slot,.pick,.skill,.fopt,.th,.sub');
      if (el && !el.contains(e.relatedTarget) && !el.disabled) play('hover');
    });
    document.addEventListener('change', (e) => {
      if (e.target.matches('input[type=checkbox]')) play('toggle');
    });
  }
  // No Return UI stingers for the clan screen (assets/sounds/cl-*.ogg, tools/rip_clan_ui_audio.py; re/clan-ui-motion.md): decoded on first use, same gates as play().
  // The preview harness reads Snd.log (?fxlog=1) to lay the same cues over its captured frames.
  const fpool = {},
    log = [],
    LOGGING = /[?&]fxlog=1/.test(location.search);
  function fx(n, g) {
    if (LOGGING) log.push({ t: Date.now(), n, g });
    if (MUTED || !enabled || volume <= 0 || document.body.classList.contains('game-on')) return;
    const a = fpool[n] || (fpool[n] = new Audio(`../assets/sounds/${n}.ogg`));
    const c = a.cloneNode();
    c.volume = Math.min(1, volume * (g == null ? 0.5 : g));
    c.play().catch(() => {});
  }
  return {
    play,
    fx,
    log,
    bind,
    setVolume: (v) => {
      volume = v / 100;
    },
    setEnabled: (b) => {
      enabled = b;
    },
  };
})();

// Ambient menu music: assets/music/*.ogg (see README). Plays the tracks in turn with a cross-fade, ducks lightly while
// downloading, fades out when the game starts and stays off while it runs.
/**
 * Background-music player and theme controller.
 */
const Mus = (() => {
  const sets = {
    neutral: ['01-ambient', '02-slide-guitar', '03-guitar'],
    wlf: ['wlf-01-seattle', 'wlf-02-watchtower', 'wlf-03-brewery'],
    sera: ['sera-01-forest', 'sera-02-island', 'sera-03-abby-island'],
  };
  let theme = 'neutral',
    files = sets.neutral;
  let vol = 0.35,
    enabled = true,
    duck = 1,
    gameUp = false,
    started = false,
    idx = 0,
    cur = null,
    timer = 0,
    master = 1,
    curAt = 0,
    curSet = 'neutral';
  const FADE = 5000,
    THEME_FADE = 3500,
    EARLY = 12000; // theme change: switch at once while the track is young, else at its natural end
  const level = (a) => Math.max(0, Math.min(1, vol * duck * master * (a._f == null ? 1 : a._f)));
  function apply() {
    if (cur) cur.volume = level(cur);
  }
  function ramp(a, to, ms, done) {
    const from = a._f == null ? 0 : a._f,
      t0 = performance.now();
    cancelAnimationFrame(a._raf);
    (function step(now) {
      const k = Math.min(1, (now - t0) / ms);
      a._f = from + (to - from) * k;
      a.volume = level(a);
      if (k < 1) a._raf = requestAnimationFrame(step);
      else if (done) done();
    })(t0);
  }
  function next(fade) {
    fade = fade || (curSet !== theme ? THEME_FADE : FADE);
    curSet = theme;
    const a = new Audio(`../assets/music/${files[idx % files.length]}.ogg`);
    idx++;
    a._f = 0;
    a.volume = 0;
    a.play()
      .then(() => {
        const old = cur;
        cur = a;
        curAt = performance.now();
        ramp(a, 1, fade);
        if (old)
          ramp(old, 0, fade, () => {
            old.pause();
          });
        clearTimeout(timer);
        const arm = () => {
          const left = (a.duration - a.currentTime) * 1000 - FADE;
          timer = setTimeout(
            () => {
              if (cur === a && wanted()) next();
            },
            Math.max(1000, left),
          );
        };
        if (isFinite(a.duration)) arm();
        else a.addEventListener('loadedmetadata', arm, { once: true });
        a.addEventListener('ended', () => {
          if (cur === a && wanted()) next();
        });
      })
      .catch(() => {});
  }
  let forceUntil = 0;
  function setTheme(t) {
    t = sets[t] ? t : 'neutral';
    if (t === theme) return;
    theme = t;
    files = sets[t];
    idx = 0; // the running track plays out, the following ones come from the new set
    const force = performance.now() < forceUntil;
    forceUntil = 0; // an SP / MP switch changes the set at once
    if (started && cur && wanted() && (force || performance.now() - curAt < EARLY)) {
      clearTimeout(timer);
      next(THEME_FADE);
    }
  }
  function switchNow() {
    forceUntil = performance.now() + 15000;
  } // the next theme change within 15 s crossfades right away
  const wanted = () => enabled && !gameUp && vol > 0;
  function sync() {
    if (wanted()) {
      if (!cur || cur.paused) {
        if (cur) cur.pause();
        cur = null;
        next();
      } else ramp(cur, 1, 800);
    } else if (cur) {
      const a = cur;
      ramp(a, 0, 1500, () => {
        a.pause();
        if (cur === a) cur = null;
      });
      clearTimeout(timer);
    }
  }
  return {
    start() {
      if (MUTED) return;
      if (!started) {
        started = true;
        setTimeout(sync, 500);
      }
    },
    setTheme,
    switchNow,
    setVolume(v) {
      vol = v / 100;
      apply();
      if (started) sync();
    },
    setEnabled(b) {
      enabled = b;
      if (started) sync();
    },
    setGame(up) {
      if (up !== gameUp) {
        gameUp = up;
        if (started) sync();
      }
    },
    fadeOutNow() {
      if (cur) {
        const a = cur;
        clearTimeout(timer);
        ramp(a, 0, 1200, () => {
          a.pause();
        });
      }
    },
    duck(on) {
      duck = on ? 0.55 : 1;
      apply();
    },
    dip() {
      if (!cur) return;
      const f = duck;
      duck = 0.7 * f;
      apply();
      setTimeout(() => {
        duck = f;
        apply();
      }, 450);
    },
  };
})();
