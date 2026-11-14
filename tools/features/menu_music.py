"""Menu music: all five official 2013 Factions lobby tracks, in random order.

The mod's re/modfs/music1/022_t2r_credits_in_menu.xvag is the five 2013 "The Last Of Us Multiplayer Lobby Soundtrack #1-#5"
rips joined into ONE 7:32 ATRAC9 cue (4 ch, 48 kHz; lengths 106.115 + 136.812 + 66.955 + 41.575 + 100.914 s = 452.371 s, the cue's exact
length). winmm starts the playlist "*music-playlist-t2r-credits-in-menu*" in the front end; that playlist has ONE chunk (the whole
cue), so the menu always began with track 1 and played them in order.

This slices the joined cue into five XVAGs WITHOUT re-encoding (ATRAC9 frames are 640 bytes = 1024 samples; there is no ATRAC9
encoder here) and stages them as the music1 files of five cues of a No Return jingle playlist that nothing in MP plays
("020_t2r_no-return_encounter_success_09/10/11/12/14"); dc_data_patches.make_menu_music_overlay points the credits-in-menu playlist's
chunk list at that playlist's chunk array (count 5). The engine plays every chunk of a multi-chunk playlist once, in random order (see
re/music-design.md: rd3 combat = 12 chunks, no repeat), so each visit to the menu plays the five tracks in a fresh order.

The five cues are the game's own PS4 streams (make_cues_ps4 below; the slicing here is only the fallback when those were not
extracted): the MP3 rips carried a comb of narrow 3-16 kHz lines (a 30 / 60 Hz-spaced buzz, 84-153 lines per track against 0-10 in the PS4
source). See re/lobby-music-ps4.md.

Cut points of the fallback slicing: each slice starts one to two frames before its track (a decoder starting mid-stream needs a frame to settle; that lead-in is
the previous track's faded tail) and the header's sample count ends the slice on the track's last sample. Header fields as in the
source: 0x30 / 0x34 / 0xd0 sample count, 0x40 data size, 0xac md5 of the data, 0xd4 / 0xd8 encoder delay (256, kept).
"""
import hashlib
import os
import struct

# the order of the joined cue = lobby soundtrack #1 .. #5; seconds from ffprobe of the five mp3s (their sum = the cue's length)
TRACK_SECONDS = (106.115208, 136.811979, 66.954750, 41.575333, 100.913938)
# five cue names of the donor playlist (*music-playlist-no-return-encounter-success*, 13 chunks; chunks 0..4)
CUES = ("020_t2r_no-return_encounter_success_09", "020_t2r_no-return_encounter_success_10",
        "020_t2r_no-return_encounter_success_11", "020_t2r_no-return_encounter_success_12",
        "020_t2r_no-return_encounter_success_14")
RATE = 48000
FRAME_SAMPLES = 1024
HDR = 0xe4
DELAY = 0x100


def track_bounds():
    """[(first sample, sample count)] of each track in the joined cue"""
    out, s = [], 0
    for sec in TRACK_SECONDS:
        n = round(sec * RATE)
        out.append((s, n))
        s += n
    return out


