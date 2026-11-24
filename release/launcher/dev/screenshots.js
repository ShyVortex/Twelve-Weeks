/**
 * @file Automated Electron screenshot scenarios for development.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const defaults = require('../defaults');
const { installShotApi } = require('./shot-api');

/**
 * Build the shared helpers each scenario uses.
 * @param {object} options
 * @returns {object}
 */
function makeDriver({ app, window, config, log, locale }) {
  const win = window;
  const cfg = config.values;
  const dir = process.env.F2_SHOT;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const snap = async (name) => {
    await win.webContents.capturePage();
    await wait(500);
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(dir, name + '.png'), img.toPNG());
  };
  const js = (code) => win.webContents.executeJavaScript(code);
  const shot = (call) => js(`window.__shot.${call}`);
  const click = (selector) => js(`document.querySelector('${selector}').click()`);
  const hover = (selector, index) =>
    js(
      `document.querySelectorAll('${selector}')[${index}].dispatchEvent(new MouseEvent('mouseover',{bubbles:true}))`,
    );
  return { app, win, cfg, dir, log, locale, wait, snap, js, shot, click, hover };
}

/**
 * Motion/transition scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioMotion({ wait, snap, shot, log }) {
  await wait(6000);
  const out = { reduced: await shot('reduced()') };
  const seq = async (name, col, act) => {
    await act();
    const v = [];
    let prev = 0;
    for (const t of [0, 70, 150, 260, 500]) {
      await wait(t - prev);
      prev = t;
      v.push(await shot(`sampleCol(${col})`));
    }
    out[name] = v.join(' ');
    await wait(300);
  };
  await shot(`view('loadout')`);
  await wait(900);
  await seq('enterEdit', 0, () => shot('edit()'));
  await shot('scrollLoadoutCol(1, 0)');
  await seq('rowSwitchPicker', 1, () => shot('tab(2)'));
  const pick = await shot('rowAt(3)');
  await shot('scrollLoadoutCol(1, 40)');
  const st0 = await shot('scrollTopCol(1)');
  await seq('itemSwitchDetails', 2, () => shot(`clickRef(${pick})`));
  out.scrollKept = (await shot('scrollTopCol(1)')) === st0;
  out.newHighlight = await shot('mNewCount()');
  await seq('backToList', 0, () => shot('back()'));
  log('MOTION TEST ' + JSON.stringify(out));
  await snap('motion-' + (process.env.F2_REDUCED ? 'reduced' : 'normal'));
}

/**
 * Notices overlay scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioNotices({ wait, snap, shot, log, locale }) {
  await wait(6000);
  const out = {};
  const upd = (n) => shot('notices(' + JSON.stringify({ notices: [n] }) + ')');
  const txt = () => shot('alertText()');
  const now = Date.now() / 1000;
  await upd({ id: 9, kind: 'u', param: 0, text: '' });
  await wait(300);
  out.update = await txt();
  await upd({ id: 9, kind: 'u', param: 0, text: '' });
  out.updateAgainSame = (await txt()) === out.update;
  await upd({ id: 3, kind: 'r', param: 130, text: 'patch', endsAt: now + 130 });
  await wait(300);
  out.restart = await txt();
  await wait(1500);
  out.restart2 = await txt();
  await shot(
    'notices(' +
      JSON.stringify({
        notices: [
          { id: 4, kind: 't', param: 0, text: 'Maintenance tonight at 22:00' },
          { id: 3, kind: 'r', param: 200, text: 'patch', endsAt: Date.now() / 1000 + 200 },
        ],
      }) +
      ')',
  );
  await wait(300);
  out.free = await txt();
  await upd({ id: 5, kind: 's', param: 0, text: '' });
  await wait(300);
  out.shutdown = await txt();
  log('NOTICES TEST ' + JSON.stringify(out));
  await snap('notice-' + locale.langNow());
}

/**
 * Alert panel scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioAlert({ wait, snap, shot, log }) {
  await wait(6000);
  const out = { reduced: await shot('reduced()') };
  await shot(`view('loadout')`);
  await wait(800);
  await shot('edit()');
  await wait(300);
  for (const [row, nm, lv] of [
    [2, 'JACK OF ALL TRADES', 2],
    [3, 'HAWK-EYED', 1],
  ]) {
    await shot(`tab(${row})`);
    await wait(150);
    const ref = await shot(`row(${JSON.stringify(nm)})`);
    await shot(`clickRef(${ref})`);
    await wait(150);
    const lvRef = await shot(`lvRef(${ref}, '.lv[data-lv="${lv}"]')`);
    await shot(`clickRef(${lvRef})`);
    await wait(150);
  }
  await shot('tab(1)');
  await wait(200);
  const shotgun = await shot(`row(${JSON.stringify('TACTICAL SHOTGUN')})`);
  const t0 = Date.now();
  await shot(`clickRef(${shotgun})`);
  let shown = -1;
  for (let i = 0; i < 100; i++) {
    if (await shot('alertOn()')) {
      shown = Date.now() - t0;
      break;
    }
    await wait(5);
  }
  out.classOnAfterMs = shown;
  out.title = await shot('alertTitle()');
  out.desc = await shot('alertDesc()');
  await wait(150);
  out.opacityMid = await shot('alertOpacity()');
  for (let i = 0; i < 4; i++) {
    await shot(`clickRef(${shotgun})`);
    await wait(60);
  }
  out.panels = await shot('alertPanels()');
  out.queuedChildren = await shot('alertChildren()');
  await wait(600);
  out.opacityFull = await shot('alertOpacity()');
  await shot(`clickRef(${await shot(`row(${JSON.stringify('FRONTIER RIFLE')})`)})`);
  await wait(80);
  out.replaced = await shot('alertDesc()');
  out.clanBoxLifted = await shot('clanBoxTransform()');
  log('ALERT TEST ' + JSON.stringify(out));
  await wait(500);
  await snap('alert-' + (process.env.F2_REDUCED ? 'reduced' : 'normal'));
}

/**
 * Display/settings scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioDisplay({ wait, snap, shot, js, log }) {
  await wait(7000);
  await shot(`view('settings')`);
  await wait(800);
  await shot(`sub('look')`);
  await wait(1500);
  log('DISPLAY blocker ' + (await shot('bgBlock()')));
  await snap('display-' + (process.env.F2_TAG || 'x'));
  await js(`document.getElementById('mus-set').scrollIntoView({block: 'center'})`); // the music rows below the fold
  await wait(600);
  await snap('display-music-' + (process.env.F2_TAG || 'x'));
}

/**
 * i18n audit scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioAudit({ wait, shot, log }) {
  await wait(7000);
  const seen = new Set();
  const steps = [
    () => shot(`view(null)`),
    () => shot(`view('clan')`),
    () => shot(`view('loadout')`),
    async () => {
      await shot(`view('loadout')`);
      await shot('edit()');
    },
    () => shot('tab(2)'),
    async () => {
      await shot('tab(1)');
      await shot(`click('.orow:nth-of-type(3)')`);
    },
    () => shot(`view('news')`),
    () => shot(`view('report')`),
    () => shot(`view('settings')`),
    () => shot(`sub('look')`),
    () => shot(`sub('files')`),
    () => shot(`sub('about')`),
  ];
  for (const step of steps) {
    await step();
    await wait(900);
    for (const text of await shot('untranslated()')) seen.add(text);
  }
  log('AUDIT English text left in ' + (await shot('lang()')) + ': ' + JSON.stringify([...seen]));
}

/**
 * Window size/overflow scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioSizes({ wait, snap, shot, log, win }) {
  await wait(6000);
  await shot(`view('loadout')`);
  await wait(1500);
  await shot('edit()');
  await wait(800);
  for (const [name, width, height] of [
    ['default', 1440, 860],
    ['min', 1300, 760],
    ['1920', 1920, 1080],
  ]) {
    win.setContentSize(width, height);
    await wait(1500);
    await shot('tab(1)');
    await wait(700);
    await shot('rowAt(3)').then((ref) => shot(`clickRef(${ref})`));
    await wait(700);
    const overflow = JSON.stringify(await shot('colsOverflow()'));
    log(
      'SIZES ' +
        name +
        ' ' +
        width +
        'x' +
        height +
        ' columns [class, scrollW, clientW, horizontalOverflow]: ' +
        overflow,
    );
    await snap('size-' + name);
  }
}

/**
 * Startup timing scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioLoad({ wait, snap, shot, log }) {
  const started = Date.now();
  await wait(400);
  await snap('00-loading-overlay');
  for (let i = 0; i < 400; i++) {
    const done = (await shot('ready()')) || (await shot('loadDone()'));
    if (done) break;
    await wait(100);
  }
  const elapsed = Date.now() - started;
  const overlay = await shot('loadingState()');
  log(
    `LOAD TIME data on screen after ${elapsed} ms (+${
      started - defaults.appStart()
    } ms to window); overlay ${overlay}`,
  );
  await wait(1200);
  log('LOAD overlay after 1.2 s more: ' + (await shot('loadingState()')));
}

/**
 * Gear-up interaction scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioGear({ wait, shot, log }) {
  await wait(6000);
  const out = {};
  await shot(`view('loadout')`);
  await wait(600);
  await shot('edit()');
  await wait(300);
  const clickRow = async (row, name) => {
    await shot(`tab(${row})`);
    await wait(200);
    if (name) {
      await shot(`clickRef(${await shot(`row(${JSON.stringify(name)})`)})`);
      await wait(200);
    }
  };
  await clickRow(2, 'HAWK-EYED');
  out.hawk = await shot(`text('[data-row="2"] b')`);
  await clickRow(3, 'CRAFTER');
  await clickRow(4, 'FIRST-AID TRAINING');
  await clickRow(5, 'JACK OF ALL TRADES');
  out.jack = await shot(`text('[data-row="5"] b')`);
  const h = await shot('h3()');
  await shot(`hoverRef(${await shot(`row(${JSON.stringify('REVIVER')})`)})`);
  await wait(200);
  out.hoverKeepsDetails = h === (await shot('h3()'));
  await shot('tab(1)');
  await wait(200);
  const lpBefore = await shot('lp()');
  await shot(`clickRef(${await shot(`bizRow(${JSON.stringify('TACTICAL SHOTGUN')})`)})`);
  await wait(300);
  out.gunEquipped = await shot(`text('[data-row="1"] b')`);
  out.gunDetails = await shot('h3()');
  out.notice = await shot('noticeText()');
  out.lp = lpBefore + ' -> ' + (await shot('lp()'));
  await shot(`clickRef(${await shot(`bizRow(${JSON.stringify('HUNTING RIFLE')})`)})`);
  await wait(200);
  out.gunOk = await shot(`text('[data-row="1"] b')`);
  const q = await shot(`quietRef(${await shot(`bizRow(${JSON.stringify('HUNTING RIFLE')})`)}, 1)`);
  await shot(`clickRef(${q})`);
  await wait(300);
  out.quietDenied = await shot(`text('[data-row="1"] b')`);
  log('GEAR TEST ' + JSON.stringify(out));
}

/**
 * Clan view scenario.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioClan({ wait, snap, shot }) {
  await wait(6000);
  await shot(`view('clan')`);
  await wait(3500);
  await snap('clan-only');
}

/**
 * Default tour of all views.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioDefault({ wait, snap, shot, click, hover }) {
  for (let i = 0; i < 40; i++) {
    if (await shot('ready()')) break;
    await wait(2000);
  }
  await wait(2500);
  await snap('01-home');
  await wait(9000);
  await snap('01b-ticker-notice');
  await shot(`view('clan')`);
  await wait(2000);
  await snap('02-clan');
  await shot('scrollClan()');
  await wait(1200);
  await snap('02b-clan-camp');
  await shot(`view('loadout')`);
  await wait(2000);
  await snap('03-gearup-list');
  await shot('edit()');
  await wait(2000);
  await shot('tab(0)');
  await wait(2000);
  await hover('.orow', 1);
  await wait(2000);
  await snap('04-gearup-small');
  await shot('tab(1)');
  await wait(2000);
  await hover('.orow', 4);
  await wait(2000);
  await snap('05-gearup-large');
  await shot(`click('.orow .lv[data-q="1"]')`);
  await wait(2000);
  await snap('05b-gearup-large-quiet');
  await shot('tab(2)');
  await wait(2000);
  await hover('.orow', 8);
  await wait(2000);
  await snap('06-gearup-skill');
  await shot('tab(6)');
  await wait(2000);
  await hover('.orow', 3);
  await wait(2000);
  await snap('07-gearup-purchasable');
  await shot('back()');
  await wait(2000);
  await shot(`clickRef(${await shot('refAt(".lrow", 8)')})`);
  await wait(2000);
  await snap('08-gearup-class');
  await shot(`view('news')`);
  await wait(2000);
  await snap('09-news');
  await shot(`view('report')`);
  await wait(2000);
  await shot(
    'setReportText(' +
      JSON.stringify(
        'The game froze for two seconds after the last round and then the scoreboard was empty.',
      ) +
      ')',
  );
  await snap('10-report');
  await shot(`view('settings')`);
  await wait(2000);
  await snap('11-settings-game');
  for (const [name, sub] of [
    ['12-settings-display', 'look'],
    ['13-settings-files', 'files'],
    ['14-settings-about', 'about'],
  ]) {
    await shot(`sub(${JSON.stringify(sub)})`);
    await wait(2000);
    await snap(name);
  }
  await shot(`view('settings')`);
  await wait(2000);
  await shot('notify("Mock server: update downloaded.", 3000)');
  if (process.env.F2_SHOT_UPDATE) {
    await click('#mi-update');
    await wait(2000);
    await snap('15-downloading');
    await wait(8000);
    await snap('16-updated');
  }
}

/**
 * Settings > MAPS tab scenario (F2_SHOT_NAME = file name, default maps).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioMaps({ wait, snap, shot, click }) {
  await wait(5000);
  await shot(`view('settings')`);
  await wait(1500);
  await shot(`sub('maps')`);
  await wait(2500);
  if (process.env.F2_SHOT_P1) await click('.mp[data-id=p1-bookstore]');
  await wait(800);
  await snap(process.env.F2_SHOT_NAME || 'maps');
}

/**
 * Part I importer UI scenario: MAPS tab in four states (no Part I, Part I set, converting, installed). Drives the renderer with
 * realistic state objects, no real conversion (F2_SHOT_NAME = file prefix).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioP1Maps({ wait, snap, shot, js, click }) {
  const pre = process.env.F2_SHOT_NAME || 'p1maps';
  await wait(5000);
  await shot(`view('settings')`);
  await wait(1500);
  await shot(`sub('maps')`);
  await wait(2500);
  const draw = (o) =>
    js(`(() => { const b = JSON.parse(JSON.stringify(mapsSt));
      const o = ${JSON.stringify(o)};
      b.converter = o.converter; b.tlou1 = o.tlou1; b.reimport = false;
      b.part1.forEach((m) => { m.installed = o.installed; });
      drawMaps(b); hideProgress(); })()`);
  await draw({ converter: true, installed: false, tlou1: { dir: '', valid: false, reason: '' } });
  await wait(600);
  await snap(pre + '-1-locked');
  const dir = 'D:\\Games\\The Last of Us Part I';
  await draw({ converter: true, installed: false, tlou1: { dir, valid: true, reason: '' } });
  await click('.mp[data-id=p1-bookstore]');
  await wait(600);
  await snap(pre + '-2-ready');
  await js(`(() => { $('mp-conv').disabled = true; $('mp-cancel').hidden = false;
    showProgress({ phase: 'play-convert', label: 'Converting p1-bookstore:levels', done: 18, total: 40, files: 40, filesDone: 18, unit: 'pct', eta: 410 }); })()`);
  await wait(600);
  await snap(pre + '-3-converting');
  await draw({ converter: true, installed: true, tlou1: { dir, valid: true, reason: '' } });
  await wait(600);
  await snap(pre + '-4-installed');
}

/**
 * FRIENDS tab scenario: the four tabs (needs a daemon with demo friends: F2_SERVER).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioFriends({ wait, snap, shot, js, log }) {
  const tag = process.env.F2_TAG || 'en';
  await wait(6000);
  await shot(`view('friends')`);
  await wait(2500);
  await snap(`friends-${tag}-1-list`);
  const tab = (t) => js(`document.querySelector('[data-ftab="${t}"]').click()`);
  await tab('pending');
  await wait(1200);
  await snap(`friends-${tag}-2-pending`);
  await tab('add');
  await wait(800);
  await js(
    `(() => { const q = document.getElementById('fr-q'); q.value = 'jo'; q.dispatchEvent(new Event('input', { bubbles: true })); document.querySelector('[data-fr="search"]').click(); })()`,
  );
  await wait(1800);
  await snap(`friends-${tag}-3-add`);
  await tab('party');
  await wait(1200);
  log(
    'FRIENDS active tab after PARTY click: ' +
      (await js(`document.querySelector('#fr-tabs .active').dataset.ftab`)),
  );
  await snap(`friends-${tag}-4-party`);
}

/**
 * Bottom-right buttons (ADD TO STEAM sits under Discord): home, Steam hover, Discord hover, settings.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioKofi({ wait, snap, js }) {
  await wait(6000);
  await js(
    `const st=document.createElement('style'); st.textContent='#prog{visibility:hidden!important} #app:not(.has-view) #steamadd, #app:not(.has-view) #discord, #app[data-view=settings] #steamadd, #app[data-view=settings] #discord{opacity:1!important;pointer-events:auto!important;transform:none!important}'; document.head.appendChild(st)`,
  ); // a real download in the shot run hides the buttons
  await snap('kofi-1-home');
  await js(
    `document.getElementById('steamadd').style.cssText='border-color:#fff;color:#fff;background:rgba(255,255,255,.06)'`,
  );
  await snap('kofi-2-steam-hover');
  await js(`document.getElementById('steamadd').style.cssText=''`);
  await js(
    `document.getElementById('discord').style.cssText='color:#fff;background:rgba(88,101,242,.22);border-color:#5865f2'`,
  );
  await snap('kofi-2b-discord-hover');
  await js(`document.getElementById('discord').style.cssText=''`);
  await js(`document.querySelector('.mi[data-view=settings]').click()`);
  await wait(4500);
  await js(`document.getElementById('prog').hidden = true`);
  await snap('kofi-3-settings');
}

/**
 * ADD TO STEAM button: home, hover, confirm (Steam running), result notice.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioSteam({ wait, snap, js }) {
  await wait(6000);
  await js(`document.getElementById('prog').hidden = true`);
  await snap('steam-1-home');
  await js(
    `document.getElementById('steamadd').style.cssText='border-color:#fff;color:#fff;background:rgba(255,255,255,.06)'`,
  );
  await wait(500);
  await snap('steam-2-hover');
  await js(`document.getElementById('steamadd').style.cssText=''`);
  await js(
    `f2.steamState = async () => ({ ok: true, found: true, running: true }); f2.steamAdd = async () => ({ ok: true, result: 'added' }); document.getElementById('steamadd').click()`,
  );
  await wait(700);
  await snap('steam-3-confirm');
  await js(`document.getElementById('cfm-yes').click()`);
  await wait(2200);
  await snap('steam-4-added');
}

/**
 * Steam started AFTER the launcher: everything that depends on Steam must recover without a restart (fake Steam process probe).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioSteamLate({ wait, snap, js, log }) {
  const hooks = require('../lib/game').testHooks;
  let up = false;
  hooks.steam = async () => ({ stdout: up ? 'yes' : '', err: null });
  await wait(6000);
  const dump = () =>
    js(
      `JSON.stringify({ steamDown, state: document.getElementById('st-state').textContent, play: document.getElementById('mi-play').textContent, disabled: document.getElementById('mi-play').parentElement.disabled, name: document.getElementById('in-name').value })`,
    );
  await wait(5000);
  console.log('STEAMLATE down ' + (await dump()));
  await snap('steamlate-1-down');
  up = true;
  await wait(6000);
  console.log('STEAMLATE up ' + (await dump()));
  await snap('steamlate-2-up');
}

/**
 * ADD TO STEAM, shortcut already in Steam: collapsed box, real mouse hover (expanded), remove confirm.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioSteamAdded({ wait, snap, js, win }) {
  await wait(6000);
  await js(
    `document.getElementById('prog').hidden = true; f2.steamState = async () => ({ ok: true, found: true, added: true, running: false }); f2.steamRemove = async () => ({ ok: true, result: 'removed' }); checkSteamBtn()`,
  );
  await wait(800);
  await snap('steamadded-1-collapsed');
  const r = JSON.parse(
    await js(`JSON.stringify(document.getElementById('steamadd').getBoundingClientRect())`),
  );
  win.webContents.sendInputEvent({
    type: 'mouseMove',
    x: Math.round(r.x + r.width / 2),
    y: Math.round(r.y + r.height / 2),
  });
  await wait(700);
  await snap('steamadded-2-hover');
  console.log(
    'STEAMADDED box',
    JSON.stringify(r),
    await js(`JSON.stringify(document.getElementById('steamadd').getBoundingClientRect())`),
  );
  await js(`document.getElementById('steamadd').click()`);
  await wait(700);
  await snap('steamadded-3-remove-confirm');
  await js(`document.getElementById('cfm-yes').click()`);
  win.webContents.sendInputEvent({ type: 'mouseMove', x: 300, y: 300 });
  await wait(2500);
  await snap('steamadded-4-removed');
}

/**
 * STATUS panel scenario: collapsed, expanded, server offline, game not found (F2_SHOT_NAME = file prefix).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioStatus({ wait, snap, js }) {
  const pre = process.env.F2_SHOT_NAME || 'status';
  await wait(6000);
  const crop = () => js(`document.getElementById('home').getBoundingClientRect().toJSON()`);
  const force = (code) => js(`(() => { ${code} })()`);
  await force(
    `localStorage.setItem('f2-status-open','0'); document.getElementById('st-rows').classList.remove('open');`,
  );
  await force(
    `state = Object.assign({}, state, { gameOk: true, gameDir: 'C:/Games/TLOU2' }); renderState();`,
  );
  await wait(700);
  await snap(pre + '-1-collapsed');
  await force(`document.getElementById('st-more').click()`);
  await wait(900);
  await snap(pre + '-2-expanded');
  await force(`document.getElementById('st-more').click()`);
  await force(
    `status = { online: false, reachable: false }; cfg.resolved.server = 'play.example.net:7002'; renderStatus();`,
  );
  await wait(900);
  await snap(pre + '-3-collapsed-server-offline');
  await force(`state = Object.assign({}, state, { gameOk: false }); renderState();`);
  await wait(900);
  await snap(pre + '-4-collapsed-server-offline-game-missing');
  await force(`document.getElementById('st-more').click()`);
  await wait(900);
  await snap(pre + '-5-expanded-both-problems');
  await force(`document.getElementById('row-nw').click()`);
  await wait(900);
  await snap(pre + '-6-news-after-click');
  await crop();
}

/**
 * Ban screen: the overlay with YOU ARE BANNED, then with a reason; Discord / Steam buttons hidden.
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioBan(ctx) {
  const { wait, snap, js } = ctx;
  await wait(2500);
  await js(`applyBan({ banned: true, reason: '' })`);
  await wait(900);
  await snap('ban');
  await js(`applyBan({ banned: true, reason: 'Cheating (aimbot)' })`);
  await wait(500);
  await snap('ban-reason');
}

/**
 * REAL Part I import for a recording (F2_SHOT_ONLY=p1real, F2_SHOT_NOFIX=1, F2_P1CONV + F2_P1RECIPE, game_dir a real client under the temp
 * dir): MAPS tab, INSTALL FROM MY PART I pressed, one frame every F2_SHOT_EVERY ms until the job ends (frames f00001.png ...).
 * @param {object} ctx
 * @returns {Promise<void>}
 */
