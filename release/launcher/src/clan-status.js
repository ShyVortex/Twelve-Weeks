'use strict';
// Clan member STATUS UPDATES (tools/clan_status.py): a survivor went hungry / sad / sick / died since the player last looked.
//  1. the clan screen: an animated card per update (headshot + name banner; the overlay goes from the healthy green gradient to the new state's colour while the
//     headshot morphs to the state's expression), the story line and a link to the journal entry. NEW-only: a card shows until it has been looked at (Fx data-new).
//  2. a small corner notification (lower left, the lane of the launcher's alert panel; in game the same corner, clear of the radar top left, the kill feed top right
//     and the ammo bottom right) with a TLOU2-style header, compact headshot with the same colour transition, one line and MORE IN JOURNAL in its corner. Shown once per
//     update, never over the clan screen, never while the game runs.
// Payload (update server /clanfeed.json chron.status): [{id, name, role, code, state, day, expr, img: {neutral,hungry,sad,sick,dead} image ids, line, ln}].
// Headshot hook: img ids are "<fac>/<sex>/<model>/<expression>" = the portraits' ids (clan.js portraitUrl); a missing picture shows the silhouette placeholder,
// the morph then tints / bows the silhouette. Real headshots drop in later with no code change (neutral image crossfades to the state's image).
const ClanStatus = (() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(
      /[&<>"]/g,
      (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m],
    );
  const COLOR = {
    healthy: '#4FB04A',
    hungry: '#E0A21A',
    sad: '#2F66D6',
    sick: '#C4202B',
    dead: '#353C47',
    injured: '#D9741F',
    recovered: '#4FB04A',
    new: '#2AA8D0',
    shock: '#8FA3B5',
    depressed: '#5B6B7B',
  };
  // the status word's colour (AA on the dark card: the plain state colours are too dark for text)
  const TXT = {
    healthy: '#7FD07A',
    hungry: '#F0B429',
    sad: '#7FA8F5',
    sick: '#F2625A',
    dead: '#A9AFB8',
    injured: '#F29A4A',
    recovered: '#7FD07A',
    new: '#55C6E8',
    shock: '#DCE7F0',
    depressed: '#9DB0C4',
  };
  const WORD = {
    healthy: 'HEALTHY',
    hungry: 'HUNGRY',
    sad: 'GRIEVING',
    sick: 'SICK',
    depressed: 'DEPRESSED',
    shock: 'SHOCK',
    dead: 'DEAD',
    injured: 'HURT',
    recovered: 'RECOVERED',
    new: 'NEW MEMBER',
  };
  const GLYPH = {
    healthy: 'healthbar',
    hungry: 'g-bowl',
    sad: 'g-cloud',
    depressed: 'g-cloud',
    shock: 'g-shock',
    sick: 'pills',
    dead: 'killfeed-skull',
    injured: 'bandage',
    recovered: 'medicine',
    new: 'person',
  };
  const KEY = 't2r.clan.stnote';
  const portraitUrl = (id) => {
    const a = String(id || '').split('/');
    return a.length === 4 ? `../assets/portraits/${a[2]}_${a[3]}.png` : '';
  }; // the member's head by pool model id + expression (tools/models/portrait_cast/ship_portraits.py; the daemon fitted the expression to what the head has)
  const T2 = (s, o) =>
    typeof T === 'function'
      ? T(s, o)
      : String(s).replace(/\{(\w+)\}/g, (m, k) => (o && k in o ? o[k] : m));
  // the silhouette placeholder (head and shoulders), only for a member without a portrait (it showed behind the headshots); the morph bends it per state
  const SIL =
    '<svg class="sc-sil" viewBox="0 0 100 120" aria-hidden="true"><g class="sc-bd"><path d="M6 120 C8 92 26 82 50 80 C74 82 92 92 94 120 Z"/></g><g class="sc-hd"><ellipse cx="50" cy="44" rx="21" ry="26"/></g></svg>';
  const pic = (id, cls) =>
    id ? `<i class="sc-img ${cls}" style="background-image:url('${portraitUrl(id)}')"></i>` : ''; // a background: a missing picture shows nothing (no broken-image mark, and the CSP allows no onerror)
  // the portrait starts on the member's PREVIOUS status (its expression, its colour wash) and crossfades to the new one; without .go (static / reduced motion) only the new status shows
  const prevOf = (s) => {
    const f = String(s.from || 'healthy');
    return WORD[f] ? f : 'healthy';
  };
  const photo = (s, fr) => {
    const im = s.img || {},
      st = s.state || 'hungry',
      t = im[s.expr || st] || im[st],
      f = fr === 'healthy' ? im.neutral : im[fr] || im.neutral;
    return `<div class="sc-ph">${im.neutral || t ? '' : SIL}${pic(f, 'n')}${pic(t, 't')}<i class="sc-wash g"></i><i class="sc-wash s"></i></div>`;
  };
  const word = (st, cls) =>
    `<span class="w ${cls}"><i class="ic i-${GLYPH[st] || 'keepsake'}" style="--s:18px"></i><b>${esc(T2(WORD[st] || String(st).toUpperCase()))}</b></span>`;
  function card(s, jid) {
    const st = s.state || 'hungry',
      fr = prevOf(s),
      col = COLOR[st] || '#999',
      fcol = COLOR[fr] || '#4FB04A';
    return `<article class="scard st-${esc(st)} from-${esc(fr)}" style="--sc:${col};--sf:${fcol};--scw:${TXT[st] || '#ddd'};--swf:${TXT[fr] || '#7FD07A'}" data-fx="right" data-fxs="st-${esc(st)}" data-new="s:${esc(s.id)}" data-nosnd="1" data-sid="${esc(s.id)}">
      <i class="sc-bgf"></i>${photo(s, fr)}
      <div class="sc-tx"><div class="sc-banner"><small>${esc(T2(String(s.role || 'survivor').toUpperCase()))}</small><b>${esc(s.name)}</b><em class="sc-st">${fr !== st ? word(fr, 'f') : ''}${word(st, 't')}</em></div>
        <p class="sc-line">${esc(s.line)}</p>
        ${jid != null ? `<button class="sc-more" data-jid="${esc(jid)}" data-snd="click">${T2('READ IN THE JOURNAL')} &rarr;</button>` : ''}</div>
    </article>`;
  }
  // the journal row that tells it: names the member, nearest to the update's day (feed rows: week, day; clan day = (week - 1) * 7 + day)
  function journalId(s, rows) {
    const re = new RegExp(
      '(^|[^\\p{L}])' + String(s.name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^\\p{L}])',
      'u',
    );
    let best = null,
      bd = 1e9;
    (rows || []).forEach((m) => {
      if (m.id == null || !re.test(String(m.text || ''))) return;
      const d =
        Math.abs(((Number(m.week) || 1) - 1) * 7 + (Number(m.day) || 1) - (s.day || 0)) * 2 +
        (m.arc ? 1 : 0);
      if (d < bd || (d === bd && Number(m.id) > Number(best.id))) {
        best = m;
        bd = d;
      }
    });
    return best && bd <= 6 ? best.id : null;
  }
  function section(list, rows, isFresh) {
    if (!list || !list.length) return '';
    const cards = list.filter((s) => isFresh(s)).map((s) => card(s, journalId(s, rows)));
    return cards.length
      ? `<section class="stat" data-fxg="40,0"><div class="stat-h" data-fx="down" data-fxs="slide"><h3>${T2('STATUS UPDATES')}</h3><small>${T2('SINCE YOU LAST LOOKED')}</small></div><div class="stat-g" data-fxg="320,700" data-fxcap="3000">${cards.join('')}</div></section>`
      : '';
  }
  // ---- the bottom-left notes (plain dark notes in the alert lane, they never move the clan box): one row per update - journal icon, the story line cut to
  // two lines, "(more in JOURNAL)" which opens the clan screen on that journal entry. Up to 3 at a time, each shown once.
  let noted = null,
    q = [],
    live = 0,
    hold = 9000,
    rowsRef = [];
  const loadNoted = () => {
    if (noted) return noted;
    try {
      noted = new Set(JSON.parse(localStorage.getItem(KEY) || '[]'));
    } catch (e) {
      noted = new Set();
    }
    return noted;
  };
  const saveNoted = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify([...noted].slice(-60)));
    } catch (e) {
      /* private window: shown again next time */
    }
  };
  const blocked = () =>
    document.body.classList.contains('game-on') ||
    document.body.classList.contains('sp-mode') ||
    (typeof curView !== 'undefined' && curView === 'clan');
  const clip = (t, n) => {
    t = String(t || '');
    return t.length > n ? t.slice(0, n - 1).replace(/[\s,.;:]+$/, '') + '…' : t;
  };
  function ensureEl() {
    let el = $('stnote');
    if (!el) {
      el = document.createElement('div');
      el.id = 'stnote';
      el.className = 'stnote';
      (document.getElementById('app') || document.body).appendChild(el);
    }
    return el;
  }
  function drop(r) {
    r.classList.remove('on');
    setTimeout(() => {
      r.remove();
      live--;
      pump();
    }, 500);
  }
  function show(s) {
    const st = s.state || 'hungry',
      el = ensureEl(),
      r = document.createElement('div'),
      jid = journalId(s, rowsRef);
    loadNoted().add(s.id);
    saveNoted();
    live++;
    r.className = `stn st-${st}`;
    r.style.setProperty('--sc', COLOR[st] || '#999');
    r.innerHTML = `<i class="ic i-journal" style="--s:22px"></i><span class="stt">${esc(clip(s.line, 66))} <u>${T2('(more in JOURNAL)')}</u></span>`;
    r.addEventListener('click', () => {
      r.remove();
      live--;
      if (typeof f2show === 'function') f2show('clan');
      if (jid != null) setTimeout(() => goto(jid), 1800);
    });
    el.appendChild(r);
    void r.offsetWidth;
    r.classList.add('on');
    if (typeof Snd !== 'undefined' && Snd.fx) Snd.fx('cl-st-' + st, 0.3);
    setTimeout(() => {
      if (r.isConnected) drop(r);
    }, hold);
  }
  function pump() {
    if (!q.length) return;
    if (blocked()) {
      setTimeout(pump, 3000);
      return;
    }
    while (live < 3 && q.length) show(q.shift());
  }
  // offer(list, feedRows): queue every update not yet announced; the clan screen shows them itself
  function offer(list, rows, opt) {
    if (opt && opt.hold) hold = opt.hold;
    if (rows) rowsRef = rows;
    const n = loadNoted();
    (list || []).forEach((s) => {
      if (!n.has(s.id) && !q.some((x) => x.id === s.id)) q.push(s);
    });
    if (q.length) setTimeout(pump, 600);
  }
  function goto(jid) {
    const body = $('clan-body');
    if (!body) return;
    const el = body.querySelector(`.jrn[data-jid="${CSS.escape(String(jid))}"]`);
    if (!el) return;
    const older = el.closest('details');
    if (older) older.open = true;
    const from = body.scrollTop,
      to = Math.max(
        0,
        from +
          el.getBoundingClientRect().top -
          body.getBoundingClientRect().top -
          (body.clientHeight - el.offsetHeight) / 2,
      ),
      t0 = performance.now(); // own eased scroll (scrollIntoView smooth does nothing in some embedders)
    const step = (now) => {
      const k = Math.min(1, (now - t0) / 700),
        e = 1 - Math.pow(1 - k, 3);
      body.scrollTop = from + (to - from) * e;
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    el.classList.add('jflash');
    setTimeout(() => el.classList.remove('jflash'), 2600);
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.sc-more');
    if (b) goto(b.dataset.jid);
  });
  return {
    section,
    offer,
    goto,
    reset() {
      noted = new Set();
      saveNoted();
      q = [];
      live = 0;
      const e = $('stnote');
      if (e) e.innerHTML = '';
    },
    journalId,
    COLOR,
    WORD,
    GLYPH,
    TXT,
  };
})();
