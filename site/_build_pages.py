"""Writes the sub pages of the site from one shared head/shell (run: python site/_build_pages.py). Edit the page bodies here."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" href="assets/icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo+Narrow:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body data-page="{page}">
<main class="page">
{body}
</main>
<script src="common.js"></script>
<script>
{script}
</script>
</body>
</html>
"""

PAGES = {}

PAGES["news.html"] = dict(
    title="News - Twelve Weeks", desc="Every Twelve Weeks update, patch notes and fixes.", page="news",
    body="""<h1 class="title">News</h1>
<p class="sub">Every update, the same notes the launcher shows.</p>
<div id="news-list" class="news"><p class="empty">Loading news...</p></div>""",
    script="""api('/api/news').then((items) => {
  document.getElementById('news-list').innerHTML = items.length ? items.map((n, i) => newsCard(n, i === 0)).join('') : '<p class="empty">No news yet.</p>';
}).catch(() => { document.getElementById('news-list').innerHTML = '<p class="empty">News could not be loaded right now.</p>'; });""")

PAGES["leaderboards.html"] = dict(
    title="Leaderboards - Twelve Weeks", desc="Global Twelve Weeks leaderboards: wins, win rate, matches and clan weeks survived.", page="leaderboards",
    body="""<h1 class="title">Leaderboards</h1>
<p class="sub">Top 50 survivors across every match on the official server.</p>
<div class="tabs" id="tabs">
  <button data-by="wins">Wins</button><button data-by="winrate">Win rate</button><button data-by="matches">Matches</button><button data-by="weeks">Weeks survived</button>
</div>
<p class="note" id="note"></p>
<div class="wide"><table class="lb"><thead><tr><th>#</th><th>Player</th><th>Wins</th><th class="opt">Losses</th><th>Win rate</th><th class="opt">Matches</th><th>Weeks</th></tr></thead><tbody id="rows"><tr><td colspan="7" class="empty">Loading...</td></tr></tbody></table></div>""",
    script="""const COL = { wins: 2, winrate: 4, matches: 5, weeks: 6 };
const fac = (f) => f ? `<span class="fac ${f === 'WLF' ? 'wlf' : 'sera'}">${f === 'WLF' ? 'WLF' : 'SERA'}</span>` : '';
const td = (v, cls) => `<td${cls ? ` class="${cls}"` : ''}>${v}</td>`;
async function show(by) {
  history.replaceState(null, '', '?by=' + by);
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.by === by));
  const rows = document.getElementById('rows');
  try {
    const d = await api('/api/leaderboard?by=' + by);
    document.getElementById('note').textContent = by === 'winrate' ? `Players with at least ${d.minMatches} matches.` : by === 'weeks' ? 'Total clan weeks survived across all twelve-week runs.' : '';
    const c = (i, v, opt) => td(v, [opt ? 'opt' : '', COL[by] === i ? 'sort' : ''].filter(Boolean).join(' '));
    rows.innerHTML = d.rows.length ? d.rows.map((p) => '<tr>' + td(p.rank, 'rank') +
      td(`<a href="/player.html?id=${esc(p.id)}">${esc(p.name)}</a>${fac(p.faction)}`) +
      c(2, p.wins) + c(3, p.losses, 1) + c(4, p.winRate + '%') + c(5, p.matches, 1) + c(6, p.weeks) + '</tr>').join('')
      : '<tr><td colspan="7" class="empty">Nobody on this board yet.</td></tr>';
  } catch (e) { rows.innerHTML = '<tr><td colspan="7" class="empty">Leaderboards could not be loaded right now.</td></tr>'; }
}
document.getElementById('tabs').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) show(b.dataset.by); });
const by0 = new URLSearchParams(location.search).get('by');
show(['wins', 'winrate', 'matches', 'weeks'].includes(by0) ? by0 : 'wins');""")

PAGES["players.html"] = dict(
    title="Players - Twelve Weeks", desc="Look up any Twelve Weeks player: stats, faction and clan.", page="players",
    body="""<h1 class="title">Player lookup</h1>
<p class="sub">Search by in-game name to see stats and clan progress.</p>
<form class="search" id="f" autocomplete="off"><input id="q" type="search" placeholder="Player name" aria-label="Player name" maxlength="32"><button class="btn main" type="submit">Search</button></form>
<div class="results" id="res"></div>""",
    script="""const res = document.getElementById('res'), q = document.getElementById('q');
let t = 0;
async function run() {
  const s = q.value.trim();
  history.replaceState(null, '', s ? '?q=' + encodeURIComponent(s) : location.pathname);
  if (s.length < 2) { res.innerHTML = '<p class="empty">Type at least 2 letters.</p>'; return; }
  try {
    const hits = await api('/api/players?q=' + encodeURIComponent(s));
    res.innerHTML = hits.length ? hits.map((p) => `<a class="prow" href="/player.html?id=${esc(p.id)}"><b>${esc(p.name)}</b><span>${p.wins} wins / ${p.matches} matches / ${p.winRate}% win rate</span><span>${p.faction ? esc(p.faction) : 'No clan yet'}</span><span>Last seen ${esc(p.lastSeen)}</span></a>`).join('') : '<p class="empty">No player with that name.</p>';
  } catch (e) { res.innerHTML = '<p class="empty">Search is not available right now.</p>'; }
}
q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 250); });
document.getElementById('f').addEventListener('submit', (e) => { e.preventDefault(); run(); });
q.value = new URLSearchParams(location.search).get('q') || '';
if (q.value) run(); else q.focus();""")

