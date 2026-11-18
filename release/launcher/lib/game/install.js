/**
 * @file Mod installation, repair and slim-client generation.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const linux = require('../linux');
const PS = require('../../src/playstate');
const upd = require('../update');
const { exists, readTrim, withTimeout, copyFileP, noProgress, sameLocation } = require('./util');
const { cleanName, nameToken } = require('./identity');
const { getDllTarget, verifyWinmm } = require('./dll');

const MARKER = 't2r-installing.txt'; // game folder: an install that has not finished
const SLIM_OUT_BYTES = 1024 * 1024 * 1024; // t2r-slim.exe writes the full winmm.dll (~850 MB) next to the old one

/**
 * Recursively list files below a directory.
 * @param {string} dir
 * @param {string[]} [out]
 * @returns {string[]}
 */
function listFiles(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) listFiles(p, out);
    else out.push(p);
  }
  return out;
}

// Runs t2r-slim.exe, parsing its "progress <done> <total>" lines (an older exe prints none: then a time-based estimate drives the bar).
// opts: { progress(p), onChild(child), timeout }. Resolves { code, stderr }.
/**
 * Run the slim-client builder and collect its result.
 * @param {string} exe
 * @param {string[]} args
 * @param {object} [opts]
 * @returns {Promise<object>}
 */
function runSlim(exe, args, opts = {}) {
  const progress = opts.progress || noProgress;
  return new Promise((resolve) => {
    const t0 = Date.now();
    let child,
      sawProgress = false,
      buf = '',
      stderr = '',
      done = false;
    const finish = (r) => {
      if (done) return;
      done = true;
      clearInterval(est);
      clearTimeout(to);
      resolve(r);
    };
    try {
      child = spawn(exe, args, {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        ...(opts.spawnOpts || {}),
      });
    } catch (e) {
      return resolve({ code: -1, stderr: String(e.message) });
    }
    if (opts.onChild) opts.onChild(child);
    const emit = (pct, eta) =>
      progress({
        phase: 'play-slim',
        label: 'Preparing the mod from your game files (one time per update)',
        unit: 'pct',
        done: pct,
        total: 100,
        eta,
      });
    const est = setInterval(() => {
      if (!sawProgress && Date.now() - t0 > 3000)
        emit(Math.round(PS.estimate(Date.now() - t0) * 100), null);
    }, 1000);
    const to = setTimeout(
      () => {
        try {
          child.kill();
        } catch {}
      },
      opts.timeout || 15 * 60 * 1000,
    );
    emit(0, null);
    child.stdout.on('data', (d) => {
      buf += d.toString('utf8');
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const p = PS.parseSlimLine(buf.slice(0, i).trim());
        buf = buf.slice(i + 1);
        if (p) {
          sawProgress = true;
          emit(Math.floor((p.done * 100) / p.total), PS.eta(p.done, p.total, Date.now() - t0));
        }
      }
    });
    child.stderr.on('data', (d) => {
      stderr += d.toString('utf8');
      if (stderr.length > 8000) stderr = stderr.slice(-8000);
    });
    child.on('error', (e) => finish({ code: -1, stderr: String(e.message) }));
    child.on('close', (code) => finish({ code, stderr }));
  });
}

/**
 * Write the in-progress install marker, translating permission failures.
 * @param {string} game
 * @returns {string}
 */
function writeInstallMarker(game) {
  // not-yet-complete marker: while it exists the mod counts as not installed, so a cut-off install is redone instead of trusted
  const marker = path.join(game, MARKER);
  try {
    fs.writeFileSync(marker, new Date().toISOString() + '\n');
  } catch (e) {
    if (['EROFS', 'EPERM', 'EACCES'].includes(e && e.code)) {
      const x = new Error(
        `The launcher cannot write to the game folder ${game} (it is read-only, or Windows / an antivirus blocks changes there). Make the folder writable (Properties > untick Read-only; or run the launcher as administrator if the game is in Program Files), then press Play again.`,
      );
      x.cause = e;
      x.code = e.code;
      x.t2rExplained = true;
      throw x;
    }
    throw upd.explainError(e, marker);
  }
  return marker;
}

