'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const mkTmp = require('./tmp');
const game = require('../lib/game');
const slimdata = require('../lib/game/slimdata');

let passed = 0;
const T = async (name, fn) => {
  try {
    await fn();
    passed++;
    console.log('  ok  ' + name);
  } catch (e) {
    console.log('FAIL  ' + name + '\n' + ((e && e.stack) || e));
    process.exitCode = 1;
  }
};

const winmmFixture = () => {
  const b = Buffer.alloc(0x60000);
  for (const o of [0x56402, 0x58725]) b.writeUInt32LE((Buffer.from([127, 0, 0, 1]).readUInt32LE(0) ^ 0x5a3c9e17) >>> 0, o);
  for (const o of [0x563f1, 0x58742]) b.writeUInt16LE(7001, o);
  return b;
};
const cfgFor = (gd) => ({ game_dir: gd, token_id: '0123456789abcdef01234567', custom_name: '' });

const slimHead = (outSize, buildId) => {
  const b = Buffer.alloc(128);
  b.write('T2SLIM03', 0, 'latin1');
  b.writeBigUInt64LE(BigInt(outSize), 32);
  buildId.copy(b, 88);
  return b;
};

const fakeDir = mkTmp('slimfake-');
const nodeExe = path.join(fakeDir, 't2r-slim.exe');
fs.copyFileSync(process.execPath, nodeExe);
const fake = path.join(fakeDir, 'fake.js');
fs.writeFileSync(
  fake,
  `const fs = require('fs');
const [slim, gameDir, target] = process.argv.slice(1);
fs.appendFileSync(${JSON.stringify(path.join(fakeDir, 'runs.txt'))}, 'run\\n');
const mode = process.env.T2R_FAKE_SLIM || 'ok';
const h = fs.readFileSync(slim).subarray(0, 128);
const size = Number(h.readBigUInt64LE(32));
const id = h.subarray(88, 104);
if (mode === 'fail') { fs.writeFileSync(target + '.tmp', Buffer.alloc(100)); console.error('t2r-slim: writing the output failed (disk full?): There is not enough space on the disk. (os error 112)'); process.exit(1); }
const out = Buffer.alloc(size);
if (mode !== 'wrongid') { id.copy(out, 0x18); id.copy(out, size - 16); }
console.log('t2r-slim: progress 1 2');
fs.writeFileSync(target, out);
console.log('t2r-slim: progress 2 2');
process.exit(0);
`,
);
const runs = () => {
  try {
    return fs.readFileSync(path.join(fakeDir, 'runs.txt'), 'utf8').split('\n').filter(Boolean).length;
  } catch {
    return 0;
  }
};

const mkGame = () => {
  const gd = mkTmp('sg-');
  fs.writeFileSync(path.join(gd, 'tlou-ii.exe'), 'stub');
  return gd;
};
const mkClient = (buildId, { staleBin = false } = {}) => {
  const c = mkTmp('sc-');
  fs.mkdirSync(path.join(c, 'slim'));
  fs.copyFileSync(nodeExe, path.join(c, 'slim', 't2r-slim.exe'));
  fs.writeFileSync(path.join(c, 'winmm.dll'), winmmFixture());
  fs.writeFileSync(path.join(c, 'version.txt'), 'v2\n');
  fs.mkdirSync(path.join(c, 't2r-maps', 'main'), { recursive: true });
  fs.writeFileSync(path.join(c, 't2r-maps', 'main', 't2r-data.slim'), Buffer.concat([slimHead(8192, buildId), Buffer.alloc(64)]));
  if (staleBin) fs.writeFileSync(path.join(c, 't2r-maps', 'main', 't2r-data.bin'), Buffer.from('an older build, never to be copied'));
  return c;
};
const target = (gd) => path.join(gd, 't2r-maps', 'main', 't2r-data.bin');

