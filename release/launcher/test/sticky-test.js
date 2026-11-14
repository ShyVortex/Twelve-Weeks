'use strict';
// node test/sticky-test.js : the launcher keeps the last good update / server answer over short failures, shows a real outage
const assert = require('assert');
const { makeSticky } = require('../lib/sticky');
let t = 0; const now = () => t;
const s = makeSticky({ maxFails: 3, maxAgeMs: 1000, now });
assert.strictEqual(s.fail(), null, 'nothing good yet: the failure shows');
s.ok({ a: 1 }); t = 100;
assert.deepStrictEqual(s.fail(), { a: 1 }, 'first failure: last good');
assert.deepStrictEqual(s.fail(), { a: 1 }, 'second failure: last good');
assert.strictEqual(s.fail(), null, 'third in a row: a real outage shows');
s.ok({ a: 2 }); t = 200;
assert.deepStrictEqual(s.fail(), { a: 2 }, 'a success resets the count');
t = 5000;
assert.strictEqual(s.fail(), null, 'a good answer older than maxAge is not shown');
console.log('sticky-test ok');
