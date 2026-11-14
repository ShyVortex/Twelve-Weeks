/**
 * @file Renderer ban screen: a banned player gets the startup/update overlay with YOU ARE BANNED and nothing else to touch.
 *
 * The verdict lives in the main process (lib/ban.js: update server answer, stored locally, Play and updates refused there); this file only
 * shows it. Global `banState` is read by doPlay (play.js), the Discord button (ui.js), the launcher-update overlay (data.js) and the end of
 * startup (app.js). The Discord button is hidden by CSS (ban.css, body.banned) whatever happens to the overlay.
 */
'use strict';

let banState = { banned: false, reason: '' };

/**
 * The text of the ban error (the Play toast).
 * @returns {string}
 */
function banText() {
  return (
    T('You are banned from Twelve Weeks. No appeals are being taken in at this time.') +
    (banState.reason ? ' ' + T('Reason: {r}', { r: banState.reason }) : '')
  );
}

// a banned player touches nothing: every key is swallowed while the screen is up
document.addEventListener(
  'keydown',
  (e) => {
    if (!banState.banned) return;
    e.preventDefault();
    e.stopImmediatePropagation();
  },
  true,
);

/**
 * Show or lift the ban screen to match the verdict.
 * @param {{banned: boolean, reason?: string}} v
 * @returns {void}
 */
function applyBan(v) {
  const banned = !!(v && v.banned),
    reason = banned ? String((v && v.reason) || '') : '',
    ov = $('loading'),
    title = ov.querySelector('.ld-title'),
    sub = ov.querySelector('.ld-sub');
  if (banned === banState.banned && reason === banState.reason) return;
  banState = { banned, reason };
  document.body.classList.toggle('banned', banned);
  ov.classList.toggle('ld-ban', banned);
  let why = ov.querySelector('.ld-reason');
  if (banned) {
    if (typeof lupBusy !== 'undefined' && lupBusy) title.classList.remove('ld-lup');
    title.textContent = T('YOU ARE BANNED');
    sub.textContent = T('No appeals are being taken in at this time.');
    if (!why) {
      why = document.createElement('div');
      why.className = 'ld-reason';
      ov.appendChild(why);
    }
    why.textContent = reason ? T('Reason: {r}', { r: reason }) : '';
    ov.classList.remove('gone');
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    f2.log('ban: this player is banned, ban screen up');
  } else {
    if (why) why.remove();
    title.textContent = T('LOADING');
    sub.textContent = T('Please wait.');
    ov.classList.add('gone');
    f2.log('ban: no ban, ban screen down');
  }
}

/**
 * Show the stored/fresh verdict now and keep following it (the main process re-checks at start and every 10 minutes).
 * @returns {void}
 */
function startBanWatch() {
  const poll = async () => {
    try {
      const r = await f2.ban();
      if (r && r.ok) applyBan(r);
    } catch (_) {
      /* next poll */
    }
  };
  poll();
  setInterval(poll, 4000);
}
