// ---------------------------------------------------------------- clan supply perks: the clan's surplus helps the match
// Included by t2r-ext.c after notify.c (one translation unit). Log prefix 'clanperk:'. Server side: tools/clan_perks.py (spec re/clan-supply-boosters.md); the pure core
// (parse of the daemon's perk tail, spawn plan, report packing, card text) is clanperk.h, tested by tests/clanperk_test.c.
//
// The daemon puts the active perks + the credited member at the END of its 0xE1 state text (pk=.. pkc/pkn/pkg/pkl/pkr/pkm); clan_parse hands the text to cp_set_from.
// An old daemon sends nothing: no perks. A perk and its use:
//   medkit  (medicine surplus)  a free health kit on every 2nd spawn of the match (cap 2): the same inventory add as Fortitude II's starting kit (skills.c), only while we
//                               carry fewer than 2
//   clip    (ammo surplus)      +1 magazine on the primary's reserve at a spawn (cap 3): the spawn ammo path (g_settotal_orig), never above the 2013 reserve cap
//   parts   (materials surplus) one crafting set (rag + alcohol, 4 units each = one whole ingredient like a supply box gives) on spawns 1, 3 (cap 2)
//   stamina (food surplus)      Marathon Runner I sprint recovery (regen x1.15, delay x0.85) for the whole match; the one use is booked when the meter first empties
//   bleed   (water surplus)     Fortitude I bleed-out time x1.25 when the player has no Fortitude; every down it stretches is a use (cap 2)
// Every grant/use: a styled HUD card "TYLER PROVIDED YOU WITH A MEDKIT" (notify.c toast; the portrait slot is the hook g_cp_portrait_cb - portraits are parked, nothing is
// drawn there yet), the No Return stinger (sfx-hud-rl-challenge-new-unlock, bank gbl-hud-rl is in the MP level list) and 0.5 s later the member's voice line
// (perkvoice.pcm: TLOU2 companion 'gives an item' barks with a memory echo made offline, PCM mixer, quiet, one per 20 s). The uses ride in the match report (0xE2 labels 31 / 32).
// Switches next to the exe: t2r-no-clan-perks.txt (off), t2r-no-clan-perk-voice.txt (no voice line).
#include "clanperk.h"
#include "perkvoice.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl cpv_blob\ncpv_blob:\n.incbin \"perkvoice.pcm\"\n.text\n");
extern const int16_t cpv_blob[];
static cp_state_t g_cp;                          // the perks of the last state reply (guarded by g_clan_cs)
static int g_cp_used[CP_N];                      // uses this match, wire order (reported in the match report)
static int g_cp_spawns;                          // spawns this match
static uint64_t g_cp_last_spawn_ms, g_cp_voice_ms, g_cp_voice_at;
static int g_cp_bad;                             // lives lost in a row without downing an enemy (cleared by the player's own down of an enemy)
static int g_cp_armed = 1;                       // one grant per streak: cleared by a grant, set again by the player's down of an enemy (and at the match arm)
static uint64_t g_cp_grant_ms;                   // the last grant of this match
static int g_cp_voice_perk = -1, g_cp_voice_fem, g_cp_voice_log;
static void (*g_cp_portrait_cb)(const cp_perk_t *who, const char *text);   // hook for the portrait slot of the card (clan portraits are parked)

