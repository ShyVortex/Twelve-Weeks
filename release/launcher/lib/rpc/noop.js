/**
 * @file Dummy adapter for when RPC is disabled
 */
'use strict';
// Just for properness: be sure to respect them nevertheless ;)
/**
 * @typedef {object} RpcActivity
 * @property {string} [details]          // e.g. 'Playing Twelve Weeks'
 * @property {string} [state]            // e.g. 'Player on live'
 * @property {Object} [timestamps]
 * @property {number} [timestamps.start] // epoch ms when the game started
 * @property {string} [partyId]          // launcher player id / session id
 * @property {number} [partySize]        // players in the lobby / match (shown as "(n of max)")
 * @property {number} [partyMax]         // lobby / match size
 * @property {Object} [assets]           // art: largeImage / smallImage (Discord asset key or https URL), largeText / smallText (hover)
 * @property {Array<Object>} [buttons]   // [{ label, url }]
 */

/**
 * @typedef {object} RpcAdapter
 * @property {string} name               // 'discord' | 'noop' | future: 'xmpp', 'matrix'
 * @property {boolean} enabled           // true when configured and usable
 * @property {boolean} isReady           // true when the pipe/socket is open
 * @property {Function} connect          // (opts) => Promise<void> — lazy, never throws hard
 * @property {Function} setActivity      // (activity: RpcActivity) => Promise<void>
 * @property {Function} clear            // () => Promise<void>
 * @property {Function} destroy          // () => Promise<void> — close on quit
 */

/**
 * Creates the no-op adapter object
 * @param {{log: Function}}
 * @returns {RpcAdapter}
 */
function createNoopAdapter({ log }) {
  return {
    name: 'noop',
    enabled: false,
    isReady: false,
    connect: async () => {},
    setActivity: async () => {},
    clear: async () => {},
    destroy: async () => {},
  };
}

module.exports = { createNoopAdapter };
