"""probe helpers for actor collision (COLLISION_DATA_FOREGROUND) items of TLOU2 / Part I actor paks"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import havok_tag, p1_archive
T2 = r"C:/Games/The Last of Us Part II Remastered/build/pc/main"
P1 = os.path.join(os.environ.get("T2R_P1_GAME", "C:/Games/The Last of Us Part I"), "build", "pc", "main")
_tsv = {}
def archive_of(tsv, actor):
    key = f"actor97/{actor}.pak"
    if tsv not in _tsv:
        d = {}
        for line in open(tsv, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 3 and p[1].startswith("actor97/"):
                d.setdefault(p[1], p[0])
        _tsv[tsv] = d
    return _tsv[tsv].get(key)
def raw_pak(game, tsv, actor):
    a = archive_of(tsv, actor)
    return p1_archive.Psarc(os.path.join(game, a)).get(f"actor97/{actor}.pak") if a else None
def t2_raw(actor):
    return raw_pak(T2, r"./re/game-files.tsv", actor)
def p1_raw(actor):
    return raw_pak(P1, r"./re/part1/game-files.tsv", actor)

def t2_fg(raw):
    """TLOU2 actor pak bytes -> list of (Tag, hdr dict) for COLLISION_DATA_FOREGROUND"""
    import ndpak, tempfile
    tmp = os.path.join(tempfile.gettempdir(), "_actcol_%d.pak" % os.getpid())
    open(tmp, "wb").write(raw)
    p = ndpak.Pak(tmp); os.remove(tmp)
    out = []
    for name, typ, pi, io in p.items:
        if typ != "COLLISION_DATA_FOREGROUND":
            continue
        b = io + 48
        t = p.ptr(b + 0x38) if False else None
        out.append((p, b, name))
    return out


def tag_from_page0(d):
    """the first TAG0 (2017.1) in the bytes of an actor pak's page 0, or None"""
    i = d.find(b"TAG0\x40\x00\x00\x10SDKV")
    if i < 0:
        return None
    tsz = struct.unpack_from(">I", d, i - 4)[0] & 0x3FFFFFFF
    return d[i - 4:i - 4 + tsz]


def t2_tag_range(ps, nm):
    hd = ps.read_range(nm, 0, 64)
    n, pt = struct.unpack_from("<I", hd, 16)[0], struct.unpack_from("<I", hd, 20)[0]
    tb = ps.read_range(nm, pt, 12 * n)
    st, sz, fl = struct.unpack_from("<III", tb, 0)
    return tag_from_page0(ps.read_range(nm, 0, st + sz))
