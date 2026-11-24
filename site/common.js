// Shared header, footer, links and helpers for every page.
// Links in one place. win / linux = the same launcher downloads the Discord bot posts (tools/discord-bot/config.json):
// bump both together on a launcher release. download = the home page's download panel.
const LINKS = {
  download: '/#download',
  win: 'https://dl.twelve-weeks.com/download/TwelveWeeks-Launcher-0.1.41.exe',
  linux: 'https://dl.twelve-weeks.com/download/TwelveWeeks-Launcher-0.1.41.AppImage',
  source: 'https://github.com/kelliex3/Twelve-Weeks',
  discord: 'https://discord.gg/wmVgW2wxge',
};

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (path) => {
  const r = await fetch(path, { credentials: 'same-origin' });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'HTTP ' + r.status);
  return r.json();
};

(function shell() {
  const page = document.body.dataset.page || '';
  if (new URLSearchParams(location.search).get('embed') === '1' && window.top !== window) {   // inside admin.twelve-weeks.com PATCH NOTES
    document.documentElement.classList.add('embed');
    return;
  }
  const items = [
    ['home', '/', 'Home'],
    ['news', '/news.html', 'News'],
    ['faq', '/faq.html', 'FAQ'],
    ['leaderboards', '/leaderboards.html', 'Leaderboards'],
    ['players', '/players.html', 'Players'],
    ['download', LINKS.download, 'Download'],
  ];
  const head = document.createElement('header');
  head.className = 'bar' + (page === 'home' ? '' : ' solid fixed-solid');
  head.id = 'bar';
  head.innerHTML =
    `<a class="logo" href="/" aria-label="Twelve Weeks home">12</a>` +
    `<button class="menu" id="menu" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>` +
    `<nav class="nav" id="nav">` +
    items.map(([k, href, label]) => `<a href="${href}"${k === page ? ' class="on"' : ''}${k === 'download' ? ' data-link="download"' : ''}>${label}</a>`).join('') +
    `<a href="/auth/steam" class="login" id="login"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 0 0-9.96 9.2l5.35 2.21a2.8 2.8 0 0 1 1.6-.5h.16l2.38-3.45v-.05a3.77 3.77 0 1 1 3.77 3.77h-.09l-3.4 2.42v.13a2.83 2.83 0 0 1-5.6.57L2.4 15.1A10 10 0 1 0 12 2zM8.28 17.17l-1.22-.5a2.12 2.12 0 1 0 1.16-2.9l1.27.52a1.56 1.56 0 1 1-1.2 2.88zm9.51-7.74a2.51 2.51 0 1 0-2.51 2.51 2.51 2.51 0 0 0 2.51-2.51zm-4.4 0a1.89 1.89 0 1 1 1.89 1.89 1.89 1.89 0 0 1-1.89-1.89z"/></svg><span>Log in with Steam</span></a>` +
    `</nav>`;
  document.body.prepend(head);

  const foot = document.createElement('footer');
  foot.innerHTML = `<span class="logo">12</span><span>Twelve Weeks is a free, non-commercial fan project. It is not made, endorsed or supported by Naughty Dog or Sony Interactive Entertainment.</span>`;
  document.body.append(foot);

  document.querySelectorAll('[data-link]').forEach((a) => {
    a.href = LINKS[a.dataset.link] || '#';
    if (/^https?:/.test(a.href) && !a.href.startsWith(location.origin)) {
      a.target = '_blank';
      a.rel = 'noopener';
    }
  });

  // home page: DOWNLOAD (hero button or nav) opens the hidden download panel under the hero and scrolls a little to it
  const dl = document.getElementById('download');
  const openDl = (smooth) => {
    if (!smooth) dl.classList.add('now');          // opened from a /#download link: no animation, land on it at once
    dl.classList.add('open'); dl.setAttribute('aria-hidden', 'false');
    const go = () => dl.scrollIntoView({ behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'instant', block: 'center' });
    if (smooth) setTimeout(go, 80); else { requestAnimationFrame(() => requestAnimationFrame(go)); addEventListener('load', go, { once: true }); }
  };
  if (dl) {
    document.addEventListener('click', (e) => {
      const a = e.target.closest('a[href="#download"], a[href="/#download"], a[data-dl-open]');
      if (!a) return;
      e.preventDefault(); openDl(true);
      if (location.hash !== '#download') history.replaceState(null, '', '#download');
    });
    if (location.hash === '#download') openDl(false);
  }

  const bar = head;
  if (page === 'home') {
    const onScroll = () => bar.classList.toggle('solid', scrollY > 40);
    addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }
  const menu = document.getElementById('menu'),
    nav = document.getElementById('nav');
  menu.addEventListener('click', () => menu.setAttribute('aria-expanded', nav.classList.toggle('open')));
  nav.addEventListener('click', (e) => { if (e.target.closest('a')) nav.classList.remove('open'); });

  // Steam session: show the player's name + log out instead of the login button.
  api('/api/me').then((me) => {
    if (!me.loggedIn) return;
    const l = document.getElementById('login');
    const name = (me.player && me.player.name) || 'My profile';
    l.outerHTML = `<a href="/player.html?id=${esc(me.id)}" class="login me${page === 'me' ? ' on' : ''}">${esc(name)}</a><a href="/auth/logout" class="logout">Log out</a>`;
  }).catch(() => {});

  // a section shows once its top is 12% into the screen: a ratio threshold never fired for a section taller than ~8 screens (the news list on a phone)
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('on'); io.unobserve(e.target); } }), { threshold: 0, rootMargin: '0px 0px -12% 0px' });
  document.querySelectorAll('.rv').forEach((el) => io.observe(el));
  window.revealNew = () => document.querySelectorAll('.rv:not(.on)').forEach((el) => io.observe(el));
})();

