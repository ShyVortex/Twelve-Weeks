"""Part I sounds for the Part I Shorty / El Diablo (T2R_P1_GUNS; re/part1/weapons.md section 10).

Part I PC ships one Sony BNK per gun (sp-common.psarc soundbank4/wpn-pistol-shotgun.bnk = the Shorty,
wpn-pistol-uber.bnk = El Diablo): the same SBlk v0x23 / RIFF-ATRAC9 format as TLOU2's, events named like TLOU2's
(sfx-pistol-shotgun-player / -npc / -dryfire, sfx-weapon-pistol-shotgun-clip-eject ...).  The bank itself cannot be loaded
as is: an event plays only with its DC sfx-info module (audio-sfx/weapons/aud-sfx-wpn-<set>), which TLOU2 lacks for these
sets (and Part I's modules are an older layout).  So the waves go into the bank of a TLOU2 sound set no MP gun uses, and
the gun's art def points at that set (p1_wire GUNS[...]['sound']) - the path the Full Auto Rifle's sound uses
(sndbank.replace_waves: each target RIFF slot gets the source wave cut to whole ATRAC9 blocks / zero padded; the decoder
reads the format from the slot's own RIFF header, so the block size may differ - only the channel count must match;
raw PCM layers get decoded Part I audio with a 3 ms fade, sndbank.replace_pcm):
  Shorty    -> set pistol-ruger (art pistol-militia), bank wpn-pistol-storm: player / npc / dryfire / clip-eject /
               clip-insert / charge-back / charge-release = exactly the Part I reload's weapon-effect suffixes
  El Diablo -> set pistol-revolver-357, bank wpn-pistol-revolver-357: player / npc / dryfire / cylinder-eject /
               cylinder-reload / revolver-open / -close (its PCM 'close' layers hold the 1.5 s shot body)
Other players hear the npc event through the engine's own 3D sound (positional, the set's sfx-info distances).
Not ported (no slot of that channel count): Part I's stereo dry fires (the host's mono dry fire stays), the Shorty's
'grab' / 'gun-foley' handling (the Ruger set has no event for them), El Diablo's stereo 'colt-mech' (the host bank's
pistol-uber-mech waves ARE Part I's El Diablo mech already).
  python p1_sound.py [shorty|diablo|all]     builds both banks into %TEMP% and checks every replaced slot"""
import glob
import os
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
sys.path[:0] = [HERE, os.path.join(TOOLS, "features")]
import sndbank  # noqa: E402

P1SOUND = os.path.join(MAIN, "re", "part1", "x", "sound")

