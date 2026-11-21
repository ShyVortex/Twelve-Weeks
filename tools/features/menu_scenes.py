"""Faction MP menu backgrounds (re/mp-menu-background.md).

The MP menu's 3D background is a task: winmm calls FUN_18000b7a0(node "to1-levels", subnode
"to1-main-menu", 0) and the task loads level set "tsk-to1-main-menu" = the mod's tiny
to1-main-menu pak (spawners "camera" + "player", the task's camera / start spawners) + the
Medicine levels med-hidden-ascent (the Seraphite shrine on Abby's day-2 skyscraper shortcut).
This build replaces that default (no clan / no side) with Ellie's Seattle day 1 forest ride.

Two more menu tasks already exist in the mod's test-tasks.bin and are unused: node
"starlight-levels", subnodes "starlight-main-menu" (level set tsk-sl-main-menu-1) and
"starlight-t2-main-menu" (tsk-sl-t2-main-menu), same camera / player spawner setup as
to1-main-menu. This build:
  - gives those two level sets new level lists (appended to level-sets-test.bin, which may grow:
    dcfile.DcFile + modules.bin size) = our own small menu pak + the SP world levels of the scene,
    sub-arrays otherwise copied from tsk-to1-main-menu (part set to1-all),
  - makes the menu paks (copies of to1-main-menu-ingame.pak with the camera / player transforms
    moved) and registers them in pak68.txt (the to1-main-menu block, renamed).
t2r-ext (feature_menu_scene) picks the task by clan side: it rewrites the imm64 node / subnode
hashes at winmm's three menu-load sites and reloads the menu world when the side changes.

Camera: position + look-at target (yaw and pitch from them). The "player" spawner goes on the
floor 0.3 m behind the camera: the task really spawns a player there. In game the ext renders the
camera itself (feature_menu_cam: a log showed the game's menu camera elsewhere than the
spawner), so these spawner poses matter less than t2r-ext's MS_POSE (keep both the same).
"""
import math
import os
import struct

from dcfile import DcFile, fnv

MENU_SRC_PAK = "to1-main-menu-ingame.pak"
MENU_SET = "tsk-to1-main-menu"
# the original pak's transforms (pos vec4 w=1, then the quaternion), found by these bytes
ORIG_CAMERA = (163.87762451171875, 52.58647155761719, -55.01377868652344)
ORIG_PLAYER = (164.07000732421875, 52.117000579833984, -55.66699981689453)

# menu send-off birds (re/menu-sendoff-impl-1115.md): actors / symbols added to a scene pak's pak68.txt block (all in
# sp-common.psarc): crow / pigeon art + the bird skeleton with its takeoff / fly anims, the flee state script
SENDOFF_ACTORS = ["bird-medium-skel-t2", "crow-t2", "pigeon-t2"]
SENDOFF_SYMBOLS = ["pigeon-dark-t2", "ss-animal-flee"]
# CUSTOMIZE stage poses (existing model viewer poses are used, re/customize-1117.md "The stage"): the No Return character-select
# poses (world-game-start.psarc actor97/rogue-mode-poses.pak, 0.8 MB, single-frame clips on base-male-skel / base-female-skel: the
# model viewer's own poses are on the story characters' skeletons); customize_stage.c holds rogue-mode-rattler-factions / -scar-archer
POSE_ACTORS = ["rogue-mode-poses"]
# CUSTOMIZE stage idles (the front model holds npc-mm-ambi-buddy-idle, the WLF menu's back model cap-npc-m-ambi-idle-lean-wall-loop):
# sp-common anim packs that are in no MP level (13.9 + 22.9 MB), loaded with the scene like the send-off actors. No script native loads an
# actor (A/B: load-actor / is-actor-loaded? do not exist), so the scene's actor list is the only way. customize_stage.c spose lines.
POSE_ANIM_ACTORS = ["anim-npc-m-buddy-ambi", "anim-npc-ambi-caps"]

