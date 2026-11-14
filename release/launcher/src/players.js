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
              `<div class="fr-row st-${CLS[p.state] || 'menu'}"><span class="fr-av"><i class="dot"></i></span><div class="fr-who"><b>${esc(p.name)}</b><small>${esc(lineOf(p))}</small></div><div class="fr-act">${p.party ? `<span class="fr-tag">${esc(T('PARTY'))}</span>` : ''}</div></div>`,
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

  function set(on) {
    if (on === open) return;
    open = on;
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
      if (e.key === 'Escape' && open) {
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
