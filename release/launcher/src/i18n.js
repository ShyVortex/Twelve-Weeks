/**
 * @file Renderer translation runtime and live DOM translation pass.
 */
'use strict';
// Renderer side of the translation: T() for dynamic text, a DOM pass for the static markup (index.html text nodes, placeholders, titles; the English
// original of every node is remembered, so switching language is live and reversible). Core: i18n-core.js.
/**
 * Translate a string with optional variable interpolation.
 * @param {string} s
 * @param {object} [vars]
 * @returns {string}
 */
function T(s, vars) {
  return I18N.T(s, vars);
}
/**
 * Live DOM translation pass over the English markup.
 */
const L10N = (() => {
  const nodes = [],
    attrs = [];
  let scanned = false;
  function scan() {
    if (scanned) return;
    scanned = true;
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) =>
        n.parentNode.closest(
          'script,style,textarea,#clan-body,#lo-body,#news-list,#rp-files,#thumbs',
        ) || !n.nodeValue.trim()
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT,
    });
    let n;
    while ((n = w.nextNode())) {
      const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(n.nodeValue);
      nodes.push({ n, lead: m[1], en: m[2], trail: m[3] });
    }
    for (const el of document.querySelectorAll('[placeholder],[title]'))
      for (const a of ['placeholder', 'title'])
        if (el.hasAttribute(a)) attrs.push({ el, a, en: el.getAttribute(a) });
    for (const o of document.querySelectorAll('option'))
      nodes.push({ n: o.firstChild, lead: '', en: o.textContent, trail: '' });
  }
  function apply() {
    scan();
    for (const r of nodes) if (r.n && r.n.isConnected) r.n.nodeValue = r.lead + T(r.en) + r.trail;
    for (const r of attrs) r.el.setAttribute(r.a, T(r.en));
    document.title = T('Twelve Weeks');
  }
  function tree(root) {
    // markup built by JS (loadout, clan, report files): translate its text nodes and attributes in place
    if (!root || I18N.lang === 'en') return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const ns = [];
    let n;
    while ((n = w.nextNode())) if (n.nodeValue.trim()) ns.push(n);
    for (const t of ns) {
      const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(t.nodeValue);
      const v = T(m[2]);
      if (v !== m[2]) t.nodeValue = m[1] + v + m[3];
    }
    for (const el of root.querySelectorAll('[title]')) el.title = T(el.title);
  }
  return { apply, scan, tree };
})();