(async () => {
  process.env.NODE_OPTIONS = `--require ${JSON.stringify(fake).slice(1, -1)}`;

  await T('readSlimHead reads size and build id, refuses other files', async () => {
    const d = mkTmp('sh-');
    const id = crypto.randomBytes(16);
    fs.writeFileSync(path.join(d, 'a.slim'), slimHead(123456, id));
    const h = slimdata.readSlimHead(path.join(d, 'a.slim'));
    assert.strictEqual(h.outSize, 123456);
    assert.ok(h.buildId.equals(id));
    fs.writeFileSync(path.join(d, 'b.slim'), Buffer.concat([Buffer.from('T2SLIM02'), Buffer.alloc(120)]));
    assert.strictEqual(slimdata.readSlimHead(path.join(d, 'b.slim')), null);
    fs.writeFileSync(path.join(d, 'c.slim'), Buffer.from('short'));
    assert.strictEqual(slimdata.readSlimHead(path.join(d, 'c.slim')), null);
    assert.strictEqual(slimdata.readSlimHead(path.join(d, 'missing.slim')), null);
  });

  await T('install rebuilds t2r-data.bin from the slim file; the .slim and a stale client .bin never reach the game folder', async () => {
    process.env.T2R_FAKE_SLIM = 'ok';
    const gd = mkGame();
    const id = crypto.randomBytes(16);
    const c = mkClient(id, { staleBin: true });
    const before = runs();
    await game.installMod(c, cfgFor(gd), () => {});
    assert.strictEqual(runs(), before + 1);
    const out = fs.readFileSync(target(gd));
    assert.strictEqual(out.length, 8192);
    assert.ok(out.subarray(0x18, 0x28).equals(id) && out.subarray(-16).equals(id));
    assert.ok(!fs.existsSync(path.join(gd, 't2r-maps', 'main', 't2r-data.slim')));
    assert.ok(!fs.existsSync(target(gd) + '.tmp'));
    assert.deepStrictEqual(game.missingModFiles(c, gd), []);
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), true);
    await game.installMod(c, cfgFor(gd), () => {});
    assert.strictEqual(runs(), before + 1);
  });

  await T('a new build id makes the rebuilt file stale: reported missing, rebuilt by the next install', async () => {
    process.env.T2R_FAKE_SLIM = 'ok';
    const gd = mkGame();
    const c = mkClient(crypto.randomBytes(16));
    await game.installMod(c, cfgFor(gd), () => {});
    const id2 = crypto.randomBytes(16);
    fs.writeFileSync(path.join(c, 't2r-maps', 'main', 't2r-data.slim'), Buffer.concat([slimHead(8192, id2), Buffer.alloc(64)]));
    assert.deepStrictEqual(game.missingModFiles(c, gd), ['t2r-maps/main/t2r-data.bin']);
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), false);
    const before = runs();
    await game.installMod(c, cfgFor(gd), () => {});
    assert.strictEqual(runs(), before + 1);
    assert.ok(fs.readFileSync(target(gd)).subarray(-16).equals(id2));
  });

  await T('helper failure (disk full): clear message, temp file removed, install stays unfinished', async () => {
    process.env.T2R_FAKE_SLIM = 'fail';
    const gd = mkGame();
    const c = mkClient(crypto.randomBytes(16));
    await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /Could not prepare the mod from your game files: .*probably full/s);
    assert.ok(!fs.existsSync(target(gd)));
    assert.ok(!fs.existsSync(target(gd) + '.tmp'));
    assert.ok(fs.existsSync(path.join(gd, 't2r-installing.txt')));
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), false);
  });

  await T('helper exits 0 but the file has the wrong build id: refused, not counted as installed', async () => {
    process.env.T2R_FAKE_SLIM = 'wrongid';
    const gd = mkGame();
    const c = mkClient(crypto.randomBytes(16));
    await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /was not written correctly/);
    assert.strictEqual(game.modCurrent(c, cfgFor(gd)), false);
  });

  await T('a damaged slim file is refused before anything runs', async () => {
    process.env.T2R_FAKE_SLIM = 'ok';
    const gd = mkGame();
    const c = mkClient(crypto.randomBytes(16));
    fs.writeFileSync(path.join(c, 't2r-maps', 'main', 't2r-data.slim'), Buffer.from('garbage'));
    const before = runs();
    await assert.rejects(game.installMod(c, cfgFor(gd), () => {}), /t2r-data\.slim in the client files is damaged/);
    assert.strictEqual(runs(), before);
  });

  delete process.env.NODE_OPTIONS;
  console.log(`slimdata-test: ${passed} passed`);
})();
