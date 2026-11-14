/**
 * @file Log, dump and binary inspection helpers for report artifacts.
 */
'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Read the tail of a file without loading the whole file.
 * @param {string} file
 * @param {number} max
 * @returns {{buf: Buffer, cut: boolean, size: number}}
 */
function readTail(file, max) {
  const st = fs.statSync(file);
  const n = Math.min(st.size, max),
    fd = fs.openSync(file, 'r');
  try {
    const b = Buffer.alloc(n);
    fs.readSync(fd, b, 0, n, st.size - n);
    return { buf: b, cut: st.size > max, size: st.size };
  } finally {
    fs.closeSync(fd);
  }
}
/**
 * Check whether a path exists.
 * @param {string} p
 * @returns {boolean}
 */
const exists = (p) => {
  try {
    fs.accessSync(p);
    return true;
  } catch {
    return false;
  }
};
/**
 * Return the newest matching files in a directory.
 * @param {string} dir
 * @param {RegExp} re
 * @param {number} n
 * @returns {object[]}
 */
const newest = (dir, re, n) => {
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => re.test(f))
      .map((f) => ({
        f,
        p: path.join(dir, f),
        st: fs.statSync(path.join(dir, f)),
      }))
      .filter((x) => x.st.isFile())
      .sort((a, b) => b.st.mtimeMs - a.st.mtimeMs)
      .slice(0, n);
  } catch {
    return [];
  }
};

// ---- which crash dump belongs to the logs being sent (reports used to carry a stale dump, or dumps of sessions days old)
// minidump header + stream directory only (never the 250 MB body): MiscInfo (type 15: size, flags, ProcessId @8, ProcessCreateTime @12 as time_t) and
// ModuleList (type 4: t2r-ext.dll's TimeDateStamp = the ext build that was loaded).
/**
 * Read crash-dump metadata for report matching.
 * @param {string} file
 * @returns {object}
 */
function dumpInfo(file) {
  const out = { pid: 0, created: 0, extStamp: 0, source: 'mtime' };
  let fd;
  try {
    fd = fs.openSync(file, 'r');
  } catch {
    return out;
  }
  try {
    const size = fs.fstatSync(fd).size,
      rd = (n, pos) => {
        const b = Buffer.alloc(n);
        const g = fs.readSync(fd, b, 0, n, pos);
        return g === n ? b : null;
      };
    const h = size >= 32 ? rd(32, 0) : null;
    if (!h || h.toString('latin1', 0, 4) !== 'MDMP') return out;
    const n = h.readUInt32LE(8),
      dirRva = h.readUInt32LE(12);
    if (!n || n > 512 || dirRva + n * 12 > size) return out;
    const dir = rd(n * 12, dirRva);
    if (!dir) return out;
    for (let i = 0; i < n; i++) {
      const type = dir.readUInt32LE(i * 12),
        len = dir.readUInt32LE(i * 12 + 4),
        rva = dir.readUInt32LE(i * 12 + 8);
      if (rva + len > size) continue;
      if (type === 15 && len >= 16) {
        const m = rd(Math.min(len, 24), rva);
        if (!m) continue;
        const flags = m.readUInt32LE(4);
        if (flags & 1) out.pid = m.readUInt32LE(8);
        if (flags & 2 && m.readUInt32LE(12) > 0) {
          out.created = m.readUInt32LE(12) * 1000;
          out.source = 'MiscInfo';
        }
      } else if (type === 4 && len >= 4 && len < 4 * 1024 * 1024) {
        const l = rd(len, rva);
        if (!l) continue;
        const cnt = l.readUInt32LE(0);
        for (let k = 0; k < cnt && 4 + (k + 1) * 108 <= len; k++) {
          const o = 4 + k * 108,
            nameRva = l.readUInt32LE(o + 20);
          if (nameRva + 4 > size) continue;
          const nl = rd(4, nameRva);
          if (!nl) continue;
          const nb = nl.readUInt32LE(0);
          if (!nb || nb > 1024) continue;
          const nm = rd(nb, nameRva + 4);
          if (nm && /t2r-ext\.dll$/i.test(nm.toString('utf16le'))) {
            out.extStamp = l.readUInt32LE(o + 8);
            break;
          }
        }
      }
    }
  } catch {
    /* a truncated / odd dump: the file mtime decides */
  } finally {
    try {
      fs.closeSync(fd);
    } catch {}
  }
  return out;
}
// t2r-crash-<pid>-1.bin (tools/ext/crashbin.h): the file the ext's crash handler writes next to t2r-ext.log, so a player WITHOUT a WER dump still has the g_cdiag rings.
// 128-byte header: "T2RCBIN1", u32 ver @8, u32 hdr size @12, u32 pid @16, u64 process create time (FILETIME) @24, u32 exception code @32, char[32] ext build @96.
/**
 * Read build/version metadata from a binary.
 * @param {string} file
 * @returns {object}
 */
