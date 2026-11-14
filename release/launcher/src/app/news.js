/**
 * @file Renderer news list, seen-state and about panel.
 */
'use strict';

// ---------------------------------------------------------------- news
let newsOk = false,
  newsBusy = null,
  newsSig = '',
  newsOpen = null;
const NEWS_SECS = [
  ['changed', 'WHAT CHANGED'],
  ['why', 'WHY'],
  ['watch', 'WATCH OUT FOR'],
  ['known', 'KNOWN ISSUES'],
  ['fixed', 'FIXED'],
];
// Localized copy: entry.<code> = {headline, sections, title, body} (entry.pl for Polish, entry.es for Spanish, ...; entry.locales.<code> is read too), used when the launcher
// language is that language, per field (a missing field falls back to English; old launchers ignore the block)
/**
 * The localized block of a news entry for a language code, or null.
 * @param {object} n
 * @param {string} lang
 * @returns {object|null}
 */
function newsLocale(n, lang) {
  if (!lang || lang === 'en') return null;
  const own = (o, k) =>
    o && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k) && o[k] && typeof o[k] === 'object' ? o[k] : null;
  return own(n, lang) || own(n.locales, lang);
}
/**
 * Normalize a news item's localized fields.
 * @param {object} n
 * @returns {object}
 */
function newsL(n) {
  const p = newsLocale(n, I18N.lang);
  const g = (k) => (p && p[k] ? p[k] : n[k]);
  const ps = p && p.sections && typeof p.sections === 'object' ? p.sections : {};
  const es = n.sections || {};
  const sections = {};
  for (const k of Object.keys(es))
    sections[k] = Array.isArray(ps[k]) && ps[k].length ? ps[k] : es[k];
  return {
    headline: g('headline'),
    title: g('title'),
    body: p && p.body ? p.body : n.body || n.text,
    sections,
    blocks: newsBlocksL(n, p),
  };
}
// Rich blocks (0.1.25+): entry.blocks = [{type:'heading',text} | {type:'text',md} | {type:'media',items:[{src,caption}]} |
// {type:'stats',cols:[..],rows:[{icon,name,values:[..]}]} | {type:'sections',sections:{changed:[..],..}}]. Polish: pl.blocks, the same
// list translated (same length and types, media src / icons are taken from the English block); a mismatch falls back to English.
// Older launchers ignore blocks and show entry.sections.
function newsBlocksL(n, p) {
  const en = Array.isArray(n.blocks) ? n.blocks.filter((b) => b && typeof b === 'object') : [];
  if (!en.length) return [];
  const pl = p && Array.isArray(p.blocks) ? p.blocks : null;
  if (!pl || pl.length !== en.length || pl.some((b, i) => !b || b.type !== en[i].type)) return en;
  return en.map((b, i) =>
    Object.assign({}, b, pl[i], {
      src: undefined,
      items: mergeItems(b, pl[i]),
      rows: mergeRows(b, pl[i]),
    }),
  );
}
function mergeItems(b, q) {
  if (!Array.isArray(b.items)) return undefined;
  return b.items.map((it, i) =>
    Object.assign({}, it, (q.items || [])[i] && { caption: q.items[i].caption || it.caption }),
  );
}
function mergeRows(b, q) {
  if (!Array.isArray(b.rows)) return undefined;
  return b.rows.map((r, i) =>
    Object.assign(
      {},
      r,
      (q.rows || [])[i] && { name: q.rows[i].name || r.name, values: q.rows[i].values || r.values },
    ),
  );
}
/**
 * Tiny text formatter for text blocks: blank line = paragraph, lines starting with "- " = list, **bold**. Everything is escaped first.
 * @param {string} md
 * @returns {string}
 */
function newsMd(md) {
  // "**Lead:** text" -> <b>Lead<i class="nb-c">:</i></b> text; a list line that starts with such a lead gets class "nb-lead" (the label column)
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?):\*\*/g, '<b>$1<i class="nb-c">:</i></b>')
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  return String(md || '')
    .split(/\n{2,}/)
    .map((par) => {
      const ls = par.split('\n').filter(Boolean);
      if (ls.length && ls.every((l) => /^- /.test(l)))
        return `<ul>${ls.map((l) => `<li${/^- \*\*[^*]+\*\*/.test(l) ? ' class="nb-lead"' : ''}>${inline(l.slice(2))}</li>`).join('')}</ul>`;
      return `<p>${ls.map(inline).join('<br>')}</p>`;
    })
    .join('');
}
const NEWS_MEDIA_RE =
  /^(?:media\/)?[A-Za-z0-9_-][A-Za-z0-9_.-]{0,80}\.(gif|webp|png|jpe?g|mp4|webm)$/i;
