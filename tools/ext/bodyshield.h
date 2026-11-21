// bodyshield.h - BODYSHIELD skill (re/bodyshield-1117.md): the pure rules, no engine calls.
// Included by bodyshield.c (the ext glue) and by tests/bodyshield_test.c (offline check).
//
// One grab = two machines that run the same rules with their own role:
//   ATTACKER (the body shielder)  bs_att_*  : the kill-block window, the aim shield, the release on damage / stop aiming / hold timeout.
//   VICTIM   (the grabbed player) bs_vic_*  : the escape QTE judged on the victim's screen, the F-mash meter of the aim shield.
// Times are in ms of each machine's own clock from the grab START (the victim's START time = its arrival, the one-way latency already
// skipped by psync, as the pin QTE does). Nothing here reads a clock: the caller passes `now`.
#pragma once
#include <stdint.h>

#define BS_LEVELS 3
// LP cost per level: above every other skill level I (the dearest is Collector I at 3); more expensive than other perks, with tiers.
static const uint8_t BS_COST[BS_LEVELS] = {4, 6, 8};

// ---- timings (re/bodyshield-1117.md "Tier table" has the reasons)
#define BS_QTE_OPEN_LO_MS   700    // the escape prompt opens at a uid-derived moment in [LO, HI] after the grab START (both machines derive the same one)
#define BS_QTE_OPEN_HI_MS  1100    // (HI ~ SP's 1067 ms: meatshield-stealth-attack-grab lets the player's execution attacks in from frame 32)
#define BS_QTE_GRACE_MS      30    // same grace as the pin QTE (MPN_GRACE_MS)
#define BS_QTE_BURN_MS      300    // a press up to this long before the prompt burns the QTE (anti-mash, pin rule MPN_BURN_MS)
#define BS_NET_MARGIN_MS    150    // kill-block tail past the victim's last pressable moment: an ESC sent at the last moment reaches the attacker first
#define BS_MASH_GAP_MS      100    // counted F presses are capped at 1 per this (10 presses/s: a turbo key cannot beat the fastest time)
#define BS_MASH_BURST         2    // press credit kept at most (a hard 100 ms gap dropped every press that came a frame early - 10 / s
                                   // freed in 3.5 s, not 2.5 s, and 12 / s counted only 6: faster mashing was slower). Credit absorbs the jitter.
#define BS_FF_TAIL_MS       150    // friendly fire on the shield victim stays this long after the shield ends (hits already on the wire)
#define BS_REACH_M          1.6f   // grab start distance (SP: 0.59 m at the synced grab after a 0.5 s intro lunge from 2.28 m; psync pulls the rest)
#define BS_REGRAB_COOL_MS  8000    // a victim that broke free cannot be grabbed by the same shielder for 8 s (pin rule MPN_ESC_COOL_MS)
// lost messages (MSG_BS is an unreliable broadcast). Not a gameplay number: net safety, reasons in re/bodyshield-1117.md "Lost messages".
#define BS_LOST_MS         1000    // a side ends the grab itself this long after the other side's own end must have come (5x the 190 ms ping kick limit)
#define BS_RESEND_N           3    // AIM / KILL / END go out 3 times: at 0, 100 and 250 ms (one lost packet, or a 200 ms burst, is covered)
static const int BS_RESEND_AT[BS_RESEND_N] = {0, 100, 250};
// the outbox: `sent` copies of the op went out, the first `since` ms ago -> 1 = send the next copy now
static int bs_resend_due(int sent, int since) { return sent >= 0 && sent < BS_RESEND_N && since >= BS_RESEND_AT[sent]; }

typedef struct {
    int qte_zone_ms;     // pressable length of the escape prompt (Iron Grip I: x1.5)
    int kb_ms;           // kill block: no choke / stab before this (from the grab START) = QTE close + grace + net margin
    int hold_max_ms;     // a grab that is neither aimed nor finished ends here: the victim breaks out
    int mash_fast_ms;    // aim shield: free after this long when F is mashed at the cap (user: 2.5 s, longer per level)
    int mash_idle_ms;    // aim shield: free after this long with no press at all (the automatic wiggle; SP: an NPC hostage breaks out 9.25 s after the grab)
} bs_tier_t;

