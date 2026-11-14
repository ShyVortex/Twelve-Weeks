"""Execution gun recoil (tools/features/exec_recoil_gestures.py, tools/ext/execrecoil.h, er_kick in t2r-ext.c).

Offline checks: the six gesture defs patch cleanly in the game's gestures/ellie-gestures.bin (same size, only the 6 clip structs change), the generated
header equals the module's table, every slot's names are unique, the ext plays the gesture at both shot loops (own / victim screen and bystander) and
honours the opt-out file.
Run: python tools/tests/test_exec_recoil.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'features'))
import exec_recoil_gestures as E  # noqa: E402

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


raw = open(E.GAME_BIN, 'rb').read()
out = E.patch(raw)
E.verify(out)
check(len(out) == len(raw), 'patched file size differs')
diff = [i for i in range(len(raw)) if raw[i] != out[i]]
check(0 < len(diff) <= 16 * len(E.SLOTS), 'unexpected number of changed bytes: %d' % len(diff))
check(max(diff) - min(diff) < len(raw), 'diff span')
check(len({s[1] for s in E.SLOTS}) == len(E.SLOTS), 'a gesture def is used by two slots')
check(len({s[5] for s in E.SLOTS}) == len(E.SLOTS), 'two slots use the same carrier clip')
for name, gdef, part, src, srcpak, carrier, k in E.SLOTS:
    check(part.endswith('-sub') and not src.endswith('-sub'), '%s: part / add clip names look swapped' % name)
    check('horse' in carrier and carrier.endswith('--add'), '%s: carrier %s is not a horse-riding additive (the throw / holster clips are reachable by MP prone / cover / supine paths)' % (name, carrier))
    check(0.0 < k < 1.0, '%s: factor %s' % (name, k))
    check(name in E.TARGETS, '%s: no target range' % name)
hdr = open(E.HEADER, encoding='ascii', newline='').read().replace(chr(13) + chr(10), chr(10))
check(hdr == E.header_text(), 'tools/ext/execrecoil.h is out of date: run python tools/features/exec_recoil_gestures.py --header')
ext = open(os.path.join(ROOT, 'tools', 'ext', 't2r-ext.c'), encoding='latin-1', newline='').read()
check('t2r-no-exec-recoil.txt' in ext, 'opt-out file not read by the ext')
check(ext.count('er_kick(') >= 3, 'er_kick is not called from both shot loops (def + 2 call sites)')
check('er_kick(ent, g_gx.pair' in ext and 'er_kick(g_tgore.att_h' in ext, 'shot loop call sites missing')
bd = open(os.path.join(ROOT, 'tools', 'features', 'build_dll.py'), encoding='utf-8', errors='replace').read()
check('exec_recoil_gestures' in bd and 'T2R_EXEC_RECOIL' in bd, 'build_dll does not ship the overlay')
check('anim-ellie-horse' in bd and 'stage_exec_recoil(paths, order)' in bd, 'build_dll does not ship the scaled clip pak')
# scaled amplitudes (needs the game's anim paks: skipped without them)
if os.path.isdir(os.path.join(E.exec_game_dir(), 'build', 'pc', 'main')):
    import exec_recoil_clips as C
    srcs = {}
    for name, gdef, part, src, srcpak, carrier, k in E.SLOTS:
        if srcpak not in srcs:
            srcs[srcpak] = C.pak_clips(srcpak)
        stock = srcs[srcpak][src]['clip']
        new = C.scale_clip(stock, k)
        p0, p1 = C.chain_peak(C.peaks(stock)), C.chain_peak(C.peaks(new))
        lo, hi = E.TARGETS[name]
        check(lo <= p1 <= hi, '%s: arm-chain peak %.1f deg outside %.0f-%.0f (stock %.1f, k=%.2f)' % (name, p1, lo, hi, p0, k))
        check(abs(p1 - p0 * k) < 0.25, '%s: scaled peak %.2f != %.2f x %.2f' % (name, p1, p0, k))
        check(len(new) <= 16384, '%s: scaled clip %d bytes' % (name, len(new)))
        print('  %-8s arm-chain peak %.1f -> %.1f deg (x%.2f)' % (name, p0, p1, k))
else:
    print('(game anim paks not found: amplitude check skipped)')
if fails:
    print('FAIL')
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('ok: exec recoil - %d gesture defs patch in place (%d bytes changed), header + ext + build in step' % (len(E.SLOTS), len(diff)))