function newsSections(secs) {
  return NEWS_SECS.filter(([k]) => Array.isArray(secs[k]) && secs[k].length)
    .map(
      ([k, h]) =>
        `<div class="nsec ${k}"><h4>${T(h)}</h4><ul>${secs[k].map((l) => `<li>${esc(l)}</li>`).join('')}</ul></div>`,
    )
    .join('');
}
/**
 * Render the rich blocks of one news entry.
 * @param {object[]} blocks
 * @returns {string}
 */
function newsBlocksHtml(blocks) {
  return blocks
    .map((b) => {
      if (b.type === 'heading') return `<h3 class="nb-h">${esc(b.text)}</h3>`;
      if (b.type === 'text') return `<div class="nb-text">${newsMd(b.md)}</div>`;
      if (b.type === 'note')
        return `<div class="nb-note">${b.title ? `<div class="nb-note-t">${esc(b.title)}</div>` : ''}<div class="nb-text">${newsMd(b.md)}</div></div>`;
      if (b.type === 'sections') return newsSections(b.sections || {});
      if (b.type === 'media') {
        const its = (b.items || [])
          .filter((it) => it && NEWS_MEDIA_RE.test(String(it.src || '')))
          .slice(0, 3);
        if (!its.length) return '';
        return (
          `<div class="nb-media n${its.length}">` +
          its
            .map(
              (it) =>
                `<figure><div class="nb-frame" data-src="${esc(it.src)}"><i class="nb-ph"></i></div>${it.caption ? `<figcaption>${esc(it.caption)}</figcaption>` : ''}</figure>`,
            )
            .join('') +
          `</div>`
        );
      }
      if (b.type === 'stats') {
        const cols = Array.isArray(b.cols) ? b.cols : [];
        const rows = Array.isArray(b.rows) ? b.rows : [];
        const head = `<div class="nb-srow nb-shead"><span class="nb-sico"></span><span class="nb-sname"></span>${cols.map((c) => `<span class="nb-sval">${esc(c)}</span>`).join('')}</div>`;
        return (
          `<div class="nb-stats" style="--nc:${cols.length}">${head}` +
          rows
            .map((r) => {
              const ic = /^[A-Za-z0-9_/-]+\.png$/.test(r.icon || '')
                ? `<img src="../assets/icons/${esc(r.icon)}" alt="" draggable="false">`
                : '';
              return `<div class="nb-srow"><span class="nb-sico">${ic}</span><span class="nb-sname">${esc(r.name)}</span>${(r.values || []).map((v) => `<span class="nb-sval">${esc(v)}</span>`).join('')}</div>`;
            })
            .join('') +
          `</div>`
        );
      }
      return '';
    })
    .join('');
}
const mediaCache = new Map();
/**
 * Fetch the media frames of an opened entry (lazy: nothing is requested while the entry is closed).
 * @param {Element} root
 * @returns {void}
 */
function newsLoadMedia(root) {
  root.querySelectorAll('.nb-frame:not([data-state])').forEach((fr) => {
    fr.dataset.state = 'loading';
    const src = fr.dataset.src;
    if (!mediaCache.has(src))
      mediaCache.set(
        src,
        f2.newsMedia(src).catch((e) => ({ ok: false, error: e.message })),
      );
    mediaCache.get(src).then((r) => {
      if (!r || !r.ok) {
        fr.dataset.state = 'missing';
        mediaCache.delete(src);
        return;
      }
      fr.dataset.state = 'ready';
      const el = document.createElement(r.video ? 'video' : 'img');
      if (r.video)
        Object.assign(el, { autoplay: true, loop: true, muted: true, playsInline: true });
      else el.alt = '';
      el.draggable = false;
      el.src = r.uri;
      fr.replaceChildren(el);
    });
  });
}
/**
 * Render the news item's category tag.
 * @param {object} n
 * @returns {string}
 */
function newsTag(n) {
  const b = n.build
    ? `${T('BUILD')} ${esc(n.build)}${n.kind === 'hotfix' ? ' ' + T('HOTFIX') : ''}`
    : esc(n.version || '');
  return n.stamp ? `${b} | ${esc(n.stamp)}` : b;
}
/**
 * Render one news list item.
 * @param {object} n0
 * @param {number} i
 * @param {boolean} seen
 * @returns {string}
 */
