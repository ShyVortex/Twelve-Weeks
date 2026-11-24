/**
 * @file Network check for bug reports (launcher 0.1.51): what each update-server address and the game server answer from this PC.
 *
 * Several reports said only "read ECONNRESET" or "Unexpected token '<'" - nobody could tell which address a home network
 * blocked, whether DNS pointed somewhere else (a filter's block page) or whether only one port was cut. Each address is asked once, directly
 * (no fallback, no redirect followed), for /status.json; the game server's TCP port is opened once. The recent request failures that
 * lib/update/hosts.js remembered go in too. Written as files/network.txt; no personal data (our own server addresses only).
 */
'use strict';

const dns = require('dns');
const http = require('http');
const https = require('https');
const net = require('net');
const hosts = require('../update/hosts');

const TIMEOUT = 8000;

function lookup(host) {
  if (net.isIP(host)) return Promise.resolve(`${host} (literal)`);
  return dns.promises
    .lookup(host, { all: true })
    .then((r) => r.map((a) => a.address).join(', ') || 'no address')
    .catch((e) => `DNS FAILED (${e.code || e.message})`);
}

// one GET, raw: status, type, size, time, and what an HTML page says (a block page names its filter)
function get(url) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const u = new URL(url);
    const mod = u.protocol === 'https:' ? https : http;
    let done = false;
    const finish = (s) => {
      if (done) return;
      done = true;
      resolve(`${s} [${Date.now() - t0} ms]`);
    };
    let req;
    try {
      req = mod.get(
        u,
        {
          timeout: TIMEOUT,
          headers: { Accept: 'application/json', 'User-Agent': 'TwelveWeeksLauncher-netcheck' },
        },
        (res) => {
          const chunks = [];
          let n = 0;
          res.on('data', (c) => {
            n += c.length;
            if (n <= 256 * 1024) chunks.push(c); // status.json is ~5 KB; a block page is small
          });
          res.on('end', () => {
            const type = res.headers['content-type'] || '-';
            let s = `HTTP ${res.statusCode}, ${type}, ${n} B`;
            if (res.headers.location)
              s += `, redirect to ${String(res.headers.location).slice(0, 120)}`;
            const body = Buffer.concat(chunks).toString('utf8');
            if (/html/i.test(type) || /^\s*</.test(body)) {
              const title = (body.match(/<title[^>]*>([^<]{0,160})/i) || [])[1];
              const text = body
                .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ')
                .replace(/<[^>]+>/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();
              s += ` - HTML (block page?) title "${(title || '').trim()}" text "${text.slice(0, 200)}"`;
            } else if (res.statusCode === 200) {
              try {
                const j = JSON.parse(body);
                const v = j.server_version || j.version;
                s += ` - JSON ok${v ? ` (server ${v})` : ''}`;
              } catch {
                s += ` - not JSON: "${body.slice(0, 80).replace(/\s+/g, ' ')}"`;
              }
            }
            finish(s);
          });
          res.on('error', (e) => finish(`FAILED mid-body (${e.code || e.message})`));
        },
      );
    } catch (e) {
      finish(`FAILED (${e.code || e.message})`);
      return;
    }
    req.on('timeout', () => {
      req.destroy(new Error('timeout'));
    });
    req.on('error', (e) => finish(`FAILED (${e.code || ''} ${e.message})`.replace(/\s+/g, ' ')));
  });
}

function tcp(host, port) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const s = net.connect({ host, port, timeout: TIMEOUT });
    const end = (r) => {
      s.destroy();
      resolve(`${r} [${Date.now() - t0} ms]`);
    };
    s.on('connect', () => end('TCP open'));
    s.on('timeout', () => end('TCP TIMEOUT'));
    s.on('error', (e) => end(`TCP FAILED (${e.code || e.message})`));
  });
}

/**
 * Run the network check. Never throws; resolves to the text of network.txt.
 * @param {{gameServer?: string, fileHost?: string}} [o] game server "host:port"; the file host when hosts.js is unconfigured
 * @returns {Promise<string>}
 */
async function netProbe(o = {}) {
  const lines = [`network check ${new Date().toISOString()}`];
  try {
    let addrs = hosts.addresses();
    if (!Object.keys(addrs).length && o.fileHost) addrs = { file: o.fileHost }; // unconfigured (test server, F2_FILE_HOST)
    const jobs = Object.entries(addrs).map(async ([k, base]) => {
      const u = new URL(base);
      const [d, g] = await Promise.all([
        lookup(u.hostname),
        get(`${base.replace(/\/$/, '')}/status.json`),
      ]);
      return `update ${k.padEnd(6)} ${base}\n    dns ${d}\n    get /status.json: ${g}`;
    });
    const gs = String(o.gameServer || '');
    const m = gs.match(/^(.+):(\d+)$/);
    if (m) {
      jobs.push(
        (async () => {
          const [d, t] = await Promise.all([lookup(m[1]), tcp(m[1], Number(m[2]))]);
          return `game server ${gs}\n    dns ${d}\n    ${t}`;
        })(),
      );
      const ip = addrs.ip && new URL(addrs.ip).hostname;
      if (ip && ip !== m[1])
        jobs.push(tcp(ip, Number(m[2])).then((t) => `game server by IP ${ip}:${m[2]}\n    ${t}`));
    }
    lines.push(...(await Promise.all(jobs)));
  } catch (e) {
    lines.push(`check failed: ${e.message}`);
  }
  const h = hosts.history();
  lines.push('', `recent update-server request failures (newest last, ${h.length}):`);
  for (const x of h)
    lines.push(`  ${x.t} ${x.k} ${x.path} - ${x.err}${x.next ? ` -> retried on ${x.next}` : ''}`);
  return lines.join('\n') + '\n';
}

module.exports = { netProbe };