MENU_SCENES = [
    {   # no clan yet / no side: Ellie's Seattle day 1 opening, the forest ride with Dina
        # (tsk-sea-approach-forest-start, world-patrol-departure.psarc). The intro cinematic's
        # origin (635.6, 64.9, -434.1) is the hilltop start; the trail runs down west through the
        # forest (horse-settings script at (435, 42.3, -464)). Replaces the shrine in the
        # original menu set + pak (task to1-levels / to1-main-menu, nothing to switch in winmm).
        "side": 0, "name": "forest",
        "subnode": "to1-main-menu", "set": MENU_SET, "pak": "to1-main-menu",
        # (v2: the gameplay start, obj-sea-arrival-cam-1 (437.0, 40.6, -464.0) / horse scripts
        # y 42.3, looking down the trail to pos-5851 (375.2, 32.0, -525.5); the hilltop spot was
        # inside the slope - bushes up to y 80 there)
        "camera": (451.86, 37.81, -494.37), "target": (442.32, 37.98, -497.36), "floor": 42.3,   # picked in the freecam (F11)
        # the player stays at the original forest spot (ground verified; the scouted camera spot
        # has no floor under it - the player fell to its death)
        "player": (437.0 - 0.3 * 0.71, 42.3, -464.0 - 0.3 * 0.70),
        "levels": ["sea-const", "sea-const-texture-adjust", "sea-const-audio", "sea-arrival-audio",
                   "sky-act2-day-1-sunny", "sea-arrival-forest-start", "sea-arrival-forest",
                   "sea-arrival-forest-vegetation", "sea-arrival-forest-vegetation-trees",
                   "sea-arrival-forest-tree-cards", "sea-arrival-extra-foliage-forest", "sea-arrival-wide"],
    },
    {   # WLF: inside the stadium (Abby day 1, fob-stadium): from the food-prep terrace of the
        # east stands (crowd spawners at y -4.1, x -28..-19) over the field farm (x -98..-47) to
        # the far stands. Field centre ~(-72, -14.4, 1045).
        "side": 1, "name": "wlf",
        "subnode": "starlight-main-menu", "set": "tsk-sl-main-menu-1", "pak": "to1-menu-wlf",
        "camera": (-26.72, -5.21, 1036.27), "target": (-44.42, -1.07, 1027.95), "floor": -4.1,   # picked in the freecam (F11, fov 30.6)
        # VRAM (B ran out of video memory with the big scenes, two clients on one PC): only what the
        # terrace view needs - main + stands; no fx / far wide LOD (audio kept: tiny, the original menu sets had it)
        "levels": ["fob-const", "fob-const-texture-adjust", "fob-stadium-const-render", "fob-const-audio",
                   "fob-stadium-audio", "fob-stadium-main", "fob-stadium-stands", "sky-act2-day-1-fob-stadium"],
        # menu send-off (re/menu-sendoff-impl-1115.md): the bird actors for the ext's flock after the horn
        # (no FlockingBird data anywhere near the stadium)
        "actors": SENDOFF_ACTORS + POSE_ACTORS + POSE_ANIM_ACTORS, "symbols": SENDOFF_SYMBOLS,
    },
    {   # Seraphites: "an outward look on the Haven island" (reference scarmenu.png, Abby day 3): the
        # forest trail on the Scar island's west coast looking across the strait at the capital (the
        # houses on the hill at x -100..-390, z -410..90; the landing-scar-capital-wide LOD level).
        # Camera at the trail's lookout over the water (flee-sle-bird-lookout-10/11 (262.6..264, 20,
        # 56.5), cliff drop to the water at x ~247, y -4.5; waterfall spot (239.8, -3.2, 48.9)),
        # ground y ~19.7-20.7; level set = the game's tsk-sle-scar-island-forest-trail without the
        # landing / logging camp / scripts. The player goes on the trail 10 m behind the camera, on
        # the ground spawner coin-sle-trail-well-1 (274.4, 19.9, 57.8).
        "side": 2, "name": "ser",
        "subnode": "starlight-t2-main-menu", "set": "tsk-sl-t2-main-menu", "pak": "to1-menu-ser",
        "camera": (272.87, 18.17, 52.01), "target": (253.20, 19.26, 48.56),   # picked in the freecam (F11, fov 51.6)
        "floor": 19.9,
        "player": (274.4, 19.9, 57.8),
        "levels": ["sle-const", "sle-const-texture-adjust", "sle-const-render-scar",
                   "sle-const-audio", "sle-scar-island-audio", "sky-act2-day-2-2-4pm-landing",
                   "sle-scar-island-forest-trail", "sle-scar-island-forest-trail-water",
                   "sle-scar-island-landing-water", "sle-scar-island-landing-wide",
                   "sle-scar-island-landing-wide-ocean", "sle-scar-island-landing-wide-water",
                   "sle-scar-island-landing-scar-capital-wide",
                   # menu send-off: the trail's script level = the game's own pigeon flocks (61 FlockingBird
                   # spawners flee-sle-bird-lookout-* / -forest-* with their splines; the ext force-flees them after the horn)
                   "sle-scar-island-forest-trail-script"],   # (VRAM: no landing main / logging camp / blockmesh)
        "actors": SENDOFF_ACTORS + POSE_ACTORS + POSE_ANIM_ACTORS, "symbols": SENDOFF_SYMBOLS,
    },
]


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    r = qmul(qmul(q, (v[0], v[1], v[2], 0.0)), (-q[0], -q[1], -q[2], q[3]))
    return r[:3]