static int bs_clamp_lv(int lv) { return lv < 1 ? 1 : lv > BS_LEVELS ? BS_LEVELS : lv; }
// attacker's BODYSHIELD level lv (1..3), the victim's Iron Grip level iron (0..2)
static bs_tier_t bs_tier(int lv, int iron) {
    static const int ZONE[BS_LEVELS] = {450, 400, 350};
    static const int HOLD[BS_LEVELS] = {6000, 7000, 8000};
    static const int FAST[BS_LEVELS] = {2500, 3000, 3500};
    static const int IDLE[BS_LEVELS] = {9250, 11100, 12950};      // 9.25 s x the same ratio as FAST (1.0 / 1.2 / 1.4)
    bs_tier_t t;
    lv = bs_clamp_lv(lv);
    t.qte_zone_ms = ZONE[lv - 1];
    if (iron >= 1) t.qte_zone_ms = t.qte_zone_ms * 3 / 2;
    t.kb_ms = BS_QTE_OPEN_HI_MS + t.qte_zone_ms + BS_QTE_GRACE_MS + BS_NET_MARGIN_MS;
    t.hold_max_ms = HOLD[lv - 1];
    t.mash_fast_ms = FAST[lv - 1];
    t.mash_idle_ms = IDLE[lv - 1];
    return t;
}
// the prompt's open moment for grab uid: the same on both machines, not guessable from one grab to the next
static int bs_qte_open_ms(uint32_t uid) {
    uint32_t h = uid * 2654435761u; h ^= h >> 15; h *= 2246822519u; h ^= h >> 13;
    return BS_QTE_OPEN_LO_MS + (int)(h % (uint32_t)(BS_QTE_OPEN_HI_MS - BS_QTE_OPEN_LO_MS + 1));
}

// ---- the escape QTE (victim)
enum { BS_Q_NONE, BS_Q_PASS, BS_Q_BURN, BS_Q_LATE };
// a press `rel` ms after the grab START: PASS inside the prompt, BURN just before it, NONE far before it (ignored), LATE after the zone
static int bs_qte_judge(int rel, int open_ms, int zone_ms) {
    if (rel < open_ms - BS_QTE_BURN_MS) return BS_Q_NONE;
    if (rel < open_ms) return BS_Q_BURN;
    if (rel <= open_ms + zone_ms + BS_QTE_GRACE_MS) return BS_Q_PASS;
    return BS_Q_LATE;
}

// ---- the aim-shield mash meter (victim). fill 0..1; a counted press adds `per press`, time adds 1 / mash_idle_ms per ms.
// Mashing at the cap (1 press / BS_MASH_GAP_MS) fills it in exactly mash_fast_ms.
typedef struct { float fill, credit; int64_t last_press; int presses, counted; } bs_mash_t;   // last_press = the last credit refill
static float bs_mash_per_press(const bs_tier_t *t) {
    float presses = (float)t->mash_fast_ms / (float)BS_MASH_GAP_MS;                 // presses at the cap in the fastest time
    float idle_part = (float)t->mash_fast_ms / (float)t->mash_idle_ms;             // what the wiggle alone fills meanwhile
    return (1.0f - idle_part) / presses;
}
static void bs_mash_reset(bs_mash_t *m) { m->fill = 0.0f; m->credit = 1.0f; m->last_press = -1; m->presses = 0; m->counted = 0; }
// a press counts while there is credit: credit refills 1 per BS_MASH_GAP_MS, kept up to BS_MASH_BURST - over time at most 10 counted / s,
// and a press that comes a frame early is not lost (it uses the stored credit)
static int bs_mash_press(bs_mash_t *m, int64_t now, const bs_tier_t *t) {           // 1 = counted
    m->presses++;
    if (m->last_press >= 0 && now > m->last_press) {
        m->credit += (float)(now - m->last_press) / (float)BS_MASH_GAP_MS;
        if (m->credit > (float)BS_MASH_BURST) m->credit = (float)BS_MASH_BURST;
    }
    m->last_press = now;
    if (m->credit < 0.999f) return 0;
    m->credit -= 1.0f; m->counted++;
    m->fill += bs_mash_per_press(t);
    return 1;
}
static int bs_mash_tick(bs_mash_t *m, int dt_ms, const bs_tier_t *t) {              // 1 = full: the victim is free
    if (dt_ms > 0 && dt_ms < 1000) m->fill += (float)dt_ms / (float)t->mash_idle_ms;
    if (m->fill > 1.0f) m->fill = 1.0f;
    return m->fill >= 0.9999f;
}

