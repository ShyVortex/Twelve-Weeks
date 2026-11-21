"""Offline consistency of every execution pair (gun + melee/unarmed): tables, carriers, baked clips, sound timeline, kill time.

Checks, per GUNEXEC_PAIRS pair: attacker + victim carrier names present, unique across ALL carrier tables (a shared carrier
= one pair overwrites the other's clip), baked 2013 clips exist for both halves, kill_s inside both clip lengths (baked clip
header: nframes u16 @0xe, fps f32 @0x1c), a GUNEXEC_SFX timeline with a death cue near the kill, GUNEXEC_SHOT / AIM / FOLEY rows,
an authored exec camera track per role, a grip/hand definition in bake_t1 for the attacker half. Same for MELEE2013.
Third-party handling is by construction: paired.c psync START carries clip sids + pair index (no per-pair table on the
bystander), so the only requirement is that the carrier paks are loaded there - checked via PAK_SETS / GUNEXEC_PAKS.
Run: python tools/tests/test_exec_tables.py
"""
import os, re, struct, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
EXT = os.path.join(ROOT, 'tools', 'ext')
BAKED = os.path.join(ROOT, 're', 'factions2013', 't1anim', 'baked')
fails = []


def rd(p):
    return open(os.path.join(EXT, p), encoding='utf-8', errors='replace', newline='').read()


def check(ok, msg):
    if not ok:
        fails.append(msg)


def clip_len(path):
    d = open(path, 'rb').read(0x40)
    nf = struct.unpack_from('<H', d, 0xe)[0]
    fps = struct.unpack_from('<f', d, 0x1c)[0]
    return (nf - 1) / fps if fps > 0 else 0.0


def carriers(h):
    return re.findall(r'\{"([^"]*)", "([^"]*)"\}', rd(h))


main = rd('t2r-ext.c')
blk = re.search(r'GUNEXEC_PAIRS\[\] = \{(.*?)\n\};', main, re.S).group(1)
pairs = [(m.group(1), m.group(2), int(m.group(3)), float(m.group(4)), int(m.group(5) or 0))
         for m in re.finditer(r'\{"([^"]+)", (GX_\w+), (\d), ([\d.]+)f(?:, (\d))?\}', blk)]
mblk = re.search(r'MELEE2013\[\] = \{(.*?)\n\};', main, re.S).group(1)
melee = []
for m in re.finditer(r'\{"([^"]+)", (MX_\w+), (?:-?\d+), ([\w.]+?)f?\}', mblk):
    try:
        k = float(m.group(3))
    except ValueError:
        k = -1.0      # a macro (SHIV_*_KILL_S)
    melee.append((m.group(1), m.group(2), k))
gc, mc = carriers('gunexec_carriers.h'), carriers('meleeexec_carriers.h')
check(len(pairs) >= 17, 'GUNEXEC_PAIRS parse: %d pairs' % len(pairs))
check(len(gc) == len(pairs), 'gunexec_carriers.h rows %d != GUNEXEC_PAIRS %d' % (len(gc), len(pairs)))
check(len(mc) == len(melee), 'meleeexec_carriers.h rows %d != MELEE2013 %d' % (len(mc), len(melee)))

seen = {}


def reg(name, who):
    if not name:
        return
    if name in seen:
        fails.append('carrier %s used twice: %s and %s (the later bake overwrites the earlier clip)' % (name, seen[name], who))
    seen[name] = who


for i, (a, v) in enumerate(gc):
    if i < len(pairs):
        reg(a, 'gun %s atk' % pairs[i][0]); reg(v, 'gun %s vic' % pairs[i][0])
for i, (a, v) in enumerate(mc):
    if i < len(melee):
        reg(a, 'melee %s atk' % melee[i][0]); reg(v, 'melee %s vic' % melee[i][0])
for h, tag in (('revive_carriers.h', 'revive'), ('dkick_carriers.h', 'dkick')):
    for i, (a, v) in enumerate(carriers(h)):
        reg(a, '%s%d atk' % (tag, i)); reg(v, '%s%d vic' % (tag, i))
m = re.search(r'STUN2013_CLIP "([^"]+)"', rd('stun2013_carrier.h'))
if m:
    reg(m.group(1), 'stun2013')
