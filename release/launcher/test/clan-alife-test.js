'use strict';
// node test/clan-alife-test.js : the CAMP tab shows the A-Life rows of the clan feed like any other row (kind "alife", mood colours) and, when the update server sends the
// optional "alife" block, a HAPPENING IN CAMP list above the journal; without the block the tab is exactly as before.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = (f) => fs.readFileSync(path.join(__dirname, '..', 'src', f), 'utf8');
const T = (s, p) => String(s).replace(/\{(\w+)\}/g, (m, k) => (p && p[k] != null ? p[k] : m));
const stub = () => ({ getContext: () => ({ clearRect() {}, createRadialGradient: () => ({ addColorStop() {} }), beginPath() {}, arc() {}, fill() {} }), hidden: false, textContent: '', dataset: {}, style: {}, set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h || ''; } });
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
const feed = [{ id: 7, day: 8, week: 2, kind: 'alife', mood: 'hopeful', text: 'Jonas and Max are back from the old library with canned food.', names: ['Jonas'], ts: 1 },
  { id: 6, day: 7, week: 1, kind: 'calm', mood: 'calm', text: 'A quiet day.', names: [], ts: 0 }];
(async () => {
  const h = await run({ ok: true, hasClan: true, feed, alife: { day: 9, weather: 'rain', season: 'deep winter', ongoing: ['Marek and Ola are out at the old clinic after fuel, due back in two days.', 'The work on the rain catchers is about half done.'] } });
  assert.ok(/class="jrn good[ "]/.test(h) && h.includes('back from the old library with canned food'), 'an A-Life row is a normal journal row (hopeful = good colour)');
  assert.ok(h.includes('HAPPENING IN CAMP') && h.includes('out at the old clinic') && h.includes('rain catchers'), 'ongoing block');
  assert.ok(h.indexOf('HAPPENING IN CAMP') < h.indexOf('class="jrnl"'), 'the block comes before the journal');
  const h2 = await run({ ok: true, hasClan: true, feed });
  assert.ok(!h2.includes('HAPPENING IN CAMP') && h2.includes('A quiet day.'), 'no block without the optional alife field');
  const h3 = await run({ ok: true, hasClan: true, feed, alife: { ongoing: ['<b>x</b> & y'] } });
  assert.ok(h3.includes('&lt;b&gt;x&lt;/b&gt; &amp; y'), 'texts are escaped');
  const pl = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'i18n', 'pl.json'), 'utf8')), en = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'i18n', 'en.json'), 'utf8'));
  assert.ok(pl['HAPPENING IN CAMP'] && en['HAPPENING IN CAMP'] === 'HAPPENING IN CAMP' && /[a-z]/i.test(pl['HAPPENING IN CAMP']) && pl['HAPPENING IN CAMP'] !== 'HAPPENING IN CAMP', 'translated');
  console.log('clan-alife-test OK');
})().catch((e) => { console.error(e); process.exit(1); });