def look_quat(cam, target):
    """Quaternion turning +Z (the engine's forward) toward target: yaw about +Y, then pitch about
    the local +X (positive = down)."""
    dx, dy, dz = (target[i] - cam[i] for i in range(3))
    yaw = math.atan2(dx, dz)
    pitch = math.atan2(-dy, math.hypot(dx, dz))
    q = qmul((0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)), (math.sin(pitch / 2), 0.0, 0.0, math.cos(pitch / 2)))
    f = qrot(q, (0.0, 0.0, 1.0))
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    assert all(abs(f[i] - d / n) < 1e-6 for i, d in enumerate((dx, dy, dz))), (f, (dx, dy, dz))
    return q, yaw


# The main menu shows the Hillcrest overview with Jesse's smoke (Ellie day 2, Rescue Jesse). Scene for scouting
# the exact camera (t2r-menu-scout.txt + F9 debug fly, F11 save; then the menu cam tuner): T2R_MENU_SCENE0=hillcrest swaps it in
# for the no-clan forest default. Camera: the game's own vantage spawner pos-res-get-vantage-1 (10.28, 12.09, 481.02) looking at
# look-res-smoke-plume-1 (121.92, 37.65, 392.42); the smoke itself is level FX (res-smoke-plume-fx).
HILLCREST = {
    "side": 0, "name": "hillcrest",
    "subnode": "to1-main-menu", "set": MENU_SET, "pak": "to1-main-menu",
    "camera": (10.3, 13.6, 481.0), "target": (121.92, 37.65, 392.42), "floor": 12.09,
    "player": (10.28, 12.09, 481.02),
    "levels": ["res-const-render", "res-const-texture-adjust", "res-const-audio", "res-neighborhood-audio",
               "res-const-fx", "res-const-dispatcher-fx", "res-stores-neighborhood-const", "sky-act2-day-2-rescue-jesse",
               "res-neighborhood-fight-tower-hill", "res-neighborhood-fight-tower-hill-wide", "res-neighborhood-fight-tower-hill-low",
               "res-neighborhood-wide-hills", "res-stores-midground-hills", "res-smoke-plume-fx", "part-level-res-smoke-plume-fx"],
}
if os.environ.get("T2R_MENU_SCENE0") == "hillcrest":
    MENU_SCENES[0] = HILLCREST