# the ten 2013 go-down clips (bake_downs.py): unique carriers, baked length = the header's, one motion value per frame
for i, m in enumerate(re.finditer(r'\{"([^"]*)", ([\d.]+)f, (-?[\d.]+)f, ([\d.]+)f, ([\d.]+)f, (\d+), DOWN2013_S\d+\}', rd('down2013_carriers.h'))):
    reg(m.group(1), 'down2013 %d' % i)
    check(m.group(1) != '', 'down2013 %d: no carrier' % i)

sfxsrc = rd('gunexec_sfx.h')
sfx = re.findall(r'\{(\d+), (\d), GXS_(\w+), (\d+), \d\}', sfxsrc)
shot_rows = re.findall(r'\{([^}]*)\}', re.search(r'GUNEXEC_SHOT\[\]\[6\] = \{(.*?)\n\};', sfxsrc, re.S).group(1))
aim_rows = re.findall(r'\{[^}]*\}', re.search(r'GUNEXEC_AIM\[\]\[6\] = \{(.*?)\n\};', rd('gunexec_aim.h'), re.S).group(1))
foley_rows = re.findall(r'\{\d+, \d+\}', re.search(r'GUNEXEC_FOLEY\[\] = \{(.*?)\n\};', rd('gunexec_foley.h'), re.S).group(1))
for tbl, n in (('GUNEXEC_SHOT', len(shot_rows)), ('GUNEXEC_AIM', len(aim_rows)), ('GUNEXEC_FOLEY', len(foley_rows))):
    check(n == len(pairs), '%s rows %d != %d pairs' % (tbl, n, len(pairs)))

tracks = ''.join(rd(f) for f in ('xcam_tracks.h', 'xcam_tracks_ps4.h') if os.path.exists(os.path.join(EXT, f)))
bake = open(os.path.join(ROOT, 're', 'factions2013', 't1anim', 'bake_t1.py'), encoding='utf-8').read()
bgp = open(os.path.join(ROOT, 're', 'factions2013', 't1anim', 'build_gunexec_pak.py'), encoding='utf-8').read()
check("PAK_SETS = [('anim-npc-alert-caps', None), ('anim-npc-m-cover-share', SECOND_SET), ('anim-npc-m-lg', THIRD_SET), ('anim-npc-m-p', FOURTH_SET),\n            ('anim-npc-m-lg-enemy-only', FIFTH_SET)]" in bgp, 'carrier PAK_SETS changed')
dll = open(os.path.join(ROOT, 'tools', 'features', 'build_dll.py'), encoding='utf-8').read()
check('GUNEXEC_PAKS = [GUNEXEC_PAK, GUNEXEC_PAK2, GUNEXEC_PAK3, GUNEXEC_PAK4, GUNEXEC_PAK5]' in dll, 'build_dll does not list all five carrier paks')

for i, (name, cls, left, kill, wset) in enumerate(pairs):
    if i >= len(gc):
        break
    a, v = gc[i]
    check(a and v, '%s: carrier missing (atk %r vic %r)' % (name, a, v))
    la = lv = 0.0
    for who in ('atk', 'vic'):
        p = os.path.join(BAKED, 't1gx-%s--%s.clip' % (name, who))
        if not os.path.exists(p):
            fails.append('%s: baked clip %s missing' % (name, os.path.basename(p)))
            continue
        L = clip_len(p)
        check(1.0 < L < 10.0, '%s %s: clip length %.2f s implausible' % (name, who, L))
        if who == 'atk':
            la = L
        else:
            lv = L
    if la and lv:
        check(0.3 < kill <= la + 0.05, '%s: kill_s %.3f outside the attacker clip (%.2f s)' % (name, kill, la))
        check(kill <= lv + 0.05, '%s: kill_s %.3f outside the victim clip (%.2f s)' % (name, kill, lv))
    rows = [(int(p_), int(w), k, int(ms)) for p_, w, k, ms in sfx if int(p_) == i]
    check(rows, '%s: no GUNEXEC_SFX timeline' % name)
    check(any(k == 'DEATH' for _, w, k, ms in rows), '%s: no victim death cue in the timeline' % name)
    if la and lv and rows:
        check(max(ms for _, w, k, ms in rows) / 1000.0 <= max(la, lv) + 0.1, '%s: a sound cue after the end of both clips' % name)
    check(any(w == 0 for _, w, k, ms in rows), '%s: no attacker cue (move foley)' % name)
    if i < len(shot_rows) and la:
        for x in shot_rows[i].split(','):
            t = int(x.split('|')[0])
            check(t / 1000.0 <= la + 0.05, '%s: shot at %.2f s after the clip end' % (name, t / 1000.0))
    for role in (1, 2):
        check(not tracks or re.search(r'\{"%s", %d,' % (re.escape(name), role), tracks), '%s: no authored exec camera track for role %d' % (name, role))
    check(("'%s':" % name) in bake, '%s: no hand / grip entry in bake_t1.py' % name)
    check(("'%s'" % name) in bgp, '%s: not in build_gunexec_pak PAIRS' % name)

