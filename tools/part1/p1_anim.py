"""Part I PC animation paks (version 0xA7D): list the clips and pull their ClipData out for the TLOU2 decoder.

Layout (measured on anim-t1x-joel-player-gun.pak; tools/part1/p1_pak.py reads the pages / fixups / login table):
  PAK_LOGIN_TABLE -> ANIM_GROUP items (48-byte item header, type id fnv('ANIM_GROUP'));
  ANIM_GROUP data (+0x30): u32 count, u32 ?, ptr -> array of `count` pointers, each to an ANIM ITEM HEADER
  (TLOU2: the same, data +0 count, +8 array ptr);
  ANIM item header: +0x10 u32 size, +0x18 u64 name sid = fnv1a64(clip name), +0x20 type fnv('ANIM');
  ANIM data (+0x30): u32 7, u32 flags (bit 0 = loop), +0x08 ptr ClipData, +0x10 ptr ANIM_RAWCHANNELS, +0x20 u32 skeleton id
  (same as TLOU2's ANIM resource, re/uc4ps4/DOWNED.md section 4).
ClipData itself is the TLOU2 format (magic 0x41430102 ... ; decoded with re/uc4ps4/tools/uc4anim.ClipDecoder).
Names: the pak carries the clip name strings, matched to the item's name sid.

  python p1_anim.py list <pak> [substring]          name, frames, fps, skeleton id, groups, flags, ClipData size
  python p1_anim.py dump <pak> <clip> <out.clip>    raw ClipData bytes
Library: P1Anims(path).clips -> {name: dict(clip=bytes, flags, skel, raw=offset or 0)}"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_pak  # noqa: E402

ANIM = p1_pak.fnv("ANIM")
GROUP = p1_pak.fnv("ANIM_GROUP")


class P1Anims:
    def __init__(self, path):
        self.k = k = p1_pak.P1Pak(path)
        d = k.d
        names = {}
        for m in re.findall(rb"[\x21-\x7e]{3,160}", d):
            names[p1_pak.fnv(m.decode("latin1"))] = m.decode("latin1")
        self.clips = {}
        self.unnamed = 0
        for t, pg, off in k.items:
            if t != "ANIM_GROUP":
                continue
            a = k.pages[pg][0] + off
            cnt = k.u32(a + 0x30)
            arr = k.ptr(a + 0x38)
            for i in range(cnt):
                it = k.ptr(arr + 8 * i)
                if not it or k.u64(it + 0x20) != ANIM:
                    continue
                sid = k.u64(it + 0x18)
                nm = names.get(sid)
                if nm is None:
                    self.unnamed += 1
                    nm = "#%016x" % sid
                base = it + 0x30
                ca = k.ptr(base + 8)
                if not ca:
                    continue
                size = k.u32(ca + 8)
                self.clips[nm] = dict(clip=d[ca:ca + size + 0x10], flags=k.u32(base + 4), skel=k.u32(base + 0x20),
                                      raw=k.ptr(base + 0x10), item=it, ca=ca)

    @staticmethod
    def info(c):
        b = c["clip"]
        magic, sig = struct.unpack_from("<II", b, 0)
        groups, frames = struct.unpack_from("<HH", b, 0xc)
        fps = struct.unpack_from("<f", b, 0x1c)[0]
        return dict(magic=magic, sig=sig, groups=groups, frames=frames, fps=fps)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    a = P1Anims(argv[2])
    if argv[1] == "list":
        sub = argv[3] if len(argv) > 3 else ""
        for n in sorted(a.clips):
            if sub in n:
                c = a.clips[n]
                i = a.info(c)
                print(f"{n}\t{i['frames']}f @{i['fps']:g}\tsig {i['sig']:08x}\tskel {c['skel']:08x}\tgroups {i['groups']}"
                      f"\tflags {c['flags']:#x}\t{len(c['clip'])} B")
        print(f"# {len(a.clips)} clips ({a.unnamed} without a name string)", file=sys.stderr)
    elif argv[1] == "dump":
        open(argv[4], "wb").write(a.clips[argv[3]]["clip"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
