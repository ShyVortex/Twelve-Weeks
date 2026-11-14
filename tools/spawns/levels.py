"""Writes in-game placed spawn points / supply boxes into the MP level paks.

Marks come from t2r-marks.txt (ext: F8 = spawn, F3 = supply box; one line per press with
position, facing quaternion and time). Per map, the presses in order are: 4 team 0 intro spawns,
4 team 1 intro spawns, then respawns; F3 presses are supply boxes.

  python levels.py apply <map> <HH:MM:SS from> <HH:MM:SS to>   # marks in that window -> pak
  python levels.py view <map>                                   # t2r-spawnview.txt for A/B
  python levels.py add <map> <HH:MM:SS from> <HH:MM:SS to>     # marks in that window -> NEW
                                                                # respawns (F8) / supply boxes (F3)
  python levels.py intro <map> <team 0|1> <HH:MM:SS from> <HH:MM:SS to>   # 4 F8 marks -> Tn-1..4
  python levels.py set <map> <label> <HH:MM:SS>                 # one spawner <- the mark at that time
  python levels.py nudge <map> <label> <fwd m> [<right m> [<up m>]]   # move along its own facing

<label> as shown in game: T0-1, T1-4, R5, BOX2.

<map> = forest, gas-station, school, shipyard, resort, seraphite-camp, rescue-jesse-houses, hospital,
and the SP-section maps hardware, motel, hillcrest-stores, tv-station (tools/maps/sp_maps.py, re/maps/).
Paks: tools/features/levels/to1-pvp-<map>-ingame.pak (build_dll.py packs changed ones).
Transforms are patched in place (position vec4 + rotation quaternion of each spawner record,
found by their current bytes), so nothing else in the pak moves. A supply box's item
positions (to1-supplybox-N-itempos-M) move and turn with their box.
"""
import json
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = os.path.join(HERE, "..", "features", "levels")
MARKS = [r"C:\Games\T2R-A\t2r-marks.txt", r"C:\Games\T2R-B\t2r-marks.txt"]   # marks from either window
GAMES = [r"C:\Games\T2R-A", r"C:\Games\T2R-B"]


def pak_path(m):
    return os.path.join(LEVELS, f"to1-pvp-{m}-ingame.pak")


def spawners(m):
    out = os.path.join(HERE, f"{m}.json")
    subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(HERE, "dump_json.ps1"), "-Pak",
                    os.path.abspath(pak_path(m)), "-Out", os.path.abspath(out)], check=True)
    return json.load(open(out, encoding="utf-8-sig"))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qrot(q, v):
    return qmul(qmul(q, (v[0], v[1], v[2], 0.0)), qconj(q))[:3]


def fwd(q):
    f = qrot(q, (0.0, 0.0, 1.0))
    n = math.hypot(f[0], f[2]) or 1.0
    return f[0] / n, f[2] / n


def find_offsets(b, sp):
    """name -> offset of its transform (pos 3f, pad, quat 4f). Two records with the same bytes
    (camera / player / spawn-point-1 can share a spot): the one nearest the others of its kind."""
    offs, dup = {}, {}
    for s in sp:
        key = struct.pack("<3f", *s["pos"])
        q = struct.pack("<4f", *s["quat"])
        hits, i = [], b.find(key)
        while i >= 0:
            if b[i + 16:i + 32] == q:
                hits.append(i)
            i = b.find(key, i + 1)
        if len(hits) == 1:
            offs[s["name"]] = hits[0]
        elif hits:
            dup[s["name"]] = hits
    for name, hits in dup.items():
        kind = name.rsplit("-", 1)[0]
        near = [o for n, o in offs.items() if n.rsplit("-", 1)[0] == kind]
        taken = set(offs.values())
        free = [h for h in hits if h not in taken] or hits
        offs[name] = min(free, key=lambda h: min((abs(h - o) for o in near), default=0))
    return offs


def read_marks(t0, t1):
    out = []
    lines = [l for p in MARKS if os.path.exists(p) for l in open(p, encoding="latin1")]
    for line in lines:
        if "@" not in line:
            continue
        p = line.split()
        t = p[p.index(next(x for x in p if x.startswith("@")))][1:]
        if not (t0 <= t <= t1):
            continue
        pos = tuple(float(x) for x in p[0:3])
        r = p.index("rot")
        quat = tuple(float(x) for x in p[r + 1:r + 5])
        out.append({"pos": pos, "quat": quat, "box": line.rstrip().endswith(" box"), "t": t})
    return sorted(out, key=lambda k: k["t"])


