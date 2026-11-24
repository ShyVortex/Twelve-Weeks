'use strict';
// FRIENDS tab (daemon op 0xD8, tools/social.py; lib/daemon.js social()): friends with presence (online first, status dot + text, offline greyed with
// the last seen), pending requests (incoming accept / decline, sent cancel), add friend (search by name or Steam id), and the party (leader crown,
// ready state, invite from the friends list, leave, kick / make leader for the leader), and private messages between friends (MESSAGE on a friend
// row or in the PLAYERS ONLINE right-click menu opens the chat; unread counts on the rows, the tab and the menu pip). The game side is automatic:
// the leader's FIND MATCH in the game asks the members to follow, the matchmaker queues the party as one unit on one team.
const Social = (() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(
      /[&<>"]/g,
      (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m],
    );
  const TABS = ['friends', 'pending', 'add', 'party'];
  let data = null,
    tab = 'friends',
    err = '', // last error text under the tabs
    offline = false, // the server did not answer (older server)
    found = null, // search results of the ADD tab
    query = '',
    busy = false,
    armed = '', // a REMOVE button that was pressed once ("SURE?")
    rendered = '',
    first = true,
    timer = 0,
    started = false,
    chatWith = '', // the friend id whose chat is open in the FRIENDS tab
    chat = null, // { with, msgs: [{ id, me, t, age }] } of chatWith
    draft = ''; // the unsent text of the chat box
  const seen = new Set(); // ids of requests / invitations already announced
  let lastUnread = null; // { friend id: unread count } of the previous state (new messages are announced)
  const MSG_BYTES = 200; // the daemon reads 200 bytes of argument: "<friend id>\n<text>"
  const u8 = (ch) => {
    const c = ch.codePointAt(0);
    return c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
  };
  const room4 = (id) => MSG_BYTES - [...(id + '\n')].reduce((n, ch) => n + u8(ch), 0);
  function fit(s, max) {
    let out = '',
      n = 0;
    for (const ch of s) {
      const b = u8(ch);
      if (n + b > max) break;
      out += ch;
      n += b;
    }
    return out;
  }
  const unreadOf = (id) => (data && data.unread && data.unread[id]) || 0;
  const unreadAll = () =>
    data && data.unread ? Object.values(data.unread).reduce((a, b) => a + b, 0) : 0;

  const ERR = {
    self: 'That is you.',
    unknown:
      'No player with that name or Steam id was found. They need to have played Twelve Weeks or opened the launcher once.',
    ambiguous:
      'More than one player has that name. Search for it and pick one from the list, or use the Steam id.',
    already: 'You are already friends.',
    pending: 'You already sent this player a request.',
    limit: 'The limit of friends or open requests is reached.',
    expired: 'That request or invitation is no longer valid.',
    rate: 'Too many actions in a short time. Wait a moment.',
    notfriend: 'You can only invite friends to a party.',
    notfriendmsg: 'You can only message friends.',
    offline: 'That friend is offline.',
    notleader: 'Only the party leader can do that.',
    full: 'The party is full.',
    notmember: 'That player is not in your party.',
    noparty: 'You are not in a party.',
  };
  const errText = (c) => T(ERR[c] || 'Something went wrong. Try again.');

  const STATUS = {
    match: 'IN A MATCH',
    search: 'SEARCHING FOR A MATCH',
    menu: 'IN THE GAME MENU',
    launcher: 'ONLINE IN THE LAUNCHER',
    off: 'OFFLINE',
  };
  function ago(s) {
    if (s == null) return '';
    if (s < 90) return T('just now');
    if (s < 5400) return T('{n} min ago', { n: Math.round(s / 60) });
    if (s < 129600) return T('{n} h ago', { n: Math.round(s / 3600) });
    return T('{n} d ago', { n: Math.round(s / 86400) });
  }
  const statusLine = (f) =>
    f.status === 'off'
      ? f.seen == null
        ? T('OFFLINE')
        : T('OFFLINE') + ' - ' + T('LAST SEEN {t}', { t: ago(f.seen) })
      : T(STATUS[f.status] || 'OFFLINE');

  const CROWN =
    '<svg class="fr-crown" viewBox="0 0 16 12" aria-hidden="true"><path d="M1 11 2 3l4 4 2-6 2 6 4-4 1 8z"/></svg>';
  const btn = (act, id, label, cls) =>
    `<button class="btn fr-b ${cls || ''}" data-fr="${act}" data-id="${esc(id)}" data-snd="click">${esc(T(label))}</button>`;
  const row = (st, name, line, acts, extra) =>
    `<div class="fr-row st-${st}"><span class="fr-av"><i class="dot"></i></span><div class="fr-who"><b>${extra || ''}${esc(name)}</b><small>${esc(line)}</small></div><div class="fr-act">${acts || ''}</div></div>`;
  const head = (t) => `<div class="pr-h">${esc(T(t))}</div>`;

  // ---------------------------------------------------------------- tabs
  function friendsPane() {
    const fl = data.friends,
      party = data.party,
      inMine = (f) => party && party.members.some((m) => m.id === f.id);
    if (!fl.length)
      return `<div class="empty">${esc(T('No friends yet. Open ADD FRIEND to find players by name or Steam id.'))}</div>`;
    const on = fl.filter((f) => f.status !== 'off'),
      off = fl.filter((f) => f.status === 'off');
    const room = !party || (party.meLeader && party.members.length < party.max);
    const one = (f) => {
      const u = unreadOf(f.id);
      let acts = btn('chat', f.id, 'MESSAGE', u ? 'fr-hot' : '');
      if (u) acts = `<em class="fr-n hot" title="${esc(T('Unread messages'))}">${u}</em>` + acts;
      if (inMine(f)) acts += `<span class="fr-tag">${esc(T('IN YOUR PARTY'))}</span>`;
      else if (f.status !== 'off' && room) acts += btn('invite', f.id, 'INVITE TO PARTY');
      acts += btn(
        'remove',
        f.id,
        armed === 'remove:' + f.id ? 'SURE?' : 'REMOVE',
        'quiet' + (armed === 'remove:' + f.id ? ' arm' : ''),
      );
      return row(f.status, f.name, statusLine(f), acts);
    };
    return (
      (on.length ? head(T('ONLINE - {n}', { n: on.length })) + on.map(one).join('') : '') +
      (off.length ? head(T('OFFLINE - {n}', { n: off.length })) + off.map(one).join('') : '')
    );
  }
  function chatFriend() {
    return (data && data.friends.find((f) => f.id === chatWith)) || null;
  }
  function msgsHtml() {
    const ms = chat && chat.with === chatWith ? chat.msgs : null;
    if (ms == null) return `<div class="empty">${esc(T('Loading messages...'))}</div>`;
    if (!ms.length) return `<div class="empty">${esc(T('No messages yet.'))}</div>`;
    return ms
      .map(
        (m) =>
          `<div class="fr-msg ${m.me ? 'me' : 'them'}"><p>${esc(m.t)}</p><small>${esc(ago(m.age))}</small></div>`,
      )
      .join('');
  }
  function chatPane() {
    const f = chatFriend();
    if (!f) return `<div class="empty">${esc(T('That player is not your friend any more.'))}</div>`;
    return (
      `<div class="fr-chat">` +
      `<div class="fr-ch-head">${btn('back', '', 'BACK', 'quiet')}${row(f.status, f.name, statusLine(f), '')}</div>` +
      `<div id="fr-msgs" class="fr-msgs" aria-live="polite">${msgsHtml()}</div>` +
      `<div class="fr-add fr-send"><input id="fr-m" data-with="${esc(f.id)}" type="text" spellcheck="true" autocomplete="off" placeholder="${esc(T('Write a message to {n}', { n: f.name }))}" value="${esc(draft)}">` +
      btn('send', f.id, 'SEND') +
      `</div><div class="msub fr-hint">${esc(T('Only friends can message you. Messages are kept for 30 days.'))}</div></div>`
    );
  }
  function scrollMsgs() {
    const m = $('fr-msgs');
    if (m) m.scrollTop = m.scrollHeight;
  }
  function pendingPane() {
    const inc = data.in,
      out = data.out;
    if (!inc.length && !out.length)
      return `<div class="empty">${esc(T('No pending requests.'))}</div>`;
    return (
      (inc.length
        ? head('INCOMING REQUESTS') +
          inc
            .map((r) =>
              row(
                'off',
                r.name,
                T('WANTS TO BE YOUR FRIEND') + ' - ' + ago(r.age),
                btn('accept', r.id, 'ACCEPT') + btn('decline', r.id, 'DECLINE', 'quiet'),
              ),
            )
            .join('')
        : '') +
      (out.length
        ? head('SENT REQUESTS') +
          out
            .map((r) =>
              row(
                'off',
                r.name,
                T('WAITING FOR AN ANSWER') + ' - ' + ago(r.age),
                btn('cancel', r.id, 'CANCEL', 'quiet'),
              ),
            )
            .join('')
        : '')
    );
  }
  function foundHtml() {
    if (found == null) return '';
    if (!found.length) return `<div class="empty">${esc(T('No players found.'))}</div>`;
    return found
      .map((p) => {
        const rel = p.rel,
          tag = rel === 'friend' ? 'FRIENDS' : rel === 'out' ? 'REQUEST SENT' : '';
        const acts = tag
          ? `<span class="fr-tag">${esc(T(tag))}</span>`
          : rel === 'in'
            ? btn('accept', p.id, 'ACCEPT')
            : btn('add', p.id, 'ADD');
        return row(
          p.status || 'off',
          p.name,
          rel === 'in' ? T('WANTS TO BE YOUR FRIEND') : p.status ? statusLine(p) : '',
          acts,
        );
      })
      .join('');
  }
  function addPane() {
    const sid = data.me && /^s:\d+$/.test(data.me.id) ? data.me.id.slice(2) : '';
    return (
      `<div class="fr-add"><input id="fr-q" type="text" maxlength="31" spellcheck="false" autocomplete="off" placeholder="${esc(T('Player name or Steam id'))}" value="${esc(query)}">` +
      btn('search', '', 'SEARCH') +
      `</div><div id="fr-found">${foundHtml()}</div>` +
      (sid
        ? `<div class="fr-me">${head('YOUR STEAM ID')}<div class="fr-add"><input type="text" readonly value="${esc(sid)}" id="fr-sid">${btn('copy', sid, 'COPY', 'quiet')}</div><div class="msub">${esc(T('Friends can add you by your name or by this number.'))}</div></div>`
        : '')
    );
  }
  function partyPane() {
    const p = data.party;
    let html = '';
    if (data.pinv.length)
      html +=
        head('PARTY INVITATIONS') +
        data.pinv
          .map((i) =>
            row(
              'menu',
              i.name,
              T('invited you to a party') + ' - ' + ago(i.age),
              btn('join', i.id, 'JOIN') + btn('pdecline', i.id, 'DECLINE', 'quiet'),
            ),
          )
          .join('');
    if (!p) {
      return (
        html +
        `<div class="note fr-note"><b>${esc(T('NOT IN A PARTY'))}</b><p>${esc(T('Invite a friend from the FRIENDS tab. Whoever sends the first invitation that gets accepted becomes the leader.'))}</p></div>` +
        partyHelp()
      );
    }
    const me = p.members.find((m) => m.me),
      lead = p.meLeader;
    html += head(T('PARTY {n}/{m}', { n: p.members.length, m: p.max }));
    html += p.members
      .map((m) => {
        let acts = '';
        if (m.me) {
          acts += btn('ready', m.ready ? '0' : '1', m.ready ? 'NOT READY' : 'READY');
          acts += btn(
            'leave',
            '',
            lead && p.members.length > 1 ? 'DISBAND PARTY' : 'LEAVE PARTY',
            'quiet',
          );
        } else if (lead) {
          acts += btn('promote', m.id, 'MAKE LEADER', 'quiet') + btn('kick', m.id, 'KICK', 'quiet');
        }
        const line = [
          m.leader ? T('PARTY LEADER') : T('MEMBER'),
          m.status === 'off' ? T('OFFLINE') : T(STATUS[m.status]),
        ].join(' - ');
        const rd = `<span class="fr-ready ${m.ready ? 'on' : ''}">${esc(T(m.ready ? 'READY' : 'NOT READY'))}</span>`;
        return row(m.status, m.name, line, rd + acts, m.leader ? CROWN : '');
      })
      .join('');
    if (me && p.members.length < p.max && lead)
      html += `<div class="msub fr-hint">${esc(T('Free places: {n}. Invite friends from the FRIENDS tab.', { n: p.max - p.members.length }))}</div>`;
    return html + partyHelp(p);
  }
  const partyHelp = (p) =>
    `<div class="msub fr-hint">${esc(
      p && p.searching
        ? T('Your party is searching for a match.')
        : T(
            'When the leader presses FIND MATCH in the game, the other members get a message and have to press it too. The match starts when the whole party searches. A party always plays on the same team.',
          ),
    )}</div>`;

  // ---------------------------------------------------------------- render
  function counts() {
    return {
      friends: data ? data.friends.filter((f) => f.status !== 'off').length : 0,
      pending: data ? data.in.length : 0,
      party: data ? (data.party ? data.party.members.length : 0) + data.pinv.length : 0,
    };
  }
  function drawTabs() {
    const c = counts(),
      el = $('fr-tabs');
    if (!el.firstChild) {
      el.innerHTML = TABS.map(
        (t) => `<button class="sub" data-ftab="${t}" data-snd="tab"></button>`,
      ).join('');
      el.addEventListener('click', (e) => {
        const b = e.target.closest('[data-ftab]');
        if (b) go(b.dataset.ftab);
      });
    }
    const LABEL = { friends: 'FRIENDS', pending: 'PENDING', add: 'ADD FRIEND', party: 'PARTY' };
    for (const b of el.children) {
      const t = b.dataset.ftab,
        n = c[t];
      b.classList.toggle('active', t === tab);
      b.innerHTML =
        esc(T(LABEL[t])) +
        (n
          ? ` <em class="fr-n ${t === 'pending' || (t === 'party' && data && data.pinv.length) ? 'hot' : ''}">${n}</em>`
          : '') +
        (t === 'friends' && unreadAll()
          ? ` <em class="fr-n hot" title="${esc(T('Unread messages'))}">${unreadAll()}</em>`
          : '');
    }
  }
  function render(force) {
    const el = $('fr-body');
    if (!data) {
      drawTabs();
      el.innerHTML = `<div class="empty">${esc(offline ? T('The friends service is not available: the game server did not answer or is an older version.') : T('Loading friends...'))}</div>`;
      return;
    }
    drawTabs();
    if (tab === 'friends' && chatWith && !chatFriend() && data) chatWith = '';
    const pane =
      tab === 'friends'
        ? chatWith
          ? chatPane()
          : friendsPane()
        : tab === 'pending'
          ? pendingPane()
          : tab === 'add'
            ? addPane()
            : partyPane();
    const html = (err ? `<div class="fr-err">${esc(err)}</div>` : '') + pane;
    if (html === rendered && !force) return; // (the polls change nothing on screen when nothing changed: no rebuild, no flicker)
    if (
      tab === 'add' &&
      !force &&
      rendered &&
      document.activeElement &&
      document.activeElement.id === 'fr-q'
    ) {
      $('fr-found').innerHTML = foundHtml(); // (typing: only the results change, never the box)
      return;
    }
    if (
      tab === 'friends' &&
      chatWith &&
      !force &&
      rendered &&
      $('fr-m') &&
      $('fr-m').dataset.with === chatWith
    ) {
      // this chat is on screen: only the messages and the friend's status change, never the box (typing, focus); the list stays at the bottom
      const m = $('fr-msgs'),
        atEnd = m.scrollHeight - m.scrollTop - m.clientHeight < 30,
        h = msgsHtml(),
        f = chatFriend(),
        hr = el.querySelector('.fr-ch-head .fr-row'),
        rh = row(f.status, f.name, statusLine(f), '');
      if (hr && hr.outerHTML !== rh) hr.outerHTML = rh;
      if (m.innerHTML !== h) {
        m.innerHTML = h;
        if (atEnd) scrollMsgs();
      }
      rendered = html;
      return;
    }
    const keep = document.activeElement && document.activeElement.id === 'fr-m';
    rendered = html;
    el.innerHTML = html;
    if (tab === 'friends' && chatWith) {
      scrollMsgs();
      if (keep) {
        const i = $('fr-m');
        if (i) {
          i.focus();
          i.setSelectionRange(i.value.length, i.value.length);
        }
      }
    }
  }

  // ---------------------------------------------------------------- data
  const badge = () => {
    const n = data ? data.in.length + data.pinv.length + unreadAll() : 0;
    $('fr-pip').hidden = !n;
  };
  function announce() {
    if (!data) return;
    const fresh = [];
    for (const r of data.in)
      if (!seen.has('f' + r.id))
        fresh.push(['f' + r.id, T('{n} sent you a friend request.', { n: r.name })]);
    for (const i of data.pinv)
      if (!seen.has('p' + i.id))
        fresh.push(['p' + i.id, T('{n} invited you to a party.', { n: i.name })]);
    const un = data.unread || {};
    if (lastUnread)
      for (const id of Object.keys(un)) {
        const open = chatWith === id && curView === 'friends';
        if (un[id] > (lastUnread[id] || 0) && !open) {
          const f = data.friends.find((x) => x.id === id);
          fresh.push([
            'm' + id + ':' + un[id],
            T('{n} sent you a message.', { n: f ? f.name : T('A friend') }),
          ]);
        }
      }
    lastUnread = Object.assign({}, un);
    for (const [k] of fresh) seen.add(k);
    if (!first && fresh.length) {
      Snd.play('confirm');
      notify(fresh[0][1]);
    }
    first = false;
  }
  function take(r) {
    // a reply of f2.social / f2.socialAct
    if (!r || !r.ok || !r.social) {
      offline = true;
      return false;
    }
    offline = false;
    data = r.social;
    if (!data.v) data = null;
    else if (data.chat) chat = data.chat;
    return !!data;
  }
  async function load(force) {
    if ((busy && !force) || document.body.classList.contains('sp-mode')) return;
    try {
      const inChat = chatWith && curView === 'friends' && tab === 'friends';
      if (take(await (inChat ? f2.socialAct('chat', chatWith) : f2.social()))) {
        announce();
        badge();
      }
    } catch {
      offline = true;
    }
    if (curView === 'friends') render();
  }
  async function act(sub, arg, opts) {
    if (busy) return;
    busy = true;
    err = '';
    try {
      const r = await f2.socialAct(sub, arg == null ? '' : String(arg));
      if (take(r)) {
        if (r.social.found) found = r.social.found;
        if (!r.social.ok && r.social.err) {
          err = errText(
            sub === 'msg' && r.social.err === 'notfriend' ? 'notfriendmsg' : r.social.err,
          );
          Snd.play('error');
        } else if (opts && opts.done) toast(T(opts.done), true, T('FRIENDS'));
        announce();
        badge();
      } else {
        err = T('The game server did not answer.');
        Snd.play('error');
      }
    } catch {
      err = T('Something went wrong. Try again.');
    }
    busy = false;
    armed = '';
    render(true);
  }
  function go(t) {
    tab = t;
    err = '';
    armed = '';
    if (data) render(true);
    else render();
    if (t === 'add')
      setTimeout(() => {
        const q = $('fr-q');
        if (q) q.focus();
      }, 60);
  }

  // ---------------------------------------------------------------- events
  function clicked(e) {
    const b = e.target.closest('[data-fr]');
    if (!b || b.disabled) return;
    const a = b.dataset.fr,
      id = b.dataset.id;
    if (a === 'invite') return act('invite', id, { done: 'Invitation sent.' });
    if (a === 'chat') return openChat(id);
    if (a === 'back') {
      chatWith = '';
      chat = null;
      draft = '';
      err = '';
      render(true);
      const r = $('fr-body').querySelector('[data-fr="chat"]');
      if (r) r.focus();
      return;
    }
    if (a === 'send') return send();
    if (a === 'remove') {
      if (armed !== 'remove:' + id) {
        armed = 'remove:' + id;
        render(true);
        return;
      }
      return act('remove', id);
    }
    if (a === 'accept') return act('accept', id);
    if (a === 'decline' || a === 'cancel') return act('remove', id);
    if (a === 'add') return act('add', id, { done: 'Friend request sent.' });
    if (a === 'search') return runSearch();
    if (a === 'join') return act('join', id).then(() => go('party'));
    if (a === 'pdecline') return act('decline', id);
    if (a === 'leave') return act('leave');
    if (a === 'kick') return act('kick', id);
    if (a === 'promote') return act('promote', id);
    if (a === 'ready') return act('ready', id);
    if (a === 'copy') {
      try {
        navigator.clipboard.writeText(id);
        toast(T('Steam id copied.'), true, T('FRIENDS'));
      } catch {
        $('fr-sid').select();
      }
    }
  }
  async function runSearch() {
    const q = ($('fr-q') ? $('fr-q').value : query).trim();
    query = q;
    if (q.length < 2) {
      found = null;
      err = T('Type at least 2 letters.');
      return render(true);
    }
    await act('search', q);
  }
  async function send() {
    const i = $('fr-m'),
      text = fit(((i ? i.value : draft) || '').trim(), room4(chatWith));
    if (!text || !chatWith || busy) return;
    draft = '';
    if (i) i.value = '';
    await act('msg', chatWith + '\n' + text);
    if (err) draft = text; // (not sent: the text comes back into the box)
    render(true);
    const box = $('fr-m');
    if (box) {
      if (err) box.value = draft;
      box.focus();
    }
  }
  function openChat(id) {
    if (chatWith !== id) {
      chat = null;
      draft = '';
    }
    chatWith = id;
    tab = 'friends';
    err = '';
    if (curView !== 'friends') showView('friends');
    else {
      render(true);
      load(true).then(schedule);
    }
    setTimeout(() => {
      const i = $('fr-m');
      if (i) i.focus();
    }, 80);
  }
  function init() {
    const body = $('fr-body');
    body.addEventListener('click', clicked);
    body.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.id === 'fr-q') {
        e.preventDefault();
        runSearch();
      }
      if (e.key === 'Enter' && e.target.id === 'fr-m') {
        e.preventDefault();
        send();
      }
      if (e.key === 'Escape' && e.target.id === 'fr-m' && !e.target.value) {
        e.preventDefault();
        e.stopPropagation();
        $('fr-body').querySelector('[data-fr="back"]').click();
      }
    });
    body.addEventListener('input', (e) => {
      if (e.target.id === 'fr-q') query = e.target.value;
      if (e.target.id === 'fr-m') {
        const v = fit(e.target.value, room4(chatWith));
        if (v !== e.target.value) e.target.value = v;
        draft = v;
      }
    });
  }
  // polls: every 5 s while the tab is open, else every 20 s (the badge + the "online" mark for the friends); 60 s while the game runs
  function schedule() {
    clearTimeout(timer);
    const gap = document.body.classList.contains('game-on')
      ? 60000
      : curView === 'friends'
        ? chatWith && tab === 'friends'
          ? 3000
          : 5000
        : 20000;
    timer = setTimeout(async () => {
      await load();
      schedule();
    }, gap);
  }
  function start() {
    if (started) return;
    started = true;
    init();
    load();
    schedule();
  }
  function open() {
    start();
    err = '';
    render();
    load(true).then(schedule);
  }
  // the PLAYERS ONLINE panel (src/players.js): what a right click on a name can do, and doing it (the server takes an exact player name)
  const same = (x, y) => String(x || '').toLowerCase() === String(y || '').toLowerCase();
  function relOf(name) {
    if (!data) return null;
    if (data.me && same(data.me.name, name)) return { rel: 'self' };
    const f = data.friends.find((x) => same(x.name, name));
    if (f) {
      const party = data.party;
      const inMine = !!party && party.members.some((m) => m.id === f.id);
      const room = !party || (party.meLeader && party.members.length < party.max);
      return {
        rel: 'friend',
        id: f.id,
        inParty: inMine,
        invite: !inMine && f.status !== 'off' && room,
      };
    }
    if (data.out.some((x) => same(x.name, name))) return { rel: 'out' };
    const i = data.in.find((x) => same(x.name, name));
    return i ? { rel: 'in', id: i.id } : { rel: null };
  }
  async function quick(sub, arg, done) {
    try {
      const r = await f2.socialAct(sub, String(arg));
      if (!take(r)) return toast(T('The game server did not answer.'), false, T('FRIENDS'));
      if (!r.social.ok && r.social.err) toast(errText(r.social.err), false, T('FRIENDS'));
      else if (done) toast(T(done), true, T('FRIENDS'));
      announce();
      badge();
      if (curView === 'friends') render(true);
    } catch {
      toast(T('Something went wrong. Try again.'), false, T('FRIENDS'));
    }
  }

  return {
    start,
    open,
    relOf,
    addByName: (name) => quick('add', name, 'Friend request sent.'),
    accept: (id) => quick('accept', id, null),
    invite: (id) => quick('invite', id, 'Invitation sent.'),
    openChat,
    rerender: () => {
      rendered = '';
      if (curView === 'friends') render(true);
    },
    last: () => data,
  };
})();
