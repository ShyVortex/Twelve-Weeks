/**
 * @file Loadout file wire format and synchronization with the game.
 */
'use strict';
// GEAR UP <-> the game, by name. The two files next to tlou-ii.exe (contract: API.md "Loadout files"):
//   t2r-loadout.json           written by the game (tools/ext/loadjson.c): its 6 custom loadouts + active pick = the truth
//   t2r-loadout-launcher.json  written here when the player saves in GEAR UP; the game applies it in a menu (rev newer than its "launcher_rev")
// Pure Node (no electron): main.js calls it, test/loadoutfile-test.js tests it in scratch folders.
const fs = require('fs');
const path = require('path');

const GAME_FILE = 't2r-loadout.json';
const LAUNCHER_FILE = 't2r-loadout-launcher.json';

/**
 * Create an empty loadout for the supplied game data.
 * @param {object} G
 * @returns {object}
 */
const blank = (G) => ({
  small: { id: G.weapons.small[0].id, supp: 0 },
  large: null,
  purch: null,
  skills: [null, null, null, null],
});
/**
 * Normalize a weapon slot entry for comparison.
 * @param {unknown} v
 * @returns {unknown}
 */
const wpn = (G, slot, id) => G.weapons[slot].find((w) => w.id === id);
/**
 * Count occupied weapon slots.
 * @param {object} w
 * @returns {number}
 */
const wcost = (G, slot, sel) => {
  if (!sel) return 0;
  const w = wpn(G, slot, sel.id);
  return w ? w.lp + (sel.supp && w.supIcon ? w.supp : 0) : 0;
};
// the game's LP rule (lo_cost): guns + purchasable + skills at their level
/**
 * Compute the LP cost of a loadout.
 * @param {object} G
 * @param {object} lo
 * @returns {number}
 */
const lpOf = (G, lo) =>
  wcost(G, 'small', lo.small) +
  wcost(G, 'large', lo.large) +
  wcost(G, 'purch', lo.purch) +
  lo.skills.reduce((a, s) => a + (s ? G.skills[s.id].cost[s.lv - 1] : 0), 0);

// launcher state (skills as G.skills indexes) -> wire loadout
/**
 * Encode a loadout into the legacy wire shape.
 * @param {object} lo
 * @returns {object}
 */
function loToWire(G, lo) {
  const w = (sel) => (sel ? { id: sel.id, supp: sel.supp ? 1 : 0 } : null);
  return {
    small: w(lo.small),
    large: w(lo.large),
    purch: w(lo.purch),
    skills: lo.skills.map((s) => (s ? { id: G.skills[s.id].key, lv: s.lv } : null)),
    lp: lpOf(G, lo),
  };
}
/**
 * Encode a loadout into the game's wire format.
 * @param {object} G
 * @param {object} st
 * @param {number} rev
 * @returns {object}
 */
function toWire(G, st, rev) {
  return {
    format: 1,
    rev,
    source: 'launcher',
    active: { kind: st.active.kind, i: st.active.i },
    custom: st.custom.map((lo) => loToWire(G, lo)),
  };
}

// wire -> launcher state, validated like the game (13 LP, ids of the tables, a skill once, level in range).
// Returns { state, problems: [text], over: [custom indexes over budget] }. Unknown pieces are dropped (null, the small slot -> the free 9mm).
/**
 * Decode the game's loadout wire format.
 * @param {object} G
 * @param {object} obj
 * @returns {object}
 */
function fromWire(G, obj) {
  const problems = [],
    over = [];
  if (!obj || typeof obj !== 'object' || !Array.isArray(obj.custom))
    return { state: null, problems: ['not a loadout file'], over };
  const custom = [];
  for (let i = 0; i < G.customSlots; i++) {
    const src = obj.custom[i],
      lo = blank(G);
    if (!src || typeof src !== 'object') {
      problems.push(`custom ${i + 1} missing`);
      custom.push(lo);
      continue;
    }
    for (const slot of ['small', 'large', 'purch']) {
      let v = src[slot];
      if (v == null) continue;
      if (typeof v === 'string') v = { id: v, supp: 0 };
      const w = v && typeof v === 'object' && typeof v.id === 'string' ? wpn(G, slot, v.id) : null;
      if (!w) {
        problems.push(`custom ${i + 1} ${slot}: unknown id ${v && v.id}`);
        if (slot !== 'small') lo[slot] = null;
        continue;
      }
      let supp = v.supp ? 1 : 0;
      if (supp && !w.supIcon) {
        problems.push(`custom ${i + 1} ${slot}: ${w.id} has no suppressed variant`);
        supp = 0;
      }
      lo[slot] = { id: w.id, supp };
    }
    const used = new Set();
    for (let j = 0; j < G.skillRows; j++) {
      const s = Array.isArray(src.skills) ? src.skills[j] : null;
      if (s == null) continue;
      const idx = s && typeof s.id === 'string' ? G.skills.findIndex((x) => x.key === s.id) : -1;
      const lv = s ? Number(s.lv) : 0;
      if (idx < 0 || !Number.isInteger(lv) || lv < 1 || lv > G.skills[idx].levels) {
        problems.push(`custom ${i + 1} skill ${j + 1}: unknown skill or level`);
        continue;
      }
      if (used.has(idx)) {
        problems.push(`custom ${i + 1} skill ${j + 1}: ${s.id} twice`);
        continue;
      }
      used.add(idx);
      lo.skills[j] = { id: idx, lv };
    }
    if (lpOf(G, lo) > G.lpMax) {
      over.push(i);
      problems.push(`custom ${i + 1}: ${lpOf(G, lo)} LP (max ${G.lpMax})`);
    }
    custom.push(lo);
  }
  let active = { kind: 'custom', i: 0 };
  const a = obj.active;
  if (
    a &&
    ((a.kind === 'custom' && a.i >= 0 && a.i < G.customSlots) ||
      (a.kind === 'class' && a.i >= 0 && a.i < G.classes.length)) &&
    Number.isInteger(a.i)
  )
    active = { kind: a.kind, i: a.i };
  else if (a) problems.push('bad active pick');
  return { state: { v: 2, custom, active }, problems, over };
}

