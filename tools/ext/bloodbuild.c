// bloodbuild.c - characters get bloodier and dirtier during a life. Included from t2r-ext.c after feel.c (uses
// clipfx.c / ctxdown.c / paired.c / feel.c helpers); bloodbuild_tick() is called from the main tick.
//
// What TLOU2 SP does (static RE, re/gamebin/dc1 + dcpl):
//  * Blood on a body is NOT a mesh variant: it is a per-character BLOOD MASK render target (shader sampler BloodMaskSampler, uvSet3) that
//    `bm-*` particle effect groups (module part-kit-blood-mask, part-blood-and-gore, the part-actor-anim-melee-* actors) stamp with their own
//    posU / posV / index params - the takedown clips fire them as `part-effect` anim events (clipfx.c, SP-exact), wounds by hit zone
//    (bm-knife-wound-cloth on l_clavicle / spineb / spinec / spined / headb / l_deltoid_helper, bm-bullet-wound-cloth, bm-blood-splatter-body
//    on the whole body, bm-ellie-melee-mouth + bm-bloody-hand late in a fight).
//  * `player-blood-effects` (startup.bin module, 411 bytes): *player-melee-blood-progression-low / -med / -high* (symbol arrays of bm-ellie-*
//    masks: head-right, ear-left, nose ...), *blood-splatter-config*, *blood-pool-slope-threshold* 20 - the C++ BloodEffectSpawner (src
//    blood-effect-spawner.cpp) reads them to escalate Ellie's masks during a melee fight. Those masks use Ellie's UV layout; MP bodies wear NPC
//    looks, so the NPC-victim masks are used here (the same ones SP's takedown victims get on the SAME body type).
//  * The SP state script ss-player-blood-splatter-1 (dc1/ss-t2, player script; events add-blood-splatter / set-blood-splatter with a float):
//    blood-amount (decays by blood-decay-amount once blood-spray-timer ran out, clamped to min-value..1) drives
//    set-table-shader-material-values-param *ellie-melee-seattle* blood-amount (Ellie's seattle look only) and, under a gas mask,
//    set-shader-instance-blend-offset. It is the SP player-only path and does nothing on an MP body (a look-specific material table), so
//    it is NOT used; the same accumulate / decay idea is kept below as the per-body `blood` level.
//  * Dirt: part-interaction-mud-character groups nav-prone-mud-mask / nav-supine-mud-mask / nav-sliding-mud-mask (the navigation system
//    stamps them into the MudMaskSampler while a character is prone / sliding); natives set-character-mud-mask-value /
//    set-character-wet-mask-value (char, float) set the per-mesh mud / wet opacity.
//  * New life: SP broadcasts `clear-wetness` at the spawn and the bm-blood-clear-eff group (part-sle-blood-clear-igc) wipes the blood mask.
//
// What this file does (everything cosmetic, per client, no network message): a per-body `blood` level and a `dirt` level, driven by events
// every client already sees identically - the synced health of each body (puppet_hp: the victim's networked health; ours: local_hp) for
// hits taken (drop size = amount; the wound zone is picked from the health value AFTER the hit, so every screen picks the same zone),
// psync paired moves (g_ps: every execution / takedown, both halves + bystanders nearby), down / death state (g_peer_downed, peer[5],
// g_downed), the downed crawl (net position / locator speed) and the life counter (our g_fl.seq, a puppet's handle). Escalation fires real
// engine blood-mask effects through clipfx_fire (the engine's own part-effect event path) with SP's own param sets taken from the
// compiled clip tables (KNIFE_HIT_FX / CTX_FX victim-half rows), dirt through spawn-particles at the root.
// Opt-out: t2r-no-blood-buildup.txt next to the exe. t2r-no-blood-dirt.txt = blood only. Log prefix "blood: ".

