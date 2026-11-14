"""Scene Editor edits of the SP levels' OWN spawners (pickups, props, chests, doors ... of the <level>-ingame paks).

  tools/maps/data/<key>-spedits.json   {"key", "edits": [{"level", "name", "action": "remove" | "move", "pos", "quat", "orig_pos", "orig_quat", "active": true}]}

Applied by collectibles.build_key (the mechanism that parks the SP collectibles at y=-3000): "remove" = the spawner is parked like a collectible, "move" = its position
(3 x float32) and rotation (4 x float32, 16 bytes behind it) are rewritten in the record; found by the ORIGINAL pose, which must be unique in the pak (same rule as the park edit).
"""
import json
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))


def spec_path(key):
    return os.path.join(HERE, "data", f"{key}-spedits.json")


def load(key):
    p = spec_path(key)
    return [e for e in json.load(open(p, encoding="utf-8")).get("edits", []) if e.get("active", True)] if os.path.exists(p) else []


def removed(key):
    """{(level, name): why}"""
    return {(e["level"], e["name"]): "removed in the Scene Editor (spedits)" for e in load(key) if e["action"] == "remove"}


def moves(key):
    return [e for e in load(key) if e["action"] == "move"]


def patch_moves(raw, edits):
    """bytes with each move applied -> (bytes, [names])"""
    b = bytearray(raw)
    done = []
    import numpy as np
    for e in edits:
        if all(abs(x - y) < 1e-3 for x, y in zip(e["pos"], e["orig_pos"])) and all(abs(x - y) < 1e-4 for x, y in zip(e["quat"], e["orig_quat"])):
            continue                                 # no-op (the editor records a selected-but-unmoved SP spawner): nothing to patch
        # the editor stores orig_pos/orig_quat rounded (3 / 5 decimals): match the record's floats with a tolerance, not bit-exact
        offs, both = [], []
        for al in range(4):
            n = (len(b) - al) // 4
            f = np.frombuffer(bytes(b[al:al + 4 * n]), "<f4")
            with np.errstate(invalid="ignore"):
                hit = (np.abs(f[:-2] - e["orig_pos"][0]) < 2e-3) & (np.abs(f[1:-1] - e["orig_pos"][1]) < 2e-3) & (np.abs(f[2:] - e["orig_pos"][2]) < 2e-3)
            for k in np.nonzero(hit)[0]:
                o = al + 4 * int(k)
                offs.append(o)
                if o + 32 <= len(b):
                    qq = struct.unpack_from("<4f", b, o + 16)
                    if all(abs(x - y) < 2e-4 for x, y in zip(qq, e["orig_quat"])) or all(abs(x + y) < 2e-4 for x, y in zip(qq, e["orig_quat"])):
                        both.append(o)
        use = both if len(both) == 1 else offs if len(offs) == 1 else None
        if use is None:
            raise SystemExit("spedits: %s / %s: %d position hits / %d with the rotation - not unique" % (e["level"], e["name"], len(offs), len(both)))
        o = use[0] if isinstance(use, list) else use
        struct.pack_into("<3f", b, o, *e["pos"])
        struct.pack_into("<4f", b, o + 16, *e["quat"])
        done.append(e["name"])
    return bytes(b), done