/**
 * Preserve a foreign winmm.dll once before replacing it.
 * @param {string} dst
 * @returns {void}
 */
function preserveForeignDll(dst) {
  if (!exists(dst) || exists(dst + '.t2r-original')) return;
  // keep a foreign winmm.dll (another mod) once; an older T2R build is just replaced
  let isT2R = false;
  try {
    getDllTarget(fs.readFileSync(dst));
    isT2R = true;
  } catch {}
  if (!isT2R) fs.copyFileSync(dst, dst + '.t2r-original');
}

/**
 * Validate inputs and prepare the install destination.
 * @param {string} clientDir
 * @param {object} cfg
 * @returns {object}
 */
function prepareInstall(clientDir, cfg) {
  const game = cfg.game_dir;
  const dst = path.join(game, 'winmm.dll');
  const src = path.join(clientDir, 'winmm.dll');
  if (!exists(src))
    throw new Error(
      'winmm.dll is missing from the downloaded client files. Press REPAIR INSTALL in Settings > Files.',
    );
  // client folder == game folder (or the same file by a link): t2r-slim would rebuild the client's own winmm.dll in place, so the next update
  // check sees a different hash, downloads the slim file over the game's winmm.dll again and the mod never loads
  if (sameLocation(clientDir, game) || sameLocation(src, dst))
    throw new Error(
      'The client files folder is the game folder (or shares winmm.dll with it). Open Settings > Files, clear the client folder (use the default), then press Update client and Play again.',
    );
  if (upd.hasPendingUpdate(clientDir))
    throw new Error(
      'The last update did not finish (the client files are half old, half new). Press Update client, then play again.',
    );
  // leftovers of an earlier install that was cut off (killed launcher, power loss): never reused, never left to fill the drive
  for (const x of [dst + '.tmp', dst + '.t2r-new']) {
    try {
      fs.unlinkSync(x);
    } catch {}
  }
  const marker = writeInstallMarker(game);
  const slimDat = path.join(clientDir, 't2r-slim.dat');
  const slimNeeded = exists(slimDat);
  upd.ensureSpace(game, slimNeeded ? SLIM_OUT_BYTES : fs.statSync(src).size, 'the mod files');
  preserveForeignDll(dst);
  return { game, dst, src, marker, slimDat, slimNeeded };
}

/**
 * Run the slim-client builder for this platform.
 * @param {object} options
 * @returns {Promise<void>}
 */
async function buildSlimMod({ clientDir, game, src, dst, slimDat, extra, log, progress, onChild }) {
  const slimExe = path.join(clientDir, 'slim', 't2r-slim.exe');
  if (!exists(slimExe)) throw new Error('slim\\t2r-slim.exe is missing from the client files.');
  log('Preparing the mod from your game files (one time per update, about a minute) ...');
  let r;
  if ((extra.platform || process.platform) === 'linux') {
    // t2r-slim.exe is a Windows tool: run under Proton (in the Steam helper's own prefix), same progress lines
    const sc = linux.slimCommand({
      clientDir,
      game,
      src,
      dat: slimDat,
      dst,
      dataDir: extra.userData,
      deps: extra.linuxDeps,
    });
    r = await runSlim(sc.cmd, sc.args, {
      progress,
      onChild,
      spawnOpts: { env: sc.env, cwd: sc.cwd },
    });
  } else
    r = await runSlim(slimExe, [src, slimDat, game, dst], {
      progress,
      onChild,
    });
  try {
    fs.unlinkSync(dst + '.tmp');
  } catch {} // t2r-slim's own temp copy (up to ~850 MB): it removes it itself unless it was killed
  if (r.code !== 0) {
    const why = (r.stderr.trim().split(/\r?\n/).pop() || `exit code ${r.code}`).replace(
      /^t2r-slim: /,
      '',
    );
    const space = /space|ENOSPC|error 112|disk full|cannot create/i.test(why),
      run = /running|error 5\b|error 32\b|denied|being used/i.test(why);
    throw new Error(
      space && run
        ? `Could not prepare the mod from your game files: ${why} (the drive of the game folder is probably full: free about 1 GB and try again) (close the game and the Steam helper, wait for the antivirus scan to finish, then try again)`
        : space
          ? `Could not prepare the mod from your game files: ${why} (the drive of the game folder is probably full: free about 1 GB and try again)`
          : run
            ? `Could not prepare the mod from your game files: ${why} (close the game and the Steam helper, wait for the antivirus scan to finish, then try again)`
            : `Could not prepare the mod from your game files: ${why}`,
    );
  }
}

