'use strict';

/**
 * @file RPC service facade. Holds the active adapter instance so any main-process
 * module can set or clear presence without constructor injection.
 */

/**
 * @type {import('./noop.js').RpcAdapter | null}
 */
let adapter = null;

/**
 * Mount the active RPC adapter instance. Call once from main.js after
 * createRpcService() resolves.
 * @param {import('./noop.js').RpcAdapter} a
 * @returns {void}
 */
function mount(a) {
  adapter = a;
}

/**
 * Set Discord Rich Presence. No-op if no adapter is mounted or disabled.
 * The adapter itself lazily opens the connection on the first activity.
 * @param {import('./noop.js').RpcActivity} activity
 * @returns {Promise<void>}
 */
async function setActivity(activity) {
  if (!adapter || !adapter.enabled) return;
  await adapter.setActivity(activity);
}

/**
 * Clear the current Rich Presence. No-op if no adapter is mounted.
 * @returns {Promise<void>}
 */
async function clear() {
  if (!adapter) return;
  await adapter.clear();
}

/**
 * Destroy the adapter and close the IPC pipe. Unmounts afterward.
 * @returns {Promise<void>}
 */
async function destroy() {
  // unmount first: a slow teardown must not unmount an adapter mounted in the meantime (Settings switch)
  const a = adapter;
  adapter = null;
  if (!a) return;
  await a.destroy();
}

/**
 * @returns {boolean}
 */
function isReady() {
  return !!adapter && adapter.isReady;
}

/**
 * @returns {boolean}
 */
function isEnabled() {
  return !!adapter && adapter.enabled;
}

module.exports = { mount, setActivity, clear, destroy, isReady, isEnabled };
