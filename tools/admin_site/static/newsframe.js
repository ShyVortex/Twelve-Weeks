"use strict";
// Admin PATCH NOTES: the launcher's own news.js renders every entry (newsItem / newsL / newsTag, NEWS_SECS, its accordion click handler); this file only
// makes that rendered text editable in place and loads / saves /api/news (validation, backup and atomic write stay on the server).
(() => {
  const ST = { entries: [], saved: "", lang: "en" };
  const list = document.getElementById("news-list");
  const KEYS = NEWS_SECS.map(([k]) => k);
  const hdrOf = (k) => (NEWS_SECS.find((s) => s[0] === k) || [k, k.toUpperCase()])[1];
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const parentApi = () => { try { return window.parent !== window ? window.parent : null; } catch (e) { return null; } };
  const flash = (m, bad) => { const p = parentApi(); if (p && p.flash) p.flash(m, bad); else console.log(m); };

  // ---- model helpers
  function clean(entries) {      // what gets saved / compared: no empty lines, no empty sections (the server does the same)
    return entries.map((e) => {
      const c = clone(e), fix = (s) => { for (const k of Object.keys(s || {})) { s[k] = (s[k] || []).filter((x) => String(x).trim()); if (!s[k].length) delete s[k]; } };
      fix(c.sections); if (c.pl) fix(c.pl.sections);
      return c;
    });
  }
  const sig = () => JSON.stringify(clean(ST.entries));
  function dirtyUi() { const d = sig() !== ST.saved, el = document.getElementById("dirty"); el.textContent = d ? "UNSAVED CHANGES" : "SAVED"; el.className = d ? "" : "clean"; }
  const byId = (id) => ST.entries.find((e) => String(e.id) === String(id));
  function lines(e, k) {         // lines in the shown language (a missing PL section falls back to EN, exactly like the launcher)
    const en = (e.sections || {})[k] || [], pl = ((e.pl || {}).sections || {})[k];
    return ST.lang === "pl" && Array.isArray(pl) && pl.length ? pl : en;
  }
  function arr(e, k) {           // the array to edit; the first edit of a fallback PL section starts it from the English lines
    if (ST.lang === "en") { e.sections = e.sections || {}; return (e.sections[k] = e.sections[k] || []); }
    e.pl = e.pl || {}; e.pl.sections = e.pl.sections || {};
    const cur = e.pl.sections[k];
    if (!Array.isArray(cur) || !cur.length) e.pl.sections[k] = ((e.sections || {})[k] || []).slice();
    return e.pl.sections[k];
  }
  function setHeadline(e, t) { if (ST.lang === "en") e.headline = t; else { e.pl = e.pl || {}; e.pl.headline = t; } }
  const headlineFb = (e) => ST.lang === "pl" && !((e.pl || {}).headline);

  // ---- rendering (launcher renderer + editing decoration)
  function ce(el) { el.contentEditable = "plaintext-only"; if (el.contentEditable !== "plaintext-only") el.contentEditable = "true"; el.spellcheck = false; }
  function articleHtml(e, i) {
    const v = newsL(e), d = Object.assign({}, e); delete d.pl;      // d has the shown language already resolved, so newsItem's own newsL passes it through
    d.headline = v.headline || ""; d.title = v.title; d.sections = {};
    for (const k of KEYS) { const l = lines(e, k); d.sections[k] = l.length ? l : [""]; }
    return newsItem(d, i, true);
  }
  function decorate(art, e) {
    const row = art.querySelector("button.nrow");
    if (row) { const div = document.createElement("div"); div.className = row.className; div.setAttribute("role", "button"); div.dataset.snd = "click"; while (row.firstChild) div.appendChild(row.firstChild); row.replaceWith(div); }
    const h = art.querySelector(".nhead"); ce(h); h.dataset.f = "headline"; h.classList.toggle("fb", headlineFb(e));
    const inner = art.querySelector(".ndet-in");
    const strip = document.createElement("div"); strip.className = "medit";
    strip.innerHTML = `<label>ID<input value="#${esc(e.id)}" disabled style="width:54px"></label><label>DATE<input class="m-date" data-m="date" value="${esc(e.date || "")}" placeholder="YYYY-MM-DD"></label>` +
      `<label>BUILD<input class="m-build" data-m="build" value="${esc(e.build || "")}"></label><label>KIND<select data-m="kind"><option value="build"${e.kind === "hotfix" ? "" : " selected"}>build</option><option value="hotfix"${e.kind === "hotfix" ? " selected" : ""}>hotfix</option></select></label>` +
      `<label>STAMP<input class="m-stamp" data-m="stamp" value="${esc(e.stamp || "")}"></label><span class="sp"></span><button class="tbtn danger" data-del>DELETE ENTRY</button>`;
    inner.prepend(strip);
    const secs = {};
    art.querySelectorAll(".nsec").forEach((s) => { const k = KEYS.find((x) => s.classList.contains(x)); if (k) secs[k] = s; });
    for (const k of KEYS) {
      let s = secs[k];
      if (!s) { s = document.createElement("div"); s.className = "nsec " + k; s.innerHTML = `<h4>${esc(T(hdrOf(k)))}</h4><ul></ul>`; inner.appendChild(s); }
      decorateSec(s, e, k);
    }
    const extra = new Set(Object.keys(e.sections || {}).concat(Object.keys((e.pl || {}).sections || {})).filter((k) => !KEYS.includes(k)));
    for (const k of extra) {      // sections the launcher has no heading for: kept and flagged
      const s = document.createElement("div"); s.className = "nsec extra"; s.innerHTML = `<h4>${esc(k.toUpperCase())} - NOT SHOWN IN THE LAUNCHER (it has no heading for this section)</h4><ul></ul>`;
      inner.appendChild(s); decorateSec(s, e, k);
    }
    return art;
  }
  function decorateSec(s, e, k) {
    s.dataset.sec = k;
    const ul = s.querySelector("ul"), ls = lines(e, k), en = (e.sections || {})[k] || [];
    ul.innerHTML = "";
    (ls.length ? ls : [""]).forEach((t, i) => { const li = document.createElement("li"); li.textContent = t; ce(li); li.dataset.sec = k; li.dataset.i = i; li.classList.toggle("fb", ST.lang === "pl" && t !== "" && t === en[i]); ul.appendChild(li); });
    s.classList.toggle("empty", !ls.length);
    const b = document.createElement("button"); b.className = "nadd"; b.dataset.add = k; b.title = "Add a line"; b.textContent = "+"; s.appendChild(b);
  }
  function renderEntry(id, focus) {
    const old = list.querySelector(`.nitem[data-key="${CSS.escape(String(id))}"]`), e = byId(id);
    if (!old || !e) return null;
    const t = document.createElement("div"); t.innerHTML = articleHtml(e, 0);
    const art = decorate(t.firstElementChild, e); art.style.animation = "none";
    old.replaceWith(art);
    if (focus) focusEl(art, focus.sel, focus.pos);
    return art;
  }
  function renderAll() {
    I18N.setLang(ST.lang);
    if (!ST.entries.length) { list.innerHTML = '<div class="empty">Nothing yet - press NEW ENTRY.</div>'; dirtyUi(); return; }
    list.innerHTML = "";
    ST.entries.forEach((e, i) => { const t = document.createElement("div"); t.innerHTML = articleHtml(e, i); list.appendChild(decorate(t.firstElementChild, e)); });
    const h = document.createElement("div"); h.className = "help";
    h.textContent = "Click an entry to open it, then click any text to edit it. ENTER = new line below, BACKSPACE on an empty line removes it, hover a section and press + to add a line. Adding or removing lines changes the shown language only. Paste is plain text. Dimmed italic text is what players get from the English version.";
    list.appendChild(h);
    dirtyUi();
  }
  function put(el, pos) {      // caret into an editable element (pos < 0 = end)
    el.focus();
    const n = el.firstChild; if (!n) return;
    const r = document.createRange(); r.setStart(n, pos < 0 ? n.textContent.length : Math.min(pos, n.textContent.length)); r.collapse(true);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  }
  function focusEl(art, sel, pos) { const el = art.querySelector(sel); if (el) put(el, pos); }
  const liSel = (k, i) => `li[data-sec="${CSS.escape(k)}"][data-i="${i}"]`;
  function caret(el) { const s = getSelection(); if (!s.rangeCount || !el.contains(s.anchorNode)) return 0; const r = s.getRangeAt(0).cloneRange(); r.selectNodeContents(el); r.setEnd(s.anchorNode, s.anchorOffset); return r.toString().length; }
  const textOf = (el) => el.textContent.replace(/\r?\n/g, " ");

  // ---- events
  list.addEventListener("click", (ev) => {
    const t = ev.target, art = t.closest(".nitem"); if (!art) return;
    const e = byId(art.dataset.key); if (!e) return;
    const add = t.closest("[data-add]");
    if (add) { const k = add.dataset.add, a = arr(e, k); a.push(""); renderEntry(e.id, { sel: liSel(k, a.length - 1), pos: 0 }); dirtyUi(); return; }
    if (t.closest("[data-del]")) del(e);
  });
  list.addEventListener("click", (ev) => { if (ev.target.closest(".nhead") && ev.target.closest(".nitem.open")) ev.stopPropagation(); }, true);      // typing in an opened headline must not fold the entry
  async function del(e) {
    const p = parentApi();
    const ok = p && p.confirmBox ? await p.confirmBox("DELETE ENTRY", `Delete patch notes entry <b>#${esc(e.id)}</b> (${esc(e.headline || e.title || "no headline")})?<br>It disappears from the launcher news after you SAVE TO LIVE.`, "DELETE", true) : confirm("Delete this entry?");
    if (!ok) return;
    ST.entries = ST.entries.filter((x) => x !== e); newsOpen = null; renderAll();
  }
  list.addEventListener("input", (ev) => {
    const t = ev.target, art = t.closest(".nitem"), e = art && byId(art.dataset.key); if (!e) return;
    if (t.dataset.m) {
      e[t.dataset.m] = t.value;
      const row = art.querySelector(".nrow"); row.querySelector(".ntag").innerHTML = newsTag(e); row.querySelector("time").textContent = e.date || ""; art.classList.toggle("hot", e.kind === "hotfix");
    } else if (t.dataset.f === "headline") { setHeadline(e, textOf(t)); t.classList.remove("fb"); }
    else if (t.matches("li[data-sec]")) {
      const k = t.dataset.sec, i = +t.dataset.i, a = arr(e, k); while (a.length <= i) a.push("");
      a[i] = textOf(t); const en = (e.sections || {})[k] || []; t.classList.toggle("fb", ST.lang === "pl" && a[i] !== "" && a[i] === en[i]);
      t.closest(".nsec").classList.remove("empty");
    } else return;
    dirtyUi();
  });
  list.addEventListener("keydown", (ev) => {
    const t = ev.target, art = t.closest && t.closest(".nitem"), e = art && byId(art.dataset.key);
    if (!e || !t.isContentEditable) return;
    const eds = Array.from(art.querySelectorAll("[contenteditable]")), at = eds.indexOf(t), pos = caret(t), len = t.textContent.length;
    if (ev.key === "Enter") {
      ev.preventDefault();
      if (t.dataset.f === "headline") return put(eds[1], 0);
      const k = t.dataset.sec, i = +t.dataset.i, a = arr(e, k), txt = textOf(t);
      a[i] = txt.slice(0, pos); a.splice(i + 1, 0, txt.slice(pos));
      renderEntry(e.id, { sel: liSel(k, i + 1), pos: 0 }); dirtyUi();
    } else if (ev.key === "Backspace" && t.matches("li[data-sec]") && !t.textContent) {
      ev.preventDefault();
      const k = t.dataset.sec, i = +t.dataset.i, a = arr(e, k);
      if (!a.length) return;      // the placeholder line of an empty section
      a.splice(i, 1);
      const na = renderEntry(e.id, null), ed = Array.from(na.querySelectorAll("[contenteditable]"));
      if (i === 0 && a.length) put(ed[at], 0); else put(ed[at - 1], -1);
      dirtyUi();
    } else if (ev.key === "ArrowUp" && pos === 0 && eds[at - 1]) { ev.preventDefault(); put(eds[at - 1], -1); }
    else if (ev.key === "ArrowDown" && pos === len && eds[at + 1]) { ev.preventDefault(); put(eds[at + 1], 0); }
  });
  list.addEventListener("paste", (ev) => {
    const t = ev.target; if (!t.isContentEditable) return;
    ev.preventDefault();
    const raw = (ev.clipboardData || window.clipboardData).getData("text/plain") || "";
    const ls = raw.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    if (!ls.length) return;
    const isH = t.dataset.f === "headline";
    document.execCommand("insertText", false, isH ? ls.join(" ") : ls[0]);
    if (isH || ls.length < 2) return;
    const art = t.closest(".nitem"), e = byId(art.dataset.key), k = t.dataset.sec, i = +t.dataset.i, a = arr(e, k);
    a.splice(i + 1, 0, ...ls.slice(1));
    renderEntry(e.id, { sel: liSel(k, i + ls.length - 1), pos: -1 }); dirtyUi();
  });

  // ---- toolbar
  document.getElementById("lang").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-l]"); if (!b || b.dataset.l === ST.lang) return;
    ST.lang = b.dataset.l; document.querySelectorAll("#lang button").forEach((x) => x.classList.toggle("on", x === b));
    const sc = list.scrollTop; renderAll(); list.scrollTop = sc;
  });
  document.getElementById("bnew").addEventListener("click", () => {
    const d = new Date(), p2 = (n) => String(n).padStart(2, "0");
    const e = { id: Math.max(0, ...ST.entries.map((x) => x.id)) + 1, date: `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`, build: "", kind: "build", stamp: "", headline: "", sections: {}, pl: { headline: "", sections: {} } };
    ST.entries.unshift(e); newsOpen = String(e.id); renderAll(); list.scrollTop = 0;
    const art = list.querySelector(".nitem"); if (art) focusEl(art, ".nhead", 0);
  });
  document.getElementById("bsave").addEventListener("click", async () => {
    const btn = document.getElementById("bsave"); btn.disabled = true;
    try {
      const r = await (await fetch("/api/news", { method: "POST", headers: { "X-Admin-Request": "1", "Content-Type": "application/json" }, body: JSON.stringify({ entries: clean(ST.entries) }) })).json();
      flash(r.ok ? `Patch notes saved - live now (${r.count} entries${r.backup ? ", backup " + r.backup : ""})` : "Save failed: " + (r.error || "unknown"), !r.ok);
      if (r.ok) { ST.entries = r.entries; ST.saved = sig(); const sc = list.scrollTop; renderAll(); list.scrollTop = sc; }
    } catch (e) { flash("Save failed: " + e.message, true); }
    btn.disabled = false;
  });
  window.addEventListener("beforeunload", (e) => { if (sig() !== ST.saved) { e.preventDefault(); e.returnValue = ""; } });

  async function load() {
    I18N.load({}); try { I18N.load(await (await fetch("/launcher/src/i18n/pl.json")).json()); } catch (e) { /* English shows */ }
    let d; try { d = await (await fetch("/api/news", { cache: "no-store" })).json(); } catch (e) { d = { ok: false, error: String(e) }; }
    if (!d.ok) { list.innerHTML = `<div class="empty">${esc(d.error || "news unavailable")}</div>`; document.getElementById("bnew").disabled = document.getElementById("bsave").disabled = true; return; }
    ST.entries = d.entries; ST.saved = sig();
    if (ST.entries[0]) newsOpen = String(ST.entries[0].id);
    renderAll();
    setTimeout(() => list.classList.add("still"), 900);
  }
  window.NewsEd = { dirty: () => sig() !== ST.saved, state: ST };
  load();
})();