function newsItem(n0, i, seen) {
  const n = Object.assign({}, n0, newsL(n0)),
    secs = n.sections || {};
  let body = n.blocks && n.blocks.length ? newsBlocksHtml(n.blocks) : newsSections(secs);
  if (!body) body = `<div class="nsec"><p>${esc(n.body || n.text || '')}</p></div>`; // old schema {title, body|text}
  const key = String(n0.id != null ? n0.id : (n0.date || '') + (n0.title || ''));
  return (
    `<article class="nitem${n.kind === 'hotfix' ? ' hot' : ''}${newsOpen === key ? ' open' : ''}" data-key="${esc(key)}" style="animation-delay:${i * 0.05}s">` +
    `<button class="nrow" data-snd="click"><span class="ntag">${newsTag(n)}</span><span class="nhead">${esc(n.headline || n.title || '')}</span>${seen ? '' : `<u class="nnew">${T('NEW')}</u>`}<time>${esc(n.date || '')}</time></button>` +
    `<div class="ndet"><div class="ndet-in">${body}</div></div></article>`
  );
}
// news must load whenever the tab opens while empty / failed, and on the periodic check (it was fetched once at startup only)
/**
 * Load and render the news list.
 * @param {boolean} [force]
 * @returns {Promise<void>}
 */
async function loadNews(force) {
  if (newsBusy) return newsBusy;
  if (newsOk && !force) return;
  return (newsBusy = (async () => {
    let r;
    try {
      r = await f2.news();
    } catch (e) {
      r = { ok: false, error: e.message };
    }
    const el = $('news-list');
    newsBusy = null;
    const items = r && r.ok && Array.isArray(r.items) ? r.items : [];
    if (!items.length) {
      newsOk = false;
      if (!el.querySelector('.nitem'))
        el.innerHTML = `<div class="empty">${r && r.error ? T('Could not load news: {e}', { e: esc(r.error) }) : T('Nothing new.')}</div>`;
      return;
    }
    newsOk = true;
    let last = '';
    try {
      last = localStorage.getItem('f2-news') || '';
    } catch {}
    const idOf = (n) => String(n.id != null ? n.id : n.date || n.title);
    const lastId = items.findIndex((n) => idOf(n) === last); // items newer than the last seen one are NEW (list is newest first)
    const sig = JSON.stringify(items);
    if (sig !== newsSig) {
      newsSig = sig;
      el.innerHTML = items
        .map((n, i) => newsItem(n, i, lastId >= 0 ? i >= lastId : i > 0))
        .join('');
    }
    const n0 = items[0];
    $('nw-title').textContent =
      (n0.build ? newsTag(n0) + '  ' : '') + (newsL(n0).headline || newsL(n0).title || '');
    $('nw-line').textContent = n0.date || '';
    if (curView === 'news') {
      try {
        localStorage.setItem('f2-news', idOf(n0));
      } catch {}
      $('news-pip').hidden = true;
    } else if (idOf(n0) !== last) $('news-pip').hidden = false;
  })());
}
$('news-list').addEventListener('click', (e) => {
  const row = e.target.closest('.nrow');
  if (!row) return;
  const it = row.parentElement,
    open = !it.classList.contains('open');
  $$('#news-list .nitem.open').forEach((x) => x.classList.remove('open'));
  it.classList.toggle('open', open);
  newsOpen = open ? it.dataset.key : null;
  const nw = it.querySelector('.nnew');
  if (nw) nw.remove();
  if (open) newsLoadMedia(it);
  if (open) setTimeout(() => it.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 120);
});
/**
 * Persist the newest news id as seen.
 * @returns {void}
 */
function markNewsSeen() {
  try {
    const f = $('news-list').querySelector('.nitem');
    if (f && newsSig) {
      const it = JSON.parse(newsSig)[0];
      localStorage.setItem('f2-news', String(it.id != null ? it.id : it.date || it.title));
    }
  } catch {}
}
/**
 * Load and render the About panel.
 * @returns {Promise<void>}
 */
async function loadAbout() {
  const i = await f2.info();
  $('ver').textContent = 'v' + i.version;
  $('ab-ver').textContent = i.version;
  $('ab-date').textContent = i.buildDate || '--';
  $('ab-el').textContent = i.electron;
  $('ab-os').textContent = `${i.hardware.os} ${i.hardware.arch}`;
  $('ab-cpu').textContent = `${i.hardware.cpu} (${T('{n} threads', { n: i.hardware.cores })})`;
  $('ab-ram').textContent = i.hardware.ram + ' GB';
  $('ab-data').textContent = i.userData;
}
