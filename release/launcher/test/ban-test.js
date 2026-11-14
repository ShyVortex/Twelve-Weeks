'use strict';
// node test/ban-test.js : a banned player gets the ban screen, no Discord, a refused Play; a network error never bans; an explicit "not banned"
// lifts a stored ban; the hardware hashes are the game's (tools/ext/hwid.c).
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const mkTmp = require('./tmp');
const { createBanGuard, banMessage } = require('../lib/ban');
const hwid = require('../lib/hwid');
const { read } = require('./srcs');

let passed = 0;
const T = async (name, fn) => {
  try {
    await fn();
    passed++;
    console.log('  ok  ' + name);
  } catch (e) {
    console.log('FAIL  ' + name + '\n' + ((e && e.stack) || e));
    process.exitCode = 1;
  }
};

const mkGuard = (answer, extra = {}) => {
  const dir = mkTmp('ban-');
  const calls = [];
  const g = createBanGuard({
    file: path.join(dir, 'ban.json'),
    getHost: () => 'http://127.0.0.1:1',
    getHashes: async () => ['a'.repeat(24), 'b'.repeat(24)],
    getSteamIds: async () => ['76561198000000001'],
    getJson: async (url) => {
      calls.push(url);
      if (typeof answer === 'function') return answer();
      return answer;
    },
    ...extra,
  });
  return { g, dir, calls, file: path.join(dir, 'ban.json') };
};

// ---- a fake DOM just big enough for src/app/ban.js
function fakeRenderer() {
  const mk = (cls = '') => {
    const el = {
      textContent: '',
      children: [],
      _c: new Set(cls.split(' ').filter(Boolean)),
      className: cls,
      classList: {
        add: (c) => el._c.add(c),
        remove: (c) => el._c.delete(c),
        toggle: (c, on) => (on === undefined ? !el._c.delete(c) && el._c.add(c) : on ? el._c.add(c) : el._c.delete(c)),
        contains: (c) => el._c.has(c),
      },
      appendChild: (c) => {
        el.children.push(c);
        c.parent = el;
      },
      remove: () => {
        if (el.parent) el.parent.children = el.parent.children.filter((x) => x !== el);
      },
      querySelector: (sel) => {
        const c = sel.slice(1);
        return el.children.find((x) => x._c.has(c) || x.className === c) || null;
      },
      blur() {},
    };
    return el;
  };
  const overlay = mk('');
  const title = mk('ld-title');
  title.textContent = 'LOADING';
  const sub = mk('ld-sub');
  sub.textContent = 'Please wait.';
  overlay.appendChild(title);
  overlay.appendChild(sub);
  overlay.classList.add('gone');
  const listeners = {};
  const body = mk('');
  const document = {
    body,
    activeElement: null,
    getElementById: (id) => (id === 'loading' ? overlay : mk()),
    createElement: () => mk(),
    addEventListener: (ev, fn) => (listeners[ev] = fn),
  };
  const logs = [];
  let ban = { ok: true, banned: false, reason: '' };
  const ctx = {
    document,
    T: (s, v) => String(s).replace(/\{(\w+)\}/g, (_, k) => (v && v[k] != null ? v[k] : '')),
    f2: { log: (m) => logs.push(m), ban: async () => ban },
    lupBusy: false,
    setInterval: () => 0,
    console,
  };
  vm.createContext(ctx);
  vm.runInContext([read('src/app/core.js'), read('src/app/ban.js')].join(String.fromCharCode(10)) + '\nthis.applyBan = applyBan; this.banText = banText; this.getState = () => banState; this.startBanWatch = startBanWatch;', ctx);
  return { ctx, overlay, title, sub, body, listeners, logs, setBan: (b) => (ban = b) };
}