def apply(m, t0, t1):
    marks = read_marks(t0, t1)
    spawns = [k for k in marks if not k["box"]]
    boxes = [k for k in marks if k["box"]]
    sp = spawners(m)
    by = {s["name"]: s for s in sp}
    targets = [f"to1-t0-intro-spawn-point-{i}" for i in range(1, 5)] + \
              [f"to1-t1-intro-spawn-point-{i}" for i in range(1, 5)]
    nresp = sum(1 for s in sp if s["name"].startswith("to1-spawn-point-"))
    targets += [f"to1-spawn-point-{i}" for i in range(1, nresp + 1)]
    nbox = sum(1 for s in sp if s["name"].startswith("to1-supplybox-") and "itempos" not in s["name"])
    if len(spawns) > len(targets):
        sys.exit(f"{len(spawns)} spawn marks but only {len(targets)} spawn slots in {m} "
                 f"({nresp} respawns): adding spawners isn't supported yet")
    if len(boxes) > nbox:
        sys.exit(f"{len(boxes)} box marks but {m} has {nbox} supply boxes: adding boxes isn't supported yet")
    b = bytearray(open(pak_path(m), "rb").read())
    offs = find_offsets(b, sp)
    moves = []                                       # (name, new pos, new quat)
    for k, name in zip(spawns, targets):
        moves.append((name, k["pos"], k["quat"]))
    for i, k in enumerate(boxes, 1):
        box = by[f"to1-supplybox-{i}"]
        dq = qmul(k["quat"], qconj(tuple(box["quat"])))
        moves.append((box["name"], k["pos"], k["quat"]))
        for s in sp:
            if s["name"].startswith(f"to1-supplybox-{i}-itempos-"):
                rel = [s["pos"][j] - box["pos"][j] for j in range(3)]
                r = qrot(dq, rel)
                moves.append((s["name"], tuple(k["pos"][j] + r[j] for j in range(3)), qmul(dq, tuple(s["quat"]))))
    for name, pos, quat in moves:
        if name not in offs:
            sys.exit(f"{name}: transform not found in pak")
        o = offs[name]
        struct.pack_into("<3f", b, o, *pos)
        struct.pack_into("<4f", b, o + 16, *quat)
        print(f"{name:32s} {pos[0]:8.2f} {pos[1]:7.2f} {pos[2]:8.2f}")
    open(pak_path(m), "wb").write(b)
    print(f"{m}: {len(spawns)} spawns, {len(boxes)} boxes written")
    view(m)


def add(m, t0, t1):
    """WARNING: add_spawners.ps1 rebuilds the pak with the SceneEditor writer, which keeps only
    spawners - Shipyard's navmesh (the client's) was lost that way (climbing block). Not for shipyard;
    rebase_nav.py restores a map from the mod's pak.
    New spawners on top of the level's own: F8 marks -> to1-spawn-point-<n+1..>, F3 marks
    -> to1-supplybox-<n+1..> (clone of box 1 with its item positions moved/turned along).
    The daemon must announce the new respawn count (RESPAWNS in daemon.py); winmm takes up to
    12 boxes (supplybox-12-* patches)."""
    marks = read_marks(t0, t1)
    sp = spawners(m)
    by = {s["name"]: s for s in sp}
    nresp = sum(1 for s in sp if s["name"].startswith("to1-spawn-point-"))
    nbox = sum(1 for s in sp if s["name"].startswith("to1-supplybox-") and "itempos" not in s["name"])
    new = []
    for k in marks:
        if not k["box"]:
            nresp += 1
            new.append({"src": "to1-spawn-point-1", "name": f"to1-spawn-point-{nresp}", "pos": k["pos"], "quat": k["quat"]})
            continue
        nbox += 1
        if nbox > 12:
            sys.exit("more than 12 supply boxes (winmm table holds 12)")
        box = by["to1-supplybox-1"]
        dq = qmul(k["quat"], qconj(tuple(box["quat"])))
        new.append({"src": box["name"], "name": f"to1-supplybox-{nbox}", "pos": k["pos"], "quat": k["quat"]})
        for s in sp:
            if s["name"].startswith("to1-supplybox-1-itempos-"):
                r = qrot(dq, [s["pos"][j] - box["pos"][j] for j in range(3)])
                new.append({"src": s["name"], "name": f"to1-supplybox-{nbox}-itempos-{s['name'].rsplit('-', 1)[1]}",
                            "pos": tuple(k["pos"][j] + r[j] for j in range(3)), "quat": qmul(dq, tuple(s["quat"]))})
    js = os.path.join(HERE, f"{m}-add.json")
    json.dump(new, open(js, "w"))
    subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(HERE, "add_spawners.ps1"), "-Pak",
                    os.path.abspath(pak_path(m)), "-Json", os.path.abspath(js)], check=True)
    print(f"{m}: now {nresp} respawns, {nbox} supply boxes -> set RESPAWNS['to1-...'] = {nresp} in daemon.py")
    view(m)