/**
 * Copy the shipped mod files into the game folder.
 * @param {object} options
 * @returns {Promise<void>}
 */
/**
 * Do two files differ? Size first, then the first and last 64 KB. part1.dat keeps its size from build to build (only its data and the 16-byte
 * build id at the end change), so a size-only check left an older build's part1.dat in the game folder and the mod switched Bookstore off.
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
function filesDiffer(a, b) {
  let fa, fb;
  try {
    const sa = fs.statSync(a).size;
    if (sa !== fs.statSync(b).size) return true;
    const n = Math.min(65536, sa);
    fa = fs.openSync(a, 'r');
    fb = fs.openSync(b, 'r');
    const ba = Buffer.alloc(n);
    const bb = Buffer.alloc(n);
    for (const pos of n ? [0, sa - n] : []) {
      fs.readSync(fa, ba, 0, n, pos);
      fs.readSync(fb, bb, 0, n, pos);
      if (!ba.equals(bb)) return true;
    }
    return false;
  } catch {
    return true;
  } finally {
    if (fa !== undefined) fs.closeSync(fa);
    if (fb !== undefined) fs.closeSync(fb);
  }
}

async function copyModJobs({ clientDir, game, src, dst, slimDat, progress }) {
  // the files to copy, counted first so the bar has a total (bytes)
  const ext = path.join(clientDir, 't2r-ext.dll');
  const mp = path.join(clientDir, 'tlou-ii-mp');
  const jobs = []; // [src, dst]
  if (!exists(slimDat)) jobs.push([src, dst]);
  if (exists(ext)) jobs.push([ext, path.join(game, 't2r-ext.dll')]);
  if (exists(mp))
    for (const f of listFiles(mp))
      jobs.push([f, path.join(game, 'tlou-ii-mp', path.relative(mp, f))]);
  // Map data shipped in the client (t2r-maps/part1/part1.dat, Bookstore) goes to the game folder too; the ext reads it there
  const maps = path.join(clientDir, 't2r-maps');
  if (exists(maps))
    for (const f of listFiles(maps)) {
      const d = path.join(game, 't2r-maps', path.relative(maps, f));
      if (!exists(d) || filesDiffer(f, d)) jobs.push([f, d]);
    }
  const total = jobs.reduce((a, j) => a + fs.statSync(j[0]).size, 0);
  let done = 0,
    n = 0;
  const t0 = Date.now();
  const label = 'Installing mod files into the game folder';
  progress({
    phase: 'play-install',
    label,
    unit: 'bytes',
    done: 0,
    total,
    files: jobs.length,
    filesDone: 0,
  });
  let lastEmit = 0;
  for (const [s, d] of jobs) {
    fs.mkdirSync(path.dirname(d), { recursive: true });
    fs.mkdirSync(path.dirname(d), { recursive: true });
    await copyFileP(s, d, (b) => {
      done += b;
      const now = Date.now();
      if (now - lastEmit > 200) {
        lastEmit = now;
        progress({
          phase: 'play-install',
          label,
          unit: 'bytes',
          done,
          total,
          files: jobs.length,
          filesDone: n,
          eta: PS.eta(done, total, now - t0),
        });
      }
    });
    n++;
  }
  progress({
    phase: 'play-install',
    label,
    unit: 'bytes',
    done: total,
    total,
    files: jobs.length,
    filesDone: n,
  });
}

/**
 * Verify the installed DLL and write the version, feature flags and token.
 * @param {object} options
 * @returns {Promise<void>}
 */
