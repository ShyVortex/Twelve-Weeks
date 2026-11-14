"""stock TLOU2 actor collision tags used as templates by actor_collision.translate (TYPE table + per-class default bytes).
data/actor-col-templates.json maps each Part I actor to the stock actor chosen by actcol_cov2.py (a superset of the classes of the result, fewest extras)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(os.path.dirname(HERE)).split(os.sep + ".claude" + os.sep)[0])
T2_GAME = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
MAP = os.path.join(HERE, "data", "actor-col-templates.json")
_arc = {}
_cache = {}


def _tsv():
    if not _arc:
        for cand in (os.path.join(MAIN, "re", "game-files.tsv"), os.path.join(os.path.dirname(os.path.dirname(HERE)), "re", "game-files.tsv")):
            if os.path.exists(cand):
                for line in open(cand, encoding="utf-8"):
                    p = line.rstrip("\n").split("\t")
                    if len(p) == 3 and p[1].startswith("actor97/"):
                        _arc.setdefault(p[1], p[0])
                break
    return _arc


def stock_tag(actor):
    """the COLLISION_DATA_FOREGROUND tag bytes (Havok 2017.1) of a stock TLOU2 actor pak"""
    if actor not in _cache:
        import actcol_probe
        import p1_archive
        key = "actor97/%s.pak" % actor
        arc = _tsv()[key]
        ps = p1_archive.Psarc(os.path.join(T2_GAME, "build", "pc", "main", arc))
        _cache[actor] = actcol_probe.t2_tag_range(ps, key)
    return _cache[actor]


def template_for(actor):
    m = json.load(open(MAP))
    if actor not in m:
        return None
    return stock_tag(m[actor])
