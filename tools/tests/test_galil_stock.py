"""Offline check that the purchasable Galil keeps its stock v1.08 shot: replays the build's weapon-art steps on a temp copy of the game's
dc1 files (clones of the suppressed rifles from SUPP_WEAPONS) and runs dc_data_patches.verify_galil_stock against the staged bank logic (the game's
wpn-rifle-autorifle2.bnk byte for byte), and that the suppressed rifles' carrier bank equals the old modified Galil bank (rebuilt here with the
the earlier build's own recipe) except for the cue table (re-laid for the retargeted hash) and the header.  Negative cases: an edited Galil bank, and the old wiring (suppressed rifle on sfx-galil-player), must be
rejected.  Needs the extracted game files (re/gamebin/dc1, re/sound in the main checkout); skipped without them."""
import os
import shutil
import struct
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))


def find(*parts):
    for base in (ROOT, MAIN):
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return None


src = find("re", "gamebin", "dc1")
bank_path = find("re", "sound", "wpn-rifle-autorifle2.bnk")
if not (src and bank_path and os.path.exists(os.path.join(src, "weapon-art.bin"))):
    print("test_galil_stock: game files not extracted here - skipped")
    sys.exit(0)

os.environ["T2R_FAR_NPC_SHOT"] = "1"
import dc_data_patches as D  # noqa: E402
import weapon_clone  # noqa: E402

FILES = ("weapon-gameplay.bin", "weapon-art.bin", "weapon-damages.bin", "weapon-upgrades.bin")
tmp = tempfile.mkdtemp(prefix="galil_stock_")
try:
    dc1 = os.path.join(tmp, "dc1")
    os.makedirs(dc1)
    for f in FILES:
        shutil.copy(os.path.join(src, f), os.path.join(dc1, f))
    for base, sfx, audio, mode in D.SUPP_WEAPONS:
        if base == "rifle-mpx5":
            weapon_clone.clone_weapon(dc1, base, base + "-supp", sfx, audio, mode, None, {D.CAN_JOINT: 1}, D.FAR_MUZZLE_SHIFT)
        elif base in ("rifle-vepr", "rifle-remington-bolt"):
            weapon_clone.clone_weapon(dc1, base, base + "-supp", sfx, audio, mode, D.SUPP_MODEL_OF.get(base))
    weapon_clone.set_art_sfx(os.path.join(dc1, "weapon-art.bin"), "rifle-mpx5", D.FAR_SFX)
    stock = open(bank_path, "rb").read()
    D.verify_galil_stock(dc1, stock, stock)
    if D.SUPP_CARRIER_ON:
        import sndbank
        snd = os.path.dirname(bank_path)
        wav = os.path.join(snd, "wav")
        # the old build's Galil bank, as build_dll made it before the fix (RIFLE_SUPP_PCM + mix_pcm GALIL_MIX)
        old = stock
        for srcb, mapping in D.SUPP_MIX_PCM:
            old = sndbank.replace_pcm(old, os.path.join(wav, "wpn-rifle-autorifle2"), mapping, os.path.join(wav, srcb))
        old = sndbank.mix_pcm(old, os.path.join(wav, "wpn-rifle-autorifle2"), D.SUPP_MIX_MIX, os.path.join(wav, "wpn-rifle-autorifle4"), 1.0)
        assert old != stock, "the old mix changed nothing?"
        carrier = D.build_supp_carrier_bank(os.path.dirname(os.path.dirname(snd)))
        mod_dir = os.path.join(src, "audio-sfx", "weapons")
        D.verify_supp_carrier(os.path.dirname(os.path.dirname(snd)), src, carrier, old)
        bad = bytearray(carrier)
        bad[0x100000 % len(bad)] ^= 0x55
        try:
            D.verify_supp_carrier(os.path.dirname(os.path.dirname(snd)), src, bytes(bad), old)
        except AssertionError:
            pass
        else:
            raise SystemExit("verify_supp_carrier accepted a changed carrier bank")
        # the old carrier: the cue hash rewritten in place (the entry stays in the old hash's chain, the lookup of the new name never finds it)
        from dcfile import fnv as _fnv
        inplace = bytearray(old)
        k = inplace.find(struct.pack("<Q", _fnv(D.SUPP_CARRIER_SRC_EVENT)))
        inplace[k:k + 8] = struct.pack("<Q", _fnv(D.SUPP_CARRIER_EVENT))
        donor = open(os.path.join(snd, D.SUPP_CARRIER_BANK + ".bnk"), "rb").read()
        inplace[0x30:0x60] = donor[0x30:0x60]
        assert sndbank.cue_lookup(carrier, _fnv(D.SUPP_CARRIER_EVENT)) is not None, "the rebuilt carrier's cue is not found by the hash lookup"
        try:
            D.verify_supp_carrier(os.path.dirname(os.path.dirname(snd)), src, bytes(inplace), old)
        except AssertionError as e:
            assert "lookup" in str(e) or "cue table" in str(e), e
        else:
            raise SystemExit("verify_supp_carrier accepted the PT79 carrier (cue hash rewritten in place, lookup misses it)")
        try:
            D.verify_supp_carrier(os.path.dirname(os.path.dirname(snd)), src, old, old)
        except AssertionError:
            pass
        else:
            raise SystemExit("verify_supp_carrier accepted the un-retargeted Galil copy")
    edited = bytearray(stock)
    edited[len(edited) // 2] ^= 0xff
    try:
        D.verify_galil_stock(dc1, bytes(edited), stock)
    except AssertionError:
        pass
    else:
        raise SystemExit("verify_galil_stock accepted an edited Galil bank")
    # the old wiring: the suppressed rifle on the Galil's own events
    for f in FILES:
        shutil.copy(os.path.join(src, f), os.path.join(dc1, f))
    weapon_clone.clone_weapon(dc1, "rifle-vepr", "rifle-vepr-supp",
                              {"sfx-rifle-vepr-player": "sfx-galil-player", "sfx-rifle-vepr-npc": "sfx-galil-npc"}, None, 2)
    try:
        D.verify_galil_stock(dc1, stock, stock)
    except AssertionError:
        pass
    else:
        raise SystemExit("verify_galil_stock accepted a suppressed rifle on the Galil's events")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("test_galil_stock: ok")
