'use strict';
// node test/players-test.js : players panel data path (test feature): /status.json roster -> sanitized list for the renderer; no extra fields leak
const assert = require('assert');
const http = require('http');
const { createStatus } = require('../main/status');
const body = { online: true, roster: [
  { name: 'Ann', state: 'match', map: 'Hillside', party: true, steamid: 7, token: 'x' },
  { name: 'B'.repeat(40), state: 'weird', map: 5 },
  null,
] };
const srv = http.createServer((req, res) => { res.setHeader('content-type', 'application/json'); res.end(JSON.stringify(req.url === '/status.json' ? body : {})); });
srv.listen(0, '127.0.0.1', async () => {
  const host = 'http://127.0.0.1:' + srv.address().port;
  let sp = false;
  const st = createStatus({ runtime: {}, config: { values: {} }, paths: { fileHost: () => host }, mode: { current: () => sp } });
  const r = await st.roster();
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.players[0], { name: 'Ann', state: 'match', map: 'Hillside', party: true });
  assert.strictEqual(r.players[1].name.length, 24); assert.strictEqual(r.players[1].state, 'menu'); assert.strictEqual(r.players[1].map, null);
  assert.deepStrictEqual(r.players[2], { name: 'PLAYER', state: 'menu', map: null, party: false });
  sp = true; assert.deepStrictEqual(await st.roster(), { ok: false, players: [] });
  sp = false; srv.close();
  const dead = createStatus({ runtime: {}, config: { values: {} }, paths: { fileHost: () => 'http://127.0.0.1:1' }, mode: { current: () => false } });
  assert.strictEqual((await dead.roster()).ok, false);
  console.log('players-test ok'); process.exit(0);
});