async function scenarioP1Real({ wait, snap, shot, js, log }) {
  const every = parseInt(process.env.F2_SHOT_EVERY || '1500', 10);
  let n = 0;
  const frame = () => snap('f' + String(++n).padStart(5, '0'));
  await wait(6000);
  await shot(`view('settings')`);
  await wait(1500);
  await shot(`sub('maps')`);
  await wait(2500);
  await frame();
  await js(`document.querySelector('.mp[data-id=p1-bookstore]').click()`);
  await wait(900);
  for (let i = 0; i < 3; i++) await frame();
  await js(`$('mp-conv').click()`);
  const t0 = Date.now();
  await wait(800);
  for (;;) {
    await frame();
    const busyNow = await js(`typeof mapsDl === 'undefined' ? null : mapsDl`);
    if (busyNow === false) break;
    if (Date.now() - t0 > 90 * 60000) {
      log('p1real: 90 min timeout');
      break;
    }
    if (process.env.F2_SHOT_MAXFRAMES && n >= +process.env.F2_SHOT_MAXFRAMES) {
      log('p1real: frame limit, cancelling the job');
      await js(`$('mp-cancel').click()`);
      for (let k = 0; k < 40 && (await js(`mapsDl`)); k++) await wait(500);
      break;
    }
    await wait(every);
  }
  log(
    `p1real: job ended after ${Math.round((Date.now() - t0) / 1000)} s; msg=${await js(`$('mp-msg').textContent`)}`,
  );
  for (let i = 0; i < 6; i++) {
    await wait(700);
    await frame();
  }
}

