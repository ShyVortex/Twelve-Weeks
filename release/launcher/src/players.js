/**
 * @file ONLINE PLAYERS panel (TEST FEATURE, to be cut before the public release).
 * Click the top-right ONLINE indicator: the panel slides in from the right and the launcher is pushed aside (#app narrows).
 * Lists every online player with name + state (in menus / searching / in a match + map / in a party) from /status.json "roster"
 * (tools/daemon.py roster_public: names and states only). Click again or Esc closes it. Polled on open and on the launcher's own 30 s status tick (app.js).
 *
 * TO CUT: set PLAYERS_PANEL to false (nothing is bound, the indicator stays a plain label), or delete this file, src/players.css,
 * the <script>/<link> lines and <aside id="players"> in index.html, and the Players.tick() line in app.js.
 */
'use strict';
const PLAYERS_PANEL = true;
const Players = (() => {
  if (!PLAYERS_PANEL) return { tick() {}, isOpen: () => false };
  const LINE = {
    menu: 'IN MENUS',
    searching: 'SEARCHING',
    match: 'IN A MATCH',
    party: 'IN A PARTY',
  };
  const CLS = { menu: 'menu', searching: 'search', match: 'match', party: 'menu' };
  const ORDER = { searching: 0, match: 1, party: 2, menu: 3 };
  let open = false;
  let seq = 0;
  const lineOf = (p) =>
    p.state === 'match' && p.map ? T('IN A MATCH') + ' - ' + p.map : T(LINE[p.state] || LINE.menu);

  function render(r) {
    const list = $('pp-list');
    if (!r.ok) {
      $('pp-n').textContent = '';
      list.innerHTML = `<div class="empty">${esc(T('Player list unavailable.'))}</div>`;
      return;
    }
    const ps = r.players
      .slice()
      .sort(
        (a, b) => (ORDER[a.state] ?? 9) - (ORDER[b.state] ?? 9) || a.name.localeCompare(b.name),
      );
    $('pp-n').textContent = ps.length;
    list.innerHTML = ps.length
      ? ps
          .map(
            (p) =>
              `<div class="fr-row st-${CLS[p.state] || 'menu'}" tabindex="0" data-name="${esc(p.name)}" title="${esc(T('ADD FRIEND'))}"><span class="fr-av"><i class="dot"></i></span><div class="fr-who"><b>${esc(p.name)}</b><small>${esc(lineOf(p))}</small></div><div class="fr-act">${p.party ? `<span class="fr-tag">${esc(T('PARTY'))}</span>` : ''}</div></div>`,
          )
          .join('')
      : `<div class="empty">${esc(T('No players online.'))}</div>`;
  }

  async function refresh() {
    const my = ++seq;
    let r = { ok: false, players: [] };
    try {
      r = await f2.playersRoster();
    } catch {
      /* shown as unavailable */
    }
    if (my === seq && open) render(r && r.ok !== undefined ? r : { ok: false, players: [] });
  }

  // ---------------------------------------------------------------- right click on a player: ADD FRIEND (or what fits the relation)
  // Enter / the context-menu key / a pad's A on a focused row open it too. The server takes the exact name (tools/social.py _resolve).
  const menu = document.createElement('div');
  menu.id = 'pp-menu';
  menu.className = 'pp-menu';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-modal', 'true'); // padnav keeps the pad focus inside while it is open
  menu.hidden = true;
  document.body.appendChild(menu);
  let menuRow = null;
  function closeMenu(refocus) {
    if (menu.hidden) return;
    menu.hidden = true;
    menu.innerHTML = '';
    if (refocus && menuRow && document.contains(menuRow)) menuRow.focus();
    menuRow = null;
  }
  function openMenu(row, x, y) {
    const name = row.dataset.name;
    const rel = typeof Social !== 'undefined' && Social.relOf ? Social.relOf(name) : null;
    if (rel && rel.rel === 'self') return; // nothing to do with your own name
    const item = (act, label, off) =>
      `<button class="pp-mi" role="menuitem" data-pp="${act}"${off ? ' disabled' : ''} data-snd="click">${esc(T(label))}</button>`;
    let items;
    if (!rel || rel.rel === null) items = item('add', 'ADD FRIEND');
    else if (rel.rel === 'friend')
      items =
        item('chat', 'MESSAGE') +
        (rel.invite
          ? item('invite', 'INVITE TO PARTY')
          : item('', rel.inParty ? 'IN YOUR PARTY' : 'FRIENDS', true));
    else if (rel.rel === 'out') items = item('', 'REQUEST SENT', true);
    else items = item('accept', 'ACCEPT');
    menu.innerHTML = `<div class="pp-mh">${esc(name)}</div>${items}`;
    menu.dataset.id = (rel && rel.id) || '';
    menuRow = row;
    menu.hidden = false;
    const w = menu.offsetWidth,
      h = menu.offsetHeight;
    menu.style.left = Math.max(4, Math.min(x, innerWidth - w - 4)) + 'px';
    menu.style.top = Math.max(4, Math.min(y, innerHeight - h - 4)) + 'px';
    Snd.play('click');
    const first = menu.querySelector('.pp-mi:not([disabled])') || menu.querySelector('.pp-mi');
    if (first) first.focus();
  }
  menu.addEventListener('click', (e) => {
    const b = e.target.closest('.pp-mi');
    if (!b || b.disabled || !menuRow) return;
    const name = menuRow.dataset.name,
      id = menu.dataset.id,
      a = b.dataset.pp;
    closeMenu(true);
    if (a === 'add') Social.addByName(name);
    else if (a === 'invite') Social.invite(id);
    else if (a === 'accept') Social.accept(id);
    else if (a === 'chat') Social.openChat(id);
  });
  // delegated on document: <aside id="players"> comes after this script in index.html
  document.addEventListener('contextmenu', (e) => {
    const row = e.target.closest && e.target.closest('#pp-list .fr-row[data-name]');
    if (!row) return;
    e.preventDefault();
    openMenu(row, e.clientX, e.clientY);
  });
  document.addEventListener('keydown', (e) => {
    const row = e.target.closest && e.target.closest('#pp-list .fr-row[data-name]');
    if (!row || !(e.key === 'Enter' || e.key === ' ' || e.key === 'ContextMenu')) return;
    e.preventDefault();
    const r = row.getBoundingClientRect();
    openMenu(row, r.left + 52, r.bottom - 6);
  });
  document.addEventListener('scroll', (e) => e.target.id === 'pp-list' && closeMenu(false), true);
  document.addEventListener('mousedown', (e) => {
    if (!menu.hidden && !menu.contains(e.target)) closeMenu(false);
  });
  window.addEventListener('blur', () => closeMenu(false));

  function set(on) {
    if (on === open) return;
    open = on;
    if (!on) closeMenu(false);
    $('app').classList.toggle('pl-open', on);
    $('online').classList.toggle('on', on);
    $('players').setAttribute('aria-hidden', on ? 'false' : 'true');
    Snd.play(on ? 'tab' : 'back');
    if (on) {
      $('pp-list').innerHTML = `<div class="empty">${esc(T('Loading...'))}</div>`;
      refresh();
    }
  }

  document.body.classList.add('players-on');
  const toggle = () => set(!open);
  $('online').addEventListener('click', toggle);
  $('online').addEventListener('mouseenter', () => Snd.play('hover'));
  $('online').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle();
    }
  });
  // Esc closes the panel first (capture phase, before the view handler in app/ui.js)
  window.addEventListener(
    'keydown',
    (e) => {
      if (e.key === 'Escape' && !menu.hidden) {
        e.stopImmediatePropagation();
        closeMenu(true); // Esc closes the menu first, the panel on the next press
      } else if (e.key === 'Escape' && open) {
        e.stopImmediatePropagation();
        set(false);
      }
    },
    true,
  );
  return {
    tick() {
      if (open) refresh();
    },
    isOpen: () => open,
  };
})();
