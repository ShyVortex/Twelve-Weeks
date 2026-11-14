'use strict';
// node test/steam-shortcut-test.js : ADD TO STEAM on a FAKE Steam folder (never the real one): binary vdf round trip, appid, idempotency, manual entries.
const fs = require('fs'),
  os = require('os'),
  path = require('path'),
  assert = require('assert');
const S = require('../lib/steam-shortcut');

// ---- crc32 / appid against Python zlib.crc32
assert.strictEqual(S.crc32('123456789'), 3421780262);
assert.strictEqual(S.shortcutAppId('"C:\\Fake\\Twelve.exe"', 'Twelve Weeks'), 2329689971); // (zlib.crc32(b'"C:\\Fake\\Twelve.exe"Twelve Weeks') | 0x80000000)

// ---- hand-written binary vdf (independent of the module's writer)
const z = (s) => Buffer.from(s + '\0', 'utf8');
const str = (k, v) => Buffer.concat([Buffer.from([1]), z(k), z(v)]);
const int = (k, n) => {
  const b = Buffer.alloc(4);
  b.writeInt32LE(n | 0);
  return Buffer.concat([Buffer.from([2]), z(k), b]);
};
const entry = (i, name, exe, appid, extra = []) =>
  Buffer.concat([
    Buffer.from([0]),
    z(String(i)),
    int('appid', appid),
    str('AppName', name),
    str('Exe', exe),
    str('StartDir', '"C:\\x"'),
    str('icon', ''),
    int('IsHidden', 0),
    Buffer.from([0]),
    z('tags'),
    str('0', 'favorite'),
    Buffer.from([8]),
    ...extra,
    Buffer.from([8]),
  ]);
const file = (...entries) => Buffer.concat([Buffer.from([0]), z('shortcuts'), ...entries, Buffer.from([8, 8])]);
const two = () => file(entry(0, 'Game A', '"C:\\A\\a.exe"', -123456), entry(1, 'Game B', '"D:\\B\\b.exe"', 77, [Buffer.concat([Buffer.from([7]), z('big'), Buffer.alloc(8, 9)])]));

assert.ok(S.serializeVdf(S.parseVdf(two())).equals(two()), 'round trip is byte-identical');
assert.throws(() => S.parseVdf(Buffer.from([0, 0x73, 0])), /truncated|unterminated/);

// ---- fake Steam
const ACCT = 1000;
const ID64 = (BigInt(ACCT) + 76561197960265728n).toString();
const mk = (extraUsers = []) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'f2-steam-'));
  fs.mkdirSync(path.join(dir, 'config'), { recursive: true });
  const users = [[ID64, 1], ...extraUsers];
  fs.writeFileSync(path.join(dir, 'config', 'loginusers.vdf'), '"users"\n{\n' + users.map(([id, r]) => `\t"${id}"\n\t{\n\t\t"AccountName"\t\t"x"\n\t\t"MostRecent"\t\t"${r}"\n\t}\n`).join('') + '}\n');
  fs.mkdirSync(path.join(dir, 'userdata', String(ACCT), 'config'), { recursive: true });
  return dir;
};
const vdfPath = (dir, acct = ACCT) => path.join(dir, 'userdata', String(acct), 'config', 'shortcuts.vdf');
// assets/ is not in the public repository: without it the test uses placeholder art files
let art = path.join(__dirname, '..', 'assets', 'steam');
if (!fs.existsSync(art)) {
  art = fs.mkdtempSync(path.join(os.tmpdir(), 't2r-tmp-steamart-'));
  for (const f of ['cover.jpg', 'wide.jpg', 'hero.jpg', 'logo.png']) fs.writeFileSync(path.join(art, f), Buffer.alloc(2048, f));
}
const EXE = 'C:\\Fake\\Twelve.exe';
const run = (dir, exe = EXE) => S.addToSteam({ steamDir: dir, exe, startDir: path.dirname(exe), icon: 'C:\\Fake\\icon.ico', artDir: art });
const items = (dir, acct) => S.parseVdf(fs.readFileSync(vdfPath(dir, acct)))[0].v;
const get = (e, k) => e.v.find((f) => f.k === k);

