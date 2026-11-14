// Rich news blocks (0.1.25): node test/news-blocks-test.js
// Old entries (sections only) render as before; blocks render headings / media / stats / text / sections; unsafe media names are dropped; PL blocks fall back to EN on a mismatch.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let fails = 0;
const ok = (c, m) => {
  console.log((c ? 'ok   ' : 'FAIL ') + m);
  if (!c) fails++;
};
const esc = (s) => String(s).replace(/[&<>"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m]);
const stubEl = { addEventListener() {}, querySelector() {}, querySelectorAll: () => [] };
const ctx = { I18N: { lang: 'en' }, T: (s) => s, esc, $: () => stubEl, $$: () => [], f2: {}, document: {}, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'src', 'app', 'news.js'), 'utf8') + '\nthis.newsItem = newsItem;', ctx);
const item = (n) => ctx.newsItem(n, 0, true);

const old = { id: 1, date: '2026-10-19', build: '76', headline: 'Old', sections: { changed: ['A line'], fixed: ['B line'] } };
let h = item(old);
ok(h.includes('<li>A line</li>') && h.includes('nsec changed') && !h.includes('nb-h'), 'old entry renders its sections');

const rich = {
  id: 2, build: '165', headline: 'Rich', sections: { changed: ['Fallback line'] },
  blocks: [
    { type: 'heading', text: 'MELEE DUELS' },
    { type: 'media', items: [{ src: 'media/a.gif', caption: 'One' }, { src: 'media/b.mp4', caption: 'Two' }, { src: 'http://evil/x.gif' }, { src: '../x.gif' }, { src: 'media/c.exe' }] },
    { type: 'text', md: 'Intro line\n\n- **Duel:** first hit\n- plain item' },
    { type: 'stats', cols: ['DAMAGE'], rows: [{ icon: 'melee/crowbar.png', name: 'Crowbar', values: ['20'] }, { icon: '../../x.png', name: 'Bad', values: ['1'] }] },
    { type: 'sections', sections: { fixed: ['Inside blocks'] } },
    { type: 'nonsense' },
  ],
};
h = item(rich);
ok(h.includes('<h3 class="nb-h">MELEE DUELS</h3>'), 'heading block');
ok(h.includes('nb-media n2') && h.includes('data-src="media/a.gif"') && h.includes('data-src="media/b.mp4"'), 'two valid media items side by side');
ok(!h.includes('evil') && !h.includes('../x.gif') && !h.includes('c.exe'), 'unsafe media names dropped');
ok(h.includes('<li class="nb-lead"><b>Duel<i class="nb-c">:</i></b> first hit</li>') && h.includes('<li>plain item</li>') && h.includes('<p>Intro line</p>'), 'text block: paragraph, lead list item, plain list item');
ok(h.includes('assets/icons/melee/crowbar.png') && !h.includes('x.png'), 'stats row icon, bad icon path dropped');
ok(h.includes('Inside blocks') && !h.includes('Fallback line'), 'blocks replace the sections list (sections block inside)');

ctx.I18N.lang = 'pl';
const pl = JSON.parse(JSON.stringify(rich));
pl.pl = { headline: 'Bogaty', blocks: [{ type: 'heading', text: 'POJEDYNKI' }, { type: 'media', items: [{ caption: 'Raz' }, { caption: 'Dwa' }, {}, {}, {}] }, { type: 'text', md: 'Wstęp' }, { type: 'stats', cols: ['OBRAŻENIA'], rows: [{ name: 'Łom', values: ['20'] }, { name: 'Zły', values: ['1'] }] }, { type: 'sections', sections: { fixed: ['W blokach'] } }, { type: 'nonsense' }] };
h = item(pl);
ok(h.includes('POJEDYNKI') && h.includes('Raz') && h.includes('data-src="media/a.gif"') && h.includes('assets/icons/melee/crowbar.png') && h.includes('Łom'), 'PL blocks: translated text, English media src and icon kept');
pl.pl.blocks.pop();
h = item(pl);
ok(h.includes('MELEE DUELS') && !h.includes('POJEDYNKI'), 'PL blocks with a different length fall back to English');

console.log(fails ? `\n${fails} failure(s)` : '\nall ok');
process.exit(fails ? 1 : 0);