const SCENARIOS = {
  ban: scenarioBan,
  friends: scenarioFriends,
  motion: scenarioMotion,
  notices: scenarioNotices,
  alert: scenarioAlert,
  display: scenarioDisplay,
  audit: scenarioAudit,
  sizes: scenarioSizes,
  load: scenarioLoad,
  gear: scenarioGear,
  clan: scenarioClan,
  maps: scenarioMaps,
  p1maps: scenarioP1Maps,
  p1real: scenarioP1Real,
  status: scenarioStatus,
  kofi: scenarioKofi,
  steam: scenarioSteam,
  steamadded: scenarioSteamAdded,
  steamlate: scenarioSteamLate,
};

/**
 * Launch the app and capture the configured screenshot scenarios.
 * @param {object} [options]
 * @returns {Promise<void>}
 */
async function runScreenshots(options) {
  const ctx = makeDriver(options);
  const { app, cfg, dir, wait, js } = ctx;
  fs.mkdirSync(dir, { recursive: true });

  try {
    if (
      !process.env.F2_SHOT_NOFIX &&
      cfg.game_dir &&
      cfg.game_dir.toLowerCase().startsWith(os.tmpdir().toLowerCase())
    ) {
      fs.writeFileSync(path.join(cfg.game_dir, 't2r-ext.log'), 'boot ok\n'.repeat(2000));
      fs.writeFileSync(path.join(cfg.game_dir, 'crash-test.mdmp'), Buffer.alloc(1200000, 3));
    }
  } catch {
    /* test fixtures are optional */
  }

  await wait(1500);
  await js(`(${installShotApi.toString()})()`);

  const only = process.env.F2_SHOT_ONLY;
  if (only && SCENARIOS[only]) await SCENARIOS[only](ctx);
  else await scenarioDefault(ctx);
  app.quit();
}

module.exports = { runScreenshots };
