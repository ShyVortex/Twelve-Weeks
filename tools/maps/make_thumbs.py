"""Map thumbnails (vote tile / loading screen) for the SP-section maps from the game's own art (read only):
  - No Return arena polaroids: texture rl-map-locale-<locale>-color of actor97/rogue-map-photo-kit.pak
    (common.psarc), stored upside down; the photo part is cropped, flipped and cut to 16:9 (as Hospital's);
  - maps without a No Return arena: the chapter-select image of their chapter (core.psarc
    gtex1/streaming/menus/chapters/<n>.png);
  - the No Return ENCOUNTER stills (core.psarc gtex1/streaming/menus/encounters/e<NN>.png, 16:9, one per No Return location: the
    game's own icon of a level): "encounter" sources.
Output: tools/features/assets/map-pvp-<key>.png (1280x720; build_dll copies it and makes the 1080p / 1440p sizes).
  python make_thumbs.py [key...]
"""
import os
import sys

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
GAME = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
CACHE = os.path.join(ROOT, "re", "maps", "paks", "_base")
OUT = os.path.join(TOOLS, "features", "assets")

# key -> ("nor", locale) | ("chapter", n) | ("encounter", n). Picked by looking at the images.
SOURCES = {
    "train-station": ("nor", "state-street"),     # NoR "State Street" polaroid = the Santa Barbara station
    "hillcrest-stores": ("nor", "streets"),       # NoR "Streets" = Hillcrest street patrol
    "motel": ("nor", "motel-lobby"),
    "tv-station": ("nor", "tv-station"),
    "hardware": ("nor", "hardware-store"),
    "downtown": ("chapter", 9),                   # Seattle day 1 downtown skyline
    "lodge": ("chapter", 3),                      # the lodge in the snow
    "jackson-suburbs": ("chapter", 5),            # snowy street in the blizzard (patrol)
    "outpost": ("chapter", 42),                   # Santa Barbara suburbs
    "wilds-houses": ("chapter", 44),              # the wilds mansion (the facade at the arena's south wall)
    "into-the-city": ("encounter", 56),           # Convention Center: the flooded-city encounter still (a boat on open water). INFERRED by elimination (it has its own game icon; the No Return encounter stills e01..e57 are matched to the other locations by the polaroids): swap the number if the in-game icon is another still
    "overpass": ("encounter", 48),                # Overpass: the burning forest at night with the wrecked car = the Overpass polaroid (rl-map-locale-overpass) as a 16:9 still
    "jackson-market": ("nor", "supermarket"),     # NoR "Supermarket" polaroid = this map (Jackson patrol supermarket + lot)
    "chase": ("chapter", 32),                     # Chase: the pier / container cranes of Abby's Seattle Day 3 pier chapter (picked from the chapter contact sheet; swap the number if the chapter is another)
    "capitol-shops": ("chapter", 11),             # Seattle day 1 Capitol Hill street (trees, the skyline; chapter 11 shows the gas station next door)
}
PHOTO = (0.064, 0.072, 0.774, 0.786)              # photo area of the flipped 1024x1024 polaroid (l, t, r, b)


def _locale_png(locale):
    import dsar_list
    import ndpak
    import texdict
    kit = os.path.join(CACHE, "rogue-map-photo-kit.pak")
    if not os.path.exists(kit):
        os.makedirs(CACHE, exist_ok=True)
        d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", "common.psarc"))
        open(kit, "wb").write(dsar_list.extract(d, ent, bs, bsz, "actor97/rogue-map-photo-kit.pak"))
    tex = [t for t in ndpak.textures(ndpak.Pak(kit)) if f"rl-map-locale-{locale}-color" in t["path"]]
    assert tex, f"no locale texture {locale}"
    h = "%016X" % tex[0]["hash"]
    out = os.path.join(CACHE, "locale")
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, h + ".png")
    if not os.path.exists(png):
        texdict.main([out, h]) if hasattr(texdict, "main") else os.system(f'"{sys.executable}" "{texdict.__file__}" "{out}" {h}')
    return png


def _chapter_png(n):
    import dsar_list
    out = os.path.join(CACHE, "ui")
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, f"chapters-{n}.png")
    if not os.path.exists(png):
        d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", "core.psarc"))
        open(png, "wb").write(dsar_list.extract(d, ent, bs, bsz, f"gtex1/streaming/menus/chapters/{n}.png"))
    return png


def _encounter_png(n):
    import dsar_list
    out = os.path.join(CACHE, "ui")
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, f"encounters-e{n:02d}.png")
    if not os.path.exists(png):
        d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", "core.psarc"))
        open(png, "wb").write(dsar_list.extract(d, ent, bs, bsz, f"gtex1/streaming/menus/encounters/e{n:02d}.png"))
    return png


def to_16_9(im):
    w, h = im.size
    if w / h > 16 / 9:
        nw = int(h * 16 / 9)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w * 9 / 16)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize((1280, 720), Image.LANCZOS)


def make(key):
    kind, src = SOURCES[key]
    if kind == "nor":
        im = ImageOps.flip(Image.open(_locale_png(src)).convert("RGB"))
        w, h = im.size
        im = im.crop((int(PHOTO[0] * w), int(PHOTO[1] * h), int(PHOTO[2] * w), int(PHOTO[3] * h)))
    elif kind == "encounter":
        im = Image.open(_encounter_png(src)).convert("RGB")
    else:
        im = Image.open(_chapter_png(src)).convert("RGB")
    dst = os.path.join(OUT, f"map-pvp-{key}.png")
    to_16_9(im).save(dst, optimize=True)
    print(f"{key}: {kind} {src} -> {os.path.relpath(dst, ROOT)}")


if __name__ == "__main__":
    for k in sys.argv[1:] or list(SOURCES):
        make(k)