def intro(m, team, t0, t1):
    marks = [k for k in read_marks(t0, t1) if not k["box"]]
    if len(marks) != 4:
        sys.exit(f"{len(marks)} F8 marks in that window, need exactly 4")
    for i, k in enumerate(marks, 1):
        move(m, f"to1-t{team}-intro-spawn-point-{i}", k["pos"], k["quat"])


def label_name(lab):
    lab = lab.upper()
    if lab.startswith("T"):
        return f"to1-t{lab[1]}-intro-spawn-point-{lab.split('-')[1]}"
    if lab.startswith("R"):
        return f"to1-spawn-point-{lab[1:]}"
    if lab.startswith("BOX"):
        return f"to1-supplybox-{lab[3:]}"
    sys.exit(f"unknown label {lab}")


def move(m, name, pos, quat):
    """One spawner to pos/quat (a supply box takes its item positions along)."""
    sp = spawners(m)
    by = {s["name"]: s for s in sp}
    b = bytearray(open(pak_path(m), "rb").read())
    offs = find_offsets(b, sp)
    old = by[name]
    moves = [(name, pos, quat)]
    if name.startswith("to1-supplybox-"):
        dq = qmul(quat, qconj(tuple(old["quat"])))
        for s in sp:
            if s["name"].startswith(name + "-itempos-"):
                r = qrot(dq, [s["pos"][j] - old["pos"][j] for j in range(3)])
                moves.append((s["name"], tuple(pos[j] + r[j] for j in range(3)), qmul(dq, tuple(s["quat"]))))
    for n, p, q in moves:
        struct.pack_into("<3f", b, offs[n], *p)
        struct.pack_into("<4f", b, offs[n] + 16, *q)
    open(pak_path(m), "wb").write(b)
    print(f"{name}: {old['pos'][0]:.2f} {old['pos'][1]:.2f} {old['pos'][2]:.2f} -> {pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f}")
    view(m)


def nudge(m, lab, f, r=0.0, u=0.0):
    name = label_name(lab)
    s = next(x for x in spawners(m) if x["name"] == name)
    q = tuple(s["quat"])
    fx, fz = fwd(q)
    rx, rz = -fz, fx                                  # right of the facing (y up)
    if qrot(q, (1.0, 0.0, 0.0))[0] * rx + qrot(q, (1.0, 0.0, 0.0))[2] * rz < 0:
        rx, rz = fz, -fx
    p = s["pos"]
    move(m, name, (p[0] + fx * f + rx * r, p[1] + u, p[2] + fz * f + rz * r), q)


def set_from_mark(m, lab, t):
    k = read_marks(t, t)
    if not k:
        sys.exit(f"no mark at {t}")
    move(m, label_name(lab), k[0]["pos"], k[0]["quat"])


def view(m):
    lines = []
    for s in spawners(m):
        n = s["name"]
        if n.startswith("to1-t") and "intro" in n:
            lab = f"T{n[5]}-{n.rsplit('-', 1)[1]}"
        elif n.startswith("to1-spawn-point-"):
            lab = "R" + n.rsplit("-", 1)[1]
        elif n.startswith("to1-supplybox-") and "itempos" not in n:
            lab = "BOX" + n.rsplit("-", 1)[1]
        else:
            continue
        fx, fz = fwd(s["quat"])
        lines.append(f"{lab} {s['pos'][0]:.3f} {s['pos'][1]:.3f} {s['pos'][2]:.3f} {fx:.4f} {fz:.4f}")
    for g in GAMES:
        with open(os.path.join(g, "t2r-spawnview.txt"), "w") as f:
            f.write("\n".join(sorted(lines)) + "\n")
    print(f"spawn view: {len(lines)} points of {m} -> A/B")


if __name__ == "__main__":
    if sys.argv[1] == "apply":
        apply(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "add":
        add(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "intro":
        intro(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif sys.argv[1] == "set":
        set_from_mark(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "nudge":
        nudge(sys.argv[2], sys.argv[3], *[float(x) for x in sys.argv[4:]])
    else:
        view(sys.argv[2])
