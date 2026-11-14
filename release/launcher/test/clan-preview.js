'use strict';
// node test/clan-preview.js <fixture.js> <out dir> [seconds] [--shot]
// Headless render of the REAL launcher page (src/index.html, no Electron, no game, CPU only: msedge --headless --disable-gpu) with a stubbed preload API that
// serves a fixture (test/clan-fixture.py): opens the CLAN tab and records the screen with the DevTools screencast, plus the sound cues Snd.fx logged
// (?fxlog=1), so a clip of the open animation with its audio can be put together (test/clan-preview-mux.py).  Writes <out>/frames/NNNNN.jpg, frames.json
// (wall-clock time of each frame), cues.json (sound cues relative to the click).  --shot: one still PNG per scroll position instead (clan-<n>.png).
const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
const [fixture, out, secArg] = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const SHOT = process.argv.includes('--shot'), SECS = Number(secArg) || 7, PORT = 9300 + Math.floor(Math.random() * 400);
const EDGE = process.env.T2R_EDGE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const src = path.join(__dirname, '..', 'src', 'index.html').replace(/\\/g, '/');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// HS=1: mockup-only heads (portraits are not approved, nothing is copied into the launcher): the page's portrait <img> are pointed at the tmp renders as data: URLs
const HS_DIR = 'work/portraits4/out/photo';
const hsMap = {};
if (process.env.HS) for (const w of ['wlf', 'ser']) for (const e of ['neutral', 'happy', 'sad', 'dead']) hsMap[w + '_' + e] = 'data:image/png;base64,' + fs.readFileSync(`${HS_DIR}/${w}_${e}_256.png`).toString('base64');
const hsStub = process.env.HS ? `(() => { const C = {}, M = ${JSON.stringify(hsMap)}, X = { happy: 'happy', neutral: 'neutral', sad: 'sad', scared: 'sad', hurt: 'sad', dead: 'dead', sick: 'neutral', hungry: 'neutral' };
  const fix = (img) => { const m = /portraits\\/(\\w)\\/(\\w)\\/(\\d+)_(\\w+)\\.png/.exec(img.getAttribute('src') || ''); if (!m) return; const key = (m[2] === 'm' ? 'wlf' : 'ser') + '_' + (X[m[4]] || 'neutral'); img.src = C[key] || M[key]; if (!C[key]) { const o = new Image(); o.onload = () => { const c = document.createElement('canvas'); c.width = c.height = 160; const g = c.getContext('2d'); g.drawImage(o, 0, 0, 1, 1, 0, 0, 1, 1); const px = g.getImageData(0, 0, 1, 1).data; g.fillStyle = 'rgb(' + px[0] + ',' + px[1] + ',' + px[2] + ')'; g.fillRect(0, 0, 160, 160); g.drawImage(o, -22.4, 14.4, 204.8, 204.8); const gr = g.createLinearGradient(0, 160 * 0.91, 0, 160); gr.addColorStop(0, 'rgba(14,14,14,0)'); gr.addColorStop(1, 'rgb(14,14,14)'); g.fillStyle = gr; g.fillRect(0, 0, 160, 160); C[key] = c.toDataURL(); img.src = C[key]; }; o.src = M[key]; } img.style.filter = e ? '' : m[4] === 'hungry' ? 'grayscale(1)' : m[4] === 'sick' ? 'sepia(.6) saturate(2) hue-rotate(-30deg)' : ''; img.style.transition = 'filter .8s'; };
  new MutationObserver((ms) => ms.forEach((r) => r.addedNodes.forEach((n) => { if (n.nodeType === 1) (n.tagName === 'IMG' ? [n] : [...n.querySelectorAll('img')]).forEach(fix); }))).observe(document, { childList: true, subtree: true });
})();` : '';
// CAST=<map.json>: mockup-only cast heads (tools/models/portrait_cast renders, not approved, nothing copied into the launcher): the map gives a picture per
// "faction/sex/model" portrait id, or one per expression as "faction/sex/model/expression"; an expression without its own picture shows the neutral one, hungry / sick / dead tinted by a filter like the HS mode
const castMap = {};
if (process.env.CAST) for (const [k, f] of Object.entries(JSON.parse(fs.readFileSync(process.env.CAST, 'utf8')))) castMap[k] = 'data:image/png;base64,' + fs.readFileSync(f).toString('base64');
const castStub = process.env.CAST ? `(() => { const M = ${JSON.stringify(castMap)};
  const fix = (img) => { const m = /portraits\\/(\\w)\\/(\\w)\\/(\\d+)_(\\w+)\\.png/.exec(img.getAttribute('src') || ''); if (!m) return; const k = m[1] + '/' + m[2] + '/' + m[3], e = M[k + '/' + m[4]], u = e || M[k]; if (!u) return; img.src = u;
    img.style.filter = e ? '' : m[4] === 'hungry' ? 'grayscale(.7) brightness(.95)' : m[4] === 'sick' ? 'sepia(.5) saturate(1.6) hue-rotate(-25deg)' : m[4] === 'dead' ? 'grayscale(1) brightness(.6)' : ''; img.style.transition = 'filter .8s'; };
  new MutationObserver((ms) => ms.forEach((r) => r.addedNodes.forEach((n) => { if (n.nodeType === 1) (n.tagName === 'IMG' ? [n] : [...n.querySelectorAll('img')]).forEach(fix); if (n.nodeType === 1) [n, ...n.querySelectorAll('.sc-img')].forEach(bg); }))).observe(document, { childList: true, subtree: true });
  // status cards draw the portrait as a CSS background (.sc-img), not an <img>
  function bg(el) { if (!el.classList || !el.classList.contains('sc-img')) return; const m = /portraits\\/(\\w)\\/(\\w)\\/(\\d+)_(\\w+)\\.png/.exec(el.style.backgroundImage || ''); if (!m) return; const k = m[1] + '/' + m[2] + '/' + m[3], e = M[k + '/' + m[4]], u = e || M[k]; if (!u) return;
    el.style.backgroundImage = 'url(' + u + ')'; el.style.filter = e ? '' : m[4] === 'hungry' ? 'grayscale(.7) brightness(.95)' : m[4] === 'sick' ? 'sepia(.5) saturate(1.6) hue-rotate(-25deg)' : m[4] === 'dead' ? 'grayscale(1) brightness(.6)' : ''; }
})();` : '';
const stub = castStub + hsStub + `(() => { ${fs.readFileSync(fixture, 'utf8')}
  const F = window.FIXTURE, ok = (x) => Promise.resolve(Object.assign({ ok: true }, x));
  const api = { clan: () => ok({ clan: F.clan }), clanFeed: () => ok({ feed: F.feed }), getConfig: () => ok({ cfg: {} }), log: () => {}, i18n: () => ok({}), info: () => ok({ version: 'preview' }),
    serverStatus: () => Promise.resolve({ ok: false }), news: () => Promise.resolve({ ok: false, items: [] }), playerName: () => Promise.resolve('Preview') };
  window.f2 = new Proxy(api, { get: (t, k) => (k in t ? t[k] : (k.startsWith('on') ? () => {} : () => Promise.resolve({ ok: false }))) });
  window.addEventListener('error', (e) => console.log('PAGEERR ' + e.message + ' @' + e.filename + ':' + e.lineno));
})();`;

