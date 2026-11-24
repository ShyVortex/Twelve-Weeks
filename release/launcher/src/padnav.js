'use strict';
// Controller and arrow-key navigation (Steam Deck without the touchscreen / trackpad, any XInput / DualShock pad).
//
// Gamepad API (standard mapping): D-pad / left stick = move the focus to the nearest control in that direction, A = select, B = back
// (Escape), LB / RB = previous / next menu page, LT / RT = previous / next sub tab, right stick = scroll, START = focus PLAY.
// The pad buttons become keydown events on the focused element first, so every existing key handler (the confirm box, Esc closing
// a page or the players panel, GEAR UP rows, the ban screen swallowing keys) answers a pad exactly like the keyboard. What no handler
// takes is done here: arrows move the focus spatially, Enter clicks the control.
// Arrow keys without a pad do the same spatial move (Steam Deck desktop mode maps the D-pad to arrows, A to Enter, B to Escape),
// except inside text fields, sliders and lists, where the keys keep their normal meaning.
(function padNav() {
  const FOCUSABLE = [
    'button',
    'a[href]',
    'input:not([type=hidden])',
    'select',
    'textarea',
    '[tabindex]:not([tabindex="-1"])',
    '[role=button]',
    'label.tg',
    '.nrow',
    '[data-mat]',
    '.jrn',
  ].join(',');
  const NATIVE = 'button, a[href], input, select, textarea, summary';
  const TEXT =
    'input:not([type=range]):not([type=checkbox]):not([type=radio]):not([type=button]), textarea, [contenteditable=""], [contenteditable=true]';
  const DIRS = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };

  let padMode = false;
  const setPadMode = (on) => {
    if (on === padMode) return;
    padMode = on;
    document.body.classList.toggle('pad-nav', on);
    const k = document.querySelectorAll('#botbar .keys kbd');
    if (k.length >= 2) {
      k[0].textContent = on ? 'A' : 'ENTER';
      k[1].textContent = on ? 'B' : 'ESC';
    }
  };
  // the mouse takes over again as soon as it moves (the Deck trackpad moves the mouse too)
  let lastMouse = null;
  document.addEventListener(
    'mousemove',
    (e) => {
      const p = e.screenX + ',' + e.screenY;
      if (lastMouse !== null && p !== lastMouse) setPadMode(false);
      lastMouse = p;
    },
    true,
  );
  // the checkbox rows hide their <input>: the row itself takes the focus
  const tagRows = () =>
    document
      .querySelectorAll('label.tg:not([tabindex])')
      .forEach((l) => l.setAttribute('tabindex', '0'));
  new MutationObserver(tagRows).observe(document.body, { childList: true, subtree: true });
  tagRows();

  const usable = (el) => {
    if (el.disabled || el.closest('[inert],[hidden]')) return false;
    if (el.matches('label.tg input') || el.closest('#titlebar')) return false; // minimise / close stay mouse-only (B and QUIT exist)
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.pointerEvents !== 'none' && cs.display !== 'none';
  };
  const visibleModal = () =>
    [
      ...document.querySelectorAll(
        '#confirm, [aria-modal="true"], [role=dialog], [role=alertdialog]',
      ),
    ].find(
      (m) => !m.hidden && m.getClientRects().length && getComputedStyle(m).visibility !== 'hidden',
    );
  const scope = () => visibleModal() || document.body;
  const candidates = () => [...scope().querySelectorAll(FOCUSABLE)].filter(usable);

  const activeView = () => document.querySelector('.view.active');
  const firstTarget = () => {
    const m = visibleModal();
    if (m) return [...m.querySelectorAll(FOCUSABLE)].filter(usable)[0];
    const v = activeView();
    const inView = v && [...v.querySelectorAll(FOCUSABLE)].filter(usable)[0];
    return (
      inView ||
      document.querySelector('.mi.active[data-view]') ||
      document.querySelector('.mi[data-act=play]')
    );
  };
  // .pad-focus mirrors the focus for the ring (also while the window itself is not focused, e.g. right after the game closed)
  let marked = null;
  const mark = (el) => {
    if (marked && marked !== el) marked.classList.remove('pad-focus');
    marked = el;
    if (el && el.classList) el.classList.add('pad-focus');
  };
  document.addEventListener('focusin', (e) => mark(e.target));
  document.addEventListener('focusout', (e) => {
    if (e.target === marked && !e.relatedTarget) mark(null);
  });
  const focusEl = (el) => {
    if (!el) return false;
    el.focus({ preventScroll: true });
    mark(el);
    el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (window.Snd && Snd.play) Snd.play('hover');
    return true;
  };
  const current = () => {
    const a = document.activeElement;
    return a && a !== document.body && usable(a) && scope().contains(a) ? a : null;
  };

  // nearest control in the direction: centres ahead of the current one, distance along the direction plus a heavy penalty for
  // sideways offset (rows stay rows, columns stay columns); a control overlapping the current one's row / column wins over one that does not
  function move(dx, dy) {
    const cur = current();
    if (!cur) return focusEl(firstTarget());
    const a = cur.getBoundingClientRect();
    const ac = { x: a.left + a.width / 2, y: a.top + a.height / 2 };
    let best = null,
      bestScore = Infinity;
    // inside an open page the focus leaves it only to the left (back to the menu), never up / right / down to the corner buttons
    const inPage = cur.closest('.view.active');
    for (const el of candidates()) {
      if (el === cur || el.contains(cur) || cur.contains(el)) continue;
      if (inPage && dx >= 0 && !inPage.contains(el)) continue;
      const b = el.getBoundingClientRect();
      const bc = { x: b.left + b.width / 2, y: b.top + b.height / 2 };
      const along = dx ? (bc.x - ac.x) * dx : (bc.y - ac.y) * dy;
      const edge = dx
        ? dx > 0
          ? b.left - a.right
          : a.left - b.right
        : dy > 0
          ? b.top - a.bottom
          : a.top - b.bottom;
      if (along <= 1 || edge < -Math.min(a.width, a.height, b.width, b.height) / 2) continue;
      const side = dx ? Math.abs(bc.y - ac.y) : Math.abs(bc.x - ac.x);
      const overlap = dx
        ? b.bottom > a.top && b.top < a.bottom
        : b.right > a.left && b.left < a.right;
      if (!overlap && side > Math.max(along, 1) * 2) continue; // out of line only inside a ~60 degree cone, never across the window
      // in line: the nearest edge wins, ties go to reading order (aligned left / top edge); out of line: far behind
      const align = dx ? Math.abs(b.top - a.top) : Math.abs(b.left - a.left);
      const score = Math.max(0, edge) + (overlap ? align * 0.05 : side * 3 + 400);
      if (score < bestScore) {
        bestScore = score;
        best = el;
      }
    }
    return best ? focusEl(best) : false;
  }

  function activate(el) {
    if (!el) return;
    if (el.matches('select')) {
      el.selectedIndex = (el.selectedIndex + 1) % el.options.length;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else if (el.matches(TEXT)) el.focus();
    else {
      el.click();
      // a menu page opened: the focus goes into it (B brings it back to the menu)
      if (el.matches('.mi[data-view]'))
        setTimeout(() => el.classList.contains('active') && focusEl(firstTarget()), 60);
    }
  }
  function step(el, dir) {
    if (el.matches('input[type=range]')) {
      if (dir > 0) el.stepUp(Math.max(1, Math.round((el.max - el.min) / 20) || 1));
      else el.stepDown(Math.max(1, Math.round((el.max - el.min) / 20) || 1));
    } else el.selectedIndex = Math.max(0, Math.min(el.options.length - 1, el.selectedIndex + dir));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // what no other handler took (runs last: bubble phase on window)
  window.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
    const el =
      document.activeElement && document.activeElement !== document.body
        ? document.activeElement
        : null;
    const d = DIRS[e.key];
    if (d) {
      if (el && el.matches('input[type=range], select') && d[0]) {
        if (!e.isTrusted) step(el, d[0]); // a real key moves the slider / list by itself
        return;
      }
      if (e.isTrusted && el && el.matches(TEXT + ', select')) return; // typing: the caret / list keeps the arrows
      if (move(d[0], d[1])) e.preventDefault();
      return;
    }
    if (e.key === 'Enter' && el) {
      if (e.isTrusted && el.matches(NATIVE)) return; // the browser clicks buttons / submits by itself
      if (!e.isTrusted || !el.matches(TEXT)) {
        e.preventDefault();
        activate(el);
      }
    }
  });
  // keyboard arrows count as pad navigation too (focus ring on), the mouse switches it off
  window.addEventListener(
    'keydown',
    (e) => {
      if (DIRS[e.key] && e.isTrusted) setPadMode(true);
    },
    true,
  );

  // ---------------------------------------------------------------- the pad
  const send = (key) => {
    const t = document.activeElement || document.body;
    const menu = document.querySelector('.mi.active[data-view]');
    t.dispatchEvent(
      new KeyboardEvent('keydown', { key, code: key, bubbles: true, cancelable: true }),
    );
    // B closed a page / panel / box: the focus was on something now hidden, put it back on the page's menu entry
    if (key === 'Escape')
      setTimeout(() => {
        if (!current()) focusEl(menu && usable(menu) ? menu : firstTarget());
      }, 60);
  };
  const page = (n) => {
    const tabs = [...document.querySelectorAll('.mi[data-view]')].filter(usable);
    if (!tabs.length) return;
    const i = tabs.findIndex((t) => t.classList.contains('active'));
    const next = tabs[i < 0 ? (n > 0 ? 0 : tabs.length - 1) : (i + n + tabs.length) % tabs.length];
    next.click();
    setTimeout(() => focusEl(firstTarget()), 60);
  };
  const subTab = (n) => {
    const v = activeView();
    const subs = v ? [...v.querySelectorAll('.subtabs .sub')].filter(usable) : [];
    if (!subs.length) return;
    const i = Math.max(
      0,
      subs.findIndex((s) => s.classList.contains('active')),
    );
    const next = subs[(i + n + subs.length) % subs.length];
    next.click();
    focusEl(next);
  };
  const scrollBox = (el) => {
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/(auto|scroll)/.test(cs.overflowY) && p.scrollHeight > p.clientHeight + 2) return p;
    }
    const v = activeView();
    return (
      v &&
      [...v.querySelectorAll('*')].find(
        (p) =>
          /(auto|scroll)/.test(getComputedStyle(p).overflowY) &&
          p.scrollHeight > p.clientHeight + 2,
      )
    );
  };

  // standard mapping: 0 A, 1 B, 4 LB, 5 RB, 6 LT, 7 RT, 9 START, 12-15 D-pad up / down / left / right
  const ACTIONS = {
    0: () => send('Enter'),
    1: () => send('Escape'),
    4: () => page(-1),
    5: () => page(1),
    6: () => subTab(-1),
    7: () => subTab(1),
    9: () => focusEl(document.querySelector('.mi[data-act=play]')),
    12: () => send('ArrowUp'),
    13: () => send('ArrowDown'),
    14: () => send('ArrowLeft'),
    15: () => send('ArrowRight'),
  };
  const REPEAT = new Set([12, 13, 14, 15]);
  const held = new Map(); // button -> next repeat time
  let raf = 0;

  function poll(now) {
    raf = 0;
    const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
    if (!pads.length) return;
    raf = requestAnimationFrame(poll);
    if (!document.hasFocus()) {
      held.clear();
      return;
    }
    const down = new Set();
    let sx = 0,
      sy = 0;
    for (const p of pads) {
      p.buttons.forEach((b, i) => {
        if (b.pressed || b.value > 0.6) down.add(i);
      });
      const [lx = 0, ly = 0, rx = 0, ry = 0] = p.axes;
      // left stick = the D-pad
      if (Math.abs(lx) > 0.6 && Math.abs(lx) > Math.abs(ly)) down.add(lx > 0 ? 15 : 14);
      else if (Math.abs(ly) > 0.6) down.add(ly > 0 ? 13 : 12);
      if (Math.abs(rx) > 0.2) sx += rx;
      if (Math.abs(ry) > 0.2) sy += ry;
    }
    for (const i of [...held.keys()]) if (!down.has(i)) held.delete(i);
    for (const i of down) {
      const act = ACTIONS[i];
      if (!act) continue;
      const t = held.get(i);
      if (t === undefined) {
        setPadMode(true);
        held.set(i, now + 380);
        act();
      } else if (REPEAT.has(i) && now >= t) {
        held.set(i, now + 110);
        act();
      }
    }
    if (sx || sy) {
      setPadMode(true);
      const box = scrollBox(document.activeElement || document.body);
      if (box) box.scrollBy(sx * 14, sy * 22);
    }
  }
  const start = () => {
    if (!raf) raf = requestAnimationFrame(poll);
  };
  window.addEventListener('gamepadconnected', start);
  window.addEventListener('focus', start);
  start();
  window.PadNav = { move, activate, setPadMode, candidates, send, page, subTab };
})();