// ---- the grab, as both machines see it
enum { BS_ST_NONE, BS_ST_HOLD, BS_ST_SHIELD, BS_ST_KILL, BS_ST_END };
enum {                                   // how a grab ended (the wire's reason byte; the end pair follows from it)
    BS_END_NONE, BS_END_QTE,             // victim: escape prompt hit
    BS_END_MASH,                         // victim: mash meter full
    BS_END_IRON,                         // victim: Iron Grip II free escape
    BS_END_STOPAIM,                      // attacker stopped aiming: the victim breaks out at once
    BS_END_DAMAGE,                       // attacker took damage: lets go
    BS_END_TIMEOUT,                      // hold ran out without aim / kill
    BS_END_KILLED,                       // the choke / stab finished
    BS_END_SHOTDEAD,                     // the victim died as a shield (its own team's fire)
    BS_END_GONE,                         // a body is gone / downed / dead elsewhere: plain abort
};
static const char *bs_end_name(int r) {
    static const char *const N[] = {"none", "QTE", "MASH", "IRON GRIP", "STOP AIM", "DAMAGE", "TIMEOUT", "KILLED", "SHOT DEAD", "GONE"};
    return r >= 0 && r <= BS_END_GONE ? N[r] : "?";
}
static int bs_end_escapes(int r) { return r == BS_END_QTE || r == BS_END_MASH || r == BS_END_IRON || r == BS_END_STOPAIM || r == BS_END_DAMAGE || r == BS_END_TIMEOUT; }

// attacker
typedef struct {
    int st, end, lv, iron;
    bs_tier_t t;
    int kb_ms;                           // max(own, the victim's ACC): the victim's Iron Grip can only lengthen it
    int aimed;                           // the shield was raised once: no choke / stab for the rest of the grab
    int shield_ms;                       // rel when the shield went up
} bs_att_t;
enum { BS_A_NONE, BS_A_SHIELD_ON, BS_A_KILL, BS_A_RELEASE };
static void bs_att_begin(bs_att_t *a, int lv, int victim_iron) {
    a->st = BS_ST_HOLD; a->end = BS_END_NONE; a->lv = bs_clamp_lv(lv); a->iron = victim_iron;
    a->t = bs_tier(a->lv, victim_iron); a->kb_ms = a->t.kb_ms; a->aimed = 0; a->shield_ms = 0;
}
// the longest the shield can last: the victim's wiggle alone frees it by mash_idle_ms on its own screen (its AIM arrived one-way later).
// Past that + BS_LOST_MS its MASH END was lost: the attacker lets go itself (TIMEOUT), else it would hold a victim that walked off.
static int bs_att_shield_cap_ms(const bs_att_t *a) { return a->t.mash_idle_ms + BS_LOST_MS; }
static void bs_att_acc(bs_att_t *a, int kb_ms) { if (kb_ms > a->kb_ms && kb_ms < 10000) a->kb_ms = kb_ms; }
static int bs_att_can_kill(const bs_att_t *a, int rel) { return a->st == BS_ST_HOLD && !a->aimed && rel >= a->kb_ms; }
// one frame: rel = ms since the grab START, aiming = the aim input, kill = the kill press edge, hurt = we took damage this frame.
// Returns BS_A_*; a RELEASE sets a->end.
static int bs_att_step(bs_att_t *a, int rel, int aiming, int kill, int hurt) {
    switch (a->st) {
    case BS_ST_HOLD:
        if (hurt) { a->st = BS_ST_END; a->end = BS_END_DAMAGE; return BS_A_RELEASE; }
        if (aiming) { a->st = BS_ST_SHIELD; a->aimed = 1; a->shield_ms = rel; return BS_A_SHIELD_ON; }
        if (kill && bs_att_can_kill(a, rel)) { a->st = BS_ST_KILL; return BS_A_KILL; }
        if (rel >= a->t.hold_max_ms) { a->st = BS_ST_END; a->end = BS_END_TIMEOUT; return BS_A_RELEASE; }
        return BS_A_NONE;
    case BS_ST_SHIELD:                   // user: once aiming, keep aiming - no stop, no choke, no stab
        if (hurt) { a->st = BS_ST_END; a->end = BS_END_DAMAGE; return BS_A_RELEASE; }
        if (!aiming) { a->st = BS_ST_END; a->end = BS_END_STOPAIM; return BS_A_RELEASE; }
        if (rel - a->shield_ms >= bs_att_shield_cap_ms(a)) { a->st = BS_ST_END; a->end = BS_END_TIMEOUT; return BS_A_RELEASE; }   // (the victim's MASH END was lost)
        return BS_A_NONE;
    case BS_ST_KILL:                     // the finisher runs; damage before the kill moment breaks it (bs.c passes hurt only before it)
        if (hurt) { a->st = BS_ST_END; a->end = BS_END_DAMAGE; return BS_A_RELEASE; }
        return BS_A_NONE;
    }
    return BS_A_NONE;
}

