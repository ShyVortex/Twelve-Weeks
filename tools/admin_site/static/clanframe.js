"use strict";
// Admin CLAN page: runs the launcher's own clan.js against /api/clanview (read-only) through the same `f2` calls the launcher's preload gives it.
// The launcher renders one long scroll; here its sections are put under four tabs (OVERVIEW / SURVIVORS / RAIDS / JOURNAL).
(() => {
  const qs = new URLSearchParams(location.search), id = qs.get("id") || "";
  let lang = qs.get("lang") === "pl" ? "pl" : "en", tab = qs.get("tab") || "overview", data = null;
  const f2 = { log(m) { const d = document.createElement("pre"); d.id = "clog"; d.hidden = true; d.textContent = m; document.body.appendChild(d); }, clan: async () => (data.clan && data.clan.ok === false ? { ok: false, error: data.clan.error } : { ok: true, clan: data.clan }),
    clanFeed: async () => ({ ok: true, feed: data.feed }) };
  window.f2 = f2; window.Scenes = { setFaction() {} };
  async function dict() {
    I18N.load({}); I18N.setLang(lang);
    if (lang !== "pl") return;
    for (const f of ["pl", "game-pl"]) { try { I18N.load(await (await fetch(`/launcher/src/i18n/${f}.json`)).json()); } catch (e) { /* English shows */ } }
  }
  function sections() {      // mark the launcher's blocks with the tab they belong to
    const b = document.getElementById("clan-body"), set = (el, t) => { el.dataset.ct = t; };
    for (const el of b.children) {
      if (el.classList.contains("camp")) {
        for (const c of el.children) set(c, c.classList.contains("roster") ? "survivors" : c.classList.contains("matches") ? "raids" : c.classList.contains("jrnl") ? "journal" : "overview");
        el.dataset.ct = "";           // the container itself always shows (its children are filtered)
        el.classList.add("ct-on");
      } else set(el, "overview");
    }
  }
  function show(t, opts = {}) {
    tab = t;
    document.querySelectorAll("#ctabs [data-ct]").forEach((b) => b.classList.toggle("on", b.dataset.ct === t));
    document.querySelectorAll("#clan-body [data-ct]").forEach((e) => e.classList.toggle("ct-on", e.dataset.ct === t || e.dataset.ct === ""));
    const b = document.getElementById("clan-body");
    if (opts.play) parent.postMessage({ clanTab: t }, location.origin);      // the admin page brings the frame's top into view
    const old = document.getElementById("cnone"); if (old) old.remove();
    if (b.querySelector(".clan-top") && !b.querySelector(`[data-ct="${t}"]`)) {     // the launcher draws nothing for a part the server has no data for yet
      const n = document.createElement("div"); n.className = "empty"; n.id = "cnone"; n.dataset.ct = t; n.classList.add("ct-on");
      n.textContent = T({ survivors: "No survivor list for this clan yet.", raids: "No raids logged for this clan yet.", journal: "Nothing in the journal yet." }[t] || "Nothing here yet.");
      b.appendChild(n);
    }
    if (opts.play) try { Fx.play(b); } catch (e) { /* motion is a nicety */ }
  }
  async function load() {
    await dict();
    L10N.apply();
    document.querySelectorAll("#ctabs [data-ct]").forEach((b) => { b.textContent = T(b.dataset.ct.toUpperCase()); });
    document.getElementById("c-lang").textContent = lang === "pl" ? "EN" : "PL";
    let d;
    try { d = await (await fetch(`/api/clanview?id=${encodeURIComponent(id)}&lang=${lang}`)).json(); } catch (e) { d = { ok: false, error: String(e) }; }
    if (!d.ok) { document.getElementById("clan-body").innerHTML = `<div id="cerr">${String(d.error || "no clan data").replace(/[<>&]/g, "")}</div>`; return; }
    data = d;
    document.getElementById("c-name").textContent = "CLAN - " + String(d.name || "").toUpperCase();
    const r = d.clan || {};
    if (r.ok && r.hasClan) { document.documentElement.dataset.theme = r.faction === 2 ? "sera" : "wlf"; document.getElementById("bg-a").style.backgroundImage = `url(/launcher/assets/bg/${r.faction === 2 ? "haven-fields" : "wlf-hq"}.jpg)`; }
    await Clan.load();
    if (qs.get("still") === "1") try { Fx.still(document.getElementById("clan-body")); } catch (e) { /* motion off */ }   // screenshots / reduced motion: the end state at once
    sections(); show(tab);
    parent.postMessage({ clanLoaded: id }, location.origin);
  }
  document.getElementById("ctabs").addEventListener("click", (e) => {
    const t = e.target.closest("[data-ct]"); if (t) return show(t.dataset.ct, { play: true });
    if (e.target.id === "c-lang") { lang = lang === "pl" ? "en" : "pl"; location.search = `?id=${encodeURIComponent(id)}&lang=${lang}&tab=${tab}`; }
  });
  // one scroll: the frame is as tall as the clan view; the admin page scrolls, nothing inside does
  let lastH = 0;
  const sizeUp = () => { const h = Math.ceil(document.getElementById("v-clan").getBoundingClientRect().height); if (Math.abs(h - lastH) > 1) { lastH = h; parent.postMessage({ clanHeight: h }, location.origin); } };
  new ResizeObserver(sizeUp).observe(document.getElementById("v-clan"));
  load();
})();