BANKS = {
    "shorty": dict(
        bank="wpn-pistol-storm", p1="wpn-pistol-shotgun",
        waves={   # host RIFF wave <- Part I wave
            # the shot body (1.67 s, -26 dB at the cut ~0.45 s, under the blooms) in the mech layer (the longest mono slots)
            "wpn-pistol-ruger-mech-1.wav": "shorty-shot-01.wav",
            "wpn-pistol-ruger-mech-2.wav": "shorty-shot-02.wav",
            "wpn-pistol-ruger-mech-3.wav": "shorty-shot-03.wav",
            "wpn-pistol-ruger-bloom-quad-1.wav": "wpn-pump-shotgun-bloom-quad-v1-1.wav",
            "wpn-pistol-ruger-bloom-quad-2.wav": "wpn-pump-shotgun-bloom-quad-v1-2.wav",
            "wpn-pistol-ruger-bloom-quad-3.wav": "wpn-pump-shotgun-bloom-quad-v1-3.wav",
            "wpn-pistol-ruger-bloom-st-1.wav": "wpn-pump-shotgun-bloom-st-v1-1.wav",
            "wpn-pistol-ruger-bloom-st-2.wav": "wpn-pump-shotgun-bloom-st-v1-2.wav",
            "wpn-pistol-ruger-bloom-st-3.wav": "wpn-pump-shotgun-bloom-st-v1-3.wav",
            "wpn-pistol-ruger-distant-1.wav": "shorty-shot-distant-01.wav",
            # reload (Part I clip suffixes clip-eject / clip-insert / charge-back / charge-release)
            "wpn-reload-beretta-m9-mag-out-2.wav": "weap-reload-pistol-shotgun-1-clip-remove.wav",
            "wpn-reload-beretta-m9-mag-in-2.wav": "weap-reload-pistol-shotgun-4-clip-insert.wav",
            "wpn-reload-beretta-m9-slide-charge.wav": "weap-reload-pistol-shotgun-6-charge-back.wav",
            "wpn-reload-beretta-m9-slide-release.wav": "weap-reload-pistol-shotgun-7-charge-release.wav",
        },
        silence=["wpn-pistol-ruger-thump-v2-1.wav", "wpn-pistol-ruger-thump-v2-2.wav", "wpn-pistol-ruger-thump-v2-3.wav"],
        pcm={"weapon-lfe-01.wav": "wpn-pump-shotgun-lfe-1.wav"}),
    "diablo": dict(
        bank="wpn-pistol-revolver-357", p1="wpn-pistol-uber",
        waves={
            "1911-bloom-player-v2-01.wav": "wpn-pistol-xaciber-bloom-quad-1.wav",
            "1911-bloom-player-v2-02.wav": "wpn-pistol-xaciber-bloom-quad-2.wav",
            "1911-bloom-player-v2-03.wav": "wpn-pistol-xaciber-bloom-quad-3.wav",
            "1911-bloom-npc-v2-01.wav": "wpn-pistol-xaciber-bloom-st-1.wav",
            "1911-bloom-npc-v2-02.wav": "wpn-pistol-xaciber-bloom-st-2.wav",
            "1911-bloom-npc-v2-03.wav": "wpn-pistol-xaciber-bloom-st-3.wav",
            "pistol-revolver-distant-01.wav": "colt-tail-outdoor-01.wav",
            "pistol-revolver-distant-02.wav": "wpn-pistol-xaciber-bloom-st-rears-dist-shot-01.wav",
            "pistol-revolver-distant-03.wav": "colt-tail-outdoor-03.wav",
            "pistol-revolver-distant-04.wav": "wpn-pistol-xaciber-bloom-st-rears-dist-shot-02.wav",
            "pistol-revolver-distant-05.wav": "wpn-pistol-xaciber-bloom-st-rears-dist-shot-03.wav",
            "wpn-sw629-eject.wav": "weap-reload-pistol-uber-cylinder-eject.wav",
            "wpn-sw629-insert.wav": "weap-reload-pistol-uber-cylinder-reload.wav",
            "wpn-sw629-open.wav": "weap-reload-pistol-uber-open.wav",
            "wpn-sw629-close.wav": "weap-reload-pistol-uber-close-alt2.wav",
            # the rounds dropping into the cylinder (there was no bullet-insert sound). Bank event map (grain table,
            # tools/part1/p1_sound.event_waves): Part I's cylinder-reload event = cylinder-reload + cylinder-drop-01 / -04;
            # the .357's = sw629-insert + the random cylinder-clicks-1..3 group
            "wpn-sw629-cylinder-clicks-1.wav": "weap-reload-pistol-uber-cylinder-drop-01.wav",
            "wpn-sw629-cylinder-clicks-2.wav": "weap-reload-pistol-uber-cylinder-drop-04.wav",
            "wpn-sw629-cylinder-clicks-3.wav": "weap-reload-pistol-uber-cylinder-drop-01.wav",
        },
        silence=[],
        # the .357's close-up shot layers are raw PCM (1.5 s): the Part I colt shot bodies (1.7 s, -80 dB at the cut)
        pcm={**{f"pistol-revolver-close-v3-0{k}.wav": f"colt-shot-02-0{k}.wav" for k in range(1, 6)},
             "pistol-revolver-spike.wav": "wpn-spike-r700.wav"}),
}


def vgm():
    for r in (ROOT, MAIN):
        p = os.path.join(r, "tools", "local", "vgmstream", "vgmstream-cli.exe")
        if os.path.exists(p):
            return p
    raise SystemExit("vgmstream-cli not found (tools/local/vgmstream)")


def find_sound(*parts):
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "sound", *parts)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(os.path.join("re", "sound", *parts))