def make_pak(src, dst, scene):
    b = bytearray(src if isinstance(src, (bytes, bytearray)) else open(src, "rb").read())
    cam = scene["camera"]
    q, yaw = look_quat(cam, scene["target"])
    qy = (0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2))          # the player only turns
    # (as in the original menu: there the player stands 10 m behind winmm's hard-coded menu camera,
    # frozen by its joypad lock - re/mp-menu-background.md section 5; t2r-ext feature_menu_lock)
    # the menu world's player (it IS spawned: it ran about in the forest when it got the
    # controls): on the floor 0.3 m behind the camera, out of the shot; the ext also hides it
    ply = (cam[0] - 0.3 * math.sin(yaw), scene["floor"], cam[2] - 0.3 * math.cos(yaw))
    if "player" in scene:          # a scouted camera (flown with debug fly) may have no ground under it: own spot
        ply = scene["player"]
    for orig, pos, quat in ((ORIG_CAMERA, cam, q), (ORIG_PLAYER, ply, qy)):
        key = struct.pack("<4f", *orig, 1.0)
        i = b.find(key)
        assert i >= 0 and b.find(key, i + 1) < 0, f"{src}: transform {orig} not found once"
        struct.pack_into("<4f", b, i, *pos, 1.0)
        struct.pack_into("<4f", b, i + 16, *quat)
    open(dst, "wb").write(b)
    return yaw


def _entries(f):
    cnt = struct.unpack_from("<I", f.data, 0x14)[0]
    eo = struct.unpack_from("<Q", f.data, 0x18)[0]
    return {struct.unpack_from("<Q", f.data, eo + i * 24)[0]: struct.unpack_from("<Q", f.data, eo + i * 24 + 16)[0]
            for i in range(cnt)}


def _cstr(f, o):
    return f.data[o:f.data.index(b"\0", o)].decode("latin1")


def patch_level_sets(path, scenes=MENU_SCENES):
    """New level lists for the scenes' level sets; the level-set-arrays block is a copy of
    tsk-to1-main-menu's (to1-all part set) with list 0 = the scene's levels."""
    f = DcFile(open(path, "rb").read())
    ent = _entries(f)
    menu = ent[fnv(MENU_SET)]
    assert _cstr(f, f.q(menu)) == MENU_SET
    marr = f.q(menu + 0x10)
    names = []                                   # (level-entry offset, name): strings go last
    for sc in scenes:
        tgt = ent[fnv(sc["set"])]
        assert _cstr(f, f.q(tgt)) == sc["set"], sc["set"]
        lst = []
        for lv in [sc["pak"]] + sc["levels"]:
            e = f.append(struct.pack("<QQII", 0, fnv(lv), 3, 7), ptr_slots=(0,), tag="level-entry")
            lst.append(e)
            names.append((e, lv))
        lo = f.append(struct.pack(f"<{len(lst)}Q", *lst), ptr_slots=tuple(range(0, 8 * len(lst), 8)))
        blob, slots = f.copy_block(marr, 0x70)
        blob = bytearray(blob)
        struct.pack_into("<QI", blob, 0, lo, len(lst))
        arr = f.append(bytes(blob), ptr_slots=slots, tag="level-set-arrays")
        f.set_ptr(tgt + 0x10, arr)
    for e, lv in names:                          # after every append(): nothing moves them now
        f.set_ptr(e, len(f.data))
        f.data += lv.encode() + b"\0"
    f.data += bytes((-len(f.data)) % 8)
    open(path, "wb").write(f.save())


