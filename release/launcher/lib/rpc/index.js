/** @file The index for RPC providers: Just Discord for now, but one never knows */
'use strict';

const { createDiscordAdapter } = require('./discord.js');
const { createNoopAdapter } = require('./noop.js');

/**
 * Create the RPC service.
 * @param {{ config: object, log: Function, player: object }} options
 * @returns {import('./noop.js').RpcAdapter}
 */
function createRpcService(config, log, player) {
  const provider = config.values.rpc?.provider || null;

  if (provider === 'discord') return createDiscordAdapter({ config, log, player });
  else {
    log('Unknown adapter or RPC disabled by user, falling back to no-op');
    return createNoopAdapter({ log });
  }
}

module.exports = { createRpcService };
