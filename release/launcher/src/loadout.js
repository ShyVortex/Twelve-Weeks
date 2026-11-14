/**
 * @file GEAR UP controller: view state, event wiring and persistence.
 *
 * Uses the global LoadoutModel (data/point math) and LoadoutView (HTML). Keeps the public
 * `Loadout` API used by src/app.js and src/app/ui.js. Stored in launcher.json until API.md
 * /loadout exists.
 */
'use strict';

const Loadout = (() => {
  const M = LoadoutModel,
    V = LoadoutView;
  const ROWS = M.ROWS,
    LP_MAX = M.LP_MAX,
    ROMAN = M.ROMAN;
  const $ = (id) => document.getElementById(id);

  let st = null,
    onSave = () => {},
    view = 'list',
    onMode = () => {},
    hi = { kind: 'custom', i: 0 },
    row = 0,
    hiItem = null;
  let syncState = ''; // 'synced' | 'pending' | 'waiting' | 'nogame' | 'error'

  // keep each column's scroll position across re-renders (picking LOUD/QUIET on a row low in the list jumped back to the top);
  // the option column only keeps it while the same slot row is open
  let lastKey = '',
    lastRow = 0,
    lastHiItem = null,
    lastHi = '';
  function render() {
    const key = view + ':' + (view === 'edit' ? hi.i + ':' + row : '');
    const prev = [...document.querySelectorAll('#lo-body .lo-cols > *')].map((el) => el.scrollTop);
    const sameView = lastKey.split(':')[0] === view,
      same = lastKey === key;
    const selSig = (el) =>
      el.className.replace(/(sel|hi|cur|act|on|m-new)/g, '').trim() +
      JSON.stringify(el.dataset) +
      (el.querySelector('b') ? el.querySelector('b').textContent : el.textContent);
    const SEL = '#lo-body .sel, #lo-body .hi, #lo-body .cur, #lo-body .act, #lo-body .lv.on';
    const wasSel = new Set([...document.querySelectorAll(SEL)].map(selSig)); // rows already highlighted before this render: no highlight animation for them
    let out;
    if (view === 'edit') {
      out = V.editHtml({ st, hi, row, hiItem, syncState });
    } else {
      out = V.listHtml({ st, hi, syncState });
    }
    $('lo-body').innerHTML = typeof out === 'string' ? out : out.html;
    if (typeof out !== 'string') $('lo-select').disabled = out.selectDisabled;
    L10N.tree($('lo-body'));
    // motion (style: motion.css): a new highlight fades in, the column whose content changed fades/slides in; scroll position is untouched (opacity/transform only)
    document.querySelectorAll(SEL).forEach((el) => {
      if (lastKey && !wasSel.has(selSig(el))) el.classList.add('m-new');
    });
    const play = (el, cls) => {
      if (el) {
        el.classList.remove(cls);
        void el.offsetWidth;
        el.classList.add(cls);
      }
    };
    const cols = [...document.querySelectorAll('#lo-body .lo-cols > *')];
    if (lastKey) {
      if (!sameView) {
        play($('lo-body').querySelector('.lo-head'), 'm-in');
        cols.forEach((c) => play(c, view === 'edit' ? 'm-in' : 'm-in-back'));
      } else if (view === 'edit') {
        if (lastRow !== row) {
          play(cols[1], 'm-in');
          play(cols[2], 'm-in');
        } else if (lastHiItem !== hiItem) play(cols[2], 'm-in');
      } else if (lastHi !== hi.kind + hi.i) play(cols[1], 'm-in');
    }
    lastRow = row;
    lastHiItem = hiItem;
    lastHi = hi.kind + hi.i;
    document.querySelectorAll('#lo-body .lo-cols > *').forEach((el, i) => {
      if (i < prev.length && sameView && (same || el.classList.contains('lo-listcol')))
        el.scrollTop = prev[i];
    });
    lastKey = key;
  }

  // Page changes (list <-> edit) are private to this module: notify the presence
  // layer so src/app/ui.js can tell "checking a loadout" from "editing a loadout".
  function setView(next) {
    view = next;
    render();
    onMode(view);
  }

  function init(saved, saveFn) {
    st = M.ensure(saved);
    hi = { ...st.active };
    onSave = saveFn;
    render();
    const body = $('lo-body');
    body.addEventListener('keydown', (e) => {
      const o = e.target.closest && e.target.closest('.orow');
      if (o && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        const key = o.dataset.key;
        o.click();
        const again = document.querySelector(`#lo-body .orow[data-key="${key}"]`);
        if (again) again.focus();
      }
    });
    body.addEventListener('click', (e) => {
      const t = e.target;
      const lr = t.closest('.lrow');
      if (lr) {
        hi = { kind: lr.dataset.kind, i: +lr.dataset.i };
        return render();
      }
      if (t.closest('#lo-select')) {
        st.active = { ...hi };
        onSave(st);
        return render();
      }
      if (t.closest('#lo-edit')) {
        row = 0;
        hiItem = null;
        return setView('edit');
      }
      if (t.closest('#lo-back')) {
        hi = { kind: 'custom', i: hi.i };
        return setView('list');
      }
      if (t.closest('#lo-reset')) {
        st.custom[hi.i] = M.blank();
        onSave(st);
        return render();
      }
      const er = t.closest('.erow');
      if (er) {
        row = +er.dataset.row;
        hiItem = null;
        return render();
      }
      const lo = st.custom[hi.i],
        r = ROWS[row];
      const lv = t.closest('.lv');
      const deny = (name, cost, left) =>
        denied(
          'NOT ENOUGH LOADOUT POINTS',
          `${name} costs ${cost}. You have ${Math.max(0, left)} left.`,
        );
      const ok = () => Snd.play('click'); // the select sound, same for rows and pills
      if (lv && lv.dataset.skill) {
        // a level pill: that level (the details show it either way)
        hiItem = 's' + lv.dataset.skill;
        const sk = M.G.skills[+lv.dataset.skill],
          c = sk.cost[+lv.dataset.lv - 1],
          left = LP_MAX - (M.total(lo) - M.rowInfo(lo, r).cost);
        if (lv.classList.contains('no')) {
          render();
          return deny(sk.name + ' ' + ROMAN[+lv.dataset.lv], c, left);
        }
        const k = +r.k[5],
          cur = lo.skills[k];
        lo.skills[k] =
          cur && cur.id === +lv.dataset.skill && cur.lv === +lv.dataset.lv
            ? null
            : { id: +lv.dataset.skill, lv: +lv.dataset.lv };
        ok();
        onSave(st);
        return render();
      }
      if (lv && lv.dataset.w) {
        // LOUD / QUIET
        hiItem = lv.dataset.w;
        const wp = M.G.weapons[r.k].find((x) => x.id === lv.dataset.w),
          c = wp.lp + (+lv.dataset.q ? wp.supp : 0),
          left = LP_MAX - (M.total(lo) - M.rowInfo(lo, r).cost);
        if (lv.classList.contains('no')) {
          render();
          return deny((+lv.dataset.q ? 'SUPPRESSED ' : '') + wp.name, c, left);
        }
        lo[r.k] = { id: lv.dataset.w, supp: +lv.dataset.q };
        ok();
        onSave(st);
        return render();
      }
      const or = t.closest('.orow');
      if (or) {
        // anywhere on a row: view it, and equip it when the points allow (skill level I; a gun LOUD, or its current LOUD / QUIET if already equipped)
        hiItem = or.dataset.key;
        const o = M.options(lo, r).find((x) => x.key === or.dataset.key);
        if (!o) return render();
        const base = M.total(lo) - M.rowInfo(lo, r).cost;
        if (o.skill) {
          const k = +r.k[5];
          if (!o.cur) {
            if (base + o.skill.cost[0] > LP_MAX) {
              render();
              return deny(o.skill.name + ' I', o.skill.cost[0], LP_MAX - base);
            }
            lo.skills[k] = { id: o.id, lv: 1 };
            ok();
            onSave(st);
          }
        } else if (o.w) {
          if (!o.cur) {
            if (base + o.w.lp > LP_MAX) {
              render();
              return deny(o.w.name, o.w.lp, LP_MAX - base);
            }
            lo[r.k] = { id: o.w.id, supp: 0 };
            ok();
            onSave(st);
          }
        } else if (!o.cur) {
          if (r.k.startsWith('skill')) lo.skills[+r.k[5]] = null;
          else lo[r.k] = null;
          onSave(st);
        }
        render();
      }
    });
  }

  function setStatus(s) {
    if (s === syncState) return;
    syncState = s;
    const el = $('lo-sync'),
      x = V.SYNC[s];
    if (el) {
      el.textContent = x ? T(x[0]) : '';
      el.className = 'lo-sync ' + (x ? x[1] : '');
    }
  }
  // the game's own loadouts replace the cache (its file is the truth); the open page stays where it is
  function adopt(n) {
    if (!st || !n) return;
    st.custom = n.custom;
    st.active = n.active;
    if (hi.kind === 'custom' && hi.i >= st.custom.length) hi = { ...st.active };
    render();
  }
  return {
    init,
    setStatus,
    adopt,
    get: () => st,
    reset() {
      view = 'list';
      if (st) render();
      onMode(view); // re-entering GEAR UP always lands on the list page
    },
    mode: () => view,
    onModeChange(fn) {
      onMode = fn;
    },
    rerender() {
      if (st) render();
    },
  };
})();
