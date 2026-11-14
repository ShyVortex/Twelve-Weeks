'use strict';
// node test/loadoutfile-test.js : GEAR UP <-> game files (lib/loadoutfile.js), in scratch folders only.
const assert = require('assert');
const fs = require('fs');
const mkTmp = require('./tmp');
const os = require('os');
const path = require('path');
const lof = require('../lib/loadoutfile');
const G = new Function(fs.readFileSync(path.join(__dirname, '..', 'src', 'gamedata.js'), 'utf8') + '\nreturn GAMEDATA;')();

const dir = mkTmp('f2-lo-');
const sk = (key, lv) => ({ id: G.skills.findIndex((s) => s.key === key), lv });
const mk = () => ({ v: 2, custom: Array.from({ length: G.customSlots }, () => lof.blank(G)), active: { kind: 'custom', i: 0 } });

// ---- wire format: names, supp flag, skill keys; LP like the game
const st = mk();
st.custom[0] = { small: { id: 'pistol-beretta', supp: 1 }, large: { id: 'rifle-mpx5', supp: 1 }, purch: { id: 'shotgun-baserri-over-under', supp: 0 }, skills: [sk('SK_REVIVER', 2), sk('SK_COVERT', 1), null, sk('SK_FORT', 1)] };
assert.strictEqual(lof.lpOf(G, st.custom[0]), 1 + 4 + 1 + 3 + 2 + 1);   // supp 9mm 1, supp full-auto 2+2, double barrel 1, reviver II 3, covert I 2, fortitude I 1
st.active = { kind: 'class', i: 2 };
const w = lof.toWire(G, st, 1234);
assert.strictEqual(w.custom[0].lp, 12);
assert.strictEqual(w.format, 1); assert.strictEqual(w.rev, 1234); assert.strictEqual(w.custom.length, 6);
assert.deepStrictEqual(w.custom[0].large, { id: 'rifle-mpx5', supp: 1 });
assert.deepStrictEqual(w.custom[0].skills, [{ id: 'SK_REVIVER', lv: 2 }, { id: 'SK_COVERT', lv: 1 }, null, { id: 'SK_FORT', lv: 1 }]);
assert.deepStrictEqual(w.custom[1], { small: { id: 'pistol-beretta', supp: 0 }, large: null, purch: null, skills: [null, null, null, null], lp: 0 });

// ---- round trip
const back = lof.fromWire(G, JSON.parse(JSON.stringify(w)));
assert.deepStrictEqual(back.problems, []); assert.ok(lof.same(G, back.state, st)); assert.deepStrictEqual(back.state.active, { kind: 'class', i: 2 });

// ---- validation: unknown ids dropped, small -> the free 9mm, suppressed variant that does not exist, skill twice, level range, over budget
const bad = JSON.parse(JSON.stringify(w));
bad.custom[1] = { small: { id: 'no-such-gun', supp: 0 }, large: { id: 'bow-ellie', supp: 1 }, purch: 'rifle-nope', skills: [{ id: 'SK_NOPE', lv: 1 }, { id: 'SK_EARS', lv: 9 }, { id: 'SK_HAWK', lv: 1 }, { id: 'SK_HAWK', lv: 1 }] };
bad.custom[2] = { small: { id: 'shotgun-shorty', supp: 0 }, large: { id: 'shotgun-tactical', supp: 1 }, purch: { id: 'pistol-el-diablo', supp: 0 }, skills: [sk2('SK_REVIVER', 3), sk2('SK_COVERT', 3), sk2('SK_STRAT', 3), null] };
function sk2(k, lv) { return { id: k, lv }; }
bad.active = { kind: 'class', i: 99 };
bad.custom.length = 5;
const r = lof.fromWire(G, bad);
assert.deepStrictEqual(r.state.custom[1].small, { id: G.weapons.small[0].id, supp: 0 });
assert.deepStrictEqual(r.state.custom[1].large, { id: 'bow-ellie', supp: 0 });
assert.strictEqual(r.state.custom[1].purch, null);
assert.deepStrictEqual(r.state.custom[1].skills, [null, null, sk('SK_HAWK', 1), null]);
assert.deepStrictEqual(r.over, [2]);                                  // 1 + 2+... tactical + diablo 3 + 4 + 5 + 5 = over 13
assert.deepStrictEqual(r.state.custom[5], lof.blank(G));              // missing entry -> blank
assert.deepStrictEqual(r.state.active, { kind: 'custom', i: 0 });
assert.ok(r.problems.length >= 8, r.problems.join(' | '));
assert.strictEqual(lof.fromWire(G, null).state, null); assert.strictEqual(lof.fromWire(G, { custom: 'x' }).state, null);

