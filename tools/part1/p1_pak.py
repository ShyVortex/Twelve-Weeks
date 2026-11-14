"""Read-only inspector for Naughty Dog .pak files in the Part I PC layout (magic/version 2685 = 0xA7D).

TLOU2 PC paks (version 2681 = 0xA79, tools/models/ndpak.py) carry a DEADBEEF header in every page with an item table
and item/type NAME strings.  Part I PC paks have none of that: pages are raw, the resource items are found through the
PAK_LOGIN_TABLE item (header u32[2] = page index, u32[3] = offset) and typed by a 64-bit string id.  Layout learned
from the community Noesis plugin (tools/models/fmt_nd_pak_t2r.py, `isTLOUP1` branches) and verified here on real files.

  python p1_pak.py items <pak>...        # header, page table, item type histogram, geometry + texture summary
  python p1_pak.py tex <pak>...          # referenced VRAM_DESC hashes (u64) and their source paths
Library: P1Pak(path) -> .items [(type, page, offset)], .submeshes, .tex_hashes
"""
import collections
import struct
import sys

def fnv(s):
    """64-bit FNV-1a; the Part I type id of an item is fnv(<TLOU2 type name>) (verified: GEOMETRY_1 = 0x349D779A792F45C1)"""
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & (2 ** 64 - 1)
    return h


# every item type name seen in TLOU2 paks (ndpak over 1139 local paks) plus Part I's TEXTURE_DICTIONARY
TYPE_NAMES = """ACTOR_FLAGS AMBSHADOWS_OCCLUDER_INFO ANIM ANIM_GROUP ANIM_RAWCHANNELS BACKGROUND_SECTION
COLLISION_DATA_BACKGROUND COLLISION_DATA_CLOTH COLLISION_DATA_EMPTY COLLISION_DATA_FOREGROUND EFFECT EFFECT_TABLE
FEATURE_DB_2 FOREGROUND_SECTION_2 GEOMETRY_1 JOINT_HIERARCHY JSON_DOC KD_TREE_2 LEVEL_BOUNDING_BOX_DATA LEVEL_INFO_3
LEVEL_INFO_4 LIGHT_TABLE_1 MATERIAL_TABLE_1 NAV_MESH_1 NAV_MESH_HEIGHT_MAP_TEX_1 PAK_LOGIN_TABLE POPULATOR_1 REGION_TREE
SKELETON_FLIPDATA SOUND_BANK_TABLE SPAWNER_GROUP SPLINE_TABLE TAG_FLOAT TAG_INT TAG_VEC4 TEXTURE_TABLE
UI_TEXTURES_METADATA VRAM_DESC VRAM_DESC_TABLE TEXTURE_DICTIONARY VIS_INFO_1 COLLISION_DATA_HAVOK_BG SPECULAR_CUBEMAPSET
ANIMATED_LIGHTS""".split()
TYPES = {fnv(n): n for n in TYPE_NAMES}
# resolved through the UC4 string dump (re/uc4/sid4_strings.txt). TLOU2 level paks carry both as OPTIONAL items (checked on 10 real
# levels: INTERACTIVE_BG_1 in 5, SPECULAR_CUBEMAPSET in 3); only INTERACTIVE_BG_1 has the same header layout - KEEPABLE below. 0xe46b228f24953070 = ANIMATED_LIGHTS (fnv matches; 32-byte entries {name ptr, kind 0 point / 1 ortho / 2 spot / 3 sun, index, 0x56d5d88f5c008545, 0} in BOTH games - the table that binds a ProcessDynLight actor to its light record; kept now).
EXTRA_TYPES = {fnv(n): n for n in ("INTERACTIVE_BG_1", "SPECULAR_CUBEMAPSET")}
KEEPABLE = {fnv("INTERACTIVE_BG_1"): "INTERACTIVE_BG_1"}      # (SPECULAR_CUBEMAPSET is now a normal TYPE: the Part I probe records are byte-identical to TLOU2's - 256 bytes, format byte 3, name pointer +0xe0, texture key +0xf0 = the cubemap VRAM_DESC hash - the old "packed" reading was taken from the wrong page)
PAD = 48          # resource item header before its payload (TLOU2 and Part I)
SUBMESH = {0xA79: 192, 0xA7D: 176}   # GEOMETRY_1 submesh record size per pak version (measured; UC4 is 176 too)
COUNTS = {0xA79: 0x88, 0xA7D: 0x80}  # offset of u32 vertex count; index count +4, stream count +8


