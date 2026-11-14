"""Offline check of the Full-Auto Rifle / MPX-S sound split (dc_data_patches.FAR_NPC_SHOT: the MPX-S did not use its SP sounds for the
suppressed gunshots): replays the build's weapon-art steps on a temp copy of the game's dc1 files (clone rifle-mpx5-supp + rifle-vepr-supp
from SUPP_WEAPONS, then the FAR's art swap) and the bank edit, then runs verify_far_mpxs.  Needs the extracted game files (re/gamebin/dc1,
re/sound in the main checkout); skipped without them."""
import os
import shutil
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
bank_path = find("re", "sound", "wpn-rifle-autorifle4.bnk")
ruger_path = find("re", "sound", "wpn-pistol-storm.bnk")
if not (src and bank_path and ruger_path and os.path.exists(os.path.join(src, "weapon-art.bin"))):
    print("test_far_mpxs: game files not extracted here - skipped")
    sys.exit(0)

os.environ["T2R_FAR_NPC_SHOT"] = "1"
import dc_data_patches as D  # noqa: E402
import sndbank  # noqa: E402
import weapon_clone  # noqa: E402

assert D.FAR_NPC_SHOT and D.FAR_WAVES is D.FAR_WAVES_NPC and not D.FAR_PCM
tmp = tempfile.mkdtemp(prefix="far_mpxs_")
try:
    dc1 = os.path.join(tmp, "dc1")
    os.makedirs(dc1)
    for f in ("weapon-gameplay.bin", "weapon-art.bin", "weapon-damages.bin", "weapon-upgrades.bin"):
        shutil.copy(os.path.join(src, f), os.path.join(dc1, f))
    wa = os.path.join(dc1, "weapon-art.bin")
    for base, sfx, audio, mode in D.SUPP_WEAPONS:
        if base == "rifle-mpx5":
            weapon_clone.clone_weapon(dc1, base, base + "-supp", sfx, audio, mode, None, {D.CAN_JOINT: 1}, D.FAR_MUZZLE_SHIFT)
        elif base == "rifle-vepr":
            weapon_clone.clone_weapon(dc1, base, base + "-supp", sfx, audio, mode, D.SUPP_MODEL_OF.get(base))
    weapon_clone.set_art_sfx(wa, "rifle-mpx5", D.FAR_SFX)
    orig = open(bank_path, "rb").read()
    far = sndbank.replace_waves(orig, open(ruger_path, "rb").read(), D.FAR_WAVES)
    D.verify_far_mpxs(dc1, far, orig)
    # the unedited bank would have failed the "tails identical" half only if the tails were touched: make sure the check can fail
    bad = sndbank.replace_waves(orig, open(ruger_path, "rb").read(), D.FAR_WAVES_LEGACY)
    try:
        D.verify_far_mpxs(dc1, bad, orig)
    except AssertionError:
        pass
    else:
        raise SystemExit("verify_far_mpxs accepted a bank with the suppressed tail edited")
    # the legacy art (no swap) must fail the art half
    for f in ("weapon-gameplay.bin", "weapon-art.bin", "weapon-damages.bin", "weapon-upgrades.bin"):
        shutil.copy(os.path.join(src, f), os.path.join(dc1, f))
    weapon_clone.clone_weapon(dc1, "rifle-mpx5", "rifle-mpx5-supp", {D.MPX5_NPC_EVENT: D.MPX5_SUPP_EVENT, **D.RIFLE_SUPP_FLASH})
    weapon_clone.clone_weapon(dc1, "rifle-vepr", "rifle-vepr-supp", dict(D.SUPP_WEAPONS[0][1]))
    try:
        D.verify_far_mpxs(dc1)
    except AssertionError:
        pass
    else:
        raise SystemExit("verify_far_mpxs accepted an un-swapped FAR art def")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("test_far_mpxs: ok")
