#!/usr/bin/env python3
"""Read the bug reports the launcher sent (stored by server.py in <data>/reports).

  python tools/update_server/reports.py --data <data> list            # new (not handled) reports, newest first
  python tools/update_server/reports.py --data <data> list --all
  python tools/update_server/reports.py --data <data> show R-7F3K     # description, when, map, version, name, steam id + file paths
  python tools/update_server/reports.py --data <data> handled R-7F3K  # mark as handled (set "handled": true in its meta.json)
  python tools/update_server/reports.py --data <data> path R-7F3K     # just the folder (for scripts)
--reports <dir> instead of --data uses that folder directly.
"""
import argparse
import json
import os
import sys


def root_of(a):
    return a.reports or os.path.join(a.data, "reports")


def all_reports(root):
    out = []
    if not os.path.isdir(root):
        return out
    for d in sorted(os.listdir(root), reverse=True):
        p = os.path.join(root, d, "meta.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append((os.path.join(root, d), json.load(f)))
            except ValueError:
                pass
    return out


def find(root, code):
    code = code.upper()
    for d, m in all_reports(root):
        if m.get("code", "").upper() == code:
            return d, m
    sys.exit("no report with code " + code)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="")
    ap.add_argument("--reports", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list"); l.add_argument("--all", action="store_true")
    for c in ("show", "handled", "path"):
        sub.add_parser(c).add_argument("code")
    a = ap.parse_args(argv)
    if not (a.data or a.reports):
        ap.error("--data or --reports is required")
    root = root_of(a)
    if a.cmd == "list":
        rows = [(d, m) for d, m in all_reports(root) if a.all or not m.get("handled")]
        for d, m in rows:
            print("%-7s %s  %-15s v%-10s %s%s" % (m.get("code"), m.get("received", "")[:16], m.get("name", ""), m.get("version", ""),
                  (m.get("text", "").strip().splitlines() or [""])[0][:70], "  [handled]" if m.get("handled") else ""))
        print("%d report(s)" % len(rows))
    elif a.cmd == "show":
        d, m = find(root, a.code)
        print("%s  received %s from %s" % (m["code"], m.get("received"), m.get("ip")))
        print("player %s (%s)  steam %s  build %s  launcher %s" % (m.get("name"), m.get("nameSource"), m.get("steamId"), m.get("version"), m.get("launcherVersion")))
        print("when: %s %s | map/mode: %s | dumps: %s" % (m.get("when"), m.get("whenText"), m.get("mapMode") or "-", m.get("includeDumps")))
        print("system: %s | %s" % (m.get("os"), m.get("gpu")))
        print("\n" + m.get("text", "") + "\n")
        print("folder: " + d)
        for f in m.get("files", []):
            print("  %9d  %s" % (f["size"], os.path.join(d, "files", f["name"])))
    elif a.cmd == "handled":
        d, m = find(root, a.code)
        m["handled"] = True
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1, ensure_ascii=False)
        print("marked handled:", m["code"])
    elif a.cmd == "path":
        print(find(root, a.code)[0])


if __name__ == "__main__":
    main()