function binInfo(file) {
  const out = { ok: false, pid: 0, created: 0, build: '', buildMs: 0, code: 0 };
  let fd;
  try {
    fd = fs.openSync(file, 'r');
  } catch {
    return out;
  }
  try {
    const b = Buffer.alloc(128);
    if (
      fs.readSync(fd, b, 0, 128, 0) !== 128 ||
      b.toString('latin1', 0, 8) !== 'T2RCBIN1' ||
      b.readUInt32LE(8) !== 1 ||
      b.readUInt32LE(12) !== 128
    )
      return out;
    out.pid = b.readUInt32LE(16);
    out.code = b.readUInt32LE(32);
    const ft = Number(b.readBigUInt64LE(24));
    if (ft > 0) out.created = Math.round(ft / 1e4 - 11644473600000);
    out.build = b.toString('latin1', 96, 128).split('\0')[0];
    const m = /^(\w{3}) +(\d+) (\d{4}) (\d+):(\d+):(\d+)/.exec(out.build),
      mon = m ? 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ').indexOf(m[1]) : -1;
    if (m && mon >= 0) out.buildMs = Date.UTC(+m[3], mon, +m[2], +m[4], +m[5], +m[6]);
    out.ok = out.pid > 0;
  } catch {
    /* short / odd file: not a crash file */
  } finally {
    try {
      fs.closeSync(fd);
    } catch {}
  }
  return out;
}
// the ext log's load line: "t2r-ext loaded, pid 1234, winmm base ..., build Oct 19 2026 12:00:00 (release)" (pid only in later builds)
/**
 * Extract session identity information from a game log.
 * @param {string} file
 * @returns {object}
 */
function logIdent(file) {
  const r = { pid: 0, build: '', buildMs: 0, birth: 0, mtime: 0 };
  try {
    const st = fs.statSync(file);
    r.mtime = st.mtimeMs;
    r.birth = st.birthtimeMs > 0 && st.birthtimeMs <= st.mtimeMs ? st.birthtimeMs : 0;
    const fd = fs.openSync(file, 'r');
    let hd;
    try {
      const b = Buffer.alloc(Math.min(st.size, 64 * 1024));
      fs.readSync(fd, b, 0, b.length, 0);
      hd = b.toString('latin1');
    } finally {
      fs.closeSync(fd);
    }
    const m =
      /t2r-ext loaded, (?:pid (\d+), )?winmm base \S+?(?:, build (\w{3}) +(\d+) (\d{4}) (\d+):(\d+):(\d+))?\s/.exec(
        hd,
      );
    if (m) {
      if (m[1]) r.pid = parseInt(m[1], 10);
      if (m[2]) {
        const mon = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ').indexOf(m[2]);
        r.build = `${m[2]} ${m[3]} ${m[4]} ${m[5]}:${m[6]}:${m[7]}`;
        if (mon >= 0) r.buildMs = Date.UTC(+m[4], mon, +m[3], +m[5], +m[6], +m[7]);
      }
    }
  } catch {
    /* unreadable: no identity */
  }
  return r;
}
// __DATE__ __TIME__ is the builder's local time, the PE stamp is UTC and written seconds after compiling: they agree up to the builder's zone offset
// (a multiple of 15 min) plus the link delay
/**
 * Check whether a dump timestamp belongs to a build window.
 * @param {number} peStampSec
 * @param {number} buildNaiveMs
 * @returns {boolean}
 */
function stampMatchesBuild(peStampSec, buildNaiveMs) {
  const d = peStampSec * 1000 - buildNaiveMs,
    q = 15 * 60000,
    rem = d - Math.round(d / q) * q;
  return Math.abs(d - rem) <= 15 * 3600000 && rem >= -60000 && rem <= 10 * 60000; // zones span UTC-12..+14: a build a day away never matches
}
// judges one dump against the logs: { ok, reason, pid, created, log }
/**
 * Decide whether a crash dump belongs to the current report session.
 * @param {object} x
 * @param {object} info
 * @param {object} cur
 * @param {object} prev
 * @returns {object}
 */
function judgeDump(x, info, cur, prev) {
  const when = info.created || x.st.mtimeMs,
    r = { pid: info.pid, created: when, log: '', ok: true, reason: '' };
  const logs = [
    ['t2r-ext.log', cur],
    ['t2r-ext.prev.log', prev],
  ].filter((l) => l[1].mtime);
  if (!logs.length) return r; // no log to compare with: the age rule alone applies
  const byPid = info.pid ? logs.find((l) => l[1].pid === info.pid) : null;
  if (byPid) r.log = byPid[0];
  if (info.pid && !byPid && logs.some((l) => l[1].pid)) {
    r.ok = false;
    r.reason = `process ${info.pid} is not in the attached logs (pids ${logs.map((l) => l[1].pid || '?').join('/')})`;
    return r;
  }
  if (!byPid) {
    // time window of the attached logs: from the earliest log start to the last write
    const slack = 10 * 60000,
      start = Math.min(...logs.map((l) => l[1].birth || l[1].mtime - 6 * 3600000)),
      end = Math.max(...logs.map((l) => l[1].mtime));
    if (when < start - slack) {
      r.ok = false;
      r.reason = 'process started before the attached logs begin';
      return r;
    }
    if (when > end + slack) {
      r.ok = false;
      r.reason = 'newer than the attached logs';
      return r;
    }
    const inLog = logs.find((l) => when >= (l[1].birth || 0) - slack && when <= l[1].mtime + slack);
    if (inLog) r.log = inLog[0];
  }
  const lg = r.log ? (r.log === 't2r-ext.log' ? cur : prev) : null;
  if (info.extStamp && lg && lg.buildMs && !stampMatchesBuild(info.extStamp, lg.buildMs)) {
    r.ok = false;
    r.reason = `ext build differs (dump has t2r-ext.dll stamp ${new Date(info.extStamp * 1000).toISOString()}, log says build ${lg.build})`;
  }
  return r;
}

module.exports = {
  readTail,
  exists,
  newest,
  dumpInfo,
  binInfo,
  logIdent,
  stampMatchesBuild,
  judgeDump,
};
