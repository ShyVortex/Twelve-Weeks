/**
 * @file Renderer core: DOM helpers, shared state and formatting utilities.
 *
 * Classic scripts share globals by design (index.html load order): `$`/`$$` DOM helpers, the
 * mutable `cfg`/`state`/`status`/`busy`/`gs`/`curView` snapshot, and formatting helpers
 * (`fmtBytes`, `fmtEta`). Later files read and update these names directly; keep them in sync
 * with src/index.html and avoid adding new cross-file globals without documenting them here.
 */
'use strict';
/**
 * Look up one DOM element by id.
 * @param {string} id
 * @returns {HTMLElement}
 */
const $ = (id) => document.getElementById(id);
/**
 * Look up all DOM elements matching a selector.
 * @param {string} sel
 * @returns {NodeListOf<HTMLElement>}
 */
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
let cfg = {},
  state = null,
  status = null,
  busy = null,
  gs = { s: 'idle', misses: 0 },
  curView = null;
/**
 * Format a byte count for compact UI labels.
 * @param {number|null|undefined} n
 * @returns {string}
 */
const fmtBytes = (n) => {
  if (n == null) return '--';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < 3) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};
/**
 * Format an ETA in seconds/minutes.
 * @param {number|null|undefined} s
 * @returns {string}
 */
const fmtEta = (s) =>
  s == null
    ? ''
    : s < 60
      ? `${Math.ceil(s)} ${T('s')}`
      : `${Math.floor(s / 60)} ${T('min')} ${Math.ceil(s % 60)} ${T('s')}`;
/**
 * Escape text for safe insertion into HTML.
 * @param {unknown} s
 * @returns {string}
 */
const esc = (s) =>
  String(s).replace(
    /[&<>"]/g,
    (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m],
  );
