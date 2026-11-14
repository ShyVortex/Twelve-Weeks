'use strict';
// node test/feed-test.js : the local ticker of src/feed.js in English and Polish (TICKER / TICKER_PL, gender forms, rare line), and the daemon feed with the language byte.
const fs = require('fs'), os = require('os'), path = require('path'), vm = require('vm'), assert = require('assert'), { spawn } = require('child_process');
const mkTmp = require('./tmp');
const dm = require('../lib/daemon'), game = require('../lib/game');
const src = (f) => fs.readFileSync(path.join(__dirname, '..', 'src', f), 'utf8');
const ctx = { console, Math, Date, setTimeout, setInterval, document: { hidden: false }, Snd: { play() {} }, Notice: { push: async () => {} }, f2: { clanFeed: async () => ({ ok: true, feed: { ok: true, hasClan: false } }) } };
vm.createContext(ctx);
vm.runInContext(src('ticker.js') + '\n' + src('feed.js') + '\nthis.Feed = Feed; this.TICKER = TICKER; this.TICKER_PL = TICKER_PL;', ctx);
const F = ctx.Feed, clan = { hasClan: true, status: 'alive', faction: 1, factionName: 'WLF', size: 12, sick: 3, hungry: 3 };
F.setClan(clan);
const en = F.sample(60).map((x) => x.text);
assert.ok(en.length > 20 && en.every((t) => !/\{A/.test(t)) && en.every((t) => !/[ąęłńśźż]/.test(t)), 'English ticker');
F.setLang('pl');
const pl = F.sample(80).map((x) => x.text);
assert.ok(pl.length > 20 && pl.every((t) => !/\{A/.test(t)), 'Polish ticker filled: ' + pl.find((t) => /\{A/.test(t)));
assert.ok(pl.some((t) => /[ąęłńśźż]/.test(t)) && pl.every((t) => !/ is | the /.test(t)), 'Polish wording');
assert.ok(ctx.TICKER_PL.rare.includes('{A}') && ctx.TICKER_PL.rare !== ctx.TICKER.rare, 'rare line per language');
F.setLang('en');
assert.ok(F.sample(30).every((t) => !/[ąęłńśźż]/.test(t.text)), 'back to English');
(async () => {
  const tmp = mkTmp('f2fd-'), root = path.join(__dirname, '..', '..', '..'), port = 17158;
  const logPre = ['daemon.log', 'daemon.log.1'].map((f) => fs.existsSync(path.join(root, 'tools', f)));
  const p = spawn('python', ['-I', path.join(root, 'tools', 'daemon.py')], { cwd: tmp, env: { ...process.env, T2R_PORT: String(port), T2R_ADMIN_PORT: '0', T2R_HOST: '127.0.0.1', T2R_DB: path.join(tmp, 't2r.db'), T2R_VERSION: 'test' }, stdio: 'ignore' });
  try {
    let n = null; for (let i = 0; i < 30 && n === null; i++) { await new Promise((r) => setTimeout(r, 500)); n = await dm.onlineCount('127.0.0.1', port); }
    const tok = game.nameToken('Tester', '0123456789abcdef01234567');
    for (const l of ['en', 'pl', undefined]) assert.ok(Array.isArray(await dm.feedLines('127.0.0.1', port, tok, l)), 'feed reply ' + l);
    console.log('feed-test OK: ' + pl.slice(0, 3).join(' / '));
  } finally { p.kill(); await new Promise((r) => setTimeout(r, 400)); ['daemon.log', 'daemon.log.1'].forEach((f, i) => { if (!logPre[i]) try { fs.unlinkSync(path.join(root, 'tools', f)); } catch { /* none */ } }); }
})().catch((e) => { console.error(e); process.exit(1); });
