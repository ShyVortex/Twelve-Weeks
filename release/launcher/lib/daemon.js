/**
 * @file Small TCP client for the game daemon read-only operations.
 */
'use strict';
// Short client connections to the game daemon (tools/daemon.py), the same ops the game's own menu uses: frames are [u16 len][op][payload], len = 1 + payload.
//   0x15 (empty)        -> 0x16 [u32 online count]      (Presence.count(): players with a keepalive inside KEEPALIVE_TTL; the in-game ONLINE number)
//   0xB4 [64B token][u8 language, optional: 0 = English, 1 = Polish]  -> 0xB5 "n=<k>\n<id>|<text>\n.." (clan feed lines for the menu notification, feed_op; <= 3 lines per call)
const net = require('net');
const { DAEMON_LANG_BYTES } = require('../src/i18n/languages');

/**
 * Build a daemon protocol frame.
 * @param {number} op
 * @param {Buffer} [payload]
 * @returns {Buffer}
 */
const frame = (op, payload = Buffer.alloc(0)) => {
  const b = Buffer.alloc(3 + payload.length);
  b.writeUInt16LE(1 + payload.length, 0);
  b[2] = op;
  payload.copy(b, 3);
  return b;
};

// sends one frame, resolves with the payload of the first reply frame whose op is `want` (null on timeout / error)
/**
 * Send one daemon request and return the matching reply payload.
 * @param {string} host
 * @param {number} port
 * @param {number} op
 * @param {Buffer} payload
 * @param {number} want
 * @param {number} [timeoutMs]
 * @returns {Promise<Buffer|null>}
 */
function ask(host, port, op, payload, want, timeoutMs = 2500) {
  return new Promise((resolve) => {
    let buf = Buffer.alloc(0),
      done = false;
    const s = net.connect({ host, port });
    const end = (v) => {
      if (!done) {
        done = true;
        s.destroy();
        resolve(v);
      }
    };
    s.setTimeout(timeoutMs, () => end(null));
    s.on('error', () => end(null));
    s.on('connect', () => s.write(frame(op, payload)));
    s.on('data', (d) => {
      buf = Buffer.concat([buf, d]);
      while (buf.length >= 3) {
        const len = buf.readUInt16LE(0);
        if (len < 1 || buf.length < 2 + len) break;
        if (buf[2] === want) return end(buf.subarray(3, 2 + len));
        buf = buf.subarray(2 + len);
      }
    });
    s.on('close', () => end(null));
  });
}

/**
 * Read the online player count from the daemon.
 * @param {string} host
 * @param {number} port
 * @returns {Promise<number|null>}
 */
async function onlineCount(host, port) {
  const p = await ask(host, port, 0x15, Buffer.alloc(0), 0x16);
  return p && p.length >= 4 ? p.readUInt32LE(0) : null;
}

// Language byte on the wire: the registry's daemonByte (src/i18n/languages.js: en 0, pl 1, es 2); a number is sent as it is, anything unknown is English (0).
// The daemon renders Polish (1) and treats every other value as English until it learns a language.
/**
 * Map a launcher language to the daemon's language byte.
 * @param {string|number} lang 'en' | 'pl' | 'es' | ... or a byte
 * @returns {number}
 */
function langByte(lang) {
  if (typeof lang === 'number') return lang & 0xff;
  const code = String(lang || '')
    .toLowerCase()
    .split(/[-_]/)[0];
  return DAEMON_LANG_BYTES[code] != null ? DAEMON_LANG_BYTES[code] : 0;
}

// lang: undefined = no language byte (what older launchers sent: English), otherwise langByte(lang)
/**
 * Read clan feed lines from the daemon.
 * @param {string} host
 * @param {number} port
 * @param {string} token
 * @param {string} lang
 * @returns {Promise<string[]|null>}
 */