// ---- add to an existing file with 2 shortcuts
let dir = mk();
fs.writeFileSync(vdfPath(dir), two());
assert.deepStrictEqual(S.steamUserDirs(dir), [path.join(dir, 'userdata', String(ACCT))]);
let r = run(dir);
assert.deepStrictEqual([r.created, r.updated, r.appid], [1, 0, 2329689971]);
assert.ok(fs.readFileSync(vdfPath(dir) + '.bak-twelveweeks').equals(two()), 'backup = original');
let list = items(dir);
assert.strictEqual(list.length, 3);
assert.ok(S.serializeVdf([{ t: 0, k: 'shortcuts', v: list.slice(0, 2) }]).equals(S.serializeVdf(S.parseVdf(two()))), 'existing shortcuts untouched');
const ours = list[2];
assert.strictEqual(ours.k, '2');
assert.strictEqual(get(ours, 'AppName').v, 'Twelve Weeks');
assert.strictEqual(get(ours, 'Exe').v, '"' + EXE + '"');
assert.strictEqual(get(ours, 'StartDir').v, '"C:\\Fake"');
assert.strictEqual(get(ours, 'appid').v.readInt32LE(0), 2329689971 | 0);
assert.strictEqual(get(ours, 'AllowOverlay').v.readInt32LE(0), 1);
assert.strictEqual(get(ours, 'OpenVR').v.readInt32LE(0), 0);
const grid = path.join(dir, 'userdata', String(ACCT), 'config', 'grid');
for (const n of ['2329689971p.jpg', '2329689971.jpg', '2329689971_hero.jpg', '2329689971_logo.png']) assert.ok(fs.statSync(path.join(grid, n)).size > 1000, n);

// ---- idempotent: no duplicate, same bytes
const bytes = fs.readFileSync(vdfPath(dir));
r = run(dir);
assert.deepStrictEqual([r.created, r.updated], [0, 1]);
assert.ok(fs.readFileSync(vdfPath(dir)).equals(bytes), 'second run changes nothing');

// ---- exe moved: updated in place, new appid, art under the new id
r = run(dir, 'D:\\New Place\\Twelve.exe');
assert.strictEqual(items(dir).length, 3);
assert.strictEqual(r.appid, S.shortcutAppId('"D:\\New Place\\Twelve.exe"', 'Twelve Weeks'));
assert.ok(fs.existsSync(path.join(grid, r.appid + '_hero.jpg')));
assert.strictEqual(get(items(dir)[2], 'StartDir').v, '"D:\\New Place"');

// ---- no shortcuts.vdf yet: created
dir = mk();
r = run(dir);
assert.strictEqual(items(dir).length, 1);
assert.ok(!fs.existsSync(vdfPath(dir) + '.bak-twelveweeks'));

// ---- the player added it by hand: same exe (other slashes / case / no quotes) or a launcher name -> updated in place
const manual = (name, exe, appid) => {
  const d = mk();
  fs.writeFileSync(vdfPath(d), file(entry(0, 'Game A', '"C:\\A\\a.exe"', 5), entry(1, name, exe, appid)));
  return d;
};
// same exe, other spelling, other name: one entry, renamed, new id
dir = manual('My Launcher', 'c:/fake/TWELVE.exe', 424242);
r = run(dir);
list = items(dir);
assert.strictEqual(list.length, 2);
assert.strictEqual(r.created, 0);
assert.strictEqual(get(list[1], 'AppName').v, 'Twelve Weeks');
assert.strictEqual(get(list[1], 'appid').v.readUInt32LE(0), 2329689971);
assert.ok(fs.existsSync(path.join(path.dirname(vdfPath(dir)), 'grid', '2329689971_logo.png')));
// known names, any case, other exe: matched, exe updated
for (const nm of ['TWELVE WEEKS', 'twelve weeks launcher', 'Twelve Weeks Launcher']) {
  dir = manual(nm, '"C:\\Old\\Twelve Weeks Launcher.exe"', 99);
  run(dir);
  list = items(dir);
  assert.strictEqual(list.length, 2, nm);
  assert.strictEqual(get(list[1], 'Exe').v, '"' + EXE + '"');
}
// exe and name already right: the player's appid is kept, art goes under it
dir = manual('Twelve Weeks', '"' + EXE + '"', 31337 | 0x80000000);
r = run(dir);
assert.strictEqual(r.appid, (31337 | 0x80000000) >>> 0);
assert.ok(fs.existsSync(path.join(path.dirname(vdfPath(dir)), 'grid', r.appid + 'p.jpg')));
// an old .png of the same kind would hide ours: removed
{
  const g = path.join(path.dirname(vdfPath(dir)), 'grid');
  fs.writeFileSync(path.join(g, r.appid + '_hero.png'), 'x');
  run(dir);
  assert.ok(!fs.existsSync(path.join(g, r.appid + '_hero.png')));
}