static void cp_set_from(const char *t) {         // worker thread (clan_parse)
    cp_state_t s;
    const char *pk = t ? strstr(t, " pk=") : NULL;
    cp_parse_tail(pk, &s);
    EnterCriticalSection(&g_clan_cs);
    int changed = memcmp(&s, &g_cp, sizeof s) != 0;
    g_cp = s;
    LeaveCriticalSection(&g_clan_cs);
    if (changed) xlog("clanperk: server perks %d (%s)", s.n, pk ? pk + 1 : "none");
}
static void cp_get(cp_state_t *o) { EnterCriticalSection(&g_clan_cs); *o = g_cp; LeaveCriticalSection(&g_clan_cs); }
static int cp_switch(const char *file, int *cache, uint64_t *at) {
    uint64_t now = GetTickCount64();
    if (*cache < 0 || now - *at > 2000) { FILE *f = exe_side_open(file, "r"); *cache = f != NULL; if (f) fclose(f); *at = now; }
    return *cache;
}
static int cp_off(void) { static int c = -1; static uint64_t at; return cp_switch("t2r-no-clan-perks.txt", &c, &at); }
static int cp_voice_off(void) { static int c = -1; static uint64_t at; return cp_switch("t2r-no-clan-perk-voice.txt", &c, &at); }
static void cp_match_reset(void) {               // the match is being armed (loading): fresh counters
    memset(g_cp_used, 0, sizeof g_cp_used);
    g_cp_spawns = 0; g_cp_last_spawn_ms = 0; g_cp_voice_at = 0; g_cp_voice_perk = -1;
    g_cp_bad = 0; g_cp_armed = 1; g_cp_grant_ms = 0;
}
static int cp_polish_text(void) { return g_loc_cur >= 0 && !strcmp(LOC_LANGS[g_loc_cur].code, "pl"); }
static int cp_polish_voice(void) { vx_lang_tab(0); return g_vx_lang_nm && !_stricmp(g_vx_lang_nm, "polish"); }
// a perk fired: card + stinger + (queued) voice. i = perk index 0..4
static void cp_announce(const cp_perk_t *p, int i) {
    static const int KIND[CP_N] = {NTF_HEAL, NTF_CRAFT, NTF_CRAFT, NTF_MOVE, NTF_HEAL};
    char text[160];
    int pl = cp_polish_text();
    cp_card_text(text, sizeof text, p->name, p->cat, p->female, pl);
    cc_card_t cc;                                // the perk pop card (clancard.c): the member's headshot, the item's big faded icon, "<NAME> PROVIDED YOU WITH <ITEM>!"
    memset(&cc, 0, sizeof cc);
    cc.kind = CC_PERK; cc.expr = CC_EX_HAPPY; cc.look = p->look; cc.female = p->female; cc.role = p->role; cc.icon = p->cat; cc.secs = 4.2f;
    snprintf(cc.name, sizeof cc.name, "%s", p->name); snprintf(cc.pic, sizeof cc.pic, "%s", p->pic); snprintf(cc.line, sizeof cc.line, "%s", text);
    int r = cc_show(&cc, g_cp_last_spawn_ms && GetTickCount64() - g_cp_last_spawn_ms < 6000);
    if (r == 2) { xlog("clanperk: \"%s\" - not at a spawn, no pop (perk %d)", text, i); return; }      // a perk pops up once, at the spawn only
    if (r == 1) { xlog("clanperk: card queued \"%s\" (perk %d, head %d, role %d)", text, i, p->look, p->role); return; }   // the stinger + voice start with the slide-in (cp_card_started)
    if (!ntf_push(KIND[i], text, 4.2f)) msg_hook(text, 4.0f, 0, 0);                                      // no card widgets in this pak: the old toast
    cp_card_started(i, p->female);
    xlog("clanperk: toast \"%s\" (perk %d, head %d, role %d)", text, i, p->look, p->role);
}
// the card started to slide in (clancard.c) or the toast fallback fired: the No Return stinger and, 0.5 s later, the member's voice line
static void cp_card_started(int i, int female) {
    if (i < 0 || i >= CP_N) return;
    ui_sfx("sfx-hud-rl-challenge-new-unlock");
    g_cp_voice_perk = i; g_cp_voice_fem = female; g_cp_voice_at = GetTickCount64() + 500;
}
static void cp_use(const cp_perk_t *p, int i, const char *what) {
    g_cp_used[i]++;
    xlog("clanperk: use %s #%d of %d - %s (%s)", what, g_cp_used[i], p->cap, p->name, "reported with the match");
    cp_announce(p, i);
}
// the member's voice line, 0.5 s after the card: companion 'gives an item' bark with the memory echo (offline), PCM mixer, quiet, one per 20 s
static void cp_voice_tick(void) {
    if (g_cp_voice_perk < 0 || !g_cp_voice_at || GetTickCount64() < g_cp_voice_at) return;
    int i = g_cp_voice_perk;
    g_cp_voice_perk = -1; g_cp_voice_at = 0;
    uint64_t now = GetTickCount64();
    if (cp_voice_off() || g_downed || !cp_voice_due(now, g_cp_voice_ms)) { if (g_cp_voice_log++ < 6) xlog("clanperk: voice skipped (%s)", cp_voice_off() ? "switch" : g_downed ? "downed" : "20 s gap"); return; }
    clan_t c = clan_get();
    int fac = c.fac == 1 ? 1 : c.fac == 2 ? 0 : -1;
    if (fac < 0) return;
    int pol = cp_polish_voice(), start = (int)(t2r_rand() % CPV_PER);
    for (int q = 0; q < CPV_PER; q++) {
        int k = (start + q) % CPV_PER;
        unsigned en = CPV_LINE[fac][g_cp_voice_fem ? 1 : 0][i][k][0], pw = CPV_LINE[fac][g_cp_voice_fem ? 1 : 0][i][k][1];
        unsigned w = pol && pw != 0xFFFF ? pw : en;
        if (w == 0xFFFF || w >= CPV_N) continue;
        if (pcm_play_rate(cpv_blob + CPV_WAVE[w].off, (int)CPV_WAVE[w].n, 0.5f, CPV_RATE)) {
            g_cp_voice_ms = now;
            xlog("clanperk: voice line %d/%d of perk %d (%s%s, wave %u, %.1f s)", k + 1, CPV_PER, i, fac ? "WLF" : "Seraphite", g_cp_voice_fem ? " woman" : " man", w, (double)CPV_WAVE[w].n / CPV_RATE);
        }
        return;
    }
}
// the per-frame tick (from skills_tick, only in a match)
static void cp_tick(void) { cp_voice_tick(); }
// ---- the help comes when the player STRUGGLES, not on a fixed spawn. Pure rule: clanperk.h cp_struggling / cp_pick_item / cp_grant_due (re/clan-supply-boosters.md section 7).
// every down in the match (ev_down, t2r-ext.c): downer / victim slots, me = our slot
static void cp_note_down(uint32_t downer, uint32_t victim, uint32_t me) {
    if (victim == me) { if (g_cp_bad < 99) g_cp_bad++; return; }
    if (downer == me && !same_team(downer, victim)) {
        if (g_cp_bad || !g_cp_armed) xlog("clanperk: you downed slot %u - struggle counter %d cleared%s", victim, g_cp_bad, g_cp_armed ? "" : ", help re-armed");
        g_cp_bad = 0; g_cp_armed = 1;
    }
}
static int cp_team_gap(void) {                   // enemy reinforcements - ours (0 when unknown / not in the 0..249 range)
    uint8_t *lo = lobby_obj();
    if (!lo) return 0;
    int al = ((int (*)(void *))VMA(0x18004C120))(lo), en = ((int (*)(void *))VMA(0x18004C150))(lo);
    if (al < 0 || al >= 250 || en < 0 || en >= 250) return 0;
    return en - al;
}
static void cp_give_medkit(const cp_perk_t *p) {
    const uint64_t KIT = 0xa4311670996f650aULL;
    uint64_t have = inv_qty(KIT);
    dc_direct(SID_ADD_QTY, KIT, 1, 0);
    if (inv_qty(KIT) > have) cp_use(p, CP_MEDKIT, "medkit"); else xlog("clanperk: medkit add did not take (carrying %llu)", (unsigned long long)inv_qty(KIT));
}
static void cp_give_parts(const cp_perk_t *p) {
    uint64_t r0 = inv_qty(ING_RAG), a0 = inv_qty(ING_ALCOHOL);
    dc_direct(SID_ADD_QTY, ING_RAG, 4, 0);
    dc_direct(SID_ADD_QTY, ING_ALCOHOL, 4, 0);
    if (inv_qty(ING_RAG) > r0 || inv_qty(ING_ALCOHOL) > a0) cp_use(p, CP_PARTS, "crafting set (rag + alcohol)");
    else xlog("clanperk: crafting set add did not take");
}
// the primary = the first carried gun with an ammo pool that is not a sidearm; fills the pool name, the magazine, the reserve now and the room (cap); returns 0 when none / full
static int cp_clip_plan(const char **an, int *mag, int *have, int *extra) {
    int best = -1;
    *an = NULL;
    for (int i = 0; i < g_spawn_ngun && best < 0; i++) {
        uint64_t g = base_weapon(g_spawn_guns[i]);
        for (size_t k = 0; k < sizeof SPAWN_AMMO / sizeof *SPAWN_AMMO; k++) {
            uint64_t sg = SPAWN_AMMO[k].gun ? SPAWN_AMMO[k].gun : fnv64(SPAWN_AMMO[k].name);
            if (sg != g) continue;
            int side = !strcmp(SPAWN_AMMO[k].ammo, "ammo-pistol") || !strcmp(SPAWN_AMMO[k].ammo, "ammo-revolver");
            if (!side) { best = i; *an = SPAWN_AMMO[k].ammo; }
        }
    }
    if (best < 0) return 0;
    uint64_t gun = base_weapon(g_spawn_guns[best]);
    *mag = 0;
    for (size_t q = 0; q < sizeof WEAPON_STATS / sizeof *WEAPON_STATS; q++) if (fnv64(WEAPON_STATS[q].weapon) == gun && WEAPON_STATS[q].mag[0]) *mag = WEAPON_STATS[q].mag[0];
    *have = (int)inv_qty(fnv64(*an));
    *extra = cp_clip_extra(*mag, *have, reserve_cap_of(gun));
    return *extra > 0;
}
static void cp_give_clip(const cp_perk_t *p, const char *an, int mag, int have, int extra) {
    uint64_t args[2] = {fnv64(an), (uint64_t)(have + extra)}, ret[64] = {0};
    g_settotal_orig(ret, 2, args, 0);
    xlog("clanperk: clip %s reserve %d -> %d (magazine %d)", an, have, (int)inv_qty(fnv64(an)), mag);
    cp_use(p, CP_CLIP, "spare clip");
}
// the spawn (skills_on_spawn, after the spawn routine + keep_restore): if the player struggles (and the clan has a surplus, i.e. a perk), ONE item arrives
static void cp_on_spawn(void) {
    uint64_t now = GetTickCount64();
    if (match_substate() != 6) return;
    if (g_cp_last_spawn_ms && now - g_cp_last_spawn_ms < 3000) { xlog("clanperk: same life (a mid-match loadout respawn) - not counted again"); return; }
    g_cp_last_spawn_ms = now;
    int n = ++g_cp_spawns;
    if (cp_off()) return;
    cp_state_t s;
    cp_get(&s);
    if (!s.n) { xlog("clanperk: spawn %d - no perks from the server (no clan surplus)", n); return; }
    int gap = cp_team_gap(), why = cp_struggling(g_cp_bad, gap, s.streak, n);
    xlog("clanperk: spawn %d, %d perk(s) (uses %d/%d/%d/%d/%d); lost lives in a row %d, reinforcement gap %d, clan loss streak %d -> %s%s", n, s.n, g_cp_used[0], g_cp_used[1], g_cp_used[2],
         g_cp_used[3], g_cp_used[4], g_cp_bad, gap, s.streak, why ? "STRUGGLING" : "not struggling", why && !g_cp_armed ? " (help already sent for this streak)" : "");
    if (!why) return;
    if (!cp_grant_due(g_cp_armed, now, g_cp_grant_ms)) { if (g_cp_armed) xlog("clanperk: help sent %d s ago - not again yet", (int)((now - g_cp_grant_ms) / 1000)); return; }
    unsigned ok = 0;
    const char *an = NULL;
    int mag = 0, have = 0, extra = 0;
    uint64_t kit = inv_qty(0xa4311670996f650aULL);
    if (kit != ~0ULL && kit < 2) ok |= 1u << CP_MEDKIT; else xlog("clanperk: medkit not needed (carrying %llu)", (unsigned long long)kit);
    if (g_settotal_orig && cp_clip_plan(&an, &mag, &have, &extra)) ok |= 1u << CP_CLIP; else xlog("clanperk: clip not needed / no primary with room in its reserve");
    ok |= 1u << CP_PARTS;
    int pick = cp_pick_item(&s, g_cp_used, ok);
    if (pick < 0) { xlog("clanperk: struggling (reason %d) but no perk item applies (caps used or nothing needed)", why); return; }
    g_cp_armed = 0; g_cp_grant_ms = now;
    xlog("clanperk: HELP ARRIVES (reason %d: %s) - perk %d from %s", why, why == CP_WHY_BAD2 ? "2 lives lost in a row" : why == CP_WHY_BEHIND ? "1 life lost, team behind / clan on a loss streak" : "clan lost 3+ matches, first spawn", pick, s.p[pick].name);
    if (pick == CP_MEDKIT) cp_give_medkit(&s.p[pick]);
    else if (pick == CP_PARTS) cp_give_parts(&s.p[pick]);
    else cp_give_clip(&s.p[pick], an, mag, have, extra);
}
// food: Marathon Runner I's sprint recovery for the whole match (sk_sprint_meter); the use is booked the first time the meter empties
static int cp_stamina_on(void) {
    if (match_substate() != 6 || cp_off()) return 0;
    cp_state_t s; cp_get(&s);
    return s.p[CP_STAMINA].cat != 0;
}
static void cp_note_exhausted(void) {
    cp_state_t s; cp_get(&s);
    cp_perk_t *p = &s.p[CP_STAMINA];
    if (p->cat && !cp_off() && g_cp_used[CP_STAMINA] < p->cap) cp_use(p, CP_STAMINA, "sprint recovery");
}
// water: Fortitude I's bleed-out x1.25 for a player without Fortitude (sk_fort_mul): every down it stretches is a use
static float cp_bleed_mul(void) {
    if (match_substate() != 6 || cp_off()) return 1.0f;
    cp_state_t s; cp_get(&s);
    cp_perk_t *p = &s.p[CP_BLEED];
    if (!p->cat || g_cp_used[CP_BLEED] >= p->cap) return 1.0f;
    cp_use(p, CP_BLEED, "bleed-out time x1.25");
    return 1.25f;
}
// the match report (feature_clan): labels 31 / 32 appended at nl, returns the new nl; the counters are cleared once reported
static int cp_report_labels(uint8_t *pl, int nl) {
    int l31, l32;
    cp_pack_uses(g_cp_used, &l31, &l32);
    int lab[2] = {l31, l32};
    for (int k = 0; k < 2; k++) {
        if (lab[k] <= 0 || nl >= 12) continue;      // (rep_pl is 48 bytes: 10 + 3 * 12)
        pl[10 + 3 * nl] = (uint8_t)(31 + k);
        uint16_t cn = (uint16_t)lab[k];
        memcpy(pl + 11 + 3 * nl, &cn, 2);
        nl++;
    }
    if (l31 || l32) xlog("clanperk: reported uses medkit %d clip %d parts %d stamina %d bleed %d", g_cp_used[0], g_cp_used[1], g_cp_used[2], g_cp_used[3], g_cp_used[4]);
    memset(g_cp_used, 0, sizeof g_cp_used);
    return nl;
}
// the gear up screen: "YOUR CLAN SENT: medkit x2 (Tyler), clip x3 (Wendy)" (empty when there are no perks / switched off)
static const char *cp_gearup_line(void) {
    static char out[220];
    out[0] = 0;
    if (cp_off()) return out;
    cp_state_t s; cp_get(&s);
    if (!s.n) return out;
    char sum[170];
    int pl = cp_polish_text();
    cp_summary(sum, sizeof sum, &s, pl);
    snprintf(out, sizeof out, "%s %s", pl ? "TWOJ KLAN WYSLAL:" : "YOUR CLAN SENT:", sum);
    return out;
}