async function finalizeInstall({ clientDir, cfg, game, dst, src, slimNeeded, marker, progress }) {
  // every step below has its own label (the bar used to sit at "100%" while they ran); the file calls are async and cut off after 30 s
  const step = (text) =>
    progress({
      phase: 'play-install',
      label: text,
      unit: 'none',
      done: 0,
      total: 0,
    });
  step('Checking the installed mod file');
  // the installed winmm.dll must be whole: when it is not, it is removed (the previous one restored) rather than left to crash the game
  const wv = await withTimeout(
    Promise.resolve().then(() => verifyWinmm(dst, slimNeeded ? 0 : fs.statSync(src).size)),
    30000,
    'Checking winmm.dll',
  );
  if (!wv.ok) {
    try {
      fs.unlinkSync(dst);
    } catch {}
    try {
      if (exists(dst + '.t2r-original')) fs.copyFileSync(dst + '.t2r-original', dst);
    } catch {}
    throw new Error(
      `The mod file winmm.dll in the game folder is damaged (${wv.why}) and was removed. Press REPAIR INSTALL in Settings > Files, then Play again.`,
    );
  }
  step('Writing the mod version and settings');
  const ver = path.join(clientDir, 'version.txt');
  if (exists(ver))
    await withTimeout(
      fs.promises.copyFile(ver, path.join(game, 't2r-version.txt')),
      30000,
      'Writing t2r-version.txt',
    );
  try {
    fs.unlinkSync(marker);
  } catch {}
  await syncFeatureFlags(clientDir, game);
  step('Writing your player name');
  writeToken(cfg, cleanName(os.userInfo().username));
}

// Baked-in feature flags: copied when the client ships them, removed when not. Also run on every Play (lib/game/play.js): a
// client update that only adds or drops a flag left the mod "current", so the install - and this copy - never ran (a game ran without t2r-melee-duel.txt on the test build)
const FEATURE_FLAGS = [
  't2r-uc4-downed.txt',
  't2r-uc4-own.txt',
  't2r-faction-looks.txt',
  't2r-faction-guns.txt',
  't2r-melee-duel.txt',
  't2r-flashlight-puppets.txt',
  't2r-no-flashlight.txt', // A live client shipped it, but only this list reaches the game folder (flashlights stayed on)
];
// test-only switches an older test build may have left in a player's game folder: removed on every sync
const STALE_TEST_FLAGS = [
  't2r-friendly-fire.txt',
  't2r-no-joel-mm.txt',
  't2r-debug-coins.txt',
  't2r-tune.txt',
  't2r-no-saves.txt',
];
async function syncFeatureFlags(clientDir, game) {
  for (const flag of FEATURE_FLAGS) {
    const s = path.join(clientDir, flag),
      d = path.join(game, flag);
    if (exists(s)) await withTimeout(fs.promises.copyFile(s, d), 30000, `Writing ${flag}`);
    else {
      try {
        fs.unlinkSync(d);
      } catch {}
    }
  }
  for (const flag of STALE_TEST_FLAGS) {
    try {
      fs.unlinkSync(path.join(game, flag));
    } catch {}
  }
}

/**
 * Install or repair the multiplayer mod into the client directory.
 * @param {string} clientDir
 * @param {object} cfg
 * @param {Function} log
 * @param {Function} [progress]
 * @param {Function|null} [onChild]
 * @param {object} [extra]
 * @returns {Promise<object>}
 */