// ---- writing: atomic, named; an over-budget loadout is reported, the rest is still written (the game keeps that one as it was)
const over = mk();
over.custom[0] = { small: { id: 'pistol-beretta', supp: 0 }, large: { id: 'shotgun-tactical', supp: 1 }, purch: { id: 'pistol-el-diablo', supp: 0 }, skills: [sk('SK_REVIVER', 3), sk('SK_COVERT', 3), sk('SK_STRAT', 3), null] };
assert.deepStrictEqual(lof.writeLauncher(G, dir, over, 5).over, [1]);
assert.ok(fs.existsSync(path.join(dir, lof.LAUNCHER_FILE)));
lof.writeLauncher(G, dir, st, 777);
assert.deepStrictEqual(fs.readdirSync(dir), [lof.LAUNCHER_FILE]);     // no .tmp left behind
const onDisk = JSON.parse(fs.readFileSync(path.join(dir, lof.LAUNCHER_FILE), 'utf8'));
assert.strictEqual(onDisk.rev, 777); assert.strictEqual(onDisk.source, 'launcher'); assert.deepStrictEqual(onDisk.active, { kind: 'class', i: 2 });
assert.ok(lof.nextRev(onDisk.rev) > 777);
assert.strictEqual(lof.nextRev(Number.MAX_SAFE_INTEGER - 5), Number.MAX_SAFE_INTEGER - 4);

// ---- reading the game's file
assert.deepStrictEqual(lof.readGame(G, dir), { found: false });
const gameFile = (o) => fs.writeFileSync(path.join(dir, lof.GAME_FILE), typeof o === 'string' ? o : JSON.stringify(o));
gameFile('{ not json'); assert.strictEqual(lof.readGame(G, dir).found, false);
gameFile({ format: 1, rev: 5000, launcher_rev: 777, active: { kind: 'custom', i: 3 }, custom: w.custom });
const g = lof.readGame(G, dir);
assert.ok(g.found); assert.strictEqual(g.rev, 5000); assert.strictEqual(g.launcherRev, 777); assert.deepStrictEqual(g.state.active, { kind: 'custom', i: 3 });
assert.deepStrictEqual(g.state.custom[0].skills[3], sk('SK_FORT', 1));

// ---- the sync state machine (what main.js loadout:sync does)
const S = (c, d = dir) => lof.syncStep(G, d, c);
fs.unlinkSync(path.join(dir, lof.GAME_FILE));
assert.strictEqual(S({}, '').status, 'nogame');
assert.strictEqual(S({}).status, 'waiting');                                         // nothing saved, no game file yet
assert.strictEqual(S({ loadout_rev: 777 }).status, 'pending');                       // saved, the game has not written its file yet
let s = S({ loadout2: st });                                                          // edited before the files existed: pushed to the game
assert.ok(s.write && s.status === 'pending');
gameFile({ format: 1, rev: 5000, launcher_rev: 0, active: { kind: 'custom', i: 0 }, custom: w.custom });
s = S({ loadout_rev: 777, loadout_game_rev: 0 });                                     // the game has not applied rev 777
assert.strictEqual(s.status, 'pending'); assert.strictEqual(s.adopt, null);
s = S({ loadout_rev: 0, loadout_game_rev: 0 });                                       // never wrote: adopt the game's truth
assert.strictEqual(s.status, 'synced'); assert.ok(s.adopt); assert.deepStrictEqual(s.patch, { loadout_game_rev: 5000 });
gameFile({ format: 1, rev: 6000, launcher_rev: 777, active: { kind: 'custom', i: 1 }, custom: w.custom });
s = S({ loadout_rev: 777, loadout_game_rev: 5000 });                                  // applied (and maybe edited in game since): adopt
assert.strictEqual(s.status, 'synced'); assert.ok(s.adopt && s.adopt.active.i === 1);
s = S({ loadout_rev: 777, loadout_game_rev: 6000 });                                  // nothing new
assert.strictEqual(s.status, 'synced'); assert.strictEqual(s.adopt, null);
gameFile({ format: 1, rev: 7000, launcher_rev: 900, active: { kind: 'custom', i: 1 }, custom: w.custom });   // in-game edit superseded our rev
s = S({ loadout_rev: 800, loadout_game_rev: 6000 });
assert.strictEqual(s.status, 'synced'); assert.ok(s.adopt);

// A past build's game file was cut off after '"custom":[' (ext lj_body bug): not usable, nothing is adopted or overwritten, the error is reported; the fixed game
// rewrites a whole file on its first tick and the launcher adopts it by itself (no cached state to clear)
const cutFile = JSON.stringify({ format: 1, rev: 8000, launcher_rev: 777, active: { kind: 'custom', i: 1 }, custom: w.custom });
gameFile(cutFile.slice(0, cutFile.indexOf('"custom":[') + 10));
s = S({ loadout_rev: 777, loadout_game_rev: 7000 });
assert.strictEqual(s.status, 'pending'); assert.strictEqual(s.adopt, null); assert.strictEqual(s.write, false); assert.deepStrictEqual(s.patch, {}); assert.strictEqual(s.error, 'unreadable');
s = S({ loadout_game_rev: 7000 });
assert.strictEqual(s.status, 'waiting'); assert.strictEqual(s.error, 'unreadable');
gameFile({ format: 1, rev: 8100, launcher_rev: 777, active: { kind: 'custom', i: 4 }, custom: w.custom });   // the fixed game's file
s = S({ loadout_rev: 777, loadout_game_rev: 7000 });
assert.strictEqual(s.status, 'synced'); assert.ok(s.adopt && s.adopt.active.i === 4); assert.strictEqual(s.error, undefined); assert.deepStrictEqual(s.patch, { loadout_game_rev: 8100 });

fs.rmSync(dir, { recursive: true, force: true });
console.log('loadoutfile-test OK');