PAGES["player.html"] = dict(
    title="Player - Twelve Weeks", desc="Twelve Weeks player profile.", page="me",
    body="""<div id="p"><p class="empty">Loading...</p></div>""",
    script="""const id = new URLSearchParams(location.search).get('id') || '';
const stat = (v, k) => `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`;
const kv = (k, v) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
function clanHtml(c, fac) {
  if (!c || !c.hasClan) return '<div class="clan"><h2>No clan yet</h2><p class="cl">This survivor has not started a twelve-week run.</p></div>';
  const st = { alive: 'Alive', dead: 'Fallen', won: 'Survived all twelve weeks' }[c.status] || c.status;
  const n = Math.max(1, c.size);
  const pct = Math.min(100, Math.round(100 * c.daysDone / (c.daysTotal || 83)));
  let h = `<div class="clan"><h2>${esc(c.factionName || fac || 'Clan')}</h2><p class="cl">${st}${c.status === 'alive' ? ` / week ${c.week} of ${c.weeks}, day ${c.dayOfWeek}` : ''}</p>`;
  h += `<div class="legend"><span><b>${c.size}</b> survivors</span><span><b>${c.healthy}</b> healthy</span><span><b>${c.hungry}</b> hungry</span><span><b>${c.sick}</b> sick</span></div>`;
  h += `<div class="bar2"><i class="h" style="width:${100 * c.healthy / n}%"></i><i class="u" style="width:${100 * c.hungry / n}%"></i><i class="s" style="width:${100 * c.sick / n}%"></i></div>`;
  h += '<div class="cgrid">';
  h += kv('Run progress', `${c.daysDone} / ${c.daysTotal} days<div class="progress"><i style="width:${pct}%"></i></div>`);
  h += kv('Largest clan', c.maxSize) + kv('Weeks survived (all runs)', c.weeksTotal) + kv('Runs won / lost', `${c.runsWon} / ${c.runsLost}`);
  if (c.mission) h += kv('Mission', `${esc(c.mission.name)} (${c.mission.daysLeft} day${c.mission.daysLeft === 1 ? '' : 's'} left)`);
  if (c.event) h += kv('Event', `${esc(c.event.name)}, day ${c.event.dayOfEvent} of ${c.event.length}`);
  return h + '</div></div>';
}
(id ? api('/api/player?id=' + encodeURIComponent(id)) : Promise.reject(new Error('no id'))).then((p) => {
  document.title = p.name + ' - Twelve Weeks';
  let h = `<div class="phead"><div><h1 class="title">${esc(p.name)}</h1><div class="meta2">${p.faction ? esc(p.faction) + ' / ' : ''}Last seen ${esc(p.lastSeen || 'never')}${p.steamProfile ? ` / <a href="${esc(p.steamProfile)}" target="_blank" rel="noopener">Steam profile</a>` : ''}</div></div></div>`;
  h += '<div class="stats">' + stat(p.matches, 'Matches') + stat(p.wins, 'Wins') + stat(p.losses, 'Losses') + stat(p.draws, 'Draws') + stat(p.winRate + '%', 'Win rate') + stat(p.weeks, 'Weeks survived') + '</div>';
  h += clanHtml(p.clan, p.faction);
  document.getElementById('p').innerHTML = h;
}).catch(() => {
  document.getElementById('p').innerHTML = '<h1 class="title">Not found</h1><p class="sub">No player with this id. If you just logged in, play a match first and your stats will show up here.</p><a class="btn ghost" href="/players.html">Search players</a>';
});""")

PAGES["404.html"] = dict(
    title="Not found - Twelve Weeks", desc="", page="",
    body="""<h1 class="title">Lost in the woods</h1><p class="sub">This page does not exist.</p><a class="btn main" href="/">Back home</a>""",
    script="")

for name, d in PAGES.items():
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as fh:
        out = HEAD
        for k in ("title", "desc", "page", "body", "script"):
            out = out.replace("{" + k + "}", d[k])
        fh.write(out)
print("wrote", ", ".join(PAGES))