class P1Pak:
    def __init__(self, path, data=None):
        self.path = path
        self.d = d = data if data is not None else open(path, "rb").read()
        u32 = self.u32 = lambda o: struct.unpack_from("<I", d, o)[0]
        self.u64 = lambda o: struct.unpack_from("<Q", d, o)[0]
        self.version, self.hdr_size, self.login_page, self.login_off, n, pt, nfix, ft = (u32(i * 4) for i in range(8))
        if self.version not in (2681, 2685, 68217, 68221):   # 0x10a79 / 0x10a7d = texture dict variants
            raise ValueError(f"{path}: version {self.version:#x} is not a TLOU pak")
        self.p1 = self.version in (2685, 68221)
        self.version_base = self.version & 0xFFFF
        # Part I has 3 extra header words before the page table (pt = 0x3c, TLOU2 0x2c)
        self.pages = [struct.unpack_from("<III", d, pt + 12 * i) for i in range(n)]
        fo, fdat, fcnt = u32(ft), u32(ft + 4), u32(ft + 8)
        self.fix = {}
        for i in range(fcnt):
            sp, dp, so = struct.unpack_from("<HHI", d, fdat + 8 * i)
            self.fix[self.pages[sp][0] + so] = dp
        self.items = []
        self.unknown = collections.Counter()
        if self.p1:
            self._items_p1()

    def ptr(self, addr):
        """absolute file offset a pointer field at `addr` refers to (0 if it has no fixup)"""
        dp = self.fix.get(addr)
        if dp is None:
            return 0
        return self.u64(addr) + self.pages[dp][0]

    def _items_p1(self):
        lt = self.pages[self.login_page][0] + self.login_off
        cnt = self.u32(lt + PAD)
        for i in range(cnt):
            pg, off = struct.unpack_from("<II", self.d, lt + PAD + 8 + 8 * i)
            addr = self.pages[pg][0] + off
            tid = self.u64(addr + 32)
            t = TYPES.get(tid)
            if t is None:
                self.unknown[tid] += 1
                t = "?%016x" % tid
            self.items.append((t, pg, off))

    def of_type(self, t):
        return [(pg, off) for tt, pg, off in self.items if tt == t]

    @property
    def submeshes(self):
        out = []
        for pg, off in self.of_type("GEOMETRY_1"):
            base = self.pages[pg][0] + off + PAD
            cnt, arr = self.u32(base + 8), self.ptr(base + 40)
            c = COUNTS[self.version_base]
            for i in range(cnt):
                o = arr + SUBMESH[self.version_base] * i
                nm = self.ptr(o + 0x20)
                out.append({"offset": o, "name": self.cstr(nm) if nm else "", "vcount": self.u32(o + c),
                            "icount": self.u32(o + c + 4), "nstreams": self.u32(o + c + 8)})
        return out

    def cstr(self, o):
        e = self.d.index(b"\0", o)
        return self.d[o:e].decode("latin1")

    @property
    def tex_hashes(self):
        """{hash: source path} of every VRAM_DESC reachable from TEXTURE_TABLE / TEXTURE_DICTIONARY items"""
        out = {}
        for t in ("TEXTURE_TABLE", "TEXTURE_DICTIONARY"):
            for pg, off in self.of_type(t):
                a = self.pages[pg][0] + off
                n = self.u32(a + PAD)
                lst = self.ptr(a + PAD + 24)
                for i in range(n):
                    dp = self.fix.get(lst + 8 * i)
                    if dp is None:
                        continue
                    v = self.pages[dp][0] + self.u64(lst + 8 * i) - 32
                    h = self.u64(v + 56)
                    try:
                        p = self.cstr(v + 112)
                    except ValueError:
                        p = ""
                    out[h] = p
        return out


def main(argv):
    if len(argv) < 3 or argv[1] not in ("items", "tex"):
        print(__doc__)
        return 1
    for path in argv[2:]:
        k = P1Pak(path)
        if argv[1] == "tex":
            for h, p in sorted(k.tex_hashes.items()):
                print(f"{h:016x}\t{p}")
            continue
        print(f"{path}: version {k.version:#x} ({'Part I' if k.p1 else 'TLOU2'}), {len(k.pages)} pages "
              f"{[(hex(a), hex(b), c) for a, b, c in k.pages]}, {len(k.fix)} fixups")
        if k.p1:
            print("  items:", dict(collections.Counter(t for t, _, _ in k.items)))
            sm = k.submeshes
            print(f"  submeshes {len(sm)}, verts {sum(s['vcount'] for s in sm)}, tris {sum(s['icount'] for s in sm) // 3}")
            print(f"  texture hashes {len(k.tex_hashes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