def check_tasks(path, scenes=MENU_SCENES):
    """The starlight subnodes in test-tasks.bin load the scenes' level sets (read only)."""
    d = open(path, "rb").read()
    for sc in scenes:
        key = struct.pack("<Q", fnv(sc["subnode"]))
        sub, i = None, d.find(key)
        while i >= 8 and sub is None:            # subnode: [0] name ptr, [8] name sid
            name = struct.unpack_from("<Q", d, i - 8)[0]
            if 0 < name < len(d) and d[name:name + len(sc["subnode"]) + 1] == sc["subnode"].encode() + b"\0":
                sub = i - 8
            i = d.find(key, i + 1)
        assert sub is not None, sc["subnode"]
        lsp = struct.unpack_from("<Q", d, sub + 0x140)[0]
        assert d[lsp:d.index(b"\0", lsp)].decode() == sc["set"], (sc["subnode"], "level set")
        arr = struct.unpack_from("<Q", d, sub + 0xB8)[0]
        assert struct.unpack_from("<Q", d, arr)[0] == fnv(sc["set"]), (sc["subnode"], "level set sid")


def _with_extras(block, sc):
    """the block with the scene's extra actor / symbol lines, each after the last line of its kind (the stock order:
    level-name, level-id, package, particle-module, actor..., symbol...)"""
    out = list(block)
    for kind, names in (("actor", sc.get("actors", [])), ("symbol", sc.get("symbols", []))):
        for nm in names:
            ln = f"{kind} {nm}"
            if ln in out:
                continue
            at = max([i for i, l in enumerate(out) if l.startswith(kind + " ")] or
                     [i for i, l in enumerate(out) if l.startswith(("package ", "particle-module ", "actor "))] or [len(out) - 1])
            out.insert(at + 1, ln)
    return out


def patch_registry(path, scenes=MENU_SCENES):
    """pak68.txt: each scene pak = a copy of the to1-main-menu block (its actors / symbols) + the scene's extra
    actors / symbols (the send-off birds)."""
    lines = open(path, encoding="latin1").read().split("\n")
    def span(name):
        i = lines.index(f"level-name {name}")
        j = i + 1
        while j < len(lines) and not lines[j].startswith("level-name "):
            j += 1
        while j > i + 1 and not lines[j - 1]:
            j -= 1
        return i, j
    i, j = span("to1-main-menu")
    block = lines[i:j]
    changed = False
    add = []
    for sc in scenes:
        if f"level-name {sc['pak']}" in lines:       # (a staged tree from an earlier run: make sure the extras are in its block)
            i, j = span(sc["pak"])
            nb = _with_extras(lines[i:j], sc)
            if nb != lines[i:j]:
                lines[i:j] = nb
                changed = True
            continue
        cp = []
        for ln in block:
            k, _, v = ln.partition(" ")
            if k in ("level-name", "level-id"):
                ln = f"{k} {sc['pak']}"
            elif k == "package":
                ln = f"package {sc['pak']}-ingame"
            cp.append(ln)
        add += _with_extras(cp, sc)
    if add:
        while lines and not lines[-1]:
            lines.pop()
        lines += add + [""]
    if add or changed:
        open(path, "w", encoding="latin1", newline="\n").write("\n".join(lines))


def apply(stage, paths, order, scenes=MENU_SCENES):
    """Everything on the staged mod tree. Returns level-sets-test.bin's new size (modules.bin)."""
    check_tasks(os.path.join(stage, "bin", "dc1", "test-tasks.bin"), scenes)
    src = open(os.path.join(stage, "pak68", MENU_SRC_PAK), "rb").read()   # (the default scene rewrites it)
    for sc in scenes:
        pak = sc["pak"] + "-ingame.pak"
        yaw = make_pak(src, os.path.join(stage, "pak68", pak), sc)
        p = "pak68/" + pak
        for lst in (paths, order):
            if p not in lst:
                lst.insert(lst.index("pak68/" + MENU_SRC_PAK) + 1, p)
        print(f"menu scene {sc['name']}: {p}, camera {sc['camera']} yaw {math.degrees(yaw):.1f}, "
              f"{len(sc['levels'])} levels -> level set {sc['set']}")
    ls = os.path.join(stage, "bin", "dc1", "level-sets", "level-sets-test.bin")
    patch_level_sets(ls, scenes)
    patch_registry(os.path.join(stage, "pak68.txt"), scenes)
    return os.path.getsize(ls)