#define BB_N (T2R_MAX_PEERS + 1)          // slots 0..7 puppets, T2R_US = ourselves
#define BB_WOUNDS 6                       // bm-knife-wound-cloth joints
#define BB_WOUND_MAX 6                    // wounds per life (SP's masks pile up on one texture; more is just noise)
typedef struct { cfxe_entry e; uint64_t clip; const char *nm, *jn; int ok; } bb_fx;
static bb_fx g_bb_w[BB_WOUNDS];           // wound masks, zone order of BB_WJ
static bb_fx g_bb_body, g_bb_mouth, g_bb_hand, g_bb_throat, g_bb_face, g_bb_nose;   // face / nose: SP blunt + fist victim rows at headb
// SHIV neck-slash blood (the takedowns' part-effect events, called on the neck in the neck-slash shiv animations): SP's own
// victim rows of its neck kills, fired through clipfx_fire at the blade's contact on the victim's neck: wpn-machete-wall-neck-slice @1667 ms (blood-ribbon-pulse-eff
// = the arterial spurt + melee-blood-gore-minimal-eff, both at "neck"), wpn-blade-wall-neck-chop @1433 (gore-minimal at r_clavicle) and its death tail relative to its
// pulse at 1333 (blood-cough headb +1300, blood-splatter-pool-eff root +1500 / +1767, blood-ribbon-splurt-eff headb +1667, blood-cough +1834)
#define BB_SPN 24
#define BB_SHIVN 12
static bb_fx g_bb_sp[BB_SPN]; static int g_bb_sp_rel[BB_SPN], g_bb_nsp;
// Interrogation: the same blood effect as slamming a head against a wall in an SP finisher, which leaves a blood mark on the floor: the victim half of
// SP's wall-combo-head-smash (seg 2 @ 1067 ms: gore-gibs / teeth burst, melee-blood-gore-minimal, saliva spray, blood-drops-burst, the dense spray at headb) plus the blood-splatter-pool-eff
// (root: the floor pool decal) of the knife kills, appended to g_bb_sp after the shiv rows [g_bb_ig0, g_bb_ig0 + g_bb_nig); g_bb_ig2[k] = also on the final smash. bb_ig_slam fires them.
static int g_bb_ig0, g_bb_nig; static uint8_t g_bb_ig2[BB_SPN];
static const char *const BB_WJ[BB_WOUNDS] = {"headb", "spineb", "spinec", "spined", "l_clavicle", "l_deltoid_helper"};
static const uint8_t BB_WW[BB_WOUNDS] = {2, 3, 3, 3, 2, 2};     // zone weights (head is rarer than the torso)
static int g_bb_init, g_bb_nfx;
static void bb_set(bb_fx *f, uint64_t clip, uint64_t nm_sid, const char *nm, const char *jn, int n, const uint64_t (*pp)[2], float frame) {
    (void)nm_sid;
    f->e.type = CFXE_TYPE; f->e.frame = frame; f->e.n = (uint32_t)n; f->e.pairs = pp;
    f->clip = clip; f->nm = nm; f->jn = jn; f->ok = pp && n > 0;
    if (f->ok) g_bb_nfx++;
}
static void bb_init(void) {
    if (g_bb_init) return;
    g_bb_init = 1;
    uint64_t wound = fnv64("bm-knife-wound-cloth"), body = fnv64("bm-blood-splatter-body"), mouth = fnv64("bm-ellie-melee-mouth"), hand = fnv64("bm-bloody-hand");
    for (int k = 0; k < BB_WOUNDS; k++)
        for (size_t i = 0; i < KNIFE_HIT_FX_N; i++)
            if (!g_bb_w[k].ok && KNIFE_HIT_FX[i].name == wound && !strcmp(KNIFE_HIT_FX[i].jn, BB_WJ[k]))
                bb_set(&g_bb_w[k], fnv64(KNIFE_HIT_FX[i].clip), wound, KNIFE_HIT_FX[i].pn, KNIFE_HIT_FX[i].jn, KNIFE_HIT_FX[i].n, KNIFE_HIT_FX[i].pp, KNIFE_HIT_FX[i].frame);
    uint64_t clip0 = fnv64("ellie-knife-combo-slash-1-hit--npc-m");
    for (size_t i = 0; i < CTX_FX_N; i++) {       // the victim half's rows (role 1: NPC body UVs), whole-body ones have no joint
        if (CTX_FX[i].role != 1) continue;
        if (!g_bb_body.ok && CTX_FX[i].name == body && !CTX_FX[i].jn[0]) bb_set(&g_bb_body, clip0, body, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        if (!g_bb_mouth.ok && CTX_FX[i].name == mouth && !strcmp(CTX_FX[i].jn, "headb")) bb_set(&g_bb_mouth, clip0, mouth, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        if (!g_bb_face.ok && CTX_FX[i].name == fnv64("bm-face") && !strcmp(CTX_FX[i].jn, "headb")) bb_set(&g_bb_face, clip0, CTX_FX[i].name, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        if (!g_bb_nose.ok && CTX_FX[i].name == fnv64("bm-ellie-melee-nose") && !strcmp(CTX_FX[i].jn, "headb")) bb_set(&g_bb_nose, clip0, CTX_FX[i].name, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        if (!g_bb_hand.ok && CTX_FX[i].name == hand && !CTX_FX[i].jn[0]) bb_set(&g_bb_hand, clip0, hand, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
    }
    // the THROAT SLASH mask: SP's own bm-knife-wound-cloth at the "neck" joint (the wpn-blade-wall-neck-chop victim row; the machete neck slice
    // and the throat punch carry the same mask at neck_helper / neck) - stamped at the cut of every throat-slash move (bb_throat_move)
    for (size_t i = 0; i < CTX_FX_N && !g_bb_throat.ok; i++)
        if (CTX_FX[i].role == 1 && CTX_FX[i].name == wound && CTX_FX[i].jn && !strcmp(CTX_FX[i].jn, "neck"))
            bb_set(&g_bb_throat, clip0, wound, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
    for (size_t i = 0; i < CTX_FX_N && g_bb_nsp < BB_SHIVN; i++) {
        if (CTX_FX[i].role != 1 || !CTX_FX[i].pair || !CTX_FX[i].pn || !CTX_FX[i].jn || !strncmp(CTX_FX[i].pn, "bm-", 3)) continue;
        int rel = -1;
        if (!strcmp(CTX_FX[i].pair, "wpn-machete-wall-neck-slice") && CTX_FX[i].ms == 1667 && !strcmp(CTX_FX[i].jn, "neck")) rel = 0;
        else if (!strcmp(CTX_FX[i].pair, "wpn-blade-wall-neck-chop") && CTX_FX[i].ms == 1433 && !strcmp(CTX_FX[i].pn, "melee-blood-gore-minimal-eff")) rel = 100;
        else if (!strcmp(CTX_FX[i].pair, "wpn-blade-wall-neck-chop") && CTX_FX[i].ms >= 2633 && CTX_FX[i].ms <= 3167) rel = CTX_FX[i].ms - 1333;
        if (rel < 0) continue;
        bb_set(&g_bb_sp[g_bb_nsp], clip0, CTX_FX[i].name, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        g_bb_sp_rel[g_bb_nsp++] = rel;
    }
    g_bb_ig0 = g_bb_nsp;
    for (size_t i = 0; i < CTX_FX_N && g_bb_ig0 + g_bb_nig < BB_SPN; i++) {
        if (CTX_FX[i].role != 1 || !CTX_FX[i].pair || !CTX_FX[i].pn || !CTX_FX[i].jn) continue;
        int pool = !strcmp(CTX_FX[i].pn, "blood-splatter-pool-eff") && !strcmp(CTX_FX[i].jn, "root");
        int smash = !strcmp(CTX_FX[i].pair, "wall-combo-head-smash") && CTX_FX[i].seg == 2 && CTX_FX[i].ms == 1067 && !strcmp(CTX_FX[i].jn, "headb") && strncmp(CTX_FX[i].pn, "bm-", 3);
        if (!pool && !smash) continue;
        int dup = 0;
        for (int k = 0; k < g_bb_nig; k++) if (!strcmp(g_bb_sp[g_bb_ig0 + k].nm, CTX_FX[i].pn)) dup = 1;
        if (dup) continue;
        int k = g_bb_nig++;
        bb_set(&g_bb_sp[g_bb_ig0 + k], clip0, CTX_FX[i].name, CTX_FX[i].pn, CTX_FX[i].jn, CTX_FX[i].n, CTX_FX[i].pp, CTX_FX[i].frame);
        g_bb_ig2[k] = pool || !strcmp(CTX_FX[i].pn, "melee-blood-gore-minimal-eff") || !strcmp(CTX_FX[i].pn, "blood-drops-burst-eff");
    }
    xlog("interrogation blood: %d SP head-smash rows loaded (wall-combo-head-smash victim half + the floor pool; t2r-no-int-blood.txt = off)", g_bb_nig);
    int nw = 0;
    for (int k = 0; k < BB_WOUNDS; k++) nw += g_bb_w[k].ok;
    xlog("shiv blood: %d SP neck-kill part-effect rows loaded (t2r-no-shiv-blood.txt = off)", g_bb_nsp);
    xlog("blood: build-up tables: %d wound zones, body splatter %d, mouth %d, hand %d, melee face %d nose %d (SP's own bm-* param sets from the clip tables)", nw, g_bb_body.ok, g_bb_mouth.ok, g_bb_hand.ok, g_bb_face.ok, g_bb_nose.ok);
}

typedef struct {
    uint64_t h;                 // puppet handle (a respawn is a new character) / SID_PLAYER
    uint32_t life;              // ours: g_fl.seq
    int seen;                   // state initialised
    float hp; int hp_ok;
    float blood, dirt;          // 0..100
    int wounds, body, mouth, hand, mud, bysplat;
    int downed, dead;           // last seen
    float crawl_m, px, pz; int pos_ok; float speed;
    uint64_t born;              // g_frame the life was first seen
} bb_body;
static bb_body g_bb[BB_N];
typedef struct { double due; int who, kind, zone, tries; const char *tag; double at; } bb_pend;
enum { BBK_WOUND = 1, BBK_BODY, BBK_MOUTH, BBK_HAND, BBK_MUD, BBK_CLEAR, BBK_THROAT, BBK_SPURT };
static bb_pend g_bb_q[24];
static int g_bb_uid_wait; static uint32_t g_bb_uid_seen;
static uint64_t g_bb_fired, g_bb_failed;

static void bb_queue(int who, int kind, int zone, double delay_ms) {
    for (int i = 0; i < 24; i++) if (!g_bb_q[i].kind) { g_bb_q[i].due = psync_ms() + delay_ms; g_bb_q[i].who = who; g_bb_q[i].kind = kind; g_bb_q[i].zone = zone; g_bb_q[i].tries = 0; g_bb_q[i].tag = NULL; g_bb_q[i].at = 0; return; }
}
static int bb_no_shiv(void) { static int c = -1; static uint64_t k; return cfxe_file("t2r-no-shiv-blood.txt", &c, &k); }
static const char *bb_name(int who);
static uint32_t bb_hash(uint32_t x) { x ^= x >> 16; x *= 0x7feb352dU; x ^= x >> 15; x *= 0x846ca68bU; x ^= x >> 16; return x; }
static int bb_zone(uint32_t seed) {
    int tot = 0; for (int k = 0; k < BB_WOUNDS; k++) tot += BB_WW[k];
    int r = (int)(bb_hash(seed) % (uint32_t)tot);
    for (int k = 0; k < BB_WOUNDS; k++) { if (r < BB_WW[k]) return k; r -= BB_WW[k]; }
    return 1;
}
static uint64_t bb_ent(int who) {
    if (who == T2R_US) return SID_PLAYER;
    return who >= 0 && who < T2R_MAX_PEERS ? g_bb[who].h : 0;
}
static const char *bb_name(int who) { static char b[4][24]; static unsigned i; char *o = b[i++ & 3]; if (who == T2R_US) return "ourselves"; snprintf(o, 24, "slot %d", who); return o; }
static int bb_off(void) { static int c = -1; static uint64_t k; return cfxe_file("t2r-no-blood-buildup.txt", &c, &k); }
static int bb_no_dirt(void) { static int c = -1; static uint64_t k; return cfxe_file("t2r-no-blood-dirt.txt", &c, &k); }

// one queued effect on a body (engine event path for the masks, a group spawn for the dirt / wipe)
static void bb_do(const bb_pend *p) {
    static int nl; static uint64_t mud_fail;
    uint64_t ent = bb_ent(p->who);
    if (!ent) return;
    if (p->kind == BBK_MUD || p->kind == BBK_CLEAR) {
        const char *nm = p->kind == BBK_MUD ? "nav-prone-mud-mask" : "bm-blood-clear-eff";
        uint64_t r = armor_fx_spawn(fnv64(nm), ent, "root");
        int ok = r && r != ~0ULL;
        if (ok) g_bb_fired++; else g_bb_failed++;
        if (nl < 60 || (!ok && mud_fail++ < 4)) { nl++; xlog("blood: %s on %s -> %llx%s", nm, bb_name(p->who), (unsigned long long)r, ok ? "" : " (not spawned)"); }
        return;
    }
    if (p->kind == BBK_SPURT) {
        bb_fx *s = &g_bb_sp[p->zone];
        if (!s->ok || clipfx_off() || !cfxe_check()) return;
        uint8_t *so = cfxe_obj_of(ent);
        if (!so) { xlog("shiv blood: %s %s at %.0f ms on %s -> body not found", p->tag, s->nm, p->at, bb_name(p->who)); return; }
        if (cfx_stream(fnv64(s->nm))) {          // GPU-compute streams need a free compute entry (the same wait ctxdown's clip streams do)
            uint8_t *m = cfx_rtmgr();
            if (m && cfx_used(m) >= CFX_N && p->tries < 8) {
                if (p->tries == 0) cfx_make_room(m);
                for (int i = 0; i < 24; i++) if (!g_bb_q[i].kind) { g_bb_q[i] = *p; g_bb_q[i].tries++; g_bb_q[i].due = psync_ms() + 20.0; break; }
                return;
            }
        }
        uint64_t r = clipfx_fire(so, s->clip, &s->e, so == bp_me());
        if (r) g_bb_fired++; else g_bb_failed++;
        xlog("shiv blood: %s %s at %.0f ms on %s -> %s %llx", p->tag, s->nm, p->at, bb_name(p->who), r ? "engine event path" : "FAILED", (unsigned long long)r);
        return;
    }
    bb_fx *f = p->kind == BBK_THROAT ? &g_bb_throat : p->kind == BBK_WOUND ? &g_bb_w[p->zone] : p->kind == BBK_BODY ? &g_bb_body : p->kind == BBK_MOUTH ? &g_bb_mouth : &g_bb_hand;
    // a wound from a blunt / fist MELEE blow (hit reaction or pin blow within 1.2 s) is stamped where SP's blunt and fist clips stamp their victim -
    // the head (cut at headb, bm-face, bm-ellie-melee-nose), never a torso knife cut (int103: a wrench pin left spineb / spined cuts). t2r-blood-melee-cuts.txt = old
    if (p->kind == BBK_WOUND && p->who >= 0 && p->who < BB_N && g_bb_melee_at[p->who] && GetTickCount64() - g_bb_melee_at[p->who] < 1200 && !g_bb_melee_blade[p->who]
        && GetFileAttributesA("t2r-blood-melee-cuts.txt") == INVALID_FILE_ATTRIBUTES) {
        int v = p->zone % 3;
        bb_fx *h = v == 1 && g_bb_face.ok ? &g_bb_face : v == 2 && g_bb_nose.ok ? &g_bb_nose : &g_bb_w[0];
        if (h->ok) f = h;
    }
    if (!f->ok || clipfx_off() || !cfxe_check()) return;
    uint8_t *obj = cfxe_obj_of(ent);
    if (!obj) { if (nl < 60) { nl++; xlog("blood: %s on %s: body not found", f->nm, bb_name(p->who)); } return; }
    uint64_t r = clipfx_fire(obj, f->clip, &f->e, obj == bp_me());
    if (r) g_bb_fired++; else g_bb_failed++;
    if (p->kind == BBK_THROAT) xlog("blood: throat slash mask %s at %s on %s -> engine event path %llx", f->nm, f->jn, bb_name(p->who), (unsigned long long)r);
    else if (nl < 60) { nl++; xlog("blood: mask %s at %s on %s (blood %.0f dirt %.0f, wounds %d) -> engine event path %llx", f->nm, f->jn[0] ? f->jn : "(body)", bb_name(p->who),
                               (double)g_bb[p->who].blood, (double)g_bb[p->who].dirt, g_bb[p->who].wounds, (unsigned long long)r); }
}

// add blood to a body and let the level decide which masks are due (SP's low / med / high progression: first wounds, then the body
// splatter, then the face and the hands)
static void bb_escalate(int who) {
    bb_body *b = &g_bb[who];
    if (b->blood > 100.0f) b->blood = 100.0f;
    if (b->blood >= 45.0f && !b->body) { b->body = 1; bb_queue(who, BBK_BODY, 0, 120.0); }
    if (b->blood >= 75.0f && !b->mouth) { b->mouth = 1; bb_queue(who, BBK_MOUTH, 0, 300.0); }
    if (b->blood >= 75.0f && !b->hand) { b->hand = 1; bb_queue(who, BBK_HAND, 0, 500.0); }
}
// a hit taken: `drop` health lost, `seed` = the health after it (the same on every screen)
static void bb_hit(int who, float drop, float hp_after) {
    bb_body *b = &g_bb[who];
    b->blood += drop * 0.5f;
    static int nl;
    int n = drop >= 35.0f ? 2 : drop >= 6.0f ? 1 : 0;
    for (int i = 0; i < n && b->wounds < BB_WOUND_MAX; i++) {
        int z = bb_zone((uint32_t)(hp_after * 16.0f) * 2654435761u + (uint32_t)i * 40503u);
        if (g_bb_w[z].ok) { b->wounds++; bb_queue(who, BBK_WOUND, z, 250.0 + 90.0 * i); }   // 250 ms: the melee blow note (hit reaction message) lands first
    }
    if (LOGCAP(nl, 60)) xlog("blood: hit on %s: -%.1f hp (now %.1f) -> blood %.0f, wounds %d", bb_name(who), (double)drop, (double)hp_after, (double)b->blood, b->wounds);
    bb_escalate(who);
}
static const float *bb_pos(int who, float *buf) {
    if (who == T2R_US) return uc4_my_loc(buf);
    return g_bb[who].h ? feel_loc(g_bb[who].h, buf) : NULL;
}
// a body died / was executed: bystanders within 5 m get a light splatter (SP: close kills spray the next man)
static void bb_nearby(int src, const char *why) {
    float sb[16], ob[16];
    const float *sp = bb_pos(src, sb);
    if (!sp) return;
    for (int w = 0; w < BB_N; w++) {
        if (w == src || !g_bb[w].seen || g_bb[w].dead || (w < T2R_MAX_PEERS && !g_bb[w].h)) continue;
        const float *op = bb_pos(w, ob);
        if (!op) continue;
        float dx = op[0] - sp[0], dz = op[2] - sp[2];
        if (dx * dx + dz * dz > 5.0f * 5.0f) continue;
        g_bb[w].blood += 8.0f;
        if (!g_bb[w].bysplat) { g_bb[w].bysplat = 1; bb_queue(w, BBK_BODY, 0, 200.0); g_bb[w].body = 1; }
        bb_escalate(w);
        static int nl; if (LOGCAP(nl, 30)) xlog("blood: %s near %s (%s): blood %.0f", bb_name(w), bb_name(src), why, (double)g_bb[w].blood);
    }
}
static int bb_body_of_ent(uint64_t ent) {
    if (ent == SID_PLAYER) return T2R_US;
    if (!ent) return -1;
    for (int s = 0; s < T2R_MAX_PEERS; s++) if (g_bb[s].h == ent) return s;
    return -1;
}
// Throat-slash moves: the 2013 pairs (throat-cutting shiv / machete), the TLOU2 finishers whose victim clip cuts the neck (neck-slice / neck-chop /
// neck-tear / decapitate: knife, machete, hatchet / axe, female knife kills) and the contextual takedowns with a neck slice (the clip's gush row = the cut).
// *at = ms from the move's start.
static int bb_throat_move(double *at, double dflt) {
    static const char *const MX_T[] = {"machete-decapitate", "machete-execute-right", "shiv-stealth-back", "fist-insta-shiv-stand-back", "shiv-ground-execution-right"};
    static const char *const FIN_T[] = {"neck-slice", "neck-chop", "neck-tear", "decap", "throat-slit"};
    *at = dflt;
    uint64_t mv = g_ps.move;
    if (g_ps.kind == PS_CTXDOWN) {
        for (int pr = 0; pr < (int)CD_N; pr++) {
            if (fnv64(CD_PAIRS[pr].name) != mv) continue;
            if (!strstr(CD_PAIRS[pr].name, "neck-slice") && !strstr(CD_PAIRS[pr].name, "neck-chop")) return 0;
            int ns = CD_PAIRS[pr].nseg;
            for (size_t k = 0; CTX_FX[k].pair; k++) {          // the gush row of the finisher = the moment of the cut
                if (strcmp(CTX_FX[k].pair, CD_PAIRS[pr].name) || CTX_FX[k].role != 1 || !CTX_FX[k].jn || strcmp(CTX_FX[k].jn, "neck") || !CTX_FX[k].pn ||
                    !strstr(CTX_FX[k].pn, "ribbon-pulse") || CTX_FX[k].seg >= ns) continue;
                double st = 0;
                for (int i = 0; i < CTX_FX[k].seg; i++) st += cd_seg_len(pr, i) * 1000.0;
                *at = st + CTX_FX[k].ms;
                return 1;
            }
            return 1;
        }
        return 0;
    }
    int m = mx_by_move(mv);
    if (m >= 0) { for (size_t i = 0; i < sizeof MX_T / sizeof *MX_T; i++) if (!strcmp(MELEE2013[m].name, MX_T[i])) return 1; return 0; }
    for (size_t i = 0; i < sizeof FIN_ANIMS / sizeof FIN_ANIMS[0]; i++)
        if (FIN_ANIMS[i].move == mv) { for (size_t j = 0; j < sizeof FIN_T / sizeof *FIN_T; j++) if (strstr(FIN_ANIMS[i].vic, FIN_T[j])) return 1; return 0; }
    return 0;
}
// the shiv kills whose blade goes through the NECK, with the contact time (ms from the move start): the 2013 stealth shiv from behind (net-shiv-stealth-kill:
// stab f9-10 / gore f11 of 30 fps = the 300 / 330-360 ms sound + blood events), the insta-shiv from behind (the "gore" row 1100 ms of exsfx2013.h), the ground
// shiv on the RIGHT (head-dismemberment + blood gush event f66 = 2200 ms). The fronts and the left ground move stab the chest / belly: not a neck slash.
static int bb_shiv_neck(double *at) {
    static const struct { const char *n; double ms; } T[] = {{"shiv-stealth-back", 330.0}, {"fist-insta-shiv-stand-back", 1100.0}, {"shiv-ground-execution-right", 2200.0}};
    if (g_ps.kind != PS_MELEE_EXEC) return 0;
    int m = mx_by_move(g_ps.move);
    if (m < 0) return 0;
    for (size_t i = 0; i < sizeof T / sizeof *T; i++) if (!strcmp(MELEE2013[m].name, T[i].n)) { *at = T[i].ms; return 1; }
    return 0;
}
// the Interrogation's head slams (intvox.c, the same synced move clock on every screen: no message): second 0 = the slam into the ground at 2267 ms (no blood), 1 = the final smash at 5000 ms (the whole head-smash set)
static int bb_ig_slam(uint64_t ent, int second) {
    static int nl, off_c = -1; static uint64_t off_k;
    bb_init();
    if (!g_bb_nig || !ent || ent == ~0ULL || cfxe_file("t2r-no-int-blood.txt", &off_c, &off_k)) return 0;
    int who = bb_body_of_ent(ent), n = 0;
    if (who < 0) { if (LOGCAP(nl, 20)) xlog("interrogation blood: slam %d - victim body not found", second); return 0; }
    if (!second) { g_bb[who].blood += 3.0f; return 0; }       // the blood belongs to the KILLING head smash (FALL_HEAD 4967 / sfx-head-slam 5000), not the first slam into the ground: a small hit only
    for (int k = 0; k < g_bb_nig; k++) {
        bb_pend p; memset(&p, 0, sizeof p);
        p.who = who; p.kind = BBK_SPURT; p.zone = g_bb_ig0 + k; p.tag = second ? "interrogation final smash" : "interrogation head slam"; p.at = second ? 5000.0 : 2267.0;
        bb_do(&p); n++;
    }
    g_bb[who].blood += 25.0f;
    return n;
}
// A finisher dodged 34 ms after its contact still bled on the attacker's screen: bb_pair_tick queues the move's masks / spurts at its START with delays up to +2 s;
// an ABORT before the kill frame (a dodge, a refusal, a cut) left them queued and they fired later on a clean dodge. psync_abort cancels the two bodies' not-yet-due effects.
// t2r-bb-abort-keep.txt = old.
static void bb_cancel_pair(int a, int v) {
    if (GetFileAttributesA("t2r-bb-abort-keep.txt") != INVALID_FILE_ATTRIBUTES) return;
    double now = psync_ms(); int n = 0;
    for (int i = 0; i < 24; i++) if (g_bb_q[i].kind && g_bb_q[i].due > now + 60.0 && (g_bb_q[i].who == a || g_bb_q[i].who == v)) { g_bb_q[i].kind = 0; n++; }
    if (n) xlog("blood: the move was aborted before its kill frame - %d queued blood effect(s) on slots %d / %d cancelled", n, a, v);
}
// paired moves = executions / takedowns on every screen (psync runs the same move on all of them)
static void bb_pair_tick(void) {
    if (!g_ps.role || g_ps.kind == PS_REVIVE || g_ps.kind == PS_TACKLE) { g_bb_uid_wait = 0; return; }
    if (g_ps.uid == g_bb_uid_seen) return;
    int a = bb_body_of_ent(g_ps.ent_att), v = bb_body_of_ent(g_ps.ent_vic);
    if ((a < 0 || v < 0) && ++g_bb_uid_wait < 30) return;           // the halves are still being set up
    g_bb_uid_seen = g_ps.uid; g_bb_uid_wait = 0;
    int lethal = (g_ps.flags & PS_F_LETHAL) != 0;
    {   // a blade finisher (ctxdown one-shot) kills its victim at the kill frame now (t2r-ext.c "finisher by a blade") - lethal blood masks, as on the victim's screen
        static int (*bladef)(uint64_t, int *, const char **) = NULL; (void)bladef;
        if (!lethal && g_ps.kind == PS_CTXDOWN && g_ps.weapon && g_ps.weapon != ~0ULL && melee_blade_kills(g_ps.weapon) &&
            GetFileAttributesA("t2r-melee-down-revivable.txt") == INVALID_FILE_ATTRIBUTES) lethal = 1;
    }
    double at = g_ps.kill_s > 0.2f ? (g_ps.kill_s > 3.5f ? 3500.0 : (double)g_ps.kill_s * 1000.0) : 1200.0;
    static int nl;
    if (LOGCAP(nl, 40)) xlog("blood: execution kind %d %s: attacker %s victim %s, masks at +%.0f ms", g_ps.kind, lethal ? "lethal" : "non-lethal", a >= 0 ? bb_name(a) : "?", v >= 0 ? bb_name(v) : "?", at);
    double tat;
    double sat = 0;
    if (v >= 0 && g_bb_nsp && !bb_no_shiv() && bb_shiv_neck(&sat)) {
        int m = mx_by_move(g_ps.move);
        for (int k = 0; k < g_bb_nsp; k++) {
            bb_queue(v, BBK_SPURT, k, sat + g_bb_sp_rel[k]);
            for (int i = 0; i < 24; i++) if (g_bb_q[i].kind == BBK_SPURT && g_bb_q[i].zone == k && g_bb_q[i].who == v && !g_bb_q[i].tag) { g_bb_q[i].tag = MELEE2013[m].name; g_bb_q[i].at = sat + g_bb_sp_rel[k]; break; }
        }
        xlog("shiv blood: %s neck slash on %s: %d SP part-effects queued from +%.0f ms (spurt + gore at the cut, death tail to +%.0f ms)", MELEE2013[m].name, bb_name(v), g_bb_nsp, sat, sat + 1834.0);
    }
    if (v >= 0 && g_bb_throat.ok && bb_throat_move(&tat, at)) {
        if (sat > 0) tat = sat;
        bb_queue(v, BBK_THROAT, 0, tat);
        g_bb[v].blood += 12.0f;
        xlog("blood: throat slash on %s (move %016llx), mask at +%.0f ms", bb_name(v), (unsigned long long)g_ps.move, tat);
    }
    if (v >= 0) {
        bb_body *b = &g_bb[v];
        b->blood += lethal ? 40.0f : 14.0f;
        if (b->wounds < BB_WOUND_MAX) { int z = bb_zone(g_ps.uid * 2654435761u + 7u); if (g_bb_w[z].ok) { b->wounds++; bb_queue(v, BBK_WOUND, z, at); } }
        if (lethal) { if (!b->body) { b->body = 1; bb_queue(v, BBK_BODY, 0, at + 80.0); } if (!b->mouth) { b->mouth = 1; bb_queue(v, BBK_MOUTH, 0, at + 160.0); } }
        bb_escalate(v);
    }
    if (a >= 0 && lethal) {
        bb_body *b = &g_bb[a];
        b->blood += 22.0f;
        if (!b->body) { b->body = 1; bb_queue(a, BBK_BODY, 0, at + 100.0); }       // the executioner is splattered
        if (!b->hand) { b->hand = 1; bb_queue(a, BBK_HAND, 0, at + 200.0); }       // bloody hands
        bb_escalate(a);
    }
    if (lethal && v >= 0) bb_nearby(v, "execution");
}

// extra modules held while in a match (the mud interaction groups, the blood wipe): the same module-reference API feel.c's blood_pin uses
static const char *const BB_MODS[2] = {"part-module/part-interaction-mud-character", "part-module/part-sle-blood-clear-igc"};
static int g_bb_pin; static uint8_t *g_bb_pin_pool, g_bb_pin_bad;
static void bb_pin(int want) {
    if (want == g_bb_pin || g_bb_pin_bad) return;
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    static const uint8_t pro[8] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x57, 0x48, 0x83};
    if (memcmp(exe + 0x20803a0, pro, 8) || memcmp(exe + 0x2080430, pro, 8)) { g_bb_pin_bad = 1; hook_miss(exe + 0x20803a0, 8, "blood: particle module pool code differs - mud / wipe modules not held"); return; }
    uint8_t *pool = *(uint8_t **)(exe + 0x92d9720 + 0x70);
    if (!pool || IsBadReadPtr(pool, 0x400) || *(volatile int *)(pool + 0x300)) return;
    typedef void (*fn_ref)(uint8_t *, uint64_t);
    typedef char (*fn_has)(uint8_t *, uint64_t);
    fn_ref f = (fn_ref)(exe + (want ? 0x20803a0 : 0x2080430));
    if (!want && pool != g_bb_pin_pool) { g_bb_pin = 0; return; }
    for (int i = 0; i < 2; i++) {
        uint64_t sid = fnv64(BB_MODS[i]);
        if (!want && !((fn_has)(exe + 0x207cff0))(pool, sid)) continue;
        f(pool, sid);
        xlog("blood: module %s %s (requested %d, in a pool slot %d)", BB_MODS[i], want ? "held" : "released",
             ((fn_has)(exe + 0x207cff0))(pool, sid) != 0, ((fn_has)(exe + 0x207cfc0))(pool, sid) != 0);
    }
    g_bb_pin = want; g_bb_pin_pool = want ? pool : NULL;
}

// a new life for the body: clean
static void bb_reset(int who, uint64_t h, uint32_t life) {
    bb_body *b = &g_bb[who];
    float keep_hp = b->hp; int hp_ok = b->hp_ok;
    memset(b, 0, sizeof *b);
    b->h = h; b->life = life; b->seen = 1; b->born = g_frame ? g_frame : 1; b->hp = keep_hp; b->hp_ok = hp_ok;
    for (int i = 0; i < 24; i++) if (g_bb_q[i].kind && g_bb_q[i].who == who) g_bb_q[i].kind = 0;     // effects queued for the old life
}
static void bb_body_tick(int who, int st, int dead, float hp, const float *pos, uint64_t h, uint32_t life) {
    bb_body *b = &g_bb[who];
    if (!b->seen || b->h != h || b->life != life || (b->dead && !dead)) {
        int had = b->seen;
        bb_reset(who, h, life);
        if (had) {
            xlog("blood: %s starts a new life (%s): clean", bb_name(who), who == T2R_US ? "our own spawn" : "new character");
            if (who == T2R_US) {                       // SP's own spawn: broadcast-event(clear-wetness) + the blood-mask wipe group
                uint64_t ev = fnv64("clear-wetness");
                uint64_t r = dc_call(fnv64("broadcast-event"), 1, &ev);
                xlog("blood: broadcast-event clear-wetness -> %llx", (unsigned long long)r);
                bb_queue(who, BBK_CLEAR, 0, 700.0);
            }
        }
    }
    // hits: health drop on a living body (the networked health, the same sequence on every screen)
    if (hp >= 0.0f && !dead) {
        if (b->hp_ok && hp < b->hp - 2.0f && b->hp > 0.0f) bb_hit(who, b->hp - hp, hp);
        b->hp = hp; b->hp_ok = 1;
    } else if (dead) b->hp_ok = 0;
    // down / death: blood on the body, bystanders sprayed by a kill
    if (st == 1 && !b->downed) {
        b->blood += 12.0f;
        if (!b->body) { b->body = 1; bb_queue(who, BBK_BODY, 0, 150.0); }
        bb_escalate(who);
        xlog("blood: %s goes down: blood %.0f", bb_name(who), (double)b->blood);
    }
    if (dead && !b->dead) bb_nearby(who, "death");
    b->downed = st == 1 || st == 2; b->dead = dead;
    // downed crawl: dirt (+ a little blood) per metre of drag
    if (pos) {
        if (b->pos_ok) {
            float dx = pos[0] - b->px, dz = pos[2] - b->pz, v = __builtin_sqrtf(dx * dx + dz * dz) * 1000.0f / frame_ms_c();
            if (v > 8.0f) v = 0;                       // teleport / net snap
            b->speed += (v - b->speed) * 0.12f;
            if (st == 1 && b->speed > 0.35f) b->crawl_m += __builtin_sqrtf(dx * dx + dz * dz);
        }
        b->px = pos[0]; b->pz = pos[2]; b->pos_ok = 1;
    }
    while (st == 1 && b->crawl_m >= 2.0f) {
        b->crawl_m -= 2.0f;
        b->dirt += 12.5f; b->blood += 4.0f;
        if (b->dirt > 100.0f) b->dirt = 100.0f;
        if (b->mud < 8 && !bb_no_dirt()) { b->mud++; bb_queue(who, BBK_MUD, 0, 0.0); }
        bb_escalate(who);
    }
}
// ---- gun execution shots (exec_gore): every shot stamps a wound mask at once and the last one leaves SP's blood pool under the corpse
// (SP: blood-effect-spawner.cpp:624, one pool per kill 1.2 - 3.9 s after the shot, a random group of the blood-pool-01..08 variant list, at the
// body root). feel.c's own death pool waits for the body's dead state, which a corpse held by psync after an execution never shows.
static struct { uint64_t ent; int who; double due; } g_gxb_pool[4];
static void gxb_wound(int who, int zone) {
    if (who < 0 || who >= BB_N || zone < 0 || zone >= BB_WOUNDS || bb_off()) return;
    bb_body *b = &g_bb[who];
    if (!g_bb_w[zone].ok || b->wounds >= BB_WOUND_MAX || (who != T2R_US && !b->h)) return;
    b->wounds++; b->blood += 12.0f;
    bb_queue(who, BBK_WOUND, zone, 30.0);
    bb_escalate(who);
}
static void gxb_pool(uint64_t ent, int who, double delay_ms) {
    if (!ent || who < 0 || who >= BB_N || bb_off()) return;
    for (int i = 0; i < 4; i++) if (!g_gxb_pool[i].ent) { g_gxb_pool[i].ent = ent; g_gxb_pool[i].who = who; g_gxb_pool[i].due = psync_ms() + delay_ms; return; }
}
static void gxb_tick(void) {
    static int nl; static unsigned pick;
    double now = psync_ms();
    for (int i = 0; i < 4; i++) {
        if (!g_gxb_pool[i].ent || g_gxb_pool[i].due > now) continue;
        uint64_t ent = g_gxb_pool[i].ent; int who = g_gxb_pool[i].who;
        g_gxb_pool[i].ent = 0;
        if (who == T2R_US && local_hp() > 0.0f) { xlog("exec gore: pool under our body skipped - alive again"); continue; }
        if (!cfxe_obj_of(ent)) { xlog("exec gore: pool under %s skipped - body gone", bb_name(who)); continue; }
        char nm[24];
        snprintf(nm, sizeof nm, "blood-pool-%02u", 1u + bb_hash((uint32_t)(g_frame * 2654435761u) + pick++) % 8u);
        uint64_t r = armor_fx_spawn(fnv64(nm), ent, "root");
        if (LOGCAP(nl, 40)) xlog("exec gore: blood pool %s under %s (1.4 s after the killing shot) -> %llx", nm, bb_name(who), (unsigned long long)r);
    }
}
static void bloodbuild_tick(void) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    static int announced;
    if (!g_frame) return;
    if (bb_off()) { bb_pin(0); if (g_bb_init) { memset(g_bb, 0, sizeof g_bb); memset(g_bb_q, 0, sizeof g_bb_q); } return; }
    int in_match = match_substate() == 6;
    bb_pin(in_match);
    if (!in_match) { memset(g_bb, 0, sizeof g_bb); memset(g_bb_q, 0, sizeof g_bb_q); g_bb_uid_seen = 0; return; }
    bb_init();
    if (!g_bb_nfx) return;
    if (!announced) { announced = 1; xlog("blood: build-up on (hits, executions, kills nearby, downed crawl; new life = clean; t2r-no-blood-buildup.txt = off)"); }
    // ourselves: local_hp every 3rd frame (a script call), the life counter, the downed state
    {
        float lb[16]; const float *ml = uc4_my_loc(lb);
        static float hp = -1.0f;
        if (g_frame % 3 == 0) hp = local_hp();
        int st = g_downed ? (g_down_dying || g_uc4_dying_until ? 2 : 1) : 0;
        if (ml) bb_body_tick(T2R_US, st, 0, hp, ml, SID_PLAYER, g_fl.seq);
    }
    for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
        uint8_t *peer = ((fn_peer)t2r_peer)(sl);
        if (!peer || IsBadReadPtr(peer, 0x90) || !peer[4]) { if (g_bb[sl].seen) memset(&g_bb[sl], 0, sizeof g_bb[sl]); continue; }
        uint64_t h = *(uint64_t *)(peer + 0x60);
        if (!h) continue;
        const float *np = (const float *)(peer + 0x68);
        if (np[0] != np[0] || np[2] != np[2] || __builtin_fabsf(np[0]) > 1e5f || __builtin_fabsf(np[2]) > 1e5f) continue;
        int dead = peer[5] != 0;
        int st = g_peer_downed[sl] == 1 ? 1 : g_peer_downed[sl] == 2 ? 2 : 0;
        float hp = (!dead && g_frame % 3 == (sl % 3)) ? puppet_hp(sl, h) : g_bb[sl].hp_ok ? g_bb[sl].hp : -1.0f;
        bb_body_tick((int)sl, st, dead, hp, np, h, 0);
    }
    bb_pair_tick();
    gxb_tick();
    // due effects, at most 2 per frame
    double now = psync_ms(); int done = 0;
    for (int i = 0; i < 24 && done < 2; i++) {
        if (!g_bb_q[i].kind || g_bb_q[i].due > now) continue;
        bb_pend p = g_bb_q[i]; g_bb_q[i].kind = 0;
        if (p.who != T2R_US && !g_bb[p.who].h) continue;
        bb_do(&p); done++;
    }
}