for i, (name, kind, kill) in enumerate(melee):
    if i >= len(mc):
        break
    a, v = mc[i]
    lens = []
    for who, ent in (('atk', a), ('vic', v)):
        check(ent, '%s (melee): %s carrier missing' % (name, who))
        p = os.path.join(BAKED, 't1mx-%s--%s.clip' % (name, who))
        if ent and os.path.exists(p):
            L = clip_len(p)
            check(1.0 < L < 10.0, '%s: clip length %.2f' % (name, L))
            lens.append(L)
    if kill > 0 and len(lens) == 2:
        check(kill <= max(lens) + 0.05, '%s: kill_s %.3f beyond both clips %s' % (name, kill, lens))

# Melee grip-class variants (meleeexec_variants.h, melee_classes.py): every row names a base MELEE2013 pair and a weapon of a variant class, with a unique carrier per variant clip,
# a baked attacker clip of the same length as the base pair's and a channel file; melee_classes.py is the one list bake_t1.py / build_gunexec_pak.py / the header agree on
sys.path.insert(0, os.path.join(ROOT, 're', 'factions2013', 't1anim'))
import melee_classes
vrows = re.findall(r'\{"([^"]*)", "([^"]*)", "([^"]*)"\},\s*// (\S+)', rd('meleeexec_variants.h'))
check(vrows, 'meleeexec_variants.h has no rows')
mnames = [m[0] for m in melee]
cars = {}
for base, weapon, car, vname in vrows:
    check(base in mnames, 'variant %s: base pair %s is not a MELEE2013 row' % (vname, base))
    check(car, 'variant %s: no carrier' % vname)
    cars.setdefault(vname, set()).add(car)
for vname, cs in cars.items():
    check(len(cs) == 1, 'variant %s: several carriers %s' % (vname, cs))
    reg(next(iter(cs)), 'melee variant %s' % vname)
    pa = os.path.join(BAKED, 't1mx-%s--atk.clip' % vname)
    check(os.path.exists(pa) and os.path.exists(os.path.join(BAKED, 't1mx-%s--atk.chan.npz' % vname)), 'variant %s: baked clip / channel file missing' % vname)
    base = next((b for n, b, s_, c in melee_classes.variants() if n == vname), None)
    pb = os.path.join(BAKED, 't1mx-%s--atk.clip' % base) if base else ''
    if os.path.exists(pa) and os.path.exists(pb):
        check(abs(clip_len(pa) - clip_len(pb)) < 1e-3, 'variant %s: length differs from its base pair %s' % (vname, base))
want = {(b, w, n) for n, b, s_, c in melee_classes.variants() for w in c['weapons']}
check({(b, w, n) for b, w, c, n in vrows} == want, 'meleeexec_variants.h does not list the weapons of melee_classes.py (rebuild: build_gunexec_pak.py)')

check('g_xcam_scope = 0;' in main and 'if (*fov < tr->k[0].fov * 0.9f) *fov = tr->k[0].fov;' in main,
      'scope / zoom removal missing in the exec camera')

if fails:
    print('FAIL: %d problem(s)' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('OK: %d gun pairs, %d melee pairs, %d carriers checked' % (len(pairs), len(melee), len(seen)))
