"""Suspect A scan: per-vertex stream values of the render submeshes around each removed footprint (geoedits) -- is a prop imprint stored there?

  python bakedao_scan.py scan <pak> <geoedits-key> [--out tools/shots] [--pad 1.0]

Decodes EVERY non-position vertex stream of every submesh that has vertices within `pad` of a removal box (numpy, vectorised):
bit-packed streams (type >= 64 except 130) = raw*scale+off per channel, raw half streams (4 / 6 half4, 11 / 12 half2), 130 = packed u32 (4 bytes).
Per box and stream channel: mean/std of vertices INSIDE the box vs a RING (box grown by pad) vs the same submesh FAR away; a footprint imprint =
inside differs from ring by more than the far spread.  Writes tools/shots/bakedao-*.png top-down maps of the most suspicious channels."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import ndpak  # noqa: E402


def unpack_bits(d, base, n, bits):
    """vectorised decode of bit-packed channels -> (n, len(bits)) raw ints"""
    stride = sum(bits)
    nb = (n * stride + 7) // 8 + 8
    buf = np.frombuffer(bytes(d[base:base + nb]), np.uint8)
    out = np.zeros((n, len(bits)), np.uint64)
    bo = np.arange(n, dtype=np.uint64) * np.uint64(stride)
    for c, b in enumerate(bits):
        if b == 0:
            continue
        byte = (bo >> np.uint64(3)).astype(np.int64)
        sh = (bo & np.uint64(7))
        w = np.zeros(n, np.uint64)
        for k in range(8):
            idx = np.minimum(byte + k, len(buf) - 1)
            w |= buf[idx].astype(np.uint64) << np.uint64(8 * k)
        out[:, c] = (w >> sh) & np.uint64((1 << b) - 1)
        bo += np.uint64(b)
    return out


def decode_stream(p, sm, st):
    n = sm["vcount"]
    t = st["type"]
    if t == 130:
        return np.frombuffer(bytes(p.d[st["buf"]:st["buf"] + 4 * n]), np.uint8).reshape(n, 4).astype(float), ["b0", "b1", "b2", "b3"]
    if t in (4, 6):
        return np.frombuffer(bytes(p.d[st["buf"]:st["buf"] + 8 * n]), "<f2").reshape(n, 4).astype(float), list("xyzw")
    if t in (11, 12):
        return np.frombuffer(bytes(p.d[st["buf"]:st["buf"] + 4 * n]), "<f2").reshape(n, 2).astype(float), list("xy")
    if t == 0:
        return np.frombuffer(bytes(p.d[st["buf"]:st["buf"] + 12 * n]), "<f4").reshape(n, 3).astype(float), list("xyz")
    bits = [b for b in st["bits"]]
    raw = unpack_bits(p.d, st["buf"], n, bits).astype(float)
    ch = [i for i, b in enumerate(bits) if b]
    # bits==0 channels keep their constant offset
    vals = raw * np.array(st["scale"]) + np.array(st["off"])
    return vals[:, :max(1, max(ch) + 1)] if ch else vals[:, :1], list("xyzw")[:max(1, max(ch) + 1) if ch else 1]


def load_boxes(key, level):
    from_geo = os.path.join(HERE, "data", f"{key}-geoedits.json")
    out = []
    for e in json.load(open(from_geo, encoding="utf-8"))["edits"]:
        if e.get("level") == level and e.get("active", True) and e.get("kind") in ("instance", "tris"):
            out.append((e["name"], e["kind"], np.array(e["box"], float)))
    return out


def streams_near(p, boxes, pad):
    """{submesh index: (pos, {stream label: (vals, chan names)})} for submeshes with vertices within pad of any box"""
    res = {}
    for i, sm in enumerate(p.submeshes):
        if not sm["vcount"] or p.pos_stream(sm) is None:
            continue
        P = p.positions(sm)
        if P is None or not np.isfinite(P).all():
            continue
        near = np.zeros(len(P), bool)
        for _, _, b in boxes:
            near |= np.all((P >= b[:3] - pad) & (P <= b[3:] + pad), axis=1)
        if not near.any():
            continue
        S = {}
        for st in sm["streams"]:
            if st["type"] in (64, 0) and st is p.pos_stream(sm):
                continue
            try:
                S[st["type"]] = decode_stream(p, sm, st)
            except Exception:
                pass
        res[i] = (P, S)
    return res


def scan(pak, key, level, pad=1.0, out="tools/shots"):
    p = ndpak.Pak(pak)
    boxes = load_boxes(key, level)
    print(len(boxes), "removal boxes")
    near = streams_near(p, boxes, pad)
    rows = []
    for bi, (name, kind, b) in enumerate(boxes):
        lo, hi = b[:3], b[3:]
        for i, (P, S) in near.items():
            inside = np.all((P >= lo) & (P <= hi), axis=1)
            ring = np.all((P >= lo - pad) & (P <= hi + pad), axis=1) & ~inside
            if inside.sum() < 3 or ring.sum() < 3:
                continue
            for t, (V, names) in S.items():
                for c, cn in enumerate(names):
                    v = V[:, c]
                    mi, mr = v[inside].mean(), v[ring].mean()
                    sd = max(v.std(), 1e-6)
                    rows.append((abs(mi - mr) / sd, bi, name, p.submeshes[i]["name"][-40:], i, t, cn, mi, mr, sd, int(inside.sum()), int(ring.sum())))
    rows.sort(reverse=True)
    return p, boxes, near, rows


# ----------------------------------------------------------------------------------------------- world-space view
def owners(p):
    import level_edit as le
    insts = le.find_instances(p)
    own = {}
    for it in insts:
        for _, ids in it.names:
            for i in ids:
                own.setdefault(i, []).append(it)
    return own


def world_verts(p, i, it):
    import level_edit as le
    P = le._qpos(p, p.submeshes[i])
    return (np.c_[P, np.ones(len(P))] @ it.M)[:, :3]


def plot_streams(p, i, it, boxes, png, pad=4.0, skip=(64, 0)):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sm = p.submeshes[i]
    W = world_verts(p, i, it)
    near = np.zeros(len(W), bool)
    for _, _, b in boxes:
        near |= np.all((W >= b[:3] - pad) & (W <= b[3:] + pad), axis=1)
    if near.sum() < 4:
        return False
    S = {}
    for st in sm["streams"]:
        if st["type"] in skip:
            continue
        try:
            S[st["type"]] = decode_stream(p, sm, st)
        except Exception:
            pass
    cols = [(t, c, V[:, k]) for t, (V, names) in S.items() for k, c in enumerate(names) if np.ptp(V[near, k]) > 1e-6]
    if not cols:
        return False
    ext = W[near].max(0) - W[near].min(0)
    ax = [0, 2] if ext[1] < max(ext[0], ext[2]) * 0.5 else ([0, 1] if ext[2] < ext[0] else [2, 1])
    nc = min(len(cols), 8)
    fig, axs = plt.subplots(2, (nc + 1) // 2, figsize=(4.2 * ((nc + 1) // 2), 7.5), squeeze=False)
    for a in axs.flat:
        a.axis("off")
    for a, (t, c, v) in zip(axs.flat, cols[:nc]):
        a.axis("on")
        lo, hi = np.percentile(v[near], [1, 99])
        sc = a.scatter(W[near, ax[0]], W[near, ax[1]], c=v[near], s=6, cmap="viridis", vmin=lo, vmax=hi + 1e-9)
        for _, _, b in boxes:
            if np.all(b[:3] - pad < W[near].max(0)) and np.all(b[3:] + pad > W[near].min(0)):
                a.add_patch(plt.Rectangle((b[ax[0]], b[ax[1]]), b[3 + ax[0]] - b[ax[0]], b[3 + ax[1]] - b[ax[1]], fill=False, ec="red", lw=1))
        a.set_title("s%d stream %d %s  [%.2f..%.2f]" % (i, t, c, lo, hi), fontsize=8)
        a.set_aspect("equal"); fig.colorbar(sc, ax=a, shrink=0.6)
    fig.suptitle(sm["name"][-70:] + "  axes " + "xyz"[ax[0]] + "," + "xyz"[ax[1]], fontsize=9)
    fig.tight_layout(); fig.savefig(png, dpi=80); plt.close(fig)
    return True