async function installMod(clientDir, cfg, log, progress = noProgress, onChild = null, extra = {}) {
  const p = prepareInstall(clientDir, cfg);
  if (exists(p.slimDat))
    await buildSlimMod({
      clientDir,
      game: p.game,
      src: p.src,
      dst: p.dst,
      slimDat: p.slimDat,
      extra,
      log,
      progress,
      onChild,
    });
  await copyModJobs({
    clientDir,
    game: p.game,
    src: p.src,
    dst: p.dst,
    slimDat: p.slimDat,
    progress,
  });
  await finalizeInstall({
    clientDir,
    cfg,
    game: p.game,
    dst: p.dst,
    src: p.src,
    slimNeeded: p.slimNeeded,
    marker: p.marker,
    progress,
  });
}

/**
 * Write the identity token used by the mod.
 * @param {object} cfg
 * @param {string} name
 * @returns {void}
 */
function writeToken(cfg, name) {
  fs.writeFileSync(
    path.join(cfg.game_dir, 'tlou-ii-mp.json'),
    JSON.stringify({ token: nameToken(name, cfg.token_id) }),
  );
}

// The files the game cannot start the mod without. An antivirus often removes (or truncates) a freshly copied winmm.dll / t2r-ext.dll a second
// or two later (same check as Confirm-ModFiles in T2R-Play.ps1): returns the names that are missing or whose size differs from the shipped one.
/**
 * List expected mod files that are missing or stale.
 * @param {string} clientDir
 * @param {string} gameDir
 * @returns {string[]}
 */
function missingModFiles(clientDir, gameDir) {
  const out = [];
  if (!exists(path.join(gameDir, 'winmm.dll'))) out.push('winmm.dll');
  const shipExt = path.join(clientDir, 't2r-ext.dll'),
    gameExt = path.join(gameDir, 't2r-ext.dll');
  if (exists(shipExt)) {
    if (!exists(gameExt)) out.push('t2r-ext.dll');
    else if (fs.statSync(shipExt).size !== fs.statSync(gameExt).size)
      out.push('t2r-ext.dll (damaged)');
  }
  const maps = path.join(clientDir, 't2r-maps');
  if (exists(maps))
    for (const f of listFiles(maps)) {
      const d = path.join(gameDir, 't2r-maps', path.relative(maps, f));
      if (!exists(d) || filesDiffer(f, d))
        out.push('t2r-maps/' + path.relative(maps, f));
    }
  return out;
}

/**
 * Check whether the installed mod matches the configured target.
 * @param {string} clientDir
 * @param {object} cfg
 * @returns {boolean}
 */
function modCurrent(clientDir, cfg) {
  if (sameLocation(clientDir, cfg.game_dir)) return false; // prepareInstall then explains it
  if (missingModFiles(clientDir, cfg.game_dir).length) return false;
  if (exists(path.join(cfg.game_dir, MARKER))) return false; // an install was cut off
  if (upd.hasPendingUpdate(clientDir)) return false;
  // an unslimmed client ships the exact winmm.dll: a different size in the game folder = cut off / replaced (Steam verify, another mod)
  try {
    const sw = path.join(clientDir, 'winmm.dll');
    if (
      !exists(path.join(clientDir, 't2r-slim.dat')) &&
      fs.statSync(sw).size !== fs.statSync(path.join(cfg.game_dir, 'winmm.dll')).size
    )
      return false;
  } catch {}
  const v = readTrim(path.join(clientDir, 'version.txt'));
  if (!v) return true;
  const inst = path.join(cfg.game_dir, 't2r-version.txt');
  if (!exists(inst)) return false;
  return v === readTrim(inst);
}

module.exports = {
  MARKER,
  SLIM_OUT_BYTES,
  listFiles,
  runSlim,
  installMod,
  syncFeatureFlags,
  writeToken,
  missingModFiles,
  modCurrent,
  copyModJobs,
};
