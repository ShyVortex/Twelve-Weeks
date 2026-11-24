'use strict';
// node test/linux-test.js : the Linux support (lib/linux.js + the Linux branch of lib/game.js play()) against fixture folders in the temp dir.
// Nothing here touches a real Steam / game folder: every path is a scratch fixture, spawn is faked.
const assert = require('assert');
const fs = require('fs');
const mkTmp = require('./tmp');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');
const linux = require('../lib/linux');
const game = require('../lib/game');

const root = mkTmp('f2lx-');
const mk = (...p) => { const d = path.join(root, ...p); fs.mkdirSync(d, { recursive: true }); return d; };
const put = (f, t = '') => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, t); return f; };

(async () => {
  // ---- VDF
  const v = linux.parseVdf('"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"/home/u/.local/share/Steam"\n\t\t"apps"\n\t\t{\n\t\t\t"228980"\t\t"1"\n\t\t}\n\t}\n\t"1" { "path" "/run/media/mmcblk0p1" }\n}\n');
  assert.deepStrictEqual(linux.parseLibraryFolders('"libraryfolders" { "0" { "path" "/a b/c" } "1" { "path" "/run/media/mmcblk0p1" } }'), ['/a b/c', '/run/media/mmcblk0p1']);
  assert.strictEqual(linux.vget(v, 'LibraryFolders', '0', 'PATH'), '/home/u/.local/share/Steam');
  assert.deepStrictEqual(linux.parseLibraryFolders('"libraryfolders" { "0" "/old/format" }'), ['/old/format']);
  assert.strictEqual(linux.parseVdf('"a" { "b" "x\\\\y\\"z" }').a.b, 'x\\y"z');

  // ---- Steam roots, libraries (SD card), game folder through the appmanifest
  const home = mk('home');
  const steam = mk('home', '.local', 'share', 'Steam');
  const sd = mk('sdcard');
  put(path.join(steam, 'steamapps', 'libraryfolders.vdf'), `"libraryfolders" { "0" { "path" "${steam.replace(/\\/g, '\\\\')}" } "1" { "path" "${sd.replace(/\\/g, '\\\\')}" } }`);
  put(path.join(sd, 'steamapps', 'appmanifest_2531310.acf'), '"AppState" { "appid" "2531310" "installdir" "The Last of Us Part II" }');
  const gdir = mk('sdcard', 'steamapps', 'common', 'The Last of Us Part II');
  put(path.join(gdir, 'tlou-ii.exe'), 'MZ');
  mk('sdcard', 'steamapps', 'common', 'The Last of Us Part II Remastered');        // a folder without the exe is not a game folder
  assert.deepStrictEqual(linux.steamRoots(home), [steam]);
  assert.deepStrictEqual(linux.findGameDirs(home), [gdir]);
  assert.strictEqual(linux.findGameDirs(mk('emptyhome')).length, 0);
  // the game is found without the appmanifest too (folder name scan), and a symlinked ~/.steam/steam is not listed twice
  fs.unlinkSync(path.join(sd, 'steamapps', 'appmanifest_2531310.acf'));
  assert.deepStrictEqual(linux.findGameDirs(home), [gdir]);
  try { fs.mkdirSync(path.join(home, '.steam')); fs.symlinkSync(steam, path.join(home, '.steam', 'steam'), 'junction'); assert.strictEqual(linux.steamRoots(home).length, 1); } catch (e) { if (e.code !== 'EPERM') throw e; }
  // Flatpak Steam
  const fhome = mk('fhome');
  const fsteam = mk('fhome', '.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam');
  assert.deepStrictEqual(linux.steamRoots(fhome), [fsteam]);
  assert.strictEqual(linux.steamLaunchCommand(fhome, mk('bin-flatpak')).cmd, 'xdg-open');   // neither steam nor flatpak on PATH -> the URL handler
  const binf = mk('bin-fp'); put(path.join(binf, 'flatpak'));
  assert.deepStrictEqual(linux.steamLaunchCommand(fhome, binf), { cmd: 'flatpak', args: ['run', 'com.valvesoftware.Steam', 'steam://rungameid/2531310'] });
  const bins = mk('bin-st'); put(path.join(bins, 'steam'));
  assert.deepStrictEqual(linux.steamLaunchCommand(home, bins), { cmd: 'steam', args: ['steam://rungameid/2531310'] });

  // ---- Proton selection
  const tool = (dir, name) => { put(path.join(dir, name, 'proton'), '#!/bin/sh'); return path.join(dir, name); };
  const common = path.join(steam, 'steamapps', 'common');
  const p9 = tool(common, 'Proton 9.0 (Beta)'), p10 = tool(common, 'Proton 10.0'), pexp = tool(common, 'Proton - Experimental');
  const ge = tool(path.join(steam, 'compatibilitytools.d'), 'GE-Proton9-20');
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(pexp));                                   // no mapping: Experimental
  const cfgv = path.join(steam, 'config', 'config.vdf');
  put(cfgv, '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "0" { "name" "proton_9" } "2531310" { "name" "proton_10" } } } } } }');
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(p10));                                     // the game's own mapping first
  put(cfgv, '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "2531310" { "name" "GE-Proton9-20" } } } } } }');
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(ge));                                      // a custom tool by its folder name
  put(cfgv, '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "2531310" { "name" "proton_experimental" } } } } } }');
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(pexp));
  put(cfgv, '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "0" { "name" "proton_hotfix" } } } } } }');   // hotfix not installed: falls to Experimental
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(pexp));
  fs.rmSync(pexp, { recursive: true });
  assert.strictEqual(fs.realpathSync(linux.findProton(home)), fs.realpathSync(p10));   // no Experimental left: newest "Proton N" (10.0 beats 9.0 numerically)
  assert.ok(linux.naturalCmp('Proton 10.0', 'Proton 9.0') > 0);
  assert.strictEqual(linux.findProton(mk('nohome')), null);
  assert.ok(p9);

  // ---- paths, helper arguments, environment
  assert.strictEqual(linux.winPath('/home/u/The Last of Us Part II/x.txt'), process.platform === 'win32' ? linux.winPath('/home/u/The Last of Us Part II/x.txt') : 'Z:\\home\\u\\The Last of Us Part II\\x.txt');
  const ha = linux.helperArgs({ exe: '/c/steam/t2r-steam.exe', nameFile: '/d/name.txt', server: '1.2.3.4:7001', tokenFile: '/g/tlou-ii-mp.json', aliveFile: '/g/t2r-alive.txt', logFile: '/d/t2r-steam.log' });
  assert.ok(ha.includes('--alive-file') && ha[ha.indexOf('--alive-file') + 1].startsWith('Z:') && ha.includes('tlou-ii.exe') && ha.includes('7777'));
  const env = linux.protonEnv('/p', '/prefix', home, { LD_PRELOAD: 'x', SteamOverlayGameId: '2531310', PATH: '/bin', SteamAppId: '2531310' });
  assert.strictEqual(env.SteamAppId, '480'); assert.strictEqual(env.SteamGameId, '480'); assert.strictEqual(env.STEAM_COMPAT_APP_ID, '480');
  assert.strictEqual(env.LD_PRELOAD, undefined); assert.strictEqual(env.SteamOverlayGameId, undefined); assert.strictEqual(env.STEAM_COMPAT_DATA_PATH, '/prefix');

  // ---- /proc: the game, but not our helper (its command line carries "tlou-ii.exe" too)
  const proc = mk('proc');
  const pr = (pid, cmd) => put(path.join(proc, String(pid), 'cmdline'), cmd.split(' ').join('\0') + '\0');
  pr(100, 'Z:\\home\\u\\steam\\tlou-ii.exe'); pr(101, 'reaper SteamLaunch AppId=2531310 -- proton waitforexitandrun /x/tlou-ii.exe');
  pr(102, 'Z:\\home\\u\\client\\steam\\t2r-steam.exe name.txt tlou-ii.exe --server 1.2.3.4:7001'); pr(103, '/x/proton run /c/steam/t2r-steam.exe n tlou-ii.exe');
  pr(104, 'bash'); fs.mkdirSync(path.join(proc, 'self'));
  assert.deepStrictEqual(linux.gameProcs(proc, -1).map((p) => p.pid), [100, 101]);
  assert.deepStrictEqual(linux.helperProcs(proc).map((p) => p.pid), [102, 103]);

  // ---- Wine registry
  const reg0 = 'WINE REGISTRY Version 2\n;; All keys relative to \\\\User\\\\S-1-5-21\n\n#arch=win64\n\n[Software\\\\Wine\\\\DllOverrides] 1700000000\n#time=1da\n"dxgi"="native"\n\n[Software\\\\Wine\\\\X11 Driver] 1700000001\n#time=1db\n"A"="b"\n';
  let reg1 = linux.patchUserReg(reg0, linux.REG_EDITS, 1800000000);
  assert.ok(/\[Software\\\\Wine\\\\DllOverrides\] 1700000000\n#time=1da\n"winmm"="native,builtin"\n"dxgi"="native"/.test(reg1), reg1);
  assert.ok(reg1.includes('[Software\\\\Naughty Dog\\\\The Last of Us Part II] 1800000000\n#time=0\n"ShowLauncher"=dword:00000000'));
  assert.ok(reg1.includes('[Software\\\\Wine\\\\X11 Driver] 1700000001\n#time=1db\n"A"="b"'));      // other sections untouched
  assert.strictEqual(linux.patchUserReg(reg1, linux.REG_EDITS, 1900000000), reg1);                    // idempotent
  assert.ok(linux.patchUserReg(reg0.replace('"dxgi"="native"', '"winmm"="builtin"'), linux.REG_EDITS).includes('"winmm"="native,builtin"'));   // an existing value is replaced
  assert.ok(!linux.patchUserReg(reg0.replace('"dxgi"="native"', '"winmm"="builtin"'), linux.REG_EDITS).includes('"winmm"="builtin"'));
  assert.ok(linux.patchUserReg('', linux.REG_EDITS, 1).includes('"winmm"="native,builtin"'));         // an empty file
  const reg2 = linux.patchUserReg(reg0.replace(/\n/g, '\r\n'), linux.REG_EDITS, 1);
  assert.ok(reg2.includes('"winmm"="native,builtin"\r\n"dxgi"'));                                       // CRLF kept

  // ---- prefix preparation
  assert.strictEqual(linux.userRegFor(gdir), path.join(sd, 'steamapps', 'compatdata', '2531310', 'pfx', 'user.reg'));
  assert.strictEqual(linux.userRegFor(mk('elsewhere', 'Game')), null);
  let r = linux.prepareGamePrefix(gdir, { procDir: mk('noproc') });
  assert.ok(!r.ok && /never been started through Steam/.test(r.reason));                               // no prefix yet
  const regFile = put(linux.userRegFor(gdir), reg0);
  r = linux.prepareGamePrefix(gdir, { procDir: proc });
  assert.ok(!r.ok && /running/.test(r.reason) && fs.readFileSync(regFile, 'utf8') === reg0);            // game running: untouched
  r = linux.prepareGamePrefix(gdir, { procDir: mk('noproc2') });
  assert.deepStrictEqual([r.ok, r.changed], [true, true]);
  assert.ok(fs.readFileSync(regFile, 'utf8').includes('"winmm"="native,builtin"') && fs.readFileSync(regFile + '.t2r-backup', 'utf8') === reg0);
  assert.deepStrictEqual(linux.prepareGamePrefix(gdir, { procDir: mk('noproc3') }), { ok: true, changed: false, reg: regFile });
  // a game moved to the SD card keeps its prefix in the internal library: found there
  const sd2 = mk('sdcard2');
  const gdir2 = mk('sdcard2', 'steamapps', 'common', 'The Last of Us Part II');
  put(path.join(gdir2, 'tlou-ii.exe'), 'MZ');
  const home2 = mk('home2');
  const steam2 = mk('home2', '.local', 'share', 'Steam');
  put(path.join(steam2, 'steamapps', 'libraryfolders.vdf'), `"libraryfolders" { "0" { "path" "${steam2.replace(/\\/g, '\\\\')}" } "1" { "path" "${sd2.replace(/\\/g, '\\\\')}" } }`);
  r = linux.prepareGamePrefix(gdir2, { procDir: mk('noproc4'), home: home2 });
  assert.ok(!r.ok && /never been started through Steam/.test(r.reason) && r.looked.length === 2, JSON.stringify(r));
  const internalReg = put(path.join(steam2, 'steamapps', 'compatdata', '2531310', 'pfx', 'user.reg'), reg0);
  r = linux.prepareGamePrefix(gdir2, { procDir: mk('noproc5'), home: home2 });
  assert.deepStrictEqual([r.ok, r.changed, r.reg], [true, true, internalReg]);
  assert.ok(fs.readFileSync(internalReg, 'utf8').includes('"winmm"="native,builtin"'));
  // the game's own library wins once it has a prefix; of two elsewhere, the newest
  const ownReg = put(linux.userRegFor(gdir2), reg0);
  assert.strictEqual(linux.findUserReg(gdir2, { home: home2 }).reg, ownReg);
  fs.unlinkSync(ownReg);
  const sd3 = mk('sdcard3');
  put(path.join(steam2, 'steamapps', 'libraryfolders.vdf'), `"libraryfolders" { "0" { "path" "${steam2.replace(/\\/g, '\\\\')}" } "1" { "path" "${sd2.replace(/\\/g, '\\\\')}" } "2" { "path" "${sd3.replace(/\\/g, '\\\\')}" } }`);
  const newer = put(path.join(sd3, 'steamapps', 'compatdata', '2531310', 'pfx', 'user.reg'), reg0);
  fs.utimesSync(internalReg, new Date(1e12), new Date(1e12));
  assert.strictEqual(linux.findUserReg(gdir2, { home: home2 }).reg, newer);

  // ---- launch options (informational)
  put(path.join(steam, 'userdata', '1', 'config', 'localconfig.vdf'), '"UserLocalConfigStore" { "Software" { "valve" { "Steam" { "apps" { "2531310" { "LaunchOptions" "WINEDLLOVERRIDES=\\"winmm=n,b\\" %command%" } } } } } }');
  assert.deepStrictEqual(linux.launchOptions(home), ['WINEDLLOVERRIDES="winmm=n,b" %command%']);

  // ---- the whole Play flow with a faked Proton / Steam
  const client = mk('client');
  put(path.join(client, 'winmm.dll'), 'dll'); put(path.join(client, 't2r-ext.dll'), 'ext'); put(path.join(client, 'version.txt'), 'v-test\n');
  put(path.join(client, 'steam', 't2r-steam.exe'), 'exe'); put(path.join(client, 'steam', 'steam_appid.txt'), '480');
  const udata = mk('userdata');
  const spawned = [];
  const fakeSpawn = (cmd, args, opts) => {
    const c = new EventEmitter(); c.pid = 4242; c.unref = () => {}; spawned.push({ cmd, args, env: opts.env, cwd: opts.cwd });
    const nameFile = args[args.indexOf('run') + 2];                              // helperArgs: exe, nameFile, ...
    setImmediate(() => { const nf = args[2].replace(/^Z:/, '').replace(/\\/g, '/'); try { fs.writeFileSync(process.platform === 'win32' ? args[2].replace(/^Z:/, '') : nf, 'SteamName\n'); } catch {} });
    void nameFile;
    return c;
  };
  const launched = [];
  const fakeLaunch = (cmd, args) => { const c = new EventEmitter(); c.unref = () => {}; launched.push([cmd, args]); put(path.join(root, 'noproc4', '777', 'cmdline'), 'Z:\\g\\tlou-ii.exe\0'); setImmediate(() => c.emit('spawn')); return c; };
  put(path.join(steam, 'steamapps', 'common', 'Proton - Experimental', 'proton'), '#!/bin/sh');
  fs.rmSync(cfgv, { force: true });
  const logs = [];
  const cfg = { game_dir: gdir, token_id: '0123456789abcdef01234567', custom_name: '' };
  // winmm.dll needs the server address sites to patch: a fixture dll
  const dllBuf = Buffer.alloc(0x60000);
  for (const o of [0x56402, 0x58725]) dllBuf.writeUInt32LE((Buffer.from([127, 0, 0, 1]).readUInt32LE(0) ^ 0x5A3C9E17) >>> 0, o);
  for (const o of [0x563F1, 0x58742]) dllBuf.writeUInt16LE(7001, o);
  fs.writeFileSync(path.join(client, 'winmm.dll'), dllBuf);
  const res = await game.play({ clientDir: client, cfg, server: '127.0.0.1:7001', skipCheck: true, log: (m) => logs.push(m), userData: udata, platform: 'linux',
    linuxDeps: { home, procDir: mk('noproc4'), spawn: fakeSpawn, launch: fakeLaunch, pollMs: 20 } });
  assert.strictEqual(res.name, 'SteamName'); assert.strictEqual(res.windowUp, true);
  assert.ok(fs.existsSync(path.join(gdir, 'winmm.dll')) && fs.existsSync(path.join(gdir, 't2r-ext.dll')) && fs.readFileSync(path.join(gdir, 't2r-version.txt'), 'utf8').trim() === 'v-test');
  assert.strictEqual(fs.readFileSync(path.join(gdir, 't2r-linux.txt'), 'utf8'), 'server=127.0.0.1:7001\nhelper=external\n');
  assert.strictEqual(game.tokenName(JSON.parse(fs.readFileSync(path.join(gdir, 'tlou-ii-mp.json'), 'utf8')).token), 'SteamName');
  assert.ok(fs.existsSync(path.join(gdir, 't2r-steam', 't2r-steam.exe')));
  assert.strictEqual(spawned.length, 1);
  assert.ok(spawned[0].cmd.endsWith(path.join('Proton - Experimental', 'proton')) && spawned[0].args[0] === 'run' && spawned[0].env.SteamAppId === '480');
  assert.ok(spawned[0].env.STEAM_COMPAT_DATA_PATH.endsWith('t2r-steam-prefix'));
  assert.deepStrictEqual(launched[0][1], ['steam://rungameid/2531310']);       // (the command is steam or xdg-open, depending on the test machine's PATH)
  assert.ok(['steam', 'xdg-open', 'flatpak'].includes(launched[0][0]));
  assert.strictEqual(linux.readState(path.join(udata, 'linux-state.json')).helper_pid, 4242);
  assert.ok(logs.some((l) => /Steam helper: reached Steam/.test(l)));
  // a game that is running is refused
  await assert.rejects(game.play({ clientDir: client, cfg, server: '127.0.0.1:7001', skipCheck: true, noWait: true, log() {}, userData: udata, platform: 'linux', linuxDeps: { home, procDir: proc } }), /already running/);
  // no helper (Proton exits at once): the game still starts, without helper=external, and says why
  const failSpawn = (cmd, args, opts) => { const c = new EventEmitter(); c.pid = 4243; c.unref = () => {}; setImmediate(() => c.emit('exit', 1)); return c; };
  logs.length = 0;
  await game.play({ clientDir: client, cfg, server: '127.0.0.1:7001', skipCheck: true, noWait: true, log: (m) => logs.push(m), userData: udata, platform: 'linux',
    linuxDeps: { home, procDir: mk('noproc5'), spawn: failSpawn, launch: fakeLaunch, pollMs: 20 } });
  assert.strictEqual(fs.readFileSync(path.join(gdir, 't2r-linux.txt'), 'utf8'), 'server=127.0.0.1:7001\n');
  assert.ok(logs.some((l) => /Steam helper could not start: Proton exited at once/.test(l)));
  // no prefix yet: a clear instruction instead of a launch that cannot load the mod
  fs.rmSync(regFile);
  await assert.rejects(game.play({ clientDir: client, cfg, server: '127.0.0.1:7001', skipCheck: true, noWait: true, log() {}, userData: udata, platform: 'linux', linuxDeps: { home, procDir: mk('noproc6'), spawn: fakeSpawn, launch: fakeLaunch, pollMs: 20 } }), /never been started through Steam/);

  // ---- stopHelper only ends a t2r-steam process
  const killed = [];
  const sf = path.join(udata, 'linux-state.json');
  linux.writeState(sf, { helper_pid: 102 });
  assert.strictEqual(linux.stopHelper(sf, proc, (pid, sig) => killed.push([pid, sig])), true);
  assert.deepStrictEqual(killed, [[-102, 'SIGTERM']]);
  linux.writeState(sf, { helper_pid: 104 });                                                           // pid reused by another program
  assert.strictEqual(linux.stopHelper(sf, proc, (pid, sig) => killed.push([pid, sig])), false);
  assert.strictEqual(killed.length, 1);

  // ---- the 0xB0 probe frame of a Linux client ends with 'L' after the token
  const net = require('net');
  const got = await new Promise((resolve) => {
    const srv = net.createServer((s) => { s.once('data', (b) => { resolve(b); s.end(); srv.close(); }); });
    srv.listen(0, '127.0.0.1', () => { game.probeServer('127.0.0.1', srv.address().port, game.nameToken('Joel', '0123456789abcdef01234567'), 'v1', 800, true); });
  });
  assert.strictEqual(got[2], 0xB0);
  assert.strictEqual(got.toString('ascii', 4 + 2, 4 + 2 + 64).length, 64);
  assert.strictEqual(got[got.length - 1], 'L'.charCodeAt(0));

  fs.rmSync(root, { recursive: true, force: true });
  console.log('linux-test OK');
  process.exit(0);
})().catch((e) => { console.error(e); try { fs.rmSync(root, { recursive: true, force: true }); } catch {} process.exit(1); });
