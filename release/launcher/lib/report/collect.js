/**
 * @file Select the logs, dumps and system data that make up a report.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { TAIL, MATCH_RAW_CAP, DUMP_MAX } = require('./constants');
const { exists, newest, dumpInfo, binInfo, logIdent, judgeDump } = require('./artifacts');

/**
 * Build the report-row collector bound to one output list.
 * @param {object[]} out
 * @returns {Function}
 */
function makeAdder(out) {
  return (name, src, kind, note) => {
    try {
      const st = fs.statSync(src);
      if (st.isFile() && (kind === 'dump' || st.size > 0))
        out.push({
          name,
          src,
          size: kind === 'dump' ? st.size : Math.min(st.size, TAIL),
          mtime: st.mtimeMs,
          kind,
          note: note || (st.size > TAIL ? 'last 20 MB' : ''),
        });
      return true;
    } catch {
      return false;
    }
  };
}

/**
 * Add the always-present game log row, including the missing-file warning.
 * @param {object[]} out
 * @param {string} gdir
 * @param {Function} add
 * @returns {void}
 */
function addGameLog(out, gdir, add) {
  if (!add('t2r-ext.log', path.join(gdir || '.', 't2r-ext.log'), 'log') || !gdir) {
    if (!out.some((f) => f.name === 't2r-ext.log'))
      out.push({
        name: 't2r-ext.log',
        src: '',
        size: 0,
        kind: 'missing',
        note: gdir
          ? `not found in ${gdir} - play a match first`
          : 'game folder not set - set it in Settings > Game',
      });
  }
}

/**
 * Collect the game, client and Steam-helper logs.
 * @param {object} options
 * @param {object[]} out
 * @param {Function} add
 * @returns {string} resolved game directory, or ''
 */
function collectLogs({ gameDir, clientDir, steamLogDir, matchLogs }, out, add) {
  const gdir = gameDir && exists(gameDir) ? gameDir : '';
  addGameLog(out, gdir, add);
  if (gdir) {
    for (const x of newest(gdir, /^t2r-ext\..*log$/i, 4)
      .filter((x) => x.f.toLowerCase() !== 't2r-ext.log')
      .slice(0, 3))
      add(x.f, x.p, 'log');
    // per-match logs (ext: <game>/logs/t2r-match-<stamp>-<map>.log, newest N kept by the game): the newest `matchLogs` (default 3, the form's 'earlier' answers send
    // more) go in, within MATCH_RAW_CAP unpacked bytes in all (logs deflate ~10:1; the zip stays far below the server's 80 MB). Each is cut to its last TAIL bytes like any log.
    {
      let budget = MATCH_RAW_CAP;
      for (const x of newest(
        path.join(gdir, 'logs'),
        /^t2r-match-.*\.log$/i,
        Math.max(0, matchLogs === undefined ? 3 : matchLogs),
      )) {
        if (budget <= 0) break;
        if (add(x.f, x.p, 'log', 'one match: from the load to the post-match screens'))
          budget -= Math.min(x.st.size, TAIL);
      }
    }
    for (const f of [
      't2r-ext-boot.txt',
      't2r-sp.log',
      't2r-sp.prev.log',
      'tlou-ii-mp.log',
      't2r-version.txt',
      't2r-settings.txt',
    ])
      add(f, path.join(gdir, f), f.endsWith('.txt') ? 'text' : 'log');
  }
  if (clientDir) add('t2r-play.log', path.join(clientDir, 't2r-play.log'), 'log');
  // The Steam helper's own log (peer states, ping, packets in / out per 10 s) is the only record of whether game traffic reached this PC in a match;
  // it lives in the temp folder and was never attached, so 'the match ended 6 s after the start' could not be told from a dead P2P path. The previous run's copy too.
  {
    const sd = steamLogDir || os.tmpdir();
    add('t2r-steam.log', path.join(sd, 't2r-steam.log'), 'log');
    add('t2r-steam.prev.log', path.join(sd, 't2r-steam.prev.log'), 'log');
  }
  return gdir;
}

/**
 * Discover crash-dump candidates from the game, Documents and WER stores.
 * @param {string} gdir
 * @param {string} [docsDir]
 * @returns {object[]}
 */
