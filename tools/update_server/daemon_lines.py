"""Daemon log lines for a bug report, saved next to it (files/daemon-lines.txt), plus a compressed archive of the rotated daemon logs.

Why: the daemon log (host186/daemon.log + .1-.5, 8 MB each) covers only about 90 minutes on a busy evening. The server side of most
reports (search refused, match id, host migration, who left, the host's view of a down) was already gone when the report was read.

- archive_rotated(): copies each rotated daemon.log.N once into <log dir>/log-archive/daemon-<mtime>.log.gz and deletes archives older
  than ARCHIVE_DAYS. A rotated file keeps its mtime when it is renamed .1 -> .2, so the mtime names it exactly once.
- snapshot(): pass 1 keeps every line that names the player (name as a whole word, steam id) and collects the (ip, port) pairs and the
  8-hex match ids on those lines; pass 2 keeps every line with one of those pairs or match ids (the same session's nameless lines, e.g.
  'MATCHMAKE (...) refused (no Steam helper) <tag>', and the whole match as the server saw it: the host's side included).
  Raw TCP dumps and pings are skipped. IPv4 addresses are written as 'IP'. At most MAX_OUT bytes.
"""
import glob
import gzip
import os
import re
import threading
import time

LOG_DIR = os.environ.get("T2R_DAEMON_LOG_DIR", os.path.expanduser("~/t2r-live/host186"))
ARCHIVE_DAYS = float(os.environ.get("T2R_DAEMON_ARCHIVE_DAYS", "3"))
HOURS = 6.0                      # how far back a snapshot reads
MAX_OUT = 6 * 1024 * 1024
SKIP = re.compile(r"^\[\d\d:\d\d:\d\d\] (TCP \(|PING |STATUS )")
PAIR = re.compile(r"\('(\d{1,3}(?:\.\d{1,3}){3})', (\d+)\)")
MID = re.compile(r"\b(?:match|mid) ([0-9a-f]{8})\b")
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _archive_dir(log_dir):
    return os.path.join(log_dir, "log-archive")


def archive_rotated(log_dir=LOG_DIR, now=None):
    """Archive every rotated daemon log not archived yet; prune old archives. Returns the number of new archives."""
    now = now or time.time()
    ad = _archive_dir(log_dir)
    os.makedirs(ad, exist_ok=True)
    made = 0
    for p in glob.glob(os.path.join(log_dir, "daemon.log.[0-9]*")):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        out = os.path.join(ad, "daemon-%s.log.gz" % time.strftime("%Y%m%d-%H%M%S", time.gmtime(mt)))
        if os.path.exists(out):
            continue
        tmp = out + ".tmp"
        try:
            with open(p, "rb") as src, gzip.open(tmp, "wb", compresslevel=6) as dst:
                while True:
                    b = src.read(1 << 20)
                    if not b:
                        break
                    dst.write(b)
            os.replace(tmp, out)
            os.utime(out, (mt, mt))
            made += 1
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
    for p in glob.glob(os.path.join(ad, "daemon-*.log.gz")):
        try:
            if now - os.path.getmtime(p) > ARCHIVE_DAYS * 86400:
                os.remove(p)
        except OSError:
            pass
    return made


def _sources(log_dir, since):
    """Log files written after `since`, oldest first: archives (the rotated files they copy are skipped) then the live file."""
    files = []
    archived = set()
    for p in glob.glob(os.path.join(_archive_dir(log_dir), "daemon-*.log.gz")):
        mt = os.path.getmtime(p)
        archived.add(int(mt))
        if mt >= since:
            files.append((mt, p))
    for p in glob.glob(os.path.join(log_dir, "daemon.log*")):
        mt = os.path.getmtime(p)
        if mt < since or (p != os.path.join(log_dir, "daemon.log") and int(mt) in archived):
            continue
        files.append((mt, p))
    files.sort()
    return [p for _, p in files]


