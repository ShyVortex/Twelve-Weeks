'use strict';
// CLAN screen motion + sound + NEW markers (re/clan-ui-motion.md). No Return's UI language: sections slide in from a fixed side with a short stagger, every
// beat that is NEW or counted has its own stinger, numbers count up with ticks and land with an accent, a verdict is stamped. Markup opts in with:
//   data-fxg="<baseMs>,<stepMs>"   a group: its [data-fx] children (document order, nested groups excluded) start at base + i * step (stagger capped at 720 ms)
//   data-fx="left|right|up|down|pop|grow|stamp|fade"   the entrance (keyframes in gear.css)
//   data-fxs="slide|loot|lootammo|lootmed|..."   the cl-*.ogg cue played when that child starts (thinned out so a long list is not a machine gun)
//   .cu[data-to][data-from]   count-up number (700 ms, ease-out-cubic, a tick per step up to 7, an accent when it lands)
//   data-new="kind:id"   a thing the player has not seen: highlight + stinger once, remembered afterwards
// Reduced motion keeps the fades and drops the slides / pops / counters (they show their end value at once); the sounds stay.
const Fx = (() => {
  const KEY = 't2r.clan.seen';
  const reduced = () => {
    try {
      return matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  };
  let seen = null,
    timers = [],
    raf = 0;
  const load = () => {
    if (seen) return seen;
    try {
      const s = JSON.parse(localStorage.getItem(KEY) || 'null');
      seen = s && s.ids ? s : null;
    } catch (e) {
      seen = null;
    }
    return seen;
  };
  const save = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify(seen));
    } catch (e) {
      /* private window: NEW simply shows again next time */
    }
  };
  const at = (ms, fn) => {
    timers.push(setTimeout(fn, Math.max(0, ms)));
  };
  // one limiter for every cue (many things start in the same 100 ms): a minimum gap per sound so counters and slides never machine-gun
  const GAP = {
      'cl-st-hungry': 500,
      'cl-st-sad': 500,
      'cl-st-sick': 500,
      'cl-st-dead': 500,
      'cl-count': 90,
      'cl-countend': 170,
      'cl-slide': 120,
      'cl-bar': 220,
      'cl-new': 200,
      'cl-open': 400,
    },
    lastCue = {};
  const cue = (n, g) => {
    if (typeof Snd === 'undefined' || !Snd.fx) return;
    const now = performance.now(),
      gap = GAP[n] || 70;
    if (lastCue[n] && now - lastCue[n] < gap) return;
    lastCue[n] = now;
    Snd.fx(n, g);
  };
  const ease = (k) => 1 - Math.pow(1 - k, 3);

  // seen store { v: 1, ids: { "j:41": 1, "m:9": 1 } }. First visit ever: only the newest things are NEW (the caller passes `newest`), so a first-time viewer
  // is not shown forty NEW tags.
  const fresh = (id, newest) => {
    const s = load();
    return s ? !(id in s.ids) : !!newest;
  };
  const has = () => !!load();
  function seed(ids) {
    if (!load()) {
      seen = { v: 1, ids: {} };
      ids.forEach((i) => {
        seen.ids[i] = 1;
      });
      save();
    }
  } // first visit: everything but the newest counts as seen
  function remember(ids) {
    if (!load()) seen = { v: 1, ids: {} };
    ids.forEach((i) => {
      seen.ids[i] = 1;
    });
    const keys = Object.keys(seen.ids);
    if (keys.length > 800)
      keys.slice(0, keys.length - 800).forEach((k) => {
        delete seen.ids[k];
      });
    save();
  }

  function cancel() {
    timers.forEach(clearTimeout);
    timers = [];
    cancelAnimationFrame(raf);
    if (io) io.disconnect();
  }
  const groupItems = (g) =>
    [...g.querySelectorAll('[data-fx]')].filter((e) => e.closest('[data-fxg]') === g);
  const live = (g) => !g.closest('[hidden]');
  function countUp(el, delay) {
    const to = Number(el.dataset.to) || 0,
      from = Number(el.dataset.from) || 0,
      dur = Number(el.dataset.dur) || 700;
    const fmt = (v) => (el.dataset.pre || '') + v + (el.dataset.suf || '');
    el.textContent = fmt(from);
    if (reduced() || to === from) {
      el.textContent = fmt(to);
      return;
    }
    const steps = Math.min(7, Math.abs(to - from));
    at(delay, () => {
      const t0 = performance.now();
      let tick = 0;
      const step = (now) => {
        const k = Math.min(1, (now - t0) / dur),
          v = Math.round(from + (to - from) * ease(k));
        el.textContent = fmt(v);
        const want = Math.floor(k * steps);
        if (want > tick && k < 1) {
          tick = want;
          cue('cl-count', 0.3);
        }
        if (k < 1) raf = requestAnimationFrame(step);
        else {
          el.textContent = fmt(to);
          if (!el.dataset.quiet) cue('cl-countend', 0.45);
          el.classList.add('landed');
        }
      };
      raf = requestAnimationFrame(step);
    });
  }
  // a nested group starts after the bases of the groups around it (up to `stop`)
  function startOf(g, stop) {
    let t = 0,
      p = g.parentElement && g.parentElement.closest('[data-fxg]');
    while (p && stop.contains(p)) {
      t += Number(String(p.dataset.fxg).split(',')[0]) || 0;
      p = p.parentElement && p.parentElement.closest('[data-fxg]');
    }
    return t;
  }
  // start one group at `t0` ms; returns the end time of its last child
  function run(g, t0, cap, sounds, st) {
    const [base, step] = String(g.dataset.fxg).split(',').map(Number),
      items = groupItems(g);
    const gap =
      items.length > 1
        ? Math.min(step || 60, (Number(g.dataset.fxcap) || cap) / (items.length - 1))
        : 0;
    let lastCue = -999,
      end = 0;
    items.forEach((el, i) => {
      const d = Math.max(0, t0 + (base || 0) + i * gap);
      if (el.classList.contains('go')) {
        el.classList.remove('go');
        void el.offsetWidth;
      } // restart only what already ran (a forced reflow per row stalled the page for ~0.5 s on 22 journal rows)
      el.style.setProperty('--fx-d', d + 'ms');
      el.classList.add('go');
      end = Math.max(end, d + 700);
      if (sounds && el.dataset.fxs) {
        const mingap = el.dataset.fxs === 'slide' ? 140 : 95;
        if (d - lastCue >= mingap) {
          lastCue = d;
          at(d + 40, () => cue('cl-' + el.dataset.fxs, 0.36));
        }
      }
      if (sounds && el.dataset.fx === 'stamp') at(d + 140, () => cue('cl-stamp', 0.5));
      if (el.classList.contains('cu')) countUp(el, d + 120);
      el.querySelectorAll('.cu').forEach((c) => countUp(c, d + 120));
      if (st) {
        const mark = el.matches('[data-new]') ? el : el.querySelector('[data-new]');
        if (mark) {
          at(d + 380, () => mark.classList.add('flash'));
          if (!mark.dataset.nosnd && d + 380 - st.last >= 220 && st.n < 4) {
            const big = st.n === 0;
            st.n++;
            st.last = d + 380;
            at(d + 380, () => cue(big ? 'cl-newbig' : 'cl-new', big ? 0.5 : 0.4));
          }
        }
      }
    });
    return end;
  }
  const base0 = (g) => Number(String(g.dataset.fxg).split(',')[0]) || 0;
  const topGroups = (root) =>
    [...root.querySelectorAll('[data-fxg]')].filter((g) => !g.parentElement.closest('[data-fxg]'));
  // run a top-level group and the groups nested in it (those inside a hidden detail wait for their own open()); `shift` moves the start (a group that
  // waited below the fold starts at once, not after its base delay)
  function runTree(g, root, shift, st) {
    let end = run(g, Math.max(0, shift), 720, true, st);
    g.querySelectorAll('[data-fxg]').forEach((n) => {
      if (live(n))
        end = Math.max(end, run(n, Math.max(0, startOf(n, root) + shift), 720, true, st));
    });
    return end;
  }
  const markIds = (g) =>
    [...g.querySelectorAll('[data-new]')]
      .filter((e) => !e.closest('[hidden]'))
      .map((e) => e.dataset.new);
  let io = null;
  function play(root) {
    cancel();
    if (io) io.disconnect();
    root.classList.remove('fx-static');
    cue('cl-open', 0.5);
    const st = { n: 0, last: -999 },
      rr = root.getBoundingClientRect(),
      now = [];
    let ends = 0;
    topGroups(root).forEach((g) => {
      if (!live(g)) return;
      if (g.getBoundingClientRect().top < rr.bottom - 40) {
        now.push(g);
        ends = Math.max(ends, runTree(g, root, 0, st));
      } else if ('IntersectionObserver' in window) {
        io =
          io ||
          new IntersectionObserver(
            (es) =>
              es.forEach((e) => {
                if (!e.isIntersecting) return;
                const gg = e.target;
                io.unobserve(gg);
                const e2 = runTree(gg, root, -base0(gg), { n: Math.max(1, st.n), last: -999 });
                at(e2 + 1200, () => {
                  if (root.offsetParent) remember(markIds(gg));
                });
              }),
            { root, rootMargin: '0px 0px -8% 0px', threshold: 0.04 },
          );
        io.observe(g);
      } else runTree(g, root, 0, st);
    });
    // whatever is NEW and on screen now counts as seen once the screen has been looked at for a moment
    at(Math.max(2600, ends + 600), () => {
      if (!root.offsetParent) return; // the player left first: still new next time
      remember(now.flatMap(markIds));
    });
  }
  // the screen drawn without an entrance (language switch, re-render): everything just visible
  function still(root) {
    cancel();
    root.classList.add('fx-static');
    root.querySelectorAll('.cu').forEach((c) => {
      c.textContent = (c.dataset.pre || '') + (c.dataset.to || '0') + (c.dataset.suf || '');
    });
  }
  // a detail panel opening inside the screen (raid details): the same stagger on just that node
  function open(node) {
    cue('cl-expand', 0.4);
    node.querySelectorAll('[data-fxg]').forEach((g) => run(g, startOf(g, node), 600, true, null));
  }
  return { play, still, open, cancel, fresh, remember, seed, has, cue };
})();
