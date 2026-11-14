"""Cue hash table of the game's sound banks (sndbank.cue_table / layout_cues / retarget_cue) and the payload audit of the suppressed-rifle carrier.

Root cause: the carrier bank's event hash was rewritten IN PLACE; the cue table is a coalesced hash table (slot hash % N, `next` chain), so the
retargeted event was never found: silent suppressed rifles.  Checks: (1) the layout algorithm reproduces the game's own tables byte for byte (every wpn bank
found under re/sound), (2) retarget_cue's result is found by the lookup and keeps every other cue, (3) an in-place rewrite is rejected by the payload audit.
Needs re/sound in the main checkout for (1)-(3) with real banks; without it only the synthetic table case runs."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import sndbank  # noqa: E402
from dcfile import fnv  # noqa: E402

# synthetic: 8 cues in an 8-slot table, built by layout_cues; every cue found, a rewritten-in-place hash is not
names = ["sfx-a", "sfx-b", "sfx-c", "sfx-d", "sfx-e", "sfx-f", "sfx-g", "sfx-h"]
ents = [(fnv(n), i) for i, n in enumerate(names)]
lay = sndbank.layout_cues(ents, 8)
table = b"".join(struct.pack(sndbank.CUE_REC, *e) for e in lay)
bank = bytes(0x40) + table + bytes(0x40)
for h, c in ents:
    assert sndbank.cue_lookup(bank, h) == c, "synthetic lookup"
new = fnv("sfx-retargeted")
moved = sndbank.rebuild_cue_table(bank, fnv("sfx-c"), new)
assert sndbank.cue_lookup(moved, new) == 2 and sndbank.cue_lookup(moved, fnv("sfx-c")) is None
for h, c in ents:
    if h != fnv("sfx-c"):
        assert sndbank.cue_lookup(moved, h) == c
inplace = bank.replace(struct.pack("<Q", fnv("sfx-c")), struct.pack("<Q", new))
try:
    found = sndbank.cue_lookup(inplace, new)
except ValueError:
    found = None
assert found is None, "an in-place rewritten hash must not be found (bucket / chain mismatch)"


def find(*parts):
    for base in (ROOT, MAIN):
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return None


snd = find("re", "sound")
if snd and os.path.exists(os.path.join(snd, "wpn-rifle-tommy.bnk")):
    ok = 0
    for fn in sorted(os.listdir(snd)):
        if not (fn.startswith("wpn-") and fn.endswith(".bnk")):
            continue
        b = open(os.path.join(snd, fn), "rb").read()
        hit = None
        for s in re.findall(rb"sfx-[ -~]{4,60}", b):
            h = fnv(s.decode())
            if b.count(struct.pack("<Q", h)) == 1:
                try:
                    hit = (h,) + sndbank.cue_table(b, h)
                    break
                except ValueError:
                    pass
        if not hit:
            continue
        _, st, n = hit
        es = [struct.unpack_from(sndbank.CUE_REC, b, st + 16 * j) for j in range(n)]
        mine = b"".join(struct.pack(sndbank.CUE_REC, *e) for e in sndbank.layout_cues([(e[0], e[3]) for e in es], n))
        assert mine == b[st:st + 16 * n], f"{fn}: the layout algorithm does not reproduce the game's cue table"
        ok += 1
    assert ok >= 5, f"only {ok} banks checked"
    print(f"cue tables: layout reproduces {ok} stock banks byte for byte")
    galil = open(os.path.join(snd, "wpn-rifle-autorifle2.bnk"), "rb").read()
    donor = open(os.path.join(snd, "wpn-rifle-tommy.bnk"), "rb").read()
    out = sndbank.retarget_cue(galil, "sfx-galil-player", "sfx-rifle-tommy-player", donor)
    assert sndbank.cue_lookup(out, fnv("sfx-rifle-tommy-player")) is not None and len(out) == len(galil)
    # payload audit on that bank: good one passes, the in-place one fails
    import dc_data_patches as D
    import payload_audit
    pak = ("level-name starlight-mp-test\nactor " + D.SUPP_CARRIER_ACTOR + "\nsound-bank " + D.SUPP_CARRIER_BANK + "\nlevel-name x\n").encode()
    good = {f"soundbank4/{D.SUPP_CARRIER_BANK}.bnk": out, "pak68.txt": pak}
    assert not payload_audit.audit_supp_carrier(good, D, sndbank), payload_audit.audit_supp_carrier(good, D, sndbank)
    k = galil.find(struct.pack("<Q", fnv("sfx-galil-player")))
    bad = bytearray(galil)
    bad[k:k + 8] = struct.pack("<Q", fnv("sfx-rifle-tommy-player"))
    bad[0x30:0x60] = donor[0x30:0x60]
    probs = payload_audit.audit_supp_carrier({f"soundbank4/{D.SUPP_CARRIER_BANK}.bnk": bytes(bad), "pak68.txt": pak}, D, sndbank)
    assert probs and "silent" in probs[0] or "cue table" in probs[0], probs
    probs = payload_audit.audit_supp_carrier({f"soundbank4/{D.SUPP_CARRIER_BANK}.bnk": out, "pak68.txt": b"level-name starlight-mp-test\n"}, D, sndbank)
    assert len(probs) == 2, probs
    assert payload_audit.audit_supp_carrier({"soundbank4/" + D.SUPP_CARRIER_BANK + ".bnk": None, "pak68.txt": pak}, D, sndbank)
    print("payload audit: good carrier passes, in-place retarget / missing level adds / missing bank are reported")
else:
    print("test_sndbank_cues: re/sound not present, real-bank cases skipped")
print("test_sndbank_cues: ok")