/**
 * Compare two loadouts for semantic equality.
 * @param {object} G
 * @param {object} a
 * @param {object} b
 * @returns {boolean}
 */
const same = (G, a, b) =>
  JSON.stringify(toWire(G, a, 0).custom) === JSON.stringify(toWire(G, b, 0).custom) &&
  a.active.kind === b.active.kind &&
  a.active.i === b.active.i;

// the game's file: { found, rev, launcherRev, state, problems } (found false: no file / not parseable)
/**
 * Read the game-owned loadout file.
 * @param {object} G
 * @param {string} dir
 * @returns {object}
 */
function readGame(G, dir) {
  let txt;
  try {
    txt = fs.readFileSync(path.join(dir, GAME_FILE), 'utf8');
  } catch {
    return { found: false };
  }
  let obj;
  try {
    obj = JSON.parse(txt);
  } catch {
    return { found: false, error: 'unreadable' };
  }
  const r = fromWire(G, obj);
  if (!r.state) return { found: false, error: 'not a loadout file' };
  return {
    found: true,
    rev: Number(obj.rev) || 0,
    launcherRev: Number(obj.launcher_rev) || 0,
    state: r.state,
    problems: r.problems,
  };
}
// our file, atomically (tmp + rename: the game never reads half a file). Over-budget loadouts are refused before anything is written.
/**
 * Write the launcher-owned loadout file.
 * @param {object} G
 * @param {string} dir
 * @param {object} st
 * @param {number} rev
 * @returns {void}
 */
function writeLauncher(G, dir, st, rev) {
  const wire = toWire(G, st, rev);
  // One over-budget loadout (a cost change made a saved one 14 LP) used to block the whole
  // file, so no edit of any loadout reached the game. The game checks each loadout itself and keeps an over-budget one as it was, so the file is
  // written anyway; the over-budget ones are reported to the caller.
  const over = [];
  for (let i = 0; i < wire.custom.length; i++) if (wire.custom[i].lp > G.lpMax) over.push(i + 1);
  const f = path.join(dir, LAUNCHER_FILE),
    tmp = f + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(wire, null, 1) + '\n');
  fs.renameSync(tmp, f);
  return { wire, over };
}
/**
 * Compute the next launcher revision.
 * @param {number} prev
 * @returns {number}
 */
function nextRev(prev) {
  return Math.max(Date.now(), (Number(prev) || 0) + 1);
}

/**
 * Decide what one sync step should do from the game file and cached revisions.
 * @param {object} g
 * @param {object} c
 * @returns {object}
 */
function decideSync(g, c) {
  const myRev = Number(c.loadout_rev) || 0;
  if (c.loadout_rev === undefined && c.loadout2 && c.loadout2.custom) {
    // loadouts edited before the files existed: they are what the player wants in game
    return {
      status: 'pending',
      adopt: null,
      write: true,
      patch: {},
      problems: g.problems || [],
    };
  }
  // error: the game's file is there but not readable (a past build wrote it cut off, ext lj_body bug): the caller logs it once; the cache stays as it is
  if (!g.found)
    return {
      status: myRev ? 'pending' : 'waiting',
      adopt: null,
      write: false,
      patch: {},
      problems: [],
      error: g.error,
    };
  if (myRev && g.launcherRev < myRev)
    return {
      status: 'pending',
      adopt: null,
      write: false,
      patch: {},
      problems: g.problems,
    };
  if (g.rev !== Number(c.loadout_game_rev))
    return {
      status: 'synced',
      adopt: g.state,
      write: false,
      patch: { loadout_game_rev: g.rev },
      problems: g.problems,
    };
  return {
    status: 'synced',
    adopt: null,
    write: false,
    patch: {},
    problems: g.problems,
  };
}

// one sync step. cfgState: { loadout2 (cache), loadout_rev (last rev we wrote, undefined = never), loadout_game_rev (game rev adopted) }.
// Returns { status: 'nogame' | 'synced' | 'pending' | 'waiting', adopt: state | null, write: bool, patch: cfg patch, problems }.
//   pending : we wrote a file the game has not applied yet ("Will apply when the game loadout menu closes"; mid-match it applies at once, for the next life)
//   waiting : no game file yet (the game writes it at its first start)
/**
 * Reconcile the game and launcher loadout files.
 * @param {object} G
 * @param {string} dir
 * @param {object} c
 * @returns {object}
 */
function syncStep(G, dir, c) {
  if (!dir)
    return {
      status: 'nogame',
      adopt: null,
      write: false,
      patch: {},
      problems: [],
    };
  return decideSync(readGame(G, dir), c);
}

module.exports = {
  GAME_FILE,
  LAUNCHER_FILE,
  blank,
  lpOf,
  toWire,
  fromWire,
  readGame,
  writeLauncher,
  nextRev,
  syncStep,
  same,
};
