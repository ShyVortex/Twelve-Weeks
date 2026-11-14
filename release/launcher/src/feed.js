/**
 * @file Renderer clan feed ticker and notifications.
 */
'use strict';
// Clan status notices in the bottom-bar lane, constantly: one after another with a long pause between them (8-15 s), each held for 12 s + 90 ms per
// character, fading in and out over 1.2 s (Notice in app.js), endlessly, never the same line twice in a row.
// Sources, in this order: (1) the game daemon's clan feed over the client protocol (op 0xB4 -> 0xB5, main process lib/daemon.js; works without the update server),
// (2) /clanfeed.json of the update server when it answers, (3) 2013-style ticker lines made locally from the clan numbers (src/ticker.js, the pools of
// tools/clan_story_data.py), so the lane never goes quiet. Lines seen are kept in history() for the CAMP journal.
/**
 * Clan-feed ticker and notification controller.
 */
const Feed = (() => {
  const GAP_MIN = 8000,
    GAP_MAX = 15000,
    HOLD_BASE = 12000,
    HOLD_CHAR = 90,
    RECENT = 12;
  const tone = (mood) =>
    ({
      hopeful: 'good',
      cheerful: 'good',
      grieving: 'bad',
      grim: 'bad',
      despair: 'bad',
      desperate: 'bad',
      afraid: 'warn',
      worried: 'warn',
    })[mood] || '';
  let hist = [],
    unseen = [],
    recent = [],
    started = false,
    people = null,
    last = null,
    rng = Math.random,
    lang = 'en'; // launcher language code; only Polish has its own ticker pool (TICKER_PL), every other language uses the English pool (the server renders en / pl)
  const seenIds = new Set();

  function shown(m) {
    // a line the lane shows now: newest first in the CAMP journal
    const text = m.short || m.text;
    if (!text) return;
    hist = hist.filter((x) => x.text !== text);
    hist.unshift({
      id: String(m.id),
      text,
      mood: m.mood || '',
      kind: m.kind || 'feed',
      day: m.day,
      week: m.week,
      ts: Date.now(),
    });
    if (hist.length > 60) hist.length = 60;
  }
  function add(items) {
    for (const m of items || []) {
      const id = String(m.id),
        text = m.short || m.text;
      if (!text || seenIds.has(id)) continue;
      seenIds.add(id);
      const it = {
        id,
        text,
        mood: m.mood || '',
        kind: m.kind || 'feed',
        day: m.day,
        week: m.week,
        ts: Date.now(),
      };
      hist.unshift(it);
      unseen.push(it);
    }
    if (hist.length > 60) hist.length = 60;
    if (unseen.length > 12) unseen = unseen.slice(-12);
  }
  // The same wall-clock schedule as the game (t2r-ext feed_tick FEED_SLOT_S /
  // FEED_LINE_S): the daemon / server batch is a pure function of (clan, 60 s slot, language); line i shows during seconds [i * 20, i * 20 + 20) of the slot.
  const SLOT_S = 60,
    LINE_S = 20,
    FADE_MS = 1200;
  let batch = { slot: -1, lines: [] },
    fetching = false,
    lastKey = -1,
    missed = 0;
  async function poll() {
    const slot = Math.floor(Date.now() / 1000 / SLOT_S);
    if (document.body.classList.contains('sp-mode')) return; // single player: no clan feed
    if (fetching) return;
    fetching = true;
    try {
      const r = await f2.clanFeed(0, lang);
      const f = r.ok && r.feed && r.feed.ok ? r.feed : null;
      if (f && f.chron && f.chron.status && typeof ClanStatus !== 'undefined')
        ClanStatus.offer(f.chron.status, f.feed); // clan member status updates: the corner notification (once per update)
      // (the CAMP journal looked random - a whole batch went into the history when fetched, unshown lines included; now a line enters it when shown)
      if (f && f.hasClan && (f.source === 'daemon' || f.source === 'server')) {
        batch = { slot, lines: f.feed || [] };
        missed = 0;
      } else if (f && f.hasClan) {
        add((f.feed || []).slice().reverse());
        missed++;
      } else missed++;
    } catch {
      missed++; /* offline: the local ticker keeps the lane alive */
    } finally {
      fetching = false;
    }
  }

  // ---- local ticker from the clan numbers
  function seeded(s) {
    let h = 2166136261;
    for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
    return () => {
      h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
      return (h % 100000) / 100000;
    };
  }
  const pool = () =>
    lang === 'pl' && typeof TICKER_PL !== 'undefined'
      ? TICKER_PL
      : typeof TICKER !== 'undefined'
        ? TICKER
        : null; // Polish pool when the launcher is Polish (tickerFill handles gender)
  function buildPeople() {
    const P = pool();
    if (!last || !last.hasClan || last.status !== 'alive' || !P) return null;
    const sera = last.faction === 2,
      names = (sera ? P.namesS : P.namesW).slice(),
      r = seeded('t2r' + (last.factionName || '') + last.size);
    names.sort(() => r() - 0.5);
    const n = Math.min(last.size, names.length),
      out = [];
    for (let i = 0; i < n; i++)
      out.push({
        n: names[i],
        s: i < last.sick ? 's' : i < last.sick + last.hungry ? 'u' : 'h',
      });
    return out;
  }
  function tickerLine() {
    if (!people) people = buildPeople();
    if (!people || !people.length) return null;
    const P = pool(),
      isPl = P === (typeof TICKER_PL !== 'undefined' ? TICKER_PL : null);
    const p = people[Math.floor(rng() * people.length)],
      sera = last.faction === 2,
      gender = isPl ? P.gender[p.n] || 'n' : 'n';
    const fill = (t) => tickerFill(t, p.n, gender);
    let tpl = p.s === 's' ? P.sick : p.s === 'u' ? P.hungry : P.healthy;
    if (p.s === 'h')
      tpl = tpl.filter((t) => !/^\{A\} (is healthy|jest zdrow\{A\?y\|a\})\.$/.test(t)); // never a bare "X is healthy." (offline fallback only; the real lines come from the daemon / server menu)
    if (sera) tpl = tpl.filter((t) => !P.notSera.some((k) => t.includes(k)));
    const fresh = tpl.filter((t) => !recent.includes(fill(t))),
      pick = (fresh.length ? fresh : tpl)[
        Math.floor(rng() * (fresh.length ? fresh.length : tpl.length))
      ];
    // rare inside joke: ~1 in 70 sick lines, same rate as the server feed (clan_story_data.TICKER_RARE_CHANCE); the line itself is P.rare
    const text = fill(p.s === 's' && rng() < 0.015 ? P.rare : pick);
    return {
      id: 'tk:' + text,
      text,
      mood: p.s === 's' ? 'worried' : p.s === 'u' ? 'worried' : '',
      kind: 'ticker',
    };
  }
  function nextItem() {
    let it = unseen.shift();
    if (!it) {
      // nothing new from the server: replay an old line or draw a ticker line, never one shown in the last RECENT
      const old = hist.filter((m) => !recent.includes(m.text));
      it =
        rng() < 0.4 && old.length
          ? old[Math.floor(rng() * old.length)]
          : tickerLine() || (old.length ? old[0] : null);
    }
    return it;
  }
  function schedTick() {
    // every 250 ms: the clock's line of this slot, once (same moment as in the game)
    if (document.hidden || document.body.classList.contains('sp-mode')) return;
    const t = Date.now() / 1000,
      slot = Math.floor(t / SLOT_S),
      sec = t - slot * SLOT_S,
      i = Math.floor(sec / LINE_S),
      key = slot * 8 + i;
    if (batch.slot !== slot) {
      if (sec >= 2 && !fetching && (!schedTick.at || Date.now() - schedTick.at > 5000)) {
        schedTick.at = Date.now();
        poll();
      }
      return;
    }
    if (key === lastKey || !batch.lines.length) return;
    lastKey = key;
    const rem = ((i + 1) * LINE_S - sec) * 1000 - 2 * FADE_MS - 700;
    if (rem < 4000) return;
    const it = batch.lines[i % batch.lines.length];
    shown(it);
    recent.push(it.text);
    if (recent.length > RECENT) recent.shift();
    if (typeof Snd !== 'undefined') Snd.play('feed');
    Notice.push(it.text, tone(it.mood), rem);
  }
  async function loop() {
    // offline fallback only (no daemon / server batch for 2 slots): the old free-running lane with local ticker lines
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    await sleep(5000);
    for (;;) {
      if (missed < 2) {
        await sleep(2000);
        continue;
      }
      if (
        document.hidden ||
        document.body.classList.contains('game-on') ||
        document.body.classList.contains('sp-mode')
      ) {
        await sleep(3000);
        continue;
      }
      const it = nextItem();
      if (!it) {
        await sleep(5000);
        continue;
      }
      recent.push(it.text);
      if (recent.length > RECENT) recent.shift();
      shown(it);
      if (typeof Snd !== 'undefined') Snd.play('feed');
      await Notice.push(it.text, tone(it.mood), HOLD_BASE + HOLD_CHAR * it.text.length);
      await sleep(GAP_MIN + rng() * (GAP_MAX - GAP_MIN));
    }
  }
  return {
    start() {
      if (started) return;
      started = true;
      poll();
      setInterval(schedTick, 250);
      loop();
    },
    refresh: poll,
    // language switch: drop the lines of the old language (the ids are the same in both languages, so the seen set goes too), refetch in the new one
    setLang(l) {
      const n =
        String(l || 'en')
          .toLowerCase()
          .split(/[-_]/)[0] || 'en';
      if (n === lang) return;
      lang = n;
      hist = [];
      unseen = [];
      recent = [];
      people = null;
      seenIds.clear();
      batch = { slot: -1, lines: [] };
      lastKey = -1;
      if (started) poll();
    },
    setClan(r) {
      const was = last && last.size;
      last = r;
      if (!was || was !== r.size) people = null;
    },
    history: () => hist,
    sample(n) {
      const out = [];
      for (let i = 0; i < n; i++) {
        const t = tickerLine();
        if (t && !out.some((x) => x.text === t.text)) out.push(t);
      }
      return out;
    },
  };
})();
