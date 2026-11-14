'use strict';
// Minimal implementation of API.md for testing the launcher without the real update server.
//   node test/mock-server.js [port] [dir-with-client-files]
// With no dir it invents a few files. Honours Range, serves /files/<sha256>.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const zlib = require('zlib');

function build(dir) {
  const files = [];
  const add = (rel, buf) => files.push({ path: rel, buf, size: buf.length, sha256: crypto.createHash('sha256').update(buf).digest('hex') });
  if (dir) {
    (function walk(d, pre) { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.isDirectory()) walk(path.join(d, e.name), pre + e.name + '/'); else add(pre + e.name, fs.readFileSync(path.join(d, e.name))); } })(dir, '');
  } else {
    add('version.txt', Buffer.from('mock-1\n')); add('server.txt', Buffer.from('127.0.0.1:7001\n'));
    add('t2r-ext.dll', crypto.randomBytes(3_000_000)); add('tlou-ii-mp/sidbase.bin', crypto.randomBytes(900_000));
    const dll = Buffer.alloc(0x60000, 7); add('winmm.dll', dll);
  }
  return files;
}

function start(port = 15390, dir = null, opts = {}) {
  const files = build(dir);
  if (opts.compress && !dir) {   // extra compressible payloads: a brotli one (.txt), a gzip one, and a gzip one that tests may corrupt
    const add = (rel, buf) => files.push({ path: rel, buf, size: buf.length, sha256: crypto.createHash('sha256').update(buf).digest('hex') });
    add('notes.txt', Buffer.from('the quick brown fox jumps over the lazy dog\n'.repeat(60000)));
    add('pad.bin', Buffer.concat([Buffer.alloc(800_000, 3), crypto.randomBytes(50_000), Buffer.alloc(800_000, 9)]));
    add('damaged.bin', Buffer.alloc(1_200_000, 5));
  }
  const reqLog = [];                       // {url, range} of every /files request
  // opts.compress: compressible files get a gzip / brotli twin served at /files/<sha>.gz|.br (manifest zsize/zurl/enc, like tools/update_server).
  // opts.corrupt: array of paths whose compressed twin is damaged (the manifest still claims it is fine) -> the launcher must fall back to raw.
  const zby = new Map();
  if (opts.compress) {
    for (const f of files) {
      const enc = f.path.endsWith('.txt') && f.path !== 'version.txt' && f.path !== 'server.txt' ? 'br' : 'gzip';
      let z = enc === 'br' ? zlib.brotliCompressSync(f.buf) : zlib.gzipSync(f.buf, { level: 9 });
      if (z.length > f.size * 0.95) continue;
      if ((opts.corrupt || []).includes(f.path)) { z = Buffer.from(z); z[Math.floor(z.length / 2)] ^= 0xff; z[Math.floor(z.length / 2) + 1] ^= 0x55; }
      f.enc = enc; f.zbuf = z; f.zsize = z.length; f.zname = f.sha256 + (enc === 'br' ? '.br' : '.gz');
      zby.set(f.zname, f);
    }
  }
  const bySha = new Map(files.map((f) => [f.sha256, f]));
  const speed = opts.bytesPerChunk || 0;
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const json = (o) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(o)); };
    if (u.pathname === '/manifest.json') {
      return json({ version: (files.find((f) => f.path === 'version.txt') || { buf: Buffer.from('mock') }).buf.toString().trim(), channel: u.searchParams.get('channel') || 'stable',
        notes: 'Mock build for launcher tests', files: files.map(({ path: p, size, sha256, zsize, enc, zname }) => ({ path: p, size, sha256, url: `/files/${sha256}`, ...(zname ? { zsize, enc, zurl: `/files/${zname}` } : {}) })),
        launcher: { version: opts.launcherVersion || '0.1.0', url: '/files/launcher', sha256: '0'.repeat(64) } });
    }
    if (u.pathname === '/news.json') return json([
      { id: 3, date: '2026-10-18', version: 'build 74', title: 'Launcher preview', body: 'The desktop launcher is here. It updates the client, shows server status and lets you sketch loadouts.' },
      { id: 2, date: '2026-10-17', title: 'Placed bombs fixed', body: 'Shooting a placed bomb detonates it for everyone.\nNo more free bombs from mines against a wall.' },
      { id: 1, date: '2026-10-15', title: 'Capitol Hill market', body: 'The north storefront window is open again.' }]);
    if (u.pathname === '/clan.json') return json({ ok: true, hasClan: true, faction: 1, factionName: 'WLF', status: 'alive', daysDone: 17, daysTotal: 83, weeksTotal: 0, size: 15, healthy: 12, hungry: 2, sick: 1,
      needed: 15, maxSize: 18, runsWon: 4, runsLost: 2, week: 3, dayOfWeek: 4, weeks: 12, event: { kind: 'attack', name: 'ATTACK', startDay: 15, dayOfEvent: 3, length: 3 }, eventToday: null,
      mission: { id: 1, name: 'Down Enemies', progress: 7, daysLeft: 1, goals: [3, 6, 9], inEvent: true }, boosterNext: 3,
      boosters: [[1, 'Starting Ammo Multiplier', 2], [2, 'Cheaper Ammo', 0], [3, 'Cheaper Armor', 1], [4, 'Cheaper Purchased Weapons', 0], [7, 'Increased Part Earnings', 1]].map(([id, name, count]) => ({ id, name, count })),
      lastMatch: { day: 16, parts: 1310, supplies: 26, needed: 14, gained: 1, died: 0, newHungry: 0, newSick: 0, healed: 1, leftEarly: false }, lastMission: { id: 1, name: 'Down Enemies', progress: 9, tier: 3, boostersEarned: 1 } });
    if (u.pathname === '/clanfeed.json') {
      const feed = [
        [9, 17, 3, 'worried', 'worse', "Priya has bronchitis is getting worse. Marcus says we need antibiotics, and soon.", ["Priya", "Marcus"]],
        [8, 17, 3, 'neutral', 'ticker', 'Hector is gnawing on rat bones.', ['Hector']],
        [7, 16, 3, 'grieving', 'grief_mercy', 'Dina is taking it really heavily after we had to put Sam out of his misery.. Jesus, when will this end?', ['Dina', 'Sam']],
        [6, 16, 3, 'grieving', 'death_mercy', 'Isaac says that is what soldiers do for each other. Does not make it easier.', ['Sam']],
        [5, 15, 3, 'grieving', 'death_bite', 'Walt got bit by a runner yesterday during those Scars attacking. Hid it under his sleeve. Fuck... how did we not notice?', ['Walt']],
        [4, 14, 2, 'hopeful', 'hope', 'Somebody found a guitar in the stadium and Rosa actually knows three chords. It is terrible. Nobody wants her to stop.', ['Rosa']]]
        .map(([id, day, week, mood, kind, text, names]) => ({ id, day, week, kind, mood, faction: 1, text, short: text.length > 118 ? text.slice(0, 115) + '...' : text, names, ts: 0 }));
      return json({ ok: true, hasClan: true, faction: 1, factionName: 'WLF', status: 'alive', daysDone: 17, feed: feed.filter((m) => m.id > +(u.searchParams.get('since') || 0)),
        morale: { value: 41, label: 'strained' }, alive: 15, people: [{ name: 'Priya', gender: 'f', role: 'medic', state: 'sick', mood: 'ill', illness: 'bronchitis' }, { name: 'Hector', gender: 'm', role: 'guard', state: 'hungry', mood: 'hungry', illness: '' }], dead: [] });
    }
    if (u.pathname === '/status.json') return json({ online: true, players_online: 7, matches: 1, server_version: 'mock-1' });
    const m = /^\/files\/([0-9a-f]{64}(?:\.gz|\.br)?)$/.exec(u.pathname);
    const zf = m && zby.get(m[1]);
    const f = zf ? { size: zf.zsize, buf: zf.zbuf } : (m && bySha.get(m[1]));
    reqLog.push({ url: u.pathname, range: req.headers.range || '' });
    if (!f) { res.statusCode = 404; return res.end('nope'); }
    let start = 0, end = f.size - 1;
    const r = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || '');
    if (r) { start = +r[1]; if (r[2]) end = +r[2]; res.statusCode = 206; res.setHeader('Content-Range', `bytes ${start}-${end}/${f.size}`); }
    res.setHeader('Accept-Ranges', 'bytes'); res.setHeader('Content-Length', end - start + 1);
    const body = f.buf.subarray(start, end + 1);
    if (!speed) return res.end(body);
    let o = 0; const t = setInterval(() => { if (o >= body.length) { clearInterval(t); return res.end(); } res.write(body.subarray(o, o + speed)); o += speed; }, 20);
    req.on('close', () => clearInterval(t));
  });
  return new Promise((resolve) => srv.listen(port, '127.0.0.1', () => resolve({ srv, files, port: srv.address().port, reqLog })));
}
module.exports = { start };
if (require.main === module) start(+process.argv[2] || 15390, (process.argv[3] && process.argv[3] !== '-') ? process.argv[3] : null, { bytesPerChunk: +process.argv[4] || 0 }).then((s) => console.log('mock update server on', s.port, 'files:', s.files.length));