async function main() {
  fs.mkdirSync(path.join(out, 'frames'), { recursive: true });
  const prof = path.join(out, 'edge-profile');
  const ps = spawn(EDGE, ['--headless=new', '--disable-gpu', '--remote-debugging-port=' + PORT, '--user-data-dir=' + prof, '--window-size=' + (process.env.PW || 1440) + ',860', '--hide-scrollbars', '--mute-audio', 'about:blank'], { stdio: 'ignore' });
  try {
    let tgt = null;
    for (let i = 0; i < 60 && !tgt; i++) { await sleep(300); try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); tgt = l.find((x) => x.type === 'page'); } catch (e) { /* not up yet */ } }
    if (!tgt) throw new Error('edge did not start');
    const ws = new WebSocket(tgt.webSocketDebuggerUrl);
    await new Promise((r) => { ws.onopen = r; });
    let id = 0; const pend = {}, frames = [], logs = [];
    ws.onmessage = (m) => {
      const d = JSON.parse(m.data);
      if (d.id && pend[d.id]) { pend[d.id](d); delete pend[d.id]; }
      else if (d.method === 'Page.screencastFrame') {
        const n = frames.length; frames.push({ n, t: d.params.metadata.timestamp });
        fs.writeFileSync(path.join(out, 'frames', String(n).padStart(5, '0') + '.jpg'), Buffer.from(d.params.data, 'base64'));
        send('Page.screencastFrameAck', { sessionId: d.params.sessionId });
      } else if (d.method === 'Runtime.consoleAPICalled') logs.push(d.params.args.map((a) => a.value).join(' '));
    };
    const send = (method, params) => new Promise((res) => { const i = ++id; pend[i] = res; ws.send(JSON.stringify({ id: i, method, params: params || {} })); });
    const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result.result.value;
    await send('Page.enable'); await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride', { width: Number(process.env.PW) || 1440, height: 860, deviceScaleFactor: Number(process.env.DSF) || 1, mobile: false });
    await send('Page.addScriptToEvaluateOnNewDocument', { source: stub });
    await send('Page.navigate', { url: 'file:///' + src + '?fxlog=1' });
    for (let i = 0; i < 40; i++) { await sleep(500); if (await ev('window.__loadDone === true')) break; }
    await sleep(800);
    if (SHOT) {
      await ev(`document.querySelector('.mi[data-view=clan]').click()`);
      await sleep(6000);
      const h = await ev(`(() => { const c = document.getElementById('clan-body'); return c.scrollHeight - c.clientHeight; })()`);
      let offs = process.env.OFFS ? process.env.OFFS.split(',').map(Number) : null;
      if (process.env.SEL) offs = await ev(`${JSON.stringify(process.env.SEL.split(','))}.map((s) => { const c = document.getElementById('clan-body'), el = document.querySelector(s); return el ? Math.max(0, el.offsetTop - c.offsetTop - 24) : 0; })`);   // SEL=.mor,.jsec: scroll each selector to the top   // OFFS=1300,2400: shoot exactly these scroll positions
      const stops = offs ? offs.length : Math.max(1, Math.ceil(h / 560) + 1);
      for (let k = 0; k < stops; k++) {
        await ev(`document.getElementById('clan-body').scrollTop = ${Math.min(h, offs ? offs[k] : k * 560)}`); await sleep(Number(process.env.SETTLE) || 500);
        const r = await send('Page.captureScreenshot', { format: 'png' });
        fs.writeFileSync(path.join(out, `clan-${k}.png`), Buffer.from(r.result.data, 'base64'));
      }
      const dbg = process.argv.find((a) => a.startsWith('--eval=')); if (dbg) console.log('eval:', JSON.stringify(await ev(dbg.slice(7))));
      console.log('shots:', stops, 'scrollable', h); console.log(logs.filter((l) => /PAGEERR/.test(l)).join('\n'));
    } else {
      await send('Page.startScreencast', { format: 'jpeg', quality: 88, everyNthFrame: 1 });
      await sleep(400);
      const t0 = await ev(`(() => { const t = Date.now(); document.querySelector('.mi[data-view=clan]').click(); return t; })()`);
      if (process.argv.includes('--cards')) {
        // all the cards' animations are paused as the first card starts and seeked in 150 ms steps (the screencast is too slow to catch a CPU-rendered transition): cards-<ms>.png
        await ev(`new Promise((res) => { const iv = setInterval(() => { const a = document.getAnimations().filter((x) => x.effect && x.effect.target && x.effect.target.closest && x.effect.target.closest('.scard')); if (document.querySelector('.scard.go') && a.length) { clearInterval(iv); a.forEach((x) => x.pause()); window.__sa = a; res(); } }, 5); })`);
        const SEEK = Number(process.env.SEEKMAX) || 4200;
        for (let ms = 0; ms <= SEEK; ms += 150) {
          await ev(`window.__sa.forEach((x) => { x.currentTime = ${ms}; })`); await sleep(120);
          fs.writeFileSync(path.join(out, 'cards-' + String(ms).padStart(5, '0') + '.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64'));
        }
      } else if (process.argv.includes('--status')) {
        // scenario (clan status updates): the clan screen opens with its status cards, the first card's journal link is followed, the screen is closed and the corner
        // notifications of the four updates come one after another (hold 3.4 s each)
        await sleep(6500);
        await ev(`(() => { const b = document.querySelector('.sc-more'); if (b) b.click(); })()`);
        await sleep(3200);
        await ev(`(() => { document.getElementById('clan-body').scrollTop = 0; window.f2show(null); ClanStatus.reset(); ClanStatus.offer(window.FIXTURE.feed.chron.status, window.FIXTURE.feed.feed, { hold: 7000 }); })()`);
        await sleep(2600);
        fs.writeFileSync(path.join(out, 'status-list.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64'));
        await sleep(7600);
      } else {
      // scenario: the header sequence plays, then scroll down to the raids (their entrance waits below the fold), open the second raid, scroll to the journal
      const scrollTo = (sel, ms) => ev(`new Promise((res) => { const c = document.getElementById('clan-body'), el = document.querySelector('${sel}'), from = c.scrollTop, to = Math.max(0, el.offsetTop - c.offsetTop - 16), t0 = performance.now();
        const iv = setInterval(() => { const k = Math.min(1, (performance.now() - t0) / ${ms}), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; c.scrollTop = from + (to - from) * e; if (k >= 1) { clearInterval(iv); res(); } }, 16); })`);
      // calm tour: hold on the STATUS UPDATES until all four cards finished (stagger + ~1 s to read), then the survivors, the journal (second entry opened) with holds
      await sleep(7600); await scrollTo('.roster', 1800);
      await sleep(3800); await scrollTo('.jsec', 1800);
      await sleep(3200); await ev(`(() => { const j = document.querySelectorAll('.jlay .jrn'); if (j[1]) j[1].click(); })()`);
      await sleep(3600); await ev(`(() => { const j = document.querySelectorAll('.jlay .jrn'); if (j[2]) j[2].click(); })()`);
      await sleep(3000);
      }
      const cues = await ev(`Snd.log.map((c) => ({ t: c.t, n: c.n, g: c.g }))`);
      await send('Page.stopScreencast');
      fs.writeFileSync(path.join(out, 'frames.json'), JSON.stringify({ t0: t0 / 1000, frames }));
      fs.writeFileSync(path.join(out, 'cues.json'), JSON.stringify(cues.map((c) => ({ at: c.t / 1000 - t0 / 1000, n: c.n, g: c.g }))));
      console.log('frames:', frames.length, 'cues:', cues.length); console.log(logs.filter((l) => /PAGEERR/.test(l)).join('\n'));
    }
    ws.close();
  } finally { ps.kill(); await sleep(300); try { fs.rmSync(prof, { recursive: true, force: true }); } catch (e) { /* edge still holds a file; the profile is scratch */ } }
}
main().then(() => process.exit(0), (e) => { console.error(e); process.exit(1); });