def p1_bank(name):
    """the Part I bank (extracted once from the install, read-only) and its decoded waves dir"""
    path = os.path.join(P1SOUND, name + ".bnk")
    if not os.path.exists(path):
        import p1_archive
        import p1_guns
        a = p1_archive.Psarc(os.path.join(p1_guns.game_dir(), "build", "pc", "main", "sp-common.psarc"))
        key = "soundbank4/" + name + ".bnk"
        os.makedirs(P1SOUND, exist_ok=True)
        open(path, "wb").write(a.get(key if key in a.ent else "/" + key))
    wav = os.path.join(P1SOUND, "wav", name)
    if not glob.glob(os.path.join(wav, "*.wav")):
        os.makedirs(wav, exist_ok=True)
        subprocess.run([vgm(), "-i", "-S", "0", "-o", os.path.join(wav, "?n"), path], check=True, capture_output=True)
    return open(path, "rb").read(), wav


def build(gun, log=print):
    """-> (bank file name, bytes) of the rebuilt host bank"""
    cfg = BANKS[gun]
    host = open(find_sound(cfg["bank"] + ".bnk"), "rb").read()
    src, src_wav = p1_bank(cfg["p1"])
    data = sndbank.replace_waves(host, src, cfg["waves"])
    if cfg["silence"]:
        data = sndbank.silence_waves(data, cfg["silence"])
    if cfg["pcm"]:
        data = sndbank.replace_pcm(data, find_sound("wav", cfg["bank"]), cfg["pcm"], src_wav)
    assert len(data) == len(host)
    check(data, src, cfg)
    log(f"sound: {gun}: {cfg['bank']}.bnk <- Part I {cfg['p1']}.bnk ({len(cfg['waves'])} waves, "
        f"{len(cfg['pcm'])} PCM layers, {len(cfg['silence'])} silenced)")
    return cfg["bank"] + ".bnk", data


def event_waves(path):
    """[(grain address, op, wave name)] of a bank's grain table in file order (read on wpn-pistol-revolver-357 /
    Part I wpn-pistol-uber): sound defs start with u32 0xa4000007, wave (stream) index at def +0x54 (= vgmstream subsong
    - 1); grains are 16-byte {u32 op, u32 arg, u32 value, u32}: op 0x01000000 plays the def at (first def - first
    grain's value) + value; 0x05000001 / 0x30000000 / 0x1bxxxxxx are group / random / wait ops.  An event record holds
    {u32 grain count << 16, ..., u32 grain offset} (e.g. the .357's cylinder-reload: 5 grains)."""
    import re
    import struct
    d = open(path, "rb").read()
    out = subprocess.run([vgm(), "-m", "-S", "0", path], capture_output=True, text=True).stdout
    names = re.findall(r"stream name: (.*)", out)
    first = d.find(struct.pack("<I", 0xa4000007))
    rows, base = [], None
    for o in range(0x200, first, 16):
        op, arg, v, _ = struct.unpack_from("<4I", d, o)
        if op == 0x01000000 and base is None:
            base = first - v
        if base is not None and op == 0x01000000:
            i = struct.unpack_from("<I", d, base + v + 0x54)[0]
            rows.append((o, "play", names[i] if i < len(names) else i))
        elif base is not None and (op in (0x05000001, 0x30000000) or op >> 24 == 0x1b):
            rows.append((o, f"op {op:08x} {arg:x}", None))
    return rows


def check(data, src, cfg):
    """every replaced slot now starts with the Part I wave's RIFF header + first audio block"""
    t, s = sndbank.riff_slots(data), sndbank.riff_slots(src)
    for tn, sn in cfg["waves"].items():
        to, tl = t[tn]
        so, sl = s[sn]
        a, b = data[to:to + tl], src[so:so + sl]
        hd = sndbank._chunks(b)[b"data"][0] + 8
        n = min(hd + 64, tl, sl)
        assert a[12:hd - 8] == b[12:hd - 8] or a[hd:n] == b[hd:n], f"{tn}: not the Part I wave {sn}"
        assert a[hd:n] == b[hd:n], f"{tn}: audio differs from {sn}"


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for g in (["shorty", "diablo"] if which == "all" else [which]):
        name, data = build(g)
        out = os.path.join(tempfile.gettempdir(), "t2r-p1-" + name)
        open(out, "wb").write(data)
        print("wrote", out)