(async () => {
  await T('server says banned -> verdict stored, assertNotBanned throws, file written', async () => {
    const { g, file } = mkGuard({ banned: true, reason: 'cheating' });
    assert.strictEqual(g.current().banned, false);
    const v = await g.check();
    assert.deepStrictEqual(v, { banned: true, reason: 'cheating' });
    assert.throws(() => g.assertNotBanned(), /YOU ARE BANNED.*No appeals are being taken in at this time.*cheating/);
    assert.ok(fs.existsSync(file));
  });

  await T('the check sends the hardware hashes and the steam ids', async () => {
    const { g, calls } = mkGuard({ banned: false });
    await g.check();
    assert.strictEqual(calls.length, 1);
    const u = new URL(calls[0]);
    assert.strictEqual(u.pathname, '/ban-check');
    assert.strictEqual(u.searchParams.get('h'), 'a'.repeat(24) + ',' + 'b'.repeat(24));
    assert.strictEqual(u.searchParams.get('s'), '76561198000000001');
  });

  await T('a stored ban is there at the next start, before (and without) any server answer', async () => {
    const a = mkGuard({ banned: true, reason: '' });
    await a.g.check();
    const g2 = createBanGuard({ file: a.file, getHost: () => 'h', getHashes: async () => [], getSteamIds: async () => [], getJson: async () => { throw new Error('timeout'); } });
    assert.strictEqual(g2.current().banned, true);
    assert.throws(() => g2.assertNotBanned(), /YOU ARE BANNED/);
    await g2.check(); // the server is blocked / offline: still banned
    assert.strictEqual(g2.current().banned, true);
  });

  await T('a network error never bans', async () => {
    const { g, file } = mkGuard(() => { throw new Error('ECONNREFUSED'); });
    const v = await g.check();
    assert.strictEqual(v.banned, false);
    assert.doesNotThrow(() => g.assertNotBanned());
    assert.ok(!fs.existsSync(file));
  });

  await T('garbage answers never ban (HTML, missing field, string "true")', async () => {
    for (const bad of [null, '<html>', {}, { banned: 'true' }, { banned: 1 }, { error: 'x' }]) {
      const { g } = mkGuard(bad);
      assert.strictEqual((await g.check()).banned, false, JSON.stringify(bad));
      assert.doesNotThrow(() => g.assertNotBanned());
    }
  });

  await T('an explicit banned:false lifts a stored ban (unban)', async () => {
    const a = mkGuard({ banned: true, reason: 'x' });
    await a.g.check();
    const g2 = createBanGuard({ file: a.file, getHost: () => 'h', getHashes: async () => [], getSteamIds: async () => [], getJson: async () => ({ banned: false }) });
    assert.strictEqual(g2.current().banned, true);
    await g2.check();
    assert.strictEqual(g2.current().banned, false);
    assert.doesNotThrow(() => g2.assertNotBanned());
    assert.ok(!fs.existsSync(a.file));
  });

  await T('no update host -> nothing asked, nothing banned', async () => {
    const { g, calls } = mkGuard({ banned: true }, { getHost: () => '' });
    assert.strictEqual((await g.check()).banned, false);
    assert.strictEqual(calls.length, 0);
  });

  await T('ban screen: YOU ARE BANNED + no appeals text, overlay up, body.banned (Discord hidden by CSS), keys swallowed', async () => {
    const r = fakeRenderer();
    r.ctx.applyBan({ banned: true, reason: '' });
    assert.strictEqual(r.title.textContent, 'YOU ARE BANNED');
    assert.strictEqual(r.sub.textContent, 'No appeals are being taken in at this time.');
    assert.ok(!r.overlay.classList.contains('gone'));
    assert.ok(r.overlay.classList.contains('ld-ban'));
    assert.ok(r.body.classList.contains('banned'));
    let stopped = 0, prevented = 0;
    r.listeners.keydown({ preventDefault: () => prevented++, stopImmediatePropagation: () => stopped++ });
    assert.deepStrictEqual([prevented, stopped], [1, 1]);
    assert.match(r.ctx.banText(), /You are banned from Twelve Weeks\. No appeals are being taken in at this time\./);
  });

  await T('ban screen shows an explicit reason; lifting the ban restores the loading text and hides the overlay', async () => {
    const r = fakeRenderer();
    r.ctx.applyBan({ banned: true, reason: 'cheating' });
    assert.ok(r.overlay.children.some((c) => c.textContent === 'Reason: cheating'));
    r.ctx.applyBan({ banned: false });
    assert.strictEqual(r.title.textContent, 'LOADING');
    assert.ok(r.overlay.classList.contains('gone'));
    assert.ok(!r.body.classList.contains('banned'));
    assert.ok(!r.overlay.children.some((c) => c.className === 'ld-reason'));
    let prevented = 0;
    r.listeners.keydown({ preventDefault: () => prevented++, stopImmediatePropagation() {} });
    assert.strictEqual(prevented, 0);
  });

  await T('not banned: the page is untouched', async () => {
    const r = fakeRenderer();
    r.ctx.applyBan({ banned: false });
    assert.strictEqual(r.title.textContent, 'LOADING');
    assert.ok(r.overlay.classList.contains('gone'));
    assert.ok(!r.body.classList.contains('banned'));
  });

  await T('wiring: Play refused in the renderer and in the main process, Discord hidden and guarded, ban.css + ban.js loaded', async () => {
    assert.match(read('src/app/play.js'), /async function doPlay\(\) \{\s+if \(banState\.banned\)/);
    const jobs = read('main/jobs.js');
    for (const fn of ['runPlay(opts = {})', 'runPlaySp()', 'runUpdate({ full = false } = {})'])
      assert.ok(jobs.includes(`async function ${fn} {\n    if (ban) ban.assertNotBanned();`), fn);
    assert.match(read('src/app/ui.js'), /\$\('discord'\)\.addEventListener\('click', \(\) => \{\s+if \(banState\.banned\) return;/);
    assert.match(read('src/ban.css'), /body\.banned #discord[^{]*\{\s*display: none !important/);
    const html = read('src/index.html');
    assert.ok(html.includes('href="ban.css"') && html.includes('src="app/ban.js"'));
    assert.match(read('src/app.js'), /startBanWatch\(\)/);
    assert.match(read('main.js'), /ban\.check\(\)/);
  });

  // ---- hardware hashes
  await T('component hash = first 12 bytes of sha256("T2R-HWID1" + tag + data), hex', async () => {
    const data = Buffer.from('some-machine-guid', 'latin1');
    const want = crypto.createHash('sha256').update(Buffer.concat([Buffer.from('T2R-HWID1'), Buffer.from([1]), data])).digest('hex').slice(0, 24);
    assert.strictEqual(hwid.componentHash(1, data), want);
    assert.strictEqual(want.length, 24);
  });

  await T('hashesFromDump keeps the game order and skips missing/garbage components', async () => {
    const dump = '3:41424344\r\n1:6162\r\nx:zz\r\n2:' + '0a'.repeat(16) + '\r\n';
    const h = hwid.hashesFromDump(dump);
    assert.deepStrictEqual(h, [hwid.componentHash(1, Buffer.from('ab')), hwid.componentHash(2, Buffer.alloc(16, 0x0a)), hwid.componentHash(3, Buffer.from('ABCD'))]);
    assert.deepStrictEqual(hwid.hashesFromDump('2:zz\n1:\n'), []);
  });

  await T('hardwareHashes: not Windows -> []; a failing powershell -> []; never throws', async () => {
    assert.deepStrictEqual(await hwid.hardwareHashes({ platform: 'linux' }), []);
    assert.deepStrictEqual(await hwid.hardwareHashes({ platform: 'win32', exec: (a, b, c, cb) => cb(new Error('spawn failed'), '') }), []);
    assert.deepStrictEqual(await hwid.hardwareHashes({ platform: 'win32', exec: () => { throw new Error('boom'); } }), []);
    const ok = await hwid.hardwareHashes({ platform: 'win32', exec: (a, b, c, cb) => cb(null, '1:6162\r\n') });
    assert.deepStrictEqual(ok, [hwid.componentHash(1, Buffer.from('ab'))]);
  });

  await T('banMessage', async () => {
    assert.strictEqual(banMessage(''), 'YOU ARE BANNED. No appeals are being taken in at this time.');
  });

  console.log(`\n${passed} ban checks passed`);
})();
