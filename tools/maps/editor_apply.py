"""Editor -> our data files -> paks, in one command (counterpart of editor_prepare.py).

  python tools/maps/editor_apply.py <key|all>            # DRY RUN: what your saved edits change (default pak = maps-edit/<key>/<key>.pak)
  python tools/maps/editor_apply.py <key|all> --apply    # write data/<key>-spawns.json, sp_maps.json props, medkits / itemspots / satchels json + ext headers,
                                                         # then rebuild tools/features/levels/to1-pvp-<key>-ingame.pak (sp_maps.py pak);
                                                         # stock maps (forest, gas-station, school, shipyard, resort, seraphite-camp, houses): the level pak itself is rewritten (editor_stock.py)
  python tools/maps/editor_apply.py <key> <saved.pak> [--apply]   # another file than the default
  --dir DIR   maps-edit folder (default maps-edit/ in the repo root)
A map whose pak is unchanged shows "no differences" and is not rebuilt.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import t2rtmp  # noqa: E402,F401
import editor_import as EI  # noqa: E402
import editor_prepare as EP  # noqa: E402
import sp_maps  # noqa: E402


def main(a):
    if not a or a[0].startswith("--"):
        print(__doc__)
        return 1
    d = a[a.index("--dir") + 1] if "--dir" in a else EP.OUT
    rest = [x for i, x in enumerate(a) if not x.startswith("--") and not (i and a[i - 1] == "--dir")]
    keys = EP.ALL if rest[0] == "all" else [rest[0]]
    changed = 0
    for k in keys:
        pak = rest[1] if len(rest) > 1 else os.path.join(d, k, k + ".pak")
        if not os.path.exists(pak):
            print(f"== {k}: {pak} missing, skipped")
            continue
        print(f"== {k}  ({pak})")
        if k in EP.STOCK:                  # pak-driven stock map: the saved pak is written back over its level pak
            import editor_stock
            df, plan = editor_stock.run(k, pak)
            df.show()
            if "--apply" in a and df.n:
                editor_stock.apply(k, df, plan, pak)
                changed += 1
            continue
        df, plan, spawns, _ = EI.run(k, pak)
        df.show()
        if "--apply" in a and df.n:
            EI.apply(k, df, plan, spawns)
            sp_maps.pak(k)
            changed += 1
    if "--apply" in a:
        print(f"{changed} map(s) applied. Next: commit data/ sp_maps.json tools/ext/*.h tools/features/levels/*.pak, then build.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
