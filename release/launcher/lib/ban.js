/**
 * @file Ban guard: a banned player cannot use the launcher at all.
 *
 * The update server answers GET /ban-check?h=<hardware hashes>&s=<steam ids> with {banned, reason} (tools/update_server/ban_check.py).
 * The hardware hashes are the ones the game reports (lib/hwid.js), so a banned PC is recognised on a new Steam account too.
 *
 *  - only an explicit answer changes the state: banned:true is stored in <userData>/ban.json and stays until the server explicitly says
 *    banned:false (an unban); a network error / bad answer / timeout keeps whatever was stored and NEVER bans on its own
 *  - the stored ban is read at every start, before the server answers, so a blocked or offline server does not lift it
 *  - assertNotBanned() is the gate in front of Play / update in the main process (the renderer screen is only the face of it)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const NO_APPEALS = 'No appeals are being taken in at this time.';

/**
 * The error text a banned player gets when Play (or an update) is refused.
 * @param {string} [reason]
 * @returns {string}
 */
function banMessage(reason) {
  return `YOU ARE BANNED. ${NO_APPEALS}${reason ? ` Reason: ${reason}` : ''}`;
}

/**
 * Create the ban guard.
 * @param {{ file: string, getHost: () => string, getHashes: () => Promise<string[]>, getSteamIds: () => Promise<string[]>,
 *           getJson: (url: string, timeoutMs: number, opts?: object) => Promise<any>, log?: Function }} deps
 * @returns {{ current: () => {banned: boolean, reason: string}, check: () => Promise<{banned: boolean, reason: string}>, assertNotBanned: () => void }}
 */
function createBanGuard({ file, getHost, getHashes, getSteamIds, getJson, log = () => {} }) {
  let mem = null; // the stored verdict, read once

  function load() {
    if (mem) return mem;
    mem = { banned: false, reason: '' };
    try {
      const j = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (j && j.banned === true)
        mem = { banned: true, reason: String(j.reason || '').slice(0, 200) };
    } catch {
      /* no stored ban */
    }
    return mem;
  }

  function store(v) {
    mem = v;
    try {
      if (v.banned) {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, JSON.stringify({ banned: true, reason: v.reason, at: Date.now() }));
      } else fs.rmSync(file, { force: true });
    } catch (e) {
      log(`ban: could not store the verdict: ${e.message}`);
    }
  }

  let hashes = null;
  let inflight = null;

  async function checkOnce() {
    const host = getHost();
    if (!host) return load();
    if (!hashes || !hashes.length) hashes = await getHashes().catch(() => []);
    const ids = await getSteamIds().catch(() => []);
    const q = new URLSearchParams();
    if (hashes.length) q.set('h', hashes.join(','));
    if (ids.length) q.set('s', ids.join(','));
    let answer;
    try {
      answer = await getJson(`${host}/ban-check?${q}`, 8000, { force: true });
    } catch (e) {
      log(`ban: check failed (${e.message}); keeping the stored verdict`);
      return load();
    }
    if (!answer || typeof answer.banned !== 'boolean') {
      log('ban: bad answer from the server; keeping the stored verdict');
      return load();
    }
    const v = {
      banned: answer.banned,
      reason: answer.banned ? String(answer.reason || '').slice(0, 200) : '',
    };
    if (v.banned !== load().banned)
      log(v.banned ? 'ban: this player is banned' : 'ban: the ban was lifted');
    store(v);
    return v;
  }

  return {
    current: () => ({ ...load() }),
    check: () => (inflight ||= checkOnce().finally(() => (inflight = null))),
    assertNotBanned() {
      const v = load();
      if (v.banned) throw new Error(banMessage(v.reason));
    },
  };
}

module.exports = { createBanGuard, banMessage, NO_APPEALS };
