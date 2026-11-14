/**
 * @file Renderer-side debug API for the automated screenshot scenarios (dev only).
 *
 * This function's source is injected into the renderer via executeJavaScript when the app
 * runs in screenshot mode (F2_SHOT). It publishes window.__shot, a small, documented surface
 * of one-liner actions and reads so the host scenarios never have to ship a blob of minified
 * DOM code over the bridge. Everything it returns is JSON-serializable; DOM nodes are exposed
 * as integer handles ("refs") that later calls act on, keeping every cross-process call a
 * plain expression.
 */
'use strict';

/**
 * Install window.__shot in the renderer. Called as a stringified IIFE in screenshot mode.
 * @returns {void}
 */
function installShotApi() {
  const refs = new Map();
  let nextRef = 1;

  const el = (selector) => document.querySelector(selector);
  const els = (selector) => [...document.querySelectorAll(selector)];
  const ref = (node) => {
    for (const [id, n] of refs) if (n === node) return id;
    const id = nextRef++;
    refs.set(id, node);
    return id;
  };
  const nodeOf = (id) => refs.get(id);

  const textOf = (node) => (node ? node.textContent.trim() : '');

  const shot = {
    /* -- readiness -- */
    loadDone() {
      return window.__loadDone === true;
    },
    ready(ids) {
      return (ids || ['srv-state', 'cl-state', 't-main']).every((id) => {
        const n = el('#' + id);
        return n && n.textContent.trim() !== '...' && n.textContent.trim() !== '';
      });
    },
    reduced() {
      return matchMedia('(prefers-reduced-motion: reduce)').matches;
    },

    /* -- navigation -- */
    view(name) {
      f2show(name);
    },
    edit() {
      el('#lo-edit').click();
    },
    back() {
      el('#lo-back').click();
    },
    tab(row) {
      el('[data-row="' + row + '"]').click();
    },
    sub(name) {
      el('[data-sub=' + name + ']').click();
    },
    click(selector) {
      el(selector).click();
    },
    clickRef(id) {
      nodeOf(id).click();
    },
    hoverRef(id) {
      nodeOf(id).dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    },

    /* -- loadout queries (return JSON-safe values / refs) -- */
    ref(selector) {
      return ref(el(selector));
    },
    refAt(selector, index) {
      return ref(els(selector)[index]);
    },
    refByText(selector, name) {
      const n = els(selector).find((e) => textOf(e.querySelector('b')) === name);
      return n ? ref(n) : null;
    },
    row(name) {
      return shot.refByText('#lo-body .orow', name);
    },
    rowAt(index) {
      return shot.refAt('#lo-body .orow', index);
    },
    quietRef(rowRef, q) {
      const lv = nodeOf(rowRef).querySelector('.lv[data-q="' + q + '"]');
      return lv ? ref(lv) : null;
    },
    lvRef(rowRef, selector) {
      const lv = nodeOf(rowRef).querySelector(selector);
      return lv ? ref(lv) : null;
    },
    bizRow(name) {
      return shot.refByText('#lo-body .orow.wrow', name);
    },
    cols() {
      return els('#lo-body .lo-cols > *').map((n) => ref(n));
    },
    col(index) {
      return ref(els('#lo-body .lo-cols > *')[index]);
    },
    scrollRef(id, top) {
      nodeOf(id).scrollTop = top;
    },
    scrollTopOf(id) {
      return nodeOf(id).scrollTop;
    },
    scrollTopCol(index) {
      return els('#lo-body .lo-cols > *')[index].scrollTop;
    },
    text(selector) {
      return textOf(el(selector));
    },
    h3() {
      return textOf(el('.lo-det h3'));
    },
    lp() {
      return textOf(el('.lo-lp'));
    },
    noticeText() {
      return textOf(el('#notice .n'));
    },
    mNewCount() {
      return els('#lo-body .m-new').length;
    },
    colsOverflow() {
      return els('#lo-body .lo-cols > *, .lo-det').map((e) => [
        e.className,
        e.scrollWidth,
        e.clientWidth,
        e.scrollWidth > e.clientWidth + 1,
      ]);
    },

    /* -- alert panel -- */
    alertOn() {
      return el('#alert').classList.contains('on');
    },
    alertTitle() {
      const n = el('#alert b');
      return n ? n.textContent : '';
    },
    alertDesc() {
      const n = el('#alert span');
      return n ? n.textContent : '';
    },
    alertText() {
      return shot.alertTitle() + ' | ' + shot.alertDesc();
    },
    alertOpacity() {
      return getComputedStyle(el('#alert')).opacity;
    },
    alertPanels() {
      return els('#alert').length;
    },
    alertChildren() {
      return el('#alert').children.length;
    },
    clanBoxTransform() {
      return getComputedStyle(el('.clanbox')).transform;
    },

    /* -- notices / misc -- */
    notices(status) {
      Notices.update(status);
    },
    notify(text, ms) {
      window.notify(text, ms);
    },
    bgBlock() {
      return getComputedStyle(el('#bg-block')).display + ' set=' + el('#bg-set').textContent;
    },
    loadingState() {
      const l = el('#loading');
      return l ? (l.classList.contains('gone') ? 'faded' : 'showing') : 'none';
    },
    setReportText(value) {
      el('#rp-text').value = value;
    },
    scrollClan() {
      el('#clan-body').scrollTop = 99999;
    },
    scrollLoadoutCol(index, top) {
      els('#lo-body .lo-cols > *')[index].scrollTop = top;
    },

    /* -- i18n audit -- */
    untranslated() {
      const out = [];
      const w = document.createTreeWalker(el('#app'), NodeFilter.SHOW_TEXT);
      let n;
      while ((n = w.nextNode())) {
        const t = n.nodeValue.trim();
        if (
          t &&
          /[A-Za-z]{3}/.test(t) &&
          !n.parentNode.closest('script,style,#loading') &&
          n.parentNode.offsetParent !== null
        ) {
          I18N.setLang('pl');
          const t2 = T(t);
          I18N.setLang('en');
          if (t2 === t) out.push(t);
        }
      }
      return [...new Set(out)];
    },
    lang() {
      return I18N.lang;
    },

    /* -- motion sampling: returns a small readable log -- */
    async sample(targetRef, props) {
      const c = getComputedStyle(nodeOf(targetRef));
      return (props || ['opacity', 'transform'])
        .map((p) => (c[p] === 'none' ? 'none' : c[p].split(',')[4] || c[p]))
        .join('/');
    },
    async sampleCol(index, props) {
      const c = getComputedStyle(els('#lo-body .lo-cols > *')[index]);
      return (props || ['opacity', 'transform'])
        .map((p) => (c[p] === 'none' ? 'none' : c[p].split(',')[4] || c[p]))
        .join('/');
    },
  };

  window.__shot = shot;
}

module.exports = { installShotApi };
