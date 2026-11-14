/**
 * @file Decode clan-state wire payloads into the view model used by the CLAN tab.
 */
'use strict';
// The game daemon's read-only clan ops -> the object the CLAN tab renders (same shape as tools/update_server/clan_view.py, whose logic this mirrors):
//   0xE0 [64B token] -> 0xE1 clan.state_text(): "v=1 fac= st= day= h= hu= s= need= wk= lday= lparts= lsup= lneed= lgain= ldied= lhungry= lsick= lheal= lleft= ev= evn= ... mx= rw= rl= ag1..3"
//   0xE8 [64B token] -> 0xE9 clan.meta_text():  "v=1 bc1..bc7= bp= ba= bn= mi= mp= ml= mz= mr<id>= mg1..3= mev= lmi= lmp= lmt= lms= lmb= ..."
// (0xE2 / 0xE4 / 0xEE / 0xEF change things and are never sent.) Tables below = tools/clan.py (EVENT_DAYS, GROWTH_NAMES, week_day, WIN_DAY).
const WEEKS = 12,
  DAYS = 84,
  WIN_DAY = 83,
  EVENT_LEN = 3;
const GROWTH_NAMES = ['FRIENDLY GROUP', 'RESCUED HOSTAGES', 'RESCUE ALLIES'];
const EVENT_DAYS = {};
for (let d = 5; d < 81; d += 5) EVENT_DAYS[d] = 'growth';
for (const d of [15, 30, 35, 50, 65, 75, 80]) EVENT_DAYS[d] = 'attack';

/**
 * Parse whitespace-separated key=value fields.
 * @param {string} text
 * @returns {object}
 */
function kv(text) {
  const o = {};
  for (const part of String(text || '')
    .trim()
    .split(/\s+/)) {
    const i = part.indexOf('=');
    if (i > 0) o[part.slice(0, i)] = part.slice(i + 1);
  }
  return o;
}
/**
 * Convert a wire value to a number.
 * @param {unknown} v
 * @returns {number}
 */
const n = (o, k, d = 0) => {
  const v = parseInt(o[k], 10);
  return Number.isFinite(v) ? v : d;
};
/**
 * Compute a clan's needed daily supplies.
 * @param {object} state
 * @returns {number}
 */
const needed = (size) => (size > 0 ? 5 + 2 * size - Math.floor((6 * size) / 5) : 0);
/**
 * Compute the current clan week/day label.
 * @param {number} now
 * @returns {string}
 */
const weekDay = (day) => {
  const d = Math.min(day, DAYS - 1);
  return [Math.floor(d / 7) + 1, (d % 7) + 1];
};
/**
 * Compute the active event window for a timestamp.
 * @param {number} now
 * @returns {object}
 */
function eventWindow(day) {
  for (let s = day; s > day - EVENT_LEN && s >= 0; s--) if (EVENT_DAYS[s]) return s;
  return -1;
}

// stateText: reply of 0xE0; metaText: reply of 0xE9 (may be null); data = GAMEDATA ({missions, boosters})
/**
 * Decode clan state and metadata payloads.
 * @param {string} stateText
 * @param {string} metaText
 * @param {object} data
 * @returns {object}
 */
function fromWire(stateText, metaText, data) {
  const s = kv(stateText),
    m = kv(metaText);
  if (!stateText || s.v === undefined) return null;
  const st = n(s, 'st'),
    fac = n(s, 'fac'),
    day = n(s, 'day');
  const size = n(s, 'h') + n(s, 'hu') + n(s, 's');
  const out = {
    ok: true,
    hasClan: st !== 0,
    faction: fac,
    factionName: fac === 1 ? 'WLF' : fac === 2 ? 'SERAPHITES' : '',
    status: { 0: 'none', 1: 'alive', 2: 'dead', 3: 'won' }[st] || 'none',
    daysDone: day,
    daysTotal: WIN_DAY,
    weeksTotal: n(s, 'wk'),
    size,
    healthy: n(s, 'h'),
    hungry: n(s, 'hu'),
    sick: n(s, 's'),
    needed: n(s, 'need', needed(size)),
    maxSize: Math.max(n(s, 'mx'), size),
    runsWon: n(s, 'rw'),
    runsLost: n(s, 'rl'),
    source: 'daemon',
  };
  if (st === 1) {
    const [wk, dw] = weekDay(day);
    Object.assign(out, { week: wk, dayOfWeek: dw, weeks: WEEKS });
    const sd = eventWindow(day);
    out.event =
      sd >= 0
        ? {
            kind: EVENT_DAYS[sd],
            name: EVENT_DAYS[sd] === 'attack' ? 'ATTACK' : GROWTH_NAMES[Math.floor(sd / 5) % 3],
            startDay: sd,
            dayOfEvent: day - sd + 1,
            length: EVENT_LEN,
          }
        : null;
    const ek = n(s, 'ev'),
      en = n(s, 'evn');
    out.eventToday = ek
      ? {
          kind: ek === 2 ? 'attack' : 'growth',
          name: ek === 2 ? 'ATTACK' : GROWTH_NAMES[en % 3],
        }
      : null;
    const mid = n(m, 'mi'),
      missions = (data && data.missions) || {};
    out.mission =
      mid > 0
        ? {
            id: mid,
            name: (missions[mid] || { name: 'Mission ' + mid }).name,
            progress: n(m, 'mp'),
            daysLeft: n(m, 'ml'),
            goals: [n(m, 'mg1'), n(m, 'mg2'), n(m, 'mg3')],
            inEvent: n(m, 'mev') === 1,
          }
        : null;
    out.boosterNext = n(m, 'bn', 0);
  }
  const bn = (data && data.boosters) || {};
  out.boosters = Object.keys(bn)
    .map(Number)
    .sort((a, b) => a - b)
    .map((id) => ({ id, name: bn[id], count: n(m, 'bc' + id) }));
  const lday = n(s, 'lday', -1);
  if (lday >= 0) {
    out.lastMatch = {
      day: lday,
      parts: n(s, 'lparts'),
      supplies: n(s, 'lsup'),
      needed: n(s, 'lneed'),
      gained: n(s, 'lgain'),
      died: n(s, 'ldied'),
      newHungry: n(s, 'lhungry'),
      newSick: n(s, 'lsick'),
      healed: n(s, 'lheal'),
      leftEarly: !!n(s, 'lleft'),
    };
    const lmi = n(m, 'lmi');
    if (lmi)
      out.lastMission = {
        id: lmi,
        name: ((data && data.missions && data.missions[lmi]) || { name: '?' }).name,
        progress: n(m, 'lmp'),
        tier: n(m, 'lmt'),
        boostersEarned: n(m, 'lmb'),
      };
  }
  return out;
}
module.exports = { fromWire, kv };
