'use strict';
// node test/clan-arc-test.js : story arc steps in the CAMP journal (caps headline, step badge, inline thread of the whole arc so far)
// (copy of the clan-alife-test harness) : the CAMP tab shows the A-Life rows of the clan feed like any other row (kind "alife", mood colours) and, when the update server sends the
// optional "alife" block, a HAPPENING IN CAMP list above the journal; without the block the tab is exactly as before.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = (f) => fs.readFileSync(path.join(__dirname, '..', 'src', f), 'utf8');
const T = (s, p) => String(s).replace(/\{(\w+)\}/g, (m, k) => (p && p[k] != null ? p[k] : m));
const stub = () => ({ addEventListener() {}, querySelector: () => null, getContext: () => ({ clearRect() {}, createRadialGradient: () => ({ addColorStop() {} }), beginPath() {}, arc() {}, fill() {} }), hidden: false, textContent: '', dataset: {}, style: {}, set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h || ''; } });
function run(feedReply) {
  const els = {};
  const document = { hidden: false, body: { classList: { contains: () => false }, contains: () => true }, documentElement: { dataset: {} }, getElementById: (id) => els[id] || (els[id] = stub()) };
  const clan = { ok: true, clan: { ok: true, hasClan: true, status: 'alive', faction: 1, factionName: 'WLF', week: 2, dayOfWeek: 3, daysDone: 9, daysTotal: 83, weeks: 12, size: 12, healthy: 9, hungry: 2, sick: 1,
    needed: 14, boosterNext: 3, boosters: [], runsWon: 0, runsLost: 0, maxSize: 12, lastMatch: null, mission: null, event: null, eventToday: null } };
  const ctx = { console, Math, Date, T, document, requestAnimationFrame() {}, cancelAnimationFrame() {}, setTimeout, clearTimeout, performance: { now: () => 0 }, localStorage: { getItem: () => null, setItem() {} }, matchMedia: () => ({ matches: true }), L10N: { tree() {} }, Scenes: { setFaction() {} }, f2: { clan: async () => clan, clanFeed: async () => ({ ok: true, feed: feedReply }), log() {} }, app: {} };
  vm.createContext(ctx);
  vm.runInContext(src('clan-fx.js') + '\n' + src('clan.js') + '\nthis.Clan = Clan;', ctx);
  return ctx.Clan.load().then(() => els['clan-body'].innerHTML);
}
const feed = [
  { id: 9, day: 8, week: 2, kind: 'chron', mood: 'grieving', style: 'arc_missing', arc: 'a1', step: 3, text: 'DAY 8: ARTEM FOUND ARNALDO AT THE EDGE OF THE RAIL YARD. Too late.', names: ['Artem'], ts: 3 },
  { id: 8, day: 7, week: 1, kind: 'chron', mood: 'afraid', style: 'arc_missing', arc: 'a1', step: 2, text: 'DAY 7: ARTEM WENT LOOKING FOR HIM. He took water and a knife.', names: ['Artem'], ts: 2 },
  { id: 7, day: 6, week: 1, kind: 'chron', mood: 'afraid', style: 'arc_missing', arc: 'a1', step: 1, text: "DAY 6: ARNALDO DIDN'T RETURN FROM THE SUPPLY RAID. The count came up one short.", names: ['Arnaldo'], ts: 1 },
  { id: 6, day: 6, week: 1, kind: 'chron', mood: 'calm', style: 'quiet', text: 'A quiet day. Nothing happened.', names: [], ts: 0 }];
(async () => {
  const h = await run({ ok: true, hasClan: true, feed });
  assert.ok(h.includes('class="jrn arc') && h.includes('data-arc="a1"'), 'an arc step is an arc card');
  assert.ok(h.includes('<h4>ARTEM FOUND ARNALDO AT THE EDGE OF THE RAIL YARD</h4>') && h.includes('<p>Too late.</p>'), 'headline and vignette are split');
  assert.ok(h.includes('STEP 3') && h.includes('THE WHOLE STORY SO FAR'), 'step badge and a thread');
  const thread = h.slice(h.indexOf('<div class="thread" hidden>'), h.indexOf('</div>', h.indexOf('<div class="thread" hidden>')));
  assert.ok(thread.indexOf("DIDN'T RETURN") < thread.indexOf('WENT LOOKING') && thread.indexOf('WENT LOOKING') < thread.indexOf('FOUND ARNALDO'), 'the thread lists every step of the arc in order');
  assert.ok(h.includes('A quiet day.') && !/class="jrn[^"]*arc[^"]*"[^>]*>[^]*A quiet day/.test(h.split('<article').filter((x) => x.includes('A quiet day'))[0] || ''), 'a plain row stays a plain row');
  const pl = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'i18n', 'pl.json'), 'utf8'));
  assert.ok(pl['THE WHOLE STORY SO FAR'] && pl['STEP {n}'] && pl['RAID'], 'translated');
  console.log('clan-arc-test OK');
})().catch((e) => { console.error(e); process.exit(1); });
