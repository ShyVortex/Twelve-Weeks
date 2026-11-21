// Offline check of bodyshield.h (BODYSHIELD skill rules: tiers, escape QTE, kill block, aim shield, mash meter).
// Build: gcc -std=gnu2x -O2 -o bodyshield_test bodyshield_test.c && ./bodyshield_test   (exit 0 = all pass)
#include <stdio.h>
#include "../bodyshield.h"
static int fails;
#define CK(c, ...) do { if (!(c)) { printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); fails++; } } while (0)

// mash at a steady rate (presses per second; 0 = none) from the shield start: ms until free (or -1 after 30 s)
static int mash_time(int lv, int iron, int hz) {
    bs_vic_t v; bs_vic_begin(&v, 7, lv, iron, 0);
    bs_vic_shield(&v, 0);
    int next = hz ? 0 : 1 << 30;
    for (int t = 0; t <= 30000; t += 1) {
        if (t >= next) { bs_vic_press_f(&v, t); next += 1000 / hz; }
        if (t % 16 == 0 && bs_vic_tick(&v, t) == BS_V_ESCAPE) return t;
    }
    return -1;
}

int main(void) {
    // ---- tiers: dearer than any other skill, longer escapes per level
    CK(BS_COST[0] == 4 && BS_COST[1] == 6 && BS_COST[2] == 8, "cost 4 / 6 / 8 LP");
    for (int lv = 1; lv <= 3; lv++) {
        bs_tier_t t = bs_tier(lv, 0), ti = bs_tier(lv, 1);
        CK(t.kb_ms == BS_QTE_OPEN_HI_MS + t.qte_zone_ms + BS_QTE_GRACE_MS + BS_NET_MARGIN_MS, "kb covers the latest prompt + zone + grace + margin (lv %d)", lv);
        CK(ti.qte_zone_ms == t.qte_zone_ms * 3 / 2 && ti.kb_ms > t.kb_ms, "Iron Grip I: zone x1.5 and the kill block follows (lv %d)", lv);
        CK(t.kb_ms < t.hold_max_ms, "the kill block ends before the hold runs out (lv %d)", lv);
        CK(t.mash_fast_ms < t.mash_idle_ms, "mashing beats waiting (lv %d)", lv);
        if (lv > 1) { bs_tier_t p = bs_tier(lv - 1, 0); CK(t.mash_fast_ms > p.mash_fast_ms && t.mash_idle_ms > p.mash_idle_ms && t.hold_max_ms > p.hold_max_ms, "longer per level (%d)", lv); }
    }
    CK(bs_tier(0, 0).mash_fast_ms == 2500 && bs_tier(9, 0).mash_fast_ms == 3500, "level clamps to 1..3");
    CK(bs_tier(1, 0).mash_fast_ms == 2500, "user: spamming frees in 2.5 s at level I");

    // ---- prompt moment: in range, the same for a uid, spread across uids
    {   int lo = 99999, hi = 0, same = 1;
        for (uint32_t u = 0; u < 5000; u++) { int o = bs_qte_open_ms(u * 977u + 3u); if (o < lo) lo = o; if (o > hi) hi = o; if (o != bs_qte_open_ms(u * 977u + 3u)) same = 0; }
        CK(lo >= BS_QTE_OPEN_LO_MS && hi <= BS_QTE_OPEN_HI_MS && hi - lo > 300, "open moment in [%d, %d]: %d..%d", BS_QTE_OPEN_LO_MS, BS_QTE_OPEN_HI_MS, lo, hi);
        CK(same, "deterministic per uid");
        CK(bs_qte_open_ms(0x01000001u) != bs_qte_open_ms(0x01000002u) || bs_qte_open_ms(0x01000002u) != bs_qte_open_ms(0x01000003u), "consecutive grabs differ");
    }

    // ---- QTE judge
    CK(bs_qte_judge(100, 800, 450) == BS_Q_NONE, "far before: ignored");
    CK(bs_qte_judge(600, 800, 450) == BS_Q_BURN, "just before the prompt: burns");
    CK(bs_qte_judge(800, 800, 450) == BS_Q_PASS && bs_qte_judge(1280, 800, 450) == BS_Q_PASS, "zone + grace pass");
    CK(bs_qte_judge(1281, 800, 450) == BS_Q_LATE, "after: late");

    // ---- victim: escape, burn, late, Iron Grip II
    {   bs_vic_t v; uint32_t uid = 0x02000005u; bs_vic_begin(&v, uid, 1, 0, 0); int o = v.open_ms;
        CK(bs_vic_press_e(&v, o - 500) == BS_V_NONE && v.qte == BS_Q_NONE, "an early stray press is ignored");
        CK(!bs_vic_qte_open(&v, o - 1) && bs_vic_qte_open(&v, o), "prompt shows at the open moment");
        CK(bs_vic_press_e(&v, o + 200) == BS_V_ESCAPE && v.end == BS_END_QTE && v.st == BS_ST_END, "press in the zone escapes");
        CK(bs_vic_press_e(&v, o + 250) == BS_V_NONE, "nothing after the end");
        bs_vic_begin(&v, uid, 1, 0, 0);
        CK(bs_vic_press_e(&v, o - 100) == BS_V_QTE_FAIL && v.qte == BS_Q_BURN, "mash before the prompt burns it");
        CK(bs_vic_press_e(&v, o + 10) == BS_V_NONE && v.st == BS_ST_HOLD, "no second try after a burn");
        CK(!bs_vic_kill_ok(&v, v.t.kb_ms - BS_NET_MARGIN_MS - 1) && bs_vic_kill_ok(&v, v.t.kb_ms), "kill accepted only past the kill block");
        bs_vic_begin(&v, uid, 1, 0, 0);
        int r = BS_V_NONE; for (int t = 0; t < 3000 && r == BS_V_NONE; t += 16) r = bs_vic_tick(&v, t);
        CK(r == BS_V_QTE_FAIL && v.qte == BS_Q_LATE, "no press: late");
        bs_vic_begin(&v, uid, 1, 2, 1); r = BS_V_NONE; int at = -1;
        for (int t = 0; t < 3000 && r == BS_V_NONE; t += 16) { r = bs_vic_tick(&v, t); at = t; }
        CK(r == BS_V_ESCAPE && v.end == BS_END_IRON && at >= o && at < o + 16, "Iron Grip II passes at the open moment (%d vs %d)", at, o);
        bs_vic_begin(&v, uid, 1, 0, 0); bs_vic_press_e(&v, o + 10);
        CK(!bs_vic_kill_ok(&v, 5000), "an escaped victim refuses the kill");
    }

    // ---- mash: 2.5 s at the cap (level I), slower tapping takes longer, no press = the wiggle time, turbo can't beat the cap
    {   int fast = mash_time(1, 0, 10), turbo = mash_time(1, 0, 40), tap = mash_time(1, 0, 3), none = mash_time(1, 0, 0);
        CK(fast >= 2450 && fast <= 2550, "10 presses/s frees in ~2.5 s (%d)", fast);
        CK(turbo >= 2450, "40 presses/s is capped (%d)", turbo);
        CK(tap > 4000 && tap < 6500, "3 presses/s takes longer (%d)", tap);
        int f12 = mash_time(1, 0, 12), f15 = mash_time(1, 0, 15);
        CK(f12 >= 2400 && f12 <= 2600 && f15 >= 2400 && f15 <= 2600, "faster than the cap is never slower: 12 / 15 presses/s free in ~2.5 s (%d %d)", f12, f15);
        {   // 10 presses/s with frame jitter (alternating 85 / 115 ms): no press lost to the cap
            bs_vic_t v; bs_vic_begin(&v, 7, 1, 0, 0); bs_vic_shield(&v, 0);
            int t = 0, k = 0, at = -1;
            for (int ms = 0; ms <= 10000 && at < 0; ms++) {
                if (ms == t) { bs_vic_press_f(&v, ms); t += (k++ & 1) ? 115 : 85; }
                if (ms % 16 == 0 && bs_vic_tick(&v, ms) == BS_V_ESCAPE) at = ms;
            }
            CK(at >= 2400 && at <= 2650, "jittered 10 presses/s frees in ~2.5 s (%d)", at);
        }
        CK(none >= 9200 && none <= 9300, "no press: 9.25 s wiggle (%d)", none);
        int f2 = mash_time(2, 0, 10), f3 = mash_time(3, 0, 10);
        CK(f2 >= 2950 && f2 <= 3050 && f3 >= 3450 && f3 <= 3550, "levels II / III: 3.0 / 3.5 s (%d %d)", f2, f3);
        bs_vic_t v; bs_vic_begin(&v, 1, 1, 0, 0); bs_vic_press_f(&v, 10);
        CK(v.m.presses == 0, "F before the shield does nothing");
    }

    // ---- attacker
    {   bs_att_t a; bs_att_begin(&a, 1, 0);
        CK(bs_att_step(&a, 500, 0, 1, 0) == BS_A_NONE && a.st == BS_ST_HOLD, "kill press inside the kill block is ignored");
        CK(bs_att_step(&a, a.kb_ms, 0, 1, 0) == BS_A_KILL && a.st == BS_ST_KILL, "kill after the block");
        CK(bs_att_step(&a, a.kb_ms + 100, 0, 0, 1) == BS_A_RELEASE && a.end == BS_END_DAMAGE, "damage during the finisher breaks it");
        bs_att_begin(&a, 1, 0); bs_att_acc(&a, a.kb_ms + 300);
        CK(bs_att_step(&a, a.t.kb_ms + 10, 0, 1, 0) == BS_A_NONE, "the victim's longer kill block (Iron Grip) wins");
        bs_att_acc(&a, 50000); CK(a.kb_ms < 10000, "an absurd ACC is ignored");
        bs_att_begin(&a, 2, 0);
        CK(bs_att_step(&a, 200, 1, 0, 0) == BS_A_SHIELD_ON && a.st == BS_ST_SHIELD, "aim raises the shield (even in the kill block)");
        CK(bs_att_step(&a, 5000, 1, 1, 0) == BS_A_NONE && a.st == BS_ST_SHIELD, "no choke / stab while shielding");
        CK(bs_att_step(&a, 200 + a.t.hold_max_ms + 500, 1, 0, 0) == BS_A_NONE, "the shield has no plain-hold timeout (the mash ends it)");
        CK(bs_att_step(&a, 9000, 0, 0, 0) == BS_A_RELEASE && a.end == BS_END_STOPAIM, "stop aiming: the victim breaks out");
        // lost messages: the shield cap is past the victim's own wiggle time, the victim's hold cap past the attacker's hold timeout
        bs_att_begin(&a, 1, 0); bs_att_step(&a, 200, 1, 0, 0);
        CK(bs_att_step(&a, 200 + a.t.mash_idle_ms + BS_LOST_MS - 1, 1, 0, 0) == BS_A_NONE, "shield held up to the wiggle time + the lost-message margin");
        CK(bs_att_step(&a, 200 + a.t.mash_idle_ms + BS_LOST_MS, 1, 0, 0) == BS_A_RELEASE && a.end == BS_END_TIMEOUT, "the victim's MASH END lost: the attacker lets go itself");
        for (int lv = 1; lv <= 3; lv++) { bs_att_t b; bs_att_begin(&b, lv, 0);
            CK(bs_att_shield_cap_ms(&b) - b.t.mash_idle_ms >= 5 * 190, "shield cap leaves >= 5 x the 190 ms ping kick limit (lv %d)", lv); }
        bs_att_begin(&a, 1, 0); bs_att_step(&a, 100, 1, 0, 0);
        CK(bs_att_step(&a, 116, 1, 0, 1) == BS_A_RELEASE && a.end == BS_END_DAMAGE, "damage while shielding: let go at once");
        bs_att_begin(&a, 1, 0);
        CK(bs_att_step(&a, 300, 0, 0, 1) == BS_A_RELEASE && a.end == BS_END_DAMAGE, "damage in a plain hold lets go too");
        bs_att_begin(&a, 1, 0);
        CK(bs_att_step(&a, a.t.hold_max_ms - 1, 0, 0, 0) == BS_A_NONE && bs_att_step(&a, a.t.hold_max_ms, 0, 0, 0) == BS_A_RELEASE && a.end == BS_END_TIMEOUT, "hold timeout");
        CK(bs_end_escapes(BS_END_STOPAIM) && bs_end_escapes(BS_END_MASH) && !bs_end_escapes(BS_END_KILLED) && !bs_end_escapes(BS_END_SHOTDEAD), "end classes");
        CK(bs_end_name(BS_END_STOPAIM)[0] == 'S' && bs_end_name(99)[0] == '?', "end names");
    }
    // ---- victim: the attacker's END / AIM never came
    {   bs_vic_t v; bs_vic_begin(&v, 0x03000001u, 1, 0, 0);
        int r = BS_V_NONE, at = -1;
        for (int t = 0; t < 20000 && r != BS_V_ESCAPE; t += 16) { r = bs_vic_tick(&v, t); at = t; }
        CK(r == BS_V_ESCAPE && v.end == BS_END_TIMEOUT && at >= v.t.hold_max_ms + BS_LOST_MS && at < v.t.hold_max_ms + BS_LOST_MS + 16, "hold cap: breaks out itself at hold max + %d ms (%d)", BS_LOST_MS, at);
        CK(bs_end_escapes(BS_END_TIMEOUT), "a timeout counts as an escape (re-grab cooldown)");
        bs_vic_begin(&v, 0x03000001u, 1, 0, 0); bs_vic_shield(&v, 1000);
        r = BS_V_NONE; at = -1;
        for (int t = 1000; t < 30000 && r != BS_V_ESCAPE; t += 16) { r = bs_vic_tick(&v, t); at = t; }
        CK(r == BS_V_ESCAPE && v.end == BS_END_MASH, "a shield never hits the hold cap: the wiggle frees it (%d)", at);
        bs_vic_begin(&v, 0x03000001u, 1, 0, 0); bs_vic_shield(&v, 500); bs_vic_press_f(&v, 600); bs_vic_press_f(&v, 700);
        float f = v.m.fill; bs_vic_shield(&v, 800);
        CK(v.m.fill == f && v.m.counted == 2, "a re-sent AIM does not reset the mash meter");
    }
    // ---- outbox: 3 copies at 0 / 100 / 250 ms, then silence
    {   int sent = 0, at[8], n = 0;
        for (int t = 0; t <= 2000 && n < 8; t += 16) if (bs_resend_due(sent, t)) { at[n++] = t; sent++; }
        CK(n == BS_RESEND_N, "%d copies (%d)", BS_RESEND_N, n);
        CK(n == 3 && at[0] == 0 && at[1] >= 100 && at[1] < 116 && at[2] >= 250 && at[2] < 266, "copy times %d %d %d", at[0], at[1], at[2]);
        CK(!bs_resend_due(-1, 0) && !bs_resend_due(BS_RESEND_N, 99999), "out of range: nothing");
    }
    printf(fails ? "%d FAILED\n" : "bodyshield: all pass\n", fails);
    return fails != 0;
}
