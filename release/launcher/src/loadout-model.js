/**
 * @file GEAR UP model: loadout data shape, point math, row/option computation.
 *
 * Loaded before loadout-view.js and loadout.js (classic scripts, src/index.html order). Exposes the
 * global `LoadoutModel`; it holds no view state and touches no DOM.
 */
'use strict';

// GEAR UP, as in the mod (tools/ext t2r-ext.c GEAR UP + skills.c; layout of the 2013 Factions pages, re/factions2013/DESIGN.md section 2):
//   list page : CUSTOM LOADOUT 1..6 then the 8 pre-made classes (view only: select = equip); preview on the right
//   edit page : "CUSTOM LOADOUT n": rows Small Firearm, Large Firearm, Survival Skill 1-4, Purchasable; picker for the highlighted row with
//               LP costs (FREE / n); details on the right; header "x/13 Loadout Points"; BACK / RESET LOADOUT / SELECT
// Rules (mirroring the mod): 13 LP total; the SMALL firearm slot always holds a gun (default: the free 9MM PISTOL); large firearm, purchasable
// and every skill row may be empty (the crossed-circle icon); one row per gun, a LOUD / QUIET switch like the skill levels (+2 LP large, +1 LP small;
// the bow, revolver, shorty and the purchasables have none); a skill is picked once, at a level I-III with its own LP cost; what would break the
// budget is dimmed ("NOT ENOUGH POINTS"). Data: gamedata.js (generated from the mod's sources).
const LoadoutModel = (() => {
  const G = GAMEDATA,
    LP_MAX = G.lpMax,
    ROMAN = ['', 'I', 'II', 'III'];
  const ROWS = [
    { k: 'small', t: 'SMALL FIREARM', none: null },
    { k: 'large', t: 'LARGE FIREARM', none: 'No Large Firearm' },
    ...[0, 1, 2, 3].map((i) => ({
      k: 'skill' + i,
      t: 'SURVIVAL SKILL ' + (i + 1),
      none: 'Nothing',
    })),
    { k: 'purch', t: 'PURCHASABLE', none: 'No Purchasable' },
  ];
  const DEFAULT_SMALL = () => ({ id: G.weapons.small[0].id, supp: 0 });

  const wpn = (slot, id) => G.weapons[slot].find((w) => w.id === id);
  const wcost = (slot, sel) => {
    if (!sel) return 0;
    const w = wpn(slot, sel.id);
    return w ? w.lp + (sel.supp && w.supIcon ? w.supp : 0) : 0;
  };
  const wname = (slot, sel) => {
    const w = sel && wpn(slot, sel.id);
    return w ? (sel.supp && w.supIcon ? 'SUPPRESSED ' : '') + w.name : null;
  };
  const wicon = (slot, sel) => {
    const w = sel && wpn(slot, sel.id);
    return w ? (sel.supp && w.supIcon ? w.supIcon : w.icon) : null;
  };
  const skill = (s) => (s ? G.skills[s.id] : null);
  const scost = (s) => (s ? G.skills[s.id].cost[s.lv - 1] : 0);
  const total = (lo) =>
    wcost('small', lo.small) +
    wcost('large', lo.large) +
    wcost('purch', lo.purch) +
    lo.skills.reduce((a, s) => a + scost(s), 0);
  const blank = () => ({
    small: DEFAULT_SMALL(),
    large: null,
    purch: null,
    skills: [null, null, null, null],
  });
  const fromClass = (c) => ({
    small: c.slots.small,
    large: c.slots.large,
    purch: c.slots.purch,
    skills: [0, 1, 2, 3].map((i) => c.skills[i] || null),
  });

  function ensure(saved) {
    const st =
      saved && saved.v === 2 && Array.isArray(saved.custom) && saved.custom.length === G.customSlots
        ? saved
        : {
            v: 2,
            custom: Array.from({ length: G.customSlots }, blank),
            active: { kind: 'custom', i: 0 },
          };
    for (const lo of st.custom)
      if (!lo.small || !wpn('small', lo.small.id)) lo.small = DEFAULT_SMALL();
    return st;
  }
  const current = (st, h) => (h.kind === 'custom' ? st.custom[h.i] : fromClass(G.classes[h.i]));
  const label = (h) => (h.kind === 'custom' ? `CUSTOM LOADOUT ${h.i + 1}` : G.classes[h.i].name);
  const isActive = (st, h) => st.active.kind === h.kind && st.active.i === h.i;

  function rowInfo(lo, r) {
    if (r.k.startsWith('skill')) {
      const s = lo.skills[+r.k[5]];
      return {
        name: s ? skill(s).name + ' ' + ROMAN[s.lv] : r.none,
        cost: scost(s),
        ic: s ? 'skill-' + skill(s).icon : null,
        empty: !s,
      };
    }
    const sel = lo[r.k];
    return {
      name: sel ? wname(r.k, sel) : r.none,
      cost: wcost(r.k, sel),
      ic: wicon(r.k, sel),
      empty: !sel,
    };
  }
  function options(lo, r) {
    const base = total(lo) - rowInfo(lo, r).cost;
    if (r.k.startsWith('skill')) {
      const mine = lo.skills[+r.k[5]],
        used = new Set(lo.skills.filter((s, i) => s && i !== +r.k[5]).map((s) => s.id));
      return [
        { key: 'none', name: 'NOTHING', ic: null, pick: null, ok: true },
        ...G.skills
          .map((s, id) => ({
            key: 's' + id,
            id,
            name: s.name,
            ic: 'skill-' + s.icon,
            skill: s,
            taken: used.has(id),
            cur: mine && mine.id === id,
          }))
          .filter((o) => !o.taken),
      ];
    }
    const out = r.none
      ? [
          {
            key: 'none',
            name: r.none.toUpperCase(),
            ic: null,
            pick: null,
            ok: true,
            cur: !lo[r.k],
          },
        ]
      : [];
    for (const w of G.weapons[r.k]) {
      const cur = lo[r.k] && lo[r.k].id === w.id,
        q = cur && lo[r.k].supp ? 1 : 0;
      out.push({
        key: w.id,
        w,
        name: w.name,
        ic: q ? w.supIcon : w.icon,
        cost: w.lp + (q ? w.supp : 0),
        ok: base + w.lp <= LP_MAX,
        cur,
        q,
      });
    }
    return out;
  }

  return {
    G,
    LP_MAX,
    ROMAN,
    ROWS,
    wpn,
    wcost,
    wname,
    wicon,
    skill,
    scost,
    total,
    blank,
    fromClass,
    ensure,
    current,
    label,
    isActive,
    rowInfo,
    options,
  };
})();