function collectDumpCandidates(gdir, docsDir) {
  // crash dumps. TWO writers produce one crash's dumps, both are wanted: the game's own reporter writes <Documents>\The Last of Us
  // Part II\*.mdmp (also copied next to the exe; MiniDumpNormal, ~1 MB, no module data), WER writes %LOCALAPPDATA%\CrashDumps\tlou-ii.exe.<pid>.dmp (flags
  // 0x200121: keeps the ext's .data, i.e. the g_cdiag block; ~120 MB) and keeps its own copies under WER\ReportArchive / ReportQueue (...\AppCrash_tlou-ii.exe_*).
  const cand = [],
    seenDir = new Set();
  const addDir = (dir, re, n, wer) => {
    if (!dir || seenDir.has(dir.toLowerCase() + re)) return;
    seenDir.add(dir.toLowerCase() + re);
    for (const x of newest(dir, re, n)) {
      x.wer = wer || /\.dmp$/i.test(x.f);
      cand.push(x);
    }
  };
  if (gdir) addDir(gdir, /\.(mdmp|dmp)$/i, 3);
  if (docsDir) addDir(path.join(docsDir, 'The Last of Us Part II'), /\.mdmp$/i, 3);
  const la = process.env.LOCALAPPDATA,
    pd = process.env.ProgramData;
  if (la) addDir(path.join(la, 'CrashDumps'), /^tlou-ii.*\.(dmp|mdmp)$/i, 3, true);
  for (const root of [
    la && path.join(la, 'Microsoft', 'Windows', 'WER'),
    pd && path.join(pd, 'Microsoft', 'Windows', 'WER'),
  ].filter(Boolean)) {
    for (const q of ['ReportArchive', 'ReportQueue']) {
      let subs = [];
      try {
        subs = fs.readdirSync(path.join(root, q)).filter((n) => /tlou-ii/i.test(n));
      } catch {
        /* no such WER store */
      }
      for (const sub of subs.slice(-6)) addDir(path.join(root, q, sub), /\.(mdmp|dmp)$/i, 2, true); // never *.hdmp: a full-memory dump (GBs, every secret in the process)
    }
  }
  cand.sort((a, b) => b.st.mtimeMs - a.st.mtimeMs);
  return cand;
}

/**
 * Filter and rank crash dumps against the attached logs.
 * @param {object} options
 * @returns {{take: object[], skippedDumps: object[], primary: object|null}}
 */
function selectDumps({ cand, cur, prev, olderDumps }) {
  const fresh = Date.now() - 7 * 86400000;
  // Reports used to carry a stale dump, or a dump of an older build. A dump goes in only if its process (MiscInfo
  // ProcessCreateTime, else the file time) belongs to the session(s) of the attached ext logs and, where both are known, its pid and t2r-ext.dll build stamp
  // match the log's. The others are NOT sent (olderDumps = the player asked for old ones: those go as STALE-<name>); every skipped one is named in the meta.
  // The newest matching dump is the crash; every other matching dump of THAT crash (same pid, or without pids the same few minutes) goes with it. Copies
  // (same kind, size, pid and time: the .mdmp next to the exe vs in Documents) are sent once. WER dumps are listed first so that, if the size cap bites, they win.
  const skippedDumps = [],
    seenCopy = new Set(),
    take = [];
  let primary = null;
  for (const x of cand) {
    if (!olderDumps && x.st.mtimeMs < fresh) {
      skippedDumps.push({ name: x.f, reason: 'older than 7 days' });
      continue;
    }
    const info = dumpInfo(x.p),
      j = judgeDump(x, info, cur, prev);
    const rec = {
      name: x.f,
      pid: info.pid,
      created: j.created ? new Date(j.created).toISOString() : '',
      log: j.log,
      source: info.source,
      writer: x.wer ? 'WER' : 'game',
    };
    if (!j.ok && !olderDumps) {
      skippedDumps.push({ ...rec, reason: j.reason });
      continue;
    }
    const key = `${x.wer}|${x.st.size}|${info.pid}|${info.created}`;
    if (info.created && seenCopy.has(key)) {
      skippedDumps.push({ ...rec, reason: 'a copy of an attached dump' });
      continue;
    }
    seenCopy.add(key);
    if (j.ok && !primary) primary = { x, info, j };
    const sameCrash =
      primary &&
      j.ok &&
      (primary.info.pid && info.pid
        ? primary.info.pid === info.pid
        : Math.abs((j.created || x.st.mtimeMs) - (primary.j.created || primary.x.st.mtimeMs)) <=
          5 * 60000);
    if (j.ok && !sameCrash) {
      skippedDumps.push({
        ...rec,
        reason: 'older than the attached dump (another crash)',
      });
      continue;
    }
    if (!j.ok && olderDumps && take.filter((t) => !t.j.ok).length >= DUMP_MAX) {
      skippedDumps.push({ ...rec, reason: 'more than ' + DUMP_MAX + ' dumps' });
      continue;
    }
    take.push({ x, info, j, rec });
  }
  take.sort((a, b) => b.j.ok - a.j.ok || b.x.wer - a.x.wer || b.x.st.mtimeMs - a.x.st.mtimeMs);
  return { take, skippedDumps, primary };
}

/**
 * Attach the selected crash dumps to the report list.
 * @param {object[]} take
 * @param {Set<string>} usedNames
 * @param {Function} add
 * @param {object[]} dumps
 * @returns {void}
 */
