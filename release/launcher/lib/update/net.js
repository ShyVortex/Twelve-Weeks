/**
 * @file HTTP transport, JSON caching and manifest fetching.
 */
'use strict';

const http = require('http');
const https = require('https');
const { safeRel, tunables, sleep, isNetErr, baseUrl, DECODERS } = require('./util');
const { cleanPatches } = require('./patch');
const hosts = require('./hosts');

/**
 * Perform a cached HTTP request with timeout and retry policy.
 * 0.1.46: the update server has two addresses (lib/update/hosts.js); a request that cannot get through on one is
 * retried once on the other.
 * @param {string} url
 * @param {{headers?: object, timeout?: number, method?: string}} [options]
 * @returns {Promise<unknown>}
 */
function request(url, options = {}) {
  return hosts.withFallback(url, (u) => requestOnce(u, options)); // 0.1.49: walks every address (hosts.js), not just one retry
}

function requestOnce(url, { headers = {}, timeout = 15000, method = 'GET', fresh = false } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const lib = u.protocol === 'https:' ? https : http;
    const req = lib.request(
      u,
      {
        method,
        headers: { 'User-Agent': 'TwelveWeeks-Launcher', ...headers },
        timeout,
        ...(fresh ? { agent: false } : {}),
      },
      (res) => {
        // our update server never redirects: ANY 3xx on one of its addresses is a network filter's block page
        // (0.1.51: 303 too - a filter answered 303 on every address and the client install stopped at "HTTP 303", no fallback)
        if (hosts.blockedRedirect(res, url)) {
          res.resume();
          return reject(new Error(`redirected (blocked?) by ${u.host} (HTTP ${res.statusCode})`));
        }
        if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
          res.resume();
          return resolve(
            request(new URL(res.headers.location, url).toString(), {
              headers,
              timeout,
              method,
            }),
          );
        }
        res.t2rUrl = url; // the address actually used (hosts.js may have moved the request)
        resolve(res);
      },
    );
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', (e) => {
      // a kept-alive connection the server already closed (the :7002 front closes after a proxied reply without saying so):
      // once more on a new connection, the usual remedy, before this counts as a failure of the address
      if (!fresh && req.reusedSocket && /ECONNRESET|EPIPE/.test(String(e && e.code)))
        return resolve(requestOnce(url, { headers, timeout, method, fresh: true }));
      reject(e);
    });
    req.end();
  });
}

// The update server is down until its tunnel exists: one failed network call marks it unreachable for a minute, so the other startup calls
// (status, manifest, news, clan, feed) fail at once instead of each waiting for its own timeout. An explicit user action calls resetDown().
let downUntil = 0;
/**
 * Clear the cached offline state after a successful request.
 * @returns {void}
 */
const resetDown = () => {
  downUntil = 0;
};
// (a new player saw 'update server unreachable' while the host answered here in 0.7 s: the playit relay is far from some players and a cold
// connection takes longer than the old 2.5 s cap; one such timeout marked the host down for a minute, the manifest included.) The cap is 8 s now and
// the manifest asks with force (it never takes the shortcut): only the cosmetic calls (status, news, clan, feed) skip a host that just failed.
/**
 * Fetch and cache a JSON document.
 * @param {string} url
 * @param {number} [timeout]
 * @param {{force?: boolean}} [options]
 * @returns {Promise<unknown>}
 */
async function getJson(url, timeout = 2500, { force = false } = {}) {
  if (!force && Date.now() < downUntil) throw new Error('update server unreachable');
  let res;
  try {
    res = await request(url, {
      timeout: Math.min(timeout, 8000),
      headers: { Accept: 'application/json' },
    });
    // our server answers JSON here; an HTML page from one of its addresses is a network filter's block page: try the other address
    for (
      let i = 0;
      i < 3 &&
      /text\/html/i.test(res.headers['content-type'] || '') &&
      hosts.whose(res.t2rUrl || url);
      i++
    ) {
      const alt = hosts.fail(res.t2rUrl || url);
      hosts.note(
        res.t2rUrl || url,
        `HTML page instead of JSON (HTTP ${res.statusCode}, block page?)`,
        alt,
      );
      if (!alt) break;
      res.resume();
      // with fallback: the next address may itself be blocked another way (redirect, reset)
      res = await hosts.withFallback(alt, (u) =>
        requestOnce(u, {
          timeout: Math.min(timeout, 8000),
          headers: { Accept: 'application/json' },
        }),
      );
    }
  } catch (e) {
    if (isNetErr(e)) downUntil = Date.now() + 60000;
    throw e;
  }
  if (res.statusCode !== 200) {
    res.resume();
    throw new Error(`HTTP ${res.statusCode}`);
  }
  const chunks = [];
  let n = 0;
  for await (const c of res) {
    n += c.length;
    if (n > 8 * 1024 * 1024) throw new Error('response too large');
    chunks.push(c);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

/**
 * Fetch a small binary file (news media) into memory.
 * @param {string} url
 * @param {number} [timeout]
 * @param {number} [max] size cap in bytes
 * @returns {Promise<Buffer>}
 */
async function getBuffer(url, timeout = 8000, max = 6 * 1024 * 1024) {
  const res = await request(url, { timeout: Math.min(timeout, 15000) });
  if (res.statusCode !== 200) {
    res.resume();
    throw new Error(`HTTP ${res.statusCode}`);
  }
  const chunks = [];
  let n = 0;
  for await (const c of res) {
    n += c.length;
    if (n > max) throw new Error('file too large');
    chunks.push(c);
  }
  return Buffer.concat(chunks);
}

/**
 * Validate and normalize a decoded update manifest.
 * @param {object} m
 * @param {string} base
 * @returns {object}
 */
function validateManifest(m, base) {
  if (!m || !Array.isArray(m.files)) throw new Error('Bad manifest (no files list).');
  const root = baseUrl(base);
  for (const f of m.files) {
    f.path = safeRel(f.path);
    if (!/^[0-9a-f]{64}$/i.test(f.sha256 || '') || !Number.isFinite(f.size))
      throw new Error(`Bad manifest entry: ${f.path}`);
    f.sha256 = f.sha256.toLowerCase();
    f.url = new URL(f.url || `/files/${f.sha256}`, root + '/').toString();
    cleanPatches(f); // patches from an installed older copy (lib/update/patch.js); malformed ones are dropped
    // compressed transfer (optional): only used when the codec is one this runtime can decode and the entry is sane
    if (f.zurl && DECODERS[f.enc] && Number.isFinite(f.zsize) && f.zsize > 0)
      f.zurl = new URL(f.zurl, root + '/').toString();
    else {
      delete f.zurl;
      delete f.zsize;
      delete f.enc;
    }
  }
  return m;
}

/**
 * Fetch and validate the update manifest for a channel.
 * @param {string} base
 * @param {string} channel
 * @param {{retries?: number}} [options]
 * @returns {Promise<object>}
 */
async function fetchManifest(base, channel, { retries = 0 } = {}) {
  let m;
  for (let i = 0; ; i++) {
    try {
      m = await getJson(
        `${baseUrl(base)}/manifest.json?channel=${encodeURIComponent(channel || 'stable')}`,
        8000,
        { force: true },
      );
      break;
    } catch (e) {
      // an explicit update retries a few times (a restarting server / tunnel is back within seconds); the startup check does not wait
      if (i >= retries || !(isNetErr(e) || /HTTP 5\d\d/.test(e.message))) throw e;
      resetDown();
      await sleep(tunables.netBackoffMs * (i + 1));
    }
  }
  return validateManifest(m, base);
}

module.exports = { request, resetDown, getJson, getBuffer, fetchManifest };
