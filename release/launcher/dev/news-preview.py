#!/usr/bin/env python3
"""Static preview of one news entry with the launcher's real CSS and news.js (no Electron):
    python dev/news-preview.py entry.json out.html [en|pl] [a|b|c]
Media frames stay as placeholders (captions only). Screenshot it with headless Chrome (re/news165/README)."""
import json, os, pathlib, sys

D = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(D, '..', 'src')
entry = json.load(open(sys.argv[1], encoding='utf-8-sig'))
lang = sys.argv[3] if len(sys.argv) > 3 else 'en'
variant = sys.argv[4] if len(sys.argv) > 4 else 'a'   # a = shipped CSS; b / c = dev/news-variants.css
css = ''.join('<link rel="stylesheet" href="%s">' % pathlib.Path(os.path.abspath(os.path.join(SRC, f))).as_uri()
              for f in ['style.css', 'gear.css', 'neat.css', 'news.css'])
css += '<link rel="stylesheet" href="%s">' % pathlib.Path(os.path.join(D, 'news-variants.css')).as_uri()
js = open(os.path.join(SRC, 'app', 'news.js'), encoding='utf8').read()
html = '''<!doctype html><html><head><meta charset="utf-8"><base href="%s/">%s
<style>*{animation:none!important;transition:none!important}.nitem{opacity:1!important}html,body{height:auto;overflow:visible}body{background:#070808}
#app{position:relative;width:1100px;margin:0 auto;padding:16px}
.view{position:relative!important;left:auto!important;right:auto!important;top:auto!important;bottom:auto!important;display:block!important;opacity:1!important;transform:none!important;visibility:visible!important}
.news{overflow:visible!important}.nb-frame::after{content:attr(data-src);position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;letter-spacing:.2em;color:#4b4a44}</style></head>
<body class="v%s"><div id="app"><section class="view active" id="v-news"><h2>NEWS</h2><div class="news" id="news-list"></div></section></div>
<script>
const I18N={lang:%s,T:(s)=>s};const T=(s)=>s;
const esc=(s)=>String(s).replace(/[&<>"]/g,(m)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const $=(i)=>document.getElementById(i);const $$=(s)=>document.querySelectorAll(s);
const f2={newsMedia:()=>new Promise(()=>{})};let curView='news';
%s
const E=%s;newsOpen=String(E.id);
$('news-list').innerHTML=newsItem(E,0,true)+newsItem({id:45,date:'2026-11-04',build:'164',kind:'hotfix',stamp:'b316b239',headline:'Fewer drops after losing the host, two crash fixes',sections:{fixed:['(older entry)']}},1,true);
</script></body></html>''' % (pathlib.Path(os.path.abspath(SRC)).as_uri(), css, variant, json.dumps(lang), js, json.dumps(entry, ensure_ascii=False))
open(sys.argv[2], 'w', encoding='utf8').write(html)