def _lines(path):
    op = gzip.open if path.endswith(".gz") else open
    try:
        with op(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line
    except OSError:
        return


def snapshot(report_dir, meta, log_dir=LOG_DIR, hours=HOURS, now=None):
    """Write <report_dir>/files/daemon-lines.txt for this report's player. Returns the number of lines written."""
    now = now or time.time()
    name = (meta.get("name") or "").strip()
    steam = (meta.get("steamId") or "").strip()
    needles = []
    if len(name) >= 2:
        needles.append(re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])"))
    if steam.isdigit() and len(steam) >= 15:
        needles.append(re.compile(re.escape(steam)))
    if not needles:
        return 0
    srcs = _sources(log_dir, now - hours * 3600)
    pairs, mids = set(), set()
    for p in srcs:
        for line in _lines(p):
            if SKIP.match(line):
                continue
            if any(n.search(line) for n in needles):
                pairs.update(PAIR.findall(line))
                mids.update(MID.findall(line))
            elif pairs and MID.search(line) and any(pr in pairs for pr in PAIR.findall(line)):
                # the session's nameless lines carry its match ids ('MATCHMAKE (ip, port) ok match <id>'); the log is in time
                # order and the session's first line (BRIDGE ... token <name>) names the player, so the pair is known by then
                mids.update(MID.findall(line))
    out, size, n = [], 0, 0
    head = "# daemon lines for %r (steam %s), %d file(s) from the last %.0f h; %d session address(es), match ids: %s\n" % (
        name, steam or "-", len(srcs), hours, len(pairs), " ".join(sorted(mids)) or "-")
    for p in srcs:
        out.append("# --- %s\n" % os.path.basename(p))
        for line in _lines(p):
            if SKIP.match(line):
                continue
            hit = any(n_.search(line) for n_ in needles)
            if not hit and pairs:
                hit = any(pr in pairs for pr in PAIR.findall(line))
            if not hit and mids:
                hit = any(m in mids for m in MID.findall(line))
            if not hit:
                continue
            line = IPV4.sub("IP", line)
            size += len(line)
            if size > MAX_OUT:
                out.append("# ... cut at %d MB\n" % (MAX_OUT >> 20))
                break
            out.append(line)
            n += 1
        if size > MAX_OUT:
            break
    fd = os.path.join(report_dir, "files")
    os.makedirs(fd, exist_ok=True)
    tmp = os.path.join(fd, "daemon-lines.txt.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(head)
        f.writelines(out)
    os.replace(tmp, os.path.join(fd, "daemon-lines.txt"))
    return n


def _meta(report_dir):
    import json
    with open(os.path.join(report_dir, "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def snapshot_later(report_dir, meta=None, delay=5.0):
    """Run snapshot() on a background thread (the report answer never waits for it); errors go to stderr only."""
    def run():
        time.sleep(delay)
        try:
            archive_rotated()
            snapshot(report_dir, meta or _meta(report_dir))
        except Exception as e:  # noqa: BLE001 - a failed snapshot must never touch the stored report
            import sys
            sys.stderr.write("daemon lines for %s failed: %r\n" % (report_dir, e))
    threading.Thread(target=run, name="daemon-lines", daemon=True).start()


def archive_loop(period=300.0):
    """Archive rotated logs every `period` seconds on a background thread (started once by the update server)."""
    def run():
        while True:
            try:
                archive_rotated()
            except Exception as e:  # noqa: BLE001
                import sys
                sys.stderr.write("daemon log archive failed: %r\n" % (e,))
            time.sleep(period)
    threading.Thread(target=run, name="daemon-archive", daemon=True).start()


if __name__ == "__main__":      # backfill: python3 daemon_lines.py <report dir> [hours]
    import sys
    d = sys.argv[1]
    print(snapshot(d, _meta(d), hours=float(sys.argv[2]) if len(sys.argv) > 2 else HOURS), "lines")
