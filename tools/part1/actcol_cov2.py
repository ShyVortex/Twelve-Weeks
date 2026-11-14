"""translate every Part I actor with a stock template of a superset class set; print results + member coverage"""
import json, os, sys, collections, pickle
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import actcol_p1, actcol_probe as pr, actor_collision as A, test_actor_collision as T, havok_tag as H
S = os.environ["ACTCOL_SCRATCH"]
raws = pickle.load(open(os.path.join(S, "p1all.pkl"), "rb"))
sc = json.load(open(os.path.join(S, "t2scan.json")))
t2 = pickle.load(open(os.path.join(S, "t2tags.pkl"), "rb"))
sets = [(nm, set(v["classes"])) for nm, v in sc.items() if v and "classes" in v]
T2BASE = {'hknpMaterial','hknpPhysicsSystemData','hknpPhysicsSystemData::bodyCinfoWithAttachment','hkRefCountedProperties','hknpMotionProperties','hknpConvexPolytopeShape','hkVector4f','hkVector4','hknpConvexPolytopeShape::Face','hkUint8','hknpConvexPolytopeShape::Connectivity','hkRefCountedProperties::Entry','hknpShapeMassProperties','hknpConvexPolytopeShape::Connectivity::Edge'}


def template_for(extra, base=None):
    need = (base if base is not None else T2BASE) | extra
    cands = [(len(s - need), nm) for nm, s in sets if need <= s]
    if not cands:
        return None
    cands.sort()
    return cands[0][1]


if __name__ == "__main__":
    res = collections.defaultdict(list)
    rep = {}
    templates = {}
    for a, tags in raws.items():
        if not tags:
            continue
        for tg in tags:
            pg = H.Tag.parse(tg)
            cls = {pg.tname(i[0]) for i in pg.items[1:]}
            extra = {c for c in cls if c in A.CONSTRAINT_CLASSES or c in ("hknpConstraintCinfo", "hknpSphereShape", "hknpCapsuleShape")}
            if "hknpCompoundShape" in cls:
                extra |= {"hknpCompoundShape", "hknpCompoundShapeData", "hkcdSimdTree::Node", "hkFreeListArrayElement<tVALUE_TYPE=hknpShapeInstance>"}
            nd = {"hknpMaterial", "hknpPhysicsSystemData", "hknpPhysicsSystemData::bodyCinfoWithAttachment", "hknpMotionProperties"}
            if "hknpConvexShape" in cls:
                nd |= {"hknpConvexPolytopeShape", "hkVector4f", "hkVector4", "hknpConvexPolytopeShape::Face", "hkUint8", "hknpConvexPolytopeShape::Connectivity",
                       "hknpConvexPolytopeShape::Connectivity::Edge"}
            if "hknpShapeProperties::Property" in cls:
                nd |= {"hkRefCountedProperties", "hkRefCountedProperties::Entry", "hknpShapeMassProperties"}
            if "hknpCompressedMeshShape" in cls:
                nd |= {"hknpCompressedMeshShape", "hknpCompressedMeshShapeData", "hkcdStaticTree::Codec3Axis4", "hkcdStaticTree::Codec3Axis5",
                       "hkcdStaticMeshTreeBase::Section", "hkcdStaticMeshTreeBase::Primitive", "hknpCompressedMeshShapeTreeDataRun", "hkcdSimdTree::Node", "hkUint32"}
            tn = template_for(extra, nd)
            try:
                if tn is None:
                    raise A.Unsupported("no template")
                templates[a] = tn[len("actor97/"):-4]
                out = A.translate(tg, t2[tn], rep)
                chk = H.Tag.parse(out)
                assert A.Graph.from_tag(chk).encode() == out
                bad = [b for s in T.shapes_of(out) for b in T.hull_problems(s)]
                res["ok" if not bad else "hull problems"].append((a, tn, bad[:2]))
            except A.Unsupported as e:
                res["unsupported: " + str(e)[:60]].append(a)
            except Exception as e:
                res["error " + repr(e)[:80]].append(a)
    if "--write" in sys.argv:
        ok = {a for a, *_ in res["ok"]}
        json.dump({a: templates[a] for a in sorted(ok)}, open(os.path.join(HERE, "data", "actor-col-templates.json"), "w"), indent=1)
    for k, v in res.items():
        print(k, len(v), [x if isinstance(x, str) else x[0] for x in v][:4])
    for cls, d in rep.get("members", {}).items():
        print(cls, "| tlou2 only:", sorted(d["tlou2 only"]), "| part1 only:", sorted(d["part1 only"]))
