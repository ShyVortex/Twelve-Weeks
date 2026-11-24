/**
 * @file Friends and party service for the FRIENDS tab (daemon op 0xD8, tools/social.py).
 */
'use strict';

const game = require('../lib/game');
const dmn = require('../lib/daemon');

/** Cut a string to at most max UTF-8 bytes without splitting a character (the daemon reads 200 bytes of argument). */
function fitBytes(s, max) {
  let out = '',
    n = 0;
  for (const ch of s) {
    const b = Buffer.byteLength(ch, 'utf8');
    if (n + b > max) break;
    out += ch;
    n += b;
  }
  return out;
}

/**
 * Create the friends/party service.
 * @param {{ config: object, paths: object, player: object, locale: object }} options
 * @returns {object} social API: get() and act(sub, arg).
 */
function createSocial({ config, paths, player, locale }) {
  async function call(sub, arg) {
    const name = await player.resolveName();
    const token = game.nameToken(name.name, config.values.token_id);
    const { host, port } = game.parseServer(paths.serverAddress());
    const r = await dmn.social(host, port, token, locale.langNow(), sub, arg);
    if (!r) return { social: null, error: 'The game server did not answer.' };
    return { social: r };
  }

  // the actions the renderer may ask for (everything but a poll changes something)
  const ACTS = new Set(Object.keys(dmn.SOCIAL_SUBS));
  return {
    get: () => call('state'),
    act: (sub, arg) => {
      if (!ACTS.has(sub)) throw new Error('Unknown friends action.');
      return call(
        sub,
        sub === 'msg' ? fitBytes(String(arg || ''), 200) : String(arg || '').slice(0, 120),
      );
    },
  };
}

module.exports = { createSocial, fitBytes };