// News items: same sections as the launcher's news tab.
const NEWS_SECS = [['new', 'New'], ['changed', 'What changed'], ['why', 'Why'], ['watch', 'Watch out for'], ['known', 'Known issues'], ['fixed', 'Fixed']];
// 'big' = a milestone post (new map, big overhaul: site/news-big.json, set by the API); 'hotfix' = the author's hotfix kind; else a patch
function newsType(n) {
  return n.big ? 'big' : n.kind === 'hotfix' ? 'hotfix' : 'patch';
}
// Rich blocks, same as the launcher (0.1.25+): n.blocks = [{type:'heading',text} | {type:'text',md} | {type:'note',title,md} |
// {type:'media',items:[{src,caption}]} | {type:'stats',cols,rows:[{icon,name,values}]} | {type:'sections',sections:{..}}].
// A post with blocks shows only them (like the launcher); else its plain sections.
function newsMd(md) {
  const inline = (s) => esc(s).replace(/\*\*(.+?):\*\*/g, '<b>$1<i class="nb-c">:</i></b>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  return String(md || '').split(/\n{2,}/).map((par) => {
    const ls = par.split('\n').filter(Boolean);
    if (ls.length && ls.every((l) => /^- /.test(l))) return `<ul>${ls.map((l) => `<li${/^- \*\*[^*]+\*\*/.test(l) ? ' class="nb-lead"' : ''}>${inline(l.slice(2))}</li>`).join('')}</ul>`;
    return `<p>${ls.map(inline).join('<br>')}</p>`;
  }).join('');
}
function newsSections(secs) {
  return NEWS_SECS.filter(([k]) => Array.isArray(secs[k]) && secs[k].length)
    .map(([k, h]) => `<div class="nsec ${k}"><h4>${h}</h4><ul>${secs[k].map((l) => `<li>${esc(l)}</li>`).join('')}</ul></div>`).join('');
}
const NEWS_MEDIA_RE = /^(?:media\/)?([A-Za-z0-9_-][A-Za-z0-9_.-]{0,80}\.(gif|webp|png|jpe?g|mp4|webm))$/i;
function newsBlocks(blocks) {
  return blocks.filter((b) => b && typeof b === 'object').map((b) => {
    if (b.type === 'heading') return `<h3 class="nb-h">${esc(b.text)}</h3>`;
    if (b.type === 'text') return `<div class="nb-text">${newsMd(b.md)}</div>`;
    if (b.type === 'note') return `<div class="nb-note">${b.title ? `<div class="nb-note-t">${esc(b.title)}</div>` : ''}<div class="nb-text">${newsMd(b.md)}</div></div>`;
    if (b.type === 'sections') return newsSections(b.sections || {});
    if (b.type === 'media') {
      const its = (b.items || []).filter((it) => it && NEWS_MEDIA_RE.test(String(it.src || ''))).slice(0, 3);
      if (!its.length) return '';
      return `<div class="nb-media n${its.length}">${its.map((it) => {
        const f = 'assets/news/media/' + String(it.src).match(NEWS_MEDIA_RE)[1];
        const el = /\.(mp4|webm)$/i.test(f) ? `<video src="${f}" autoplay loop muted playsinline onerror="this.closest('figure').remove()"></video>` : `<img src="${f}" alt="" loading="lazy" onerror="this.closest('figure').remove()">`;
        return `<figure><div class="nb-frame">${el}</div>${it.caption ? `<figcaption>${esc(it.caption)}</figcaption>` : ''}</figure>`;
      }).join('')}</div>`;
    }
    if (b.type === 'stats') {
      const cols = Array.isArray(b.cols) ? b.cols : [], rows = Array.isArray(b.rows) ? b.rows : [];
      const head = `<div class="nb-srow nb-shead"><span class="nb-sico"></span><span class="nb-sname"></span>${cols.map((c) => `<span class="nb-sval">${esc(c)}</span>`).join('')}</div>`;
      return `<div class="nb-stats" style="--nc:${cols.length}">${head}${rows.map((r) => {
        const m = /^(?:[A-Za-z0-9_-]+\/)*([A-Za-z0-9_-]+\.png)$/.exec(r.icon || '');
        return `<div class="nb-srow"><span class="nb-sico">${m ? `<img src="assets/news/${m[1]}" alt="" draggable="false">` : ''}</span><span class="nb-sname">${esc(r.name)}</span>${(r.values || []).map((v, i) => `<span class="nb-sval" data-l="${esc(cols[i] || '')}">${esc(v)}</span>`).join('')}</div>`;
      }).join('')}</div>`;
    }
    return '';
  }).join('');
}
function newsCard(n, open) {
  const secs = n.sections || {};
  let body = Array.isArray(n.blocks) && n.blocks.length ? newsBlocks(n.blocks) : newsSections(secs);
  if (!body) body = `<div class="nsec"><p>${esc(n.body || n.text || '')}</p></div>`;
  const t = newsType(n);
  const tag = `<span class="nkind ${t}">${{ big: 'Big update', hotfix: 'Hotfix', patch: 'Patch' }[t]}</span>${n.build ? `<span class="nbuild">Build ${esc(n.build)}</span>` : ''}`;
  return `<details class="ncard ${t === 'big' ? 'big' : 'hot'}" data-id="${esc(n.id)}"${open ? ' open' : ''}><summary><span class="ntag">${tag}</span><span class="nhead">${esc(n.headline || n.title || '')}</span><time>${esc(n.date || '')}</time></summary><div class="nbody">${body}</div></details>`;
}
