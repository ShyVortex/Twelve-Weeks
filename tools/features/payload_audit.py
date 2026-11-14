"""Build-time audit of the FINAL packed payload (the T2ME blob inside the finished full winmm.dll), not of the staging folder.

An earlier build shipped with silent suppressed rifles although every staging check passed: the carrier bank (dc_data_patches.build_supp_carrier_bank) was
in the payload, but its cue table was not a valid hash table for the retargeted event (sndbank.retarget_cue rewrote the hash in place).  This reads
the payload back the way the game does (decrypt, lz4, PSARC lookup by md5 of the path) and asserts what the staging checks assert, on those bytes.

  python payload_audit.py <full winmm.dll>          (build_release.py runs it on the full DLL of every build)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))


def read_payload_files(dll, paths):
    """{path: bytes or None} of files of the payload archive (None = not in it)"""
    import slim
    blob = slim.Blob(dll)
    try:
        md5 = {p: hashlib.md5(p.encode()).digest() for p in paths}
        loc = slim.psarc_locate(blob, md5.values())
        return {p: (blob.read(*loc[md5[p]]) if md5[p] in loc else None) for p in paths}
    finally:
        blob.close()


def audit_supp_carrier(files, D, sndbank):
    """files = read_payload_files result for carrier_paths(D); returns a list of problems (empty = fine)"""
    from dcfile import fnv
    bad = []
    if not D.SUPP_CARRIER_ON:
        return bad
    bank_path = f"soundbank4/{D.SUPP_CARRIER_BANK}.bnk"
    bank = files.get(bank_path)
    if bank is None:
        return [f"payload has no {bank_path} (the carrier bank of the suppressed rifles)"]
    ev = fnv(D.SUPP_CARRIER_EVENT)
    if bank.count(struct.pack("<Q", ev)) != 1:
        bad.append(f"{bank_path}: cue hash of {D.SUPP_CARRIER_EVENT} occurs {bank.count(struct.pack('<Q', ev))} times (want 1)")
    else:
        try:
            if sndbank.cue_lookup(bank, ev) is None:
                bad.append(f"{bank_path}: the engine's hash lookup (slot hash % N, follow next) does not find {D.SUPP_CARRIER_EVENT} - silent suppressed rifles")
        except ValueError as e:
            bad.append(f"{bank_path}: cue table not valid ({e})")
    if bank.count(struct.pack("<Q", fnv(D.SUPP_CARRIER_SRC_EVENT))):
        bad.append(f"{bank_path}: still holds the Galil cue {D.SUPP_CARRIER_SRC_EVENT}")
    pak68 = files.get("pak68.txt")
    if pak68 is None:
        bad.append("payload has no pak68.txt")
    else:
        lines = pak68.decode("utf-8", "replace").split("\n")
        try:
            i = lines.index("level-name starlight-mp-test")
        except ValueError:
            return bad + ["pak68.txt: no level-name starlight-mp-test"]
        j = i + 1
        while j < len(lines) and not lines[j].startswith("level-name "):
            j += 1
        blk = set(lines[i:j])
        for need in ("actor " + D.SUPP_CARRIER_ACTOR, "sound-bank " + D.SUPP_CARRIER_BANK):
            if need not in blk:
                bad.append(f"pak68.txt: the MP level lacks '{need}'")
    return bad


def carrier_paths(D):
    return [f"soundbank4/{D.SUPP_CARRIER_BANK}.bnk", "pak68.txt"]


def audit(dll):
    import dc_data_patches as D
    import sndbank
    files = read_payload_files(dll, carrier_paths(D))
    return audit_supp_carrier(files, D, sndbank)


def main():
    problems = audit(sys.argv[1])
    for p in problems:
        print("PAYLOAD AUDIT FAIL:", p)
    if problems:
        sys.exit(1)
    print("payload audit: suppressed-rifle carrier bank + MP level adds OK in", sys.argv[1])


if __name__ == "__main__":
    main()