function attachDumps(take, usedNames, add, dumps) {
  for (const { x, info, j, rec } of take) {
    let nm = j.ok ? x.f : 'STALE-' + x.f;
    if (usedNames.has(nm)) nm = (x.wer ? 'wer-' : 'game-') + nm;
    if (usedNames.has(nm)) nm = path.basename(path.dirname(x.p)).slice(0, 40) + '-' + nm;
    usedNames.add(nm);
    add(
      nm,
      x.p,
      'dump',
      !j.ok
        ? 'crash dump from another session: ' + j.reason
        : (x.wer
            ? 'WER crash dump (has the ext diagnostics block)'
            : 'game crash dump (small, no ext data)') +
            (j.log ? `, process ${info.pid || '?'}, log ${j.log}` : ''),
    );
    dumps.push({ ...rec, sent_as: nm, stale: !j.ok, reason: j.reason });
  }
}

/**
 * Add the ext's own crash file when it belongs to the selected crash.
 * @param {object} options
 * @returns {void}
 */
function collectExtCrashFile({
  gdir,
  olderDumps,
  cur,
  prev,
  primary,
  usedNames,
  add,
  dumps,
  skippedDumps,
}) {
  // the ext's own crash file (t2r-crash-<pid>-1.bin, next to the log): sent when its process is one of the attached logs' (pid, else the log's time window) and its
  // ext build equals the log's build; if a dump of another process was chosen as THE crash, the file of that other crash stays out. Only the newest matching one.
  if (!gdir) return;
  let taken = null;
  for (const x of newest(gdir, /^t2r-crash-.*\.bin$/i, 6)) {
    const bi = binInfo(x.p),
      rec = {
        name: x.f,
        pid: bi.pid,
        created: bi.created ? new Date(bi.created).toISOString() : '',
        log: '',
        source: 'ext crash file',
        writer: 'ext',
      };
    let why = '';
    if (!bi.ok) why = 'not a crash file of this ext (bad header)';
    else if (!olderDumps && x.st.mtimeMs < Date.now() - 7 * 86400000) why = 'older than 7 days';
    else {
      const j = judgeDump(x, { pid: bi.pid, created: bi.created, extStamp: 0 }, cur, prev);
      rec.log = j.log;
      const lg = j.log ? (j.log === 't2r-ext.log' ? cur : prev) : null;
      if (!j.ok) why = j.reason;
      else if (lg && lg.buildMs && bi.buildMs && lg.buildMs !== bi.buildMs)
        why = `ext build differs (file ${bi.build}, log says build ${lg.build})`;
      else if (primary && primary.info.pid && primary.info.pid !== bi.pid)
        why = `process ${bi.pid} is not the crashed process ${primary.info.pid}`;
      else if (taken) why = 'older than the attached crash file (another crash)';
    }
    if (why) {
      skippedDumps.push({ ...rec, reason: why });
      continue;
    }
    taken = x;
    let nm = x.f;
    if (usedNames.has(nm)) nm = 'ext-' + nm;
    usedNames.add(nm);
    add(
      nm,
      x.p,
      'dump',
      `ext crash file (diagnostic rings written by the game process itself), process ${bi.pid}, build ${bi.build}` +
        (rec.log ? `, log ${rec.log}` : ''),
    );
    dumps.push({ ...rec, sent_as: nm, stale: false, reason: '' });
  }
}

// list of what would be sent: [{name, src, size, mtime, kind: 'log'|'text'|'dump'|'missing', note}] in the order shown to the player:
// game files first (t2r-ext.log is ALWAYS there, a missing one is a warning row), the newest crash dump (always, if from the last 7 days; older ones
// only with olderDumps), then the play and launcher logs. system.txt is added by the caller / build().
/**
 * Collect the logs, dumps and metadata that make up a report.
 * @param {object} options
 * @returns {object[]}
 */
function collect({ gameDir, clientDir, launcherLog, docsDir, olderDumps, steamLogDir, matchLogs }) {
  const out = [];
  const add = makeAdder(out);
  const gdir = collectLogs({ gameDir, clientDir, steamLogDir, matchLogs }, out, add);
  const cand = collectDumpCandidates(gdir, docsDir);
  const cur = gdir ? logIdent(path.join(gdir, 't2r-ext.log')) : { mtime: 0 },
    prev = gdir ? logIdent(path.join(gdir, 't2r-ext.prev.log')) : { mtime: 0 };
  const { take, skippedDumps, primary } = selectDumps({ cand, cur, prev, olderDumps });
  const dumps = [],
    usedNames = new Set(out.map((f) => f.name));
  attachDumps(take, usedNames, add, dumps);
  collectExtCrashFile({
    gdir,
    olderDumps,
    cur,
    prev,
    primary,
    usedNames,
    add,
    dumps,
    skippedDumps,
  });
  if (launcherLog) add('launcher.log', launcherLog, 'log');
  out.dumps = dumps;
  out.skippedDumps = skippedDumps;
  return out;
}

module.exports = { collect };