async function feedLines(host, port, token, lang) {
  const pl = lang === undefined || lang === null ? Buffer.alloc(0) : Buffer.from([langByte(lang)]);
  const p = await ask(host, port, 0xb4, Buffer.concat([Buffer.from(token, 'latin1'), pl]), 0xb5);
  if (!p) return null;
  const lines = p.toString('utf8').split('\n');
  const m = /^n=(\d+)$/.exec(lines[0] || '');
  if (!m) return null;
  return lines
    .slice(1, 1 + +m[1])
    .map((l) => {
      const i = l.indexOf('|');
      return i > 0 ? { id: l.slice(0, i), text: l.slice(i + 1) } : null;
    })
    .filter(Boolean);
}

// server notices: 0xBA [64B token][u8 ver=1][u8 lang: langByte] -> 0xBB "n=<k>, then lines id|kind|param|text" (tools/notices.py); kinds u update, r restart (param = s left), s shutting down, t free text
/**
 * Read server notices from the daemon.
 * @param {string} host
 * @param {number} port
 * @param {string} token
 * @param {string} lang
 * @returns {Promise<object|null>}
 */
async function notices(host, port, token, lang) {
  const p = await ask(
    host,
    port,
    0xba,
    Buffer.concat([Buffer.from(token, 'latin1'), Buffer.from([1, langByte(lang)])]),
    0xbb,
  );
  if (!p) return null;
  const lines = p.toString('utf8').split('\n');
  const m = /^n=(\d+)$/.exec(lines[0] || '');
  if (!m) return null;
  return lines
    .slice(1, 1 + +m[1])
    .map((l) => {
      const a = l.split('|');
      return a.length >= 3
        ? {
            id: +a[0],
            kind: a[1],
            param: +a[2] || 0,
            text: a.slice(3).join('|'),
          }
        : null;
    })
    .filter(Boolean);
}

// read-only clan ops: 0xE0 -> 0xE1 (state text), 0xE8 -> 0xE9 (booster / mission text). Never 0xE2 / 0xE4 / 0xEE / 0xEF (they change the clan).
/**
 * Read clan state and metadata text from the daemon.
 * @param {string} host
 * @param {number} port
 * @param {string} token
 * @param {string} steamId
 * @returns {Promise<object|null>}
 */
async function clanTexts(host, port, token, steamId) {
  let tok = Buffer.from(token, 'latin1');
  if (steamId && /^\d{15,20}$/.test(String(steamId))) {
    const h = Buffer.alloc(8);
    h.writeBigUInt64LE(BigInt(steamId));
    tok = Buffer.concat([tok, h]);
  } // optional hint for an install the daemon does not know yet (read only)
  const [st, mt] = await Promise.all([
    ask(host, port, 0xe0, tok, 0xe1),
    ask(host, port, 0xe8, tok, 0xe9),
  ]);
  return {
    state: st ? st.toString('latin1') : null,
    meta: mt ? mt.toString('latin1') : null,
  };
}