// ---- accounts: most recent only; none recent -> all that have a folder
dir = mk([[(BigInt(2000) + 76561197960265728n).toString(), 0]]);
fs.mkdirSync(path.join(dir, 'userdata', '2000', 'config'), { recursive: true });
assert.strictEqual(S.steamUserDirs(dir).length, 1);
fs.writeFileSync(path.join(dir, 'config', 'loginusers.vdf'), fs.readFileSync(path.join(dir, 'config', 'loginusers.vdf'), 'utf8').replace('"MostRecent"\t\t"1"', '"MostRecent"\t\t"0"'));
assert.strictEqual(S.steamUserDirs(dir).length, 2);
r = run(dir);
assert.strictEqual(r.users, 2);

// ---- a file we cannot read exactly is never written
dir = mk();
fs.writeFileSync(vdfPath(dir), Buffer.from([0, 0x73, 0x68, 0, 9, 9]));
assert.throws(() => run(dir), /shortcuts\.vdf/);
assert.deepStrictEqual([...fs.readFileSync(vdfPath(dir))], [0, 0x73, 0x68, 0, 9, 9]);

// ---- isAdded / remove: only ours goes (entry + its 4 grid files), the others stay byte-identical (renumbered), a backup exists
dir = mk();
fs.writeFileSync(vdfPath(dir), file(entry(0, 'Game A', '"C:\A\a.exe"', -123456), entry(1, 'Twelve Weeks Launcher', '"c:/fake/TWELVE.exe"', 5), entry(2, 'Game B', '"D:\B\b.exe"', 77)));
assert.strictEqual(S.isAdded({ steamDir: dir, exe: EXE }), true, 'manual entry counts as added');
r = run(dir);
assert.strictEqual(S.isAdded({ steamDir: dir, exe: EXE }), true);
const g2 = path.join(path.dirname(vdfPath(dir)), 'grid');
fs.writeFileSync(path.join(g2, '999_hero.png'), 'keep'); // someone else's art stays
assert.strictEqual(S.removeFromSteam({ steamDir: dir, exe: EXE }).removed, 1);
assert.strictEqual(S.isAdded({ steamDir: dir, exe: EXE }), false);
assert.ok(S.serializeVdf(S.parseVdf(fs.readFileSync(vdfPath(dir)))).equals(fs.readFileSync(vdfPath(dir))));
assert.ok(fs.readFileSync(vdfPath(dir)).equals(file(entry(0, 'Game A', '"C:\A\a.exe"', -123456), entry(1, 'Game B', '"D:\B\b.exe"', 77))), 'others untouched');
assert.ok(fs.existsSync(vdfPath(dir) + '.bak-twelveweeks'));
assert.deepStrictEqual(fs.readdirSync(g2).sort(), ['999_hero.png']);
assert.strictEqual(S.removeFromSteam({ steamDir: dir, exe: EXE }).removed, 0, 'nothing left to remove');
assert.strictEqual(S.isAdded({ steamDir: mk(), exe: EXE }), false, 'no shortcuts.vdf');

// ---- exe choice
const ex = () => true;
assert.strictEqual(S.launcherExe({ env: { APPIMAGE: '/a/x.AppImage', PORTABLE_EXECUTABLE_FILE: 'P' }, exists: ex }), '/a/x.AppImage');
assert.strictEqual(S.launcherExe({ env: { PORTABLE_EXECUTABLE_FILE: 'C:\\dl\\tw.exe' }, root: 'R', rootExe: 'r.exe', exists: ex }), 'C:\\dl\\tw.exe');
assert.strictEqual(S.launcherExe({ env: {}, root: 'R', rootExe: 'r.exe', execPath: 'E', exists: ex }), path.join('R', 'r.exe'));
assert.strictEqual(S.launcherExe({ env: {}, root: 'R', rootExe: 'r.exe', execPath: 'E', exists: () => false }), 'E');

// ---- Steam process handling (no real process is touched)
(async () => {
  assert.strictEqual(await S.steamRunning('win32', async () => 'steam.exe                   1234 Console   1    90,000 K\r\n'), true);
  assert.strictEqual(await S.steamRunning('win32', async () => 'INFO: No tasks are running which match the specified criteria.\r\n'), false);
  assert.strictEqual(await S.steamRunning('linux', async () => '4321\n'), true);
  assert.strictEqual(await S.steamRunning('linux', async () => ''), false);
  let asked = 0,
    polls = 0;
  const gone = await S.quitSteam({ steamDir: 'x', ask: () => asked++, running: async () => ++polls < 3, sleep: async () => {} });
  assert.deepStrictEqual([gone, asked, polls], [true, 1, 3]);
  const stuck = await S.quitSteam({ steamDir: 'x', ask: () => {}, running: async () => true, sleep: async () => {}, timeoutMs: 2000 });
  assert.strictEqual(stuck, false);
  console.log('steam-shortcut-test OK');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