// victim
typedef struct {
    int st, end;
    bs_tier_t t;
    int open_ms;                         // prompt open (from the uid)
    int qte;                             // BS_Q_* result so far (NONE = still open)
    int iron_free;                       // Iron Grip II: pass at the open moment
    bs_mash_t m;
    int64_t last_ms;                     // last tick (the mash wiggle's dt)
} bs_vic_t;
enum { BS_V_NONE, BS_V_ESCAPE, BS_V_QTE_FAIL };
static int bs_vic_hold_cap_ms(const bs_vic_t *v) { return v->t.hold_max_ms + BS_LOST_MS; }
static void bs_vic_begin(bs_vic_t *v, uint32_t uid, int att_lv, int iron, int iron_free) {
    v->st = BS_ST_HOLD; v->end = BS_END_NONE; v->t = bs_tier(att_lv, iron); v->open_ms = bs_qte_open_ms(uid);
    v->qte = BS_Q_NONE; v->iron_free = iron_free; bs_mash_reset(&v->m); v->last_ms = 0;
}
static int bs_vic_qte_open(const bs_vic_t *v, int rel) { return v->st == BS_ST_HOLD && v->qte == BS_Q_NONE && rel >= v->open_ms && rel <= v->open_ms + v->t.qte_zone_ms + BS_QTE_GRACE_MS; }
// the E press of the escape prompt (edge)
static int bs_vic_press_e(bs_vic_t *v, int rel) {
    if (v->st != BS_ST_HOLD || v->qte != BS_Q_NONE) return BS_V_NONE;
    int q = bs_qte_judge(rel, v->open_ms, v->t.qte_zone_ms);
    if (q == BS_Q_NONE) return BS_V_NONE;
    v->qte = q;
    if (q == BS_Q_PASS) { v->st = BS_ST_END; v->end = BS_END_QTE; return BS_V_ESCAPE; }
    return BS_V_QTE_FAIL;
}
// the F press of the shield mash (edge)
static void bs_vic_press_f(bs_vic_t *v, int rel) { if (v->st == BS_ST_SHIELD) bs_mash_press(&v->m, rel, &v->t); }
// the attacker raised the shield (its AIM message): the mash starts now
static void bs_vic_shield(bs_vic_t *v, int rel) { if (v->st == BS_ST_HOLD) { v->st = BS_ST_SHIELD; bs_mash_reset(&v->m); v->last_ms = rel; } }
// one frame
static int bs_vic_tick(bs_vic_t *v, int rel) {
    int dt = (int)(rel - v->last_ms); v->last_ms = rel;
    if (v->st == BS_ST_HOLD) {
        if (v->qte == BS_Q_NONE && v->iron_free && rel >= v->open_ms) { v->qte = BS_Q_PASS; v->st = BS_ST_END; v->end = BS_END_IRON; return BS_V_ESCAPE; }
        if (v->qte == BS_Q_NONE && rel > v->open_ms + v->t.qte_zone_ms + BS_QTE_GRACE_MS) { v->qte = BS_Q_LATE; return BS_V_QTE_FAIL; }
        // the attacker's own hold timeout (or its STOP AIM / DAMAGE END, or its AIM) never reached us: break out ourselves. The attacker
        // takes a victim's END as the victim's call, so both screens end on the escape pair.
        if (rel >= bs_vic_hold_cap_ms(v)) { v->st = BS_ST_END; v->end = BS_END_TIMEOUT; return BS_V_ESCAPE; }
        return BS_V_NONE;
    }
    if (v->st == BS_ST_SHIELD && bs_mash_tick(&v->m, dt, &v->t)) { v->st = BS_ST_END; v->end = BS_END_MASH; return BS_V_ESCAPE; }
    return BS_V_NONE;
}
// the attacker's KILL reached us: accepted only from a plain hold past the kill block (rel on our clock; the START skip makes our clock
// run ~one-way behind the attacker's, so its kill press can't arrive before our own kb) - else the victim's escape stands
static int bs_vic_kill_ok(const bs_vic_t *v, int rel) { return v->st == BS_ST_HOLD && v->qte != BS_Q_PASS && rel >= v->t.kb_ms - BS_NET_MARGIN_MS; }