// ---- player reports (game server op 0xD4 / 0xD6): the players of my last 3 matches and a report about one of them.
//   0xD6 [64B token] -> 0xD7 "n=<k>, then lines m|<mid>|<age s> and p|<mid>|<slot>|<steamid>|<name>"   (never a token; the list does not contain me)
//   0xD4 [64B token][u8 ver=1][u8 reasons][u8 slot][8 ASCII hex mid][u16 tlen][text] -> 0xD5 "ok=1 code=R12" | "ok=0 err=<why>"
const REASON_BITS = { aimbot: 1, wallhack: 2, speed: 4, griefing: 8, other: 16 };
function parseRecent(text) {
  const lines = String(text || '').split('\n');
  const m = /^n=(\d+)$/.exec(lines[0] || '');
  if (!m) return null;
  const out = [],
    byMid = new Map();
  for (const l of lines.slice(1)) {
    const a = l.split('|');
    if (a[0] === 'm' && /^[0-9a-f]{8}$/.test(a[1] || '')) {
      const o = { mid: a[1], age: Math.max(0, parseInt(a[2], 10) || 0), players: [] };
      byMid.set(a[1], o);
      out.push(o);
    } else if (a[0] === 'p' && byMid.has(a[1])) {
      const slot = parseInt(a[2], 10);
      if (slot >= 0 && slot < 8)
        byMid.get(a[1]).players.push({
          slot,
          steamid: a[3] || '0',
          name: a.slice(4).join('|').slice(0, 31) || 'PLAYER',
        });
    }
  }
  return out.slice(0, 3);
}
async function recentPlayers(host, port, token) {
  const p = await ask(host, port, 0xd6, Buffer.from(token, 'latin1'), 0xd7, 4000);
  return p ? parseRecent(p.toString('utf8')) : null;
}
function reportBody(token, r) {
  const text = Buffer.from(
    String(r.text || '')
      // eslint-disable-next-line no-control-regex -- control characters are exactly what is stripped from the typed text
      .replace(/[\u0000-\u001f\u007f]+/g, ' ')
      .trim()
      .slice(0, 500),
    'utf8',
  );
  const h = Buffer.alloc(13);
  h[0] = 1;
  h[1] = (r.reasons | 0) & 31 || 16;
  h[2] = r.slot & 255;
  h.write(String(r.mid), 3, 8, 'ascii');
  h.writeUInt16LE(text.length, 11);
  return Buffer.concat([Buffer.from(token, 'latin1'), h, text]);
}
async function reportPlayer(host, port, token, r) {
  if (!/^[0-9a-f]{8}$/.test(String(r.mid)) || !(r.slot >= 0 && r.slot < 8))
    return { ok: false, code: '', err: 'bad request' };
  const p = await ask(host, port, 0xd4, reportBody(token, r), 0xd5, 6000);
  if (!p) return null;
  const t = p.toString('utf8'),
    ok = /(^| )ok=1( |$)/.test(t),
    code = /code=(\S+)/.exec(t),
    err = /err=(.*)$/.exec(t);
  return { ok, code: code ? code[1] : '', err: err ? err[1] : '' };
}

// ---- friends + parties (tools/social.py): 0xD8 [64B token][u8 ver=1][u8 lang 0 en / 1 pl][u8 sub][UTF-8 argument] -> 0xD9 JSON
//   {ok, err, me, friends[{id,name,status,seen,party}], in[{id,name,age}], out[..], party{id,leader,meLeader,max,members[..],searching}|null, pinv[{id,name,age}], found[..]}
//   status: match | search | menu | launcher | off. Every call also counts as "launcher online" for the friends (about 60 s).
const SOCIAL_SUBS = {
  state: 1,
  search: 2,
  add: 3,
  accept: 4,
  remove: 5,
  invite: 6,
  join: 7,
  decline: 8,
  leave: 9,
  kick: 10,
  promote: 11,
  ready: 12,
  msg: 13,
  chat: 14,
};
/**
 * Call the friends/party service of the daemon.
 * @param {string} host
 * @param {number} port
 * @param {string} token
 * @param {string} lang 'en' | 'pl' | 'es' (langByte)
 * @param {string} sub one of SOCIAL_SUBS
 * @param {string} [arg]
 * @returns {Promise<object|null>} the reply, or null when the daemon did not answer (older server)
 */
async function social(host, port, token, lang, sub, arg = '') {
  const code = SOCIAL_SUBS[sub];
  if (!code) return null;
  const pl = Buffer.concat([
    Buffer.from(token, 'latin1'),
    Buffer.from([1, langByte(lang), code]),
    Buffer.from(String(arg || ''), 'utf8').subarray(0, 200),
  ]);
  const p = await ask(host, port, 0xd8, pl, 0xd9, 4000);
  if (!p) return null;
  try {
    return JSON.parse(p.toString('utf8'));
  } catch {
    return null;
  }
}

module.exports = {
  frame,
  ask,
  social,
  SOCIAL_SUBS,
  onlineCount,
  feedLines,
  clanTexts,
  notices,
  recentPlayers,
  reportPlayer,
  parseRecent,
  reportBody,
  REASON_BITS,
};