def slice_xvag(src, first, count):
    """the XVAG for samples [first, first + count) of the joined cue (output samples, i.e. after the encoder delay)"""
    d = open(src, "rb").read() if isinstance(src, str) else src
    assert d[:4] == b"XVAG" and struct.unpack_from("<I", d, 4)[0] == HDR
    fsz, spf = struct.unpack_from("<II", d, 0xc4)
    assert (fsz, spf) == (640, FRAME_SAMPLES) and struct.unpack_from("<I", d, 0xd4)[0] == DELAY
    nframes = (len(d) - HDR) // fsz
    f0 = max(first // spf - 1, 0)                                   # one to two frames of lead-in
    lead = first - f0 * spf                                         # samples the reader plays of the previous track's tail before the track starts
    f1 = min(-(-(first + count + DELAY) // spf) + 1, nframes)        # one frame past the last sample (overlap)
    data = d[HDR + f0 * fsz: HDR + f1 * fsz]
    keep = lead + count                                              # reader output q = 0 is source sample f0 * 1024 (it skips the 256 delay); play to the track's last sample
    assert keep <= (f1 - f0) * spf - DELAY
    h = bytearray(d[:HDR])
    for off in (0x30, 0x34, 0xd0):
        struct.pack_into("<I", h, off, keep)
    struct.pack_into("<I", h, 0x40, len(data))
    h[0xac:0xbc] = hashlib.md5(data).digest()
    return bytes(h) + data


def make_cues(src, out_dir):
    """writes the five cue XVAGs into out_dir (music1 of the stage); returns [(cue file name, bytes)]"""
    os.makedirs(out_dir, exist_ok=True)
    d = open(src, "rb").read()
    res = []
    for cue, (s, n) in zip(CUES, track_bounds()):
        b = slice_xvag(d, s, n)
        with open(os.path.join(out_dir, cue + ".xvag"), "wb") as f:
            f.write(b)
        res.append((cue + ".xvag", len(b)))
    return res


# --- original PS4 streams (the MP3-rip cue had a buzz behind the music) ----------------------------------------------------------
# The five lobby tracks are the game's own "tension" score streams of TLOU1 Remastered (core.psarc, sound1/streams/music), found by matching the
# rips against every music stream (re/lobby-music-ps4.md). They are ATRAC9 4 ch / 48 kHz XVAGs in exactly the mod's format (frame 640 B, 1024
# samples, delay 256), so nothing is decoded or re-encoded: the only difference is the mod's header carries an 'md5 ' chunk (24 bytes) in front of
# 'a9in'. Each stream starts at sample 0 (the engine's own start, no mid-stream slice, no lead-in click).
LOBBY_PS4_DIR = ("re", "modfs", "lobby-ps4")          # under the repo root; extracted by lobby_music_ps4.py, never committed (game audio)
LOBBY_PS4_FILES = ("lobby-1_510_gs_tension1.xvag", "lobby-2_142_jm_tension5.xvag", "lobby-3_128_jm_tension3.xvag",
                   "lobby-4_143_jm_tension6.xvag", "lobby-5_138_jm_tension4.xvag")
PS4_HDR = 0xcc


def ps4_to_cue(d):
    """TLOU1 PS4 XVAG bytes -> the mod's XVAG (0xe4 header with the md5 chunk), same ATRAC9 frames."""
    assert d[:4] == b"XVAG" and struct.unpack_from("<I", d, 4)[0] == PS4_HDR and d[0xa4:0xa8] == b"a9in"
    fsz, spf = struct.unpack_from("<II", d, 0xac)
    assert (fsz, spf) == (640, FRAME_SAMPLES) and struct.unpack_from("<I", d, 0xbc)[0] == DELAY
    data = d[PS4_HDR:]
    assert len(data) == struct.unpack_from("<I", d, 0x40)[0] and len(data) % fsz == 0
    h = bytearray(d[:0xa4]) + b"md5 " + struct.pack("<I", 16) + hashlib.md5(data).digest() + d[0xa4:PS4_HDR]
    struct.pack_into("<I", h, 4, HDR)
    assert len(h) == HDR
    return bytes(h) + data


def have_ps4(root):
    return all(os.path.exists(os.path.join(root, *LOBBY_PS4_DIR, f)) for f in LOBBY_PS4_FILES)


def make_cues_ps4(root, out_dir):
    """writes the five cue XVAGs (the PS4 streams, repackaged) into out_dir; returns [(cue file name, bytes)]"""
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for cue, f in zip(CUES, LOBBY_PS4_FILES):
        b = ps4_to_cue(open(os.path.join(root, *LOBBY_PS4_DIR, f), "rb").read())
        with open(os.path.join(out_dir, cue + ".xvag"), "wb") as o:
            o.write(b)
        res.append((cue + ".xvag", len(b)))
    return res
