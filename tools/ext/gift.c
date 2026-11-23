// gift.c - Crafter II / III gifts, as in 2013 Factions (crafter.md, rules/skills.md: booster c8bef697, 8dcd3a70 = 3 / 2 crafts).
//
// Every 3rd (Crafter II) / 2nd (Crafter III) item crafted gives ONE gift. The gift is a REAL engine item `gift` (dc_data_patches.add_gift_item +
// weapon_clone.clone_weapon(brick -> gift), drawn with the brick's actors whose mesh paks carry the SP box: tools/models/gift_box_pak.py; HUD icon = the 2013 box): the stock Factions slot
// *hud2-slot-up-three-factions* of player-weapon-cross.bin names it, so the engine's own weapon cross draws the slot / selection / count and
// the d-pad (or the item keys) selects it; the hold is the throwable hold of the brick. This file only grants / removes the item and does the
// E-to-give: with the gift in the hand, walk up to a teammate and press E ("Give gift" world prompt, taking priority over the First-Aid heal while
// a gift can be given: sk_fat_heal returns while g_gift_block_heal). What the gift holds (health kit / molotov / smoke bomb / nail bomb = every
// craftable of our recipe list except the shiv and the modded melee weapon) is picked when it is crafted and kept here.
//
// Net (skills.c skills_recv hands these to gift_recv):
//   MSG_SK_GIFTSTOCK 0x56 [u8 mask]  to everyone, 1 per 2.5 s and on every change: bit k = this player can take one more of kind k (the item's max
//                                    carried: 3, nail bomb 4, 4 health kits with Fortitude II). The giver reads it: a full teammate gets no prompt.
//   MSG_SK_GIFT      0x53 [u8 kind]  giver -> receiver. The receiver re-checks everything (teammate, up, in reach, room), adds the item, answers
//   MSG_SK_GIFTACK   0x57 [u8 1/0]   receiver -> giver. 1: the giver's gift item is removed and the giver gets 100 parts (2013 NET_STAT_GAVE_GIFT,
//                                    award "Gift", not boosted by Collector / Increased Parts Earnings); 0: the giver keeps it.
// The gift is not throwable (dc_data_patches.make_gift_unthrowable: the health kit's def layout, no throw / projectile / aim-arc sids, own use def with heal 0) and gift_tick swallows aim and
// fire-press / fire / fire-hold (joypad-disable-commands, every frame, keyboard and pad: the engine's own commands) while it is in the hand. Progress toward the next gift is lost when the class has no
// Crafter II / III. The gift is dropped with the life (the spawn routine removes weapons; gift_on_spawn).
// t2r-no-crafter-gift.txt = no gifts at all, t2r-no-gift-anim.txt = no hand-out gesture. Logs "gift:".

#define GIFT_NK 4
static const struct { uint64_t item; const char *name; } GIFT_K[GIFT_NK] = {
    {0xa4311670996f650aULL, "Health Kit"}, {0x2a3164cb4a1c95d9ULL, "Molotov Cocktail"},
    {0xa2aa922866d0479dULL, "Smoke Bomb"}, {0xcf576d288d014eacULL, "Nail Bomb"},
};
static uint64_t gift_sid(void) { static uint64_t s; if (!s) s = fnv64("gift"); return s; }
static int g_gift_kind = -1;                       // what the carried gift holds (GIFT_K index), -1 = none
#define GIFT_QMAX 4
static uint8_t g_gift_q[GIFT_QMAX]; static int g_gift_qn;   // Gifts earned while one is carried wait here (the item max is 1); the next one is handed to the hand when the carried one is given
static uint32_t g_gift_pend_slot = 99; static uint8_t g_gift_pend_kind; static uint64_t g_gift_pend_until;   // a give waiting for the receiver's answer
static volatile LONG g_gift_ack;                   // answer arrived (net thread -> tick): 1 taken, 2 refused
static uint8_t g_gift_room[T2R_MAX_PEERS]; static uint64_t g_gift_room_ms[T2R_MAX_PEERS];   // teammates' room masks (MSG_SK_GIFTSTOCK)
static int g_gift_block_heal;                      // a gift can be given right now: E is the gift, not the First-Aid hold
static uint64_t g_gift_anim_until;                 // hand-out gesture running
static uint64_t g_gift_in_ms[T2R_MAX_PEERS];
static int gift_off(void) { static uint64_t at; static int val = -1; return feel_flag("t2r-no-crafter-gift.txt", &at, &val, 180); }
// the engine's own max carried (player-inventory.bin +0x88: kit 3, molotov 3, smoke bomb 3, nail bomb 4); Fortitude II: 4 health kits (2013)
static int gift_cap(int k) { return k == 0 ? (skl(SK_FORT) >= 2 ? 4 : 3) : k == 3 ? 4 : 3; }
static uint8_t gift_room_mask(void) {
    uint8_t m = 0;
    for (int k = 0; k < GIFT_NK; k++) if (inv_qty(GIFT_K[k].item) < (uint64_t)gift_cap(k)) m |= (uint8_t)(1 << k);
    return m;
}
static int gift_peer_has_room(uint32_t slot, int k) {
    if (slot >= T2R_MAX_PEERS || !g_gift_room_ms[slot] || GetTickCount64() - g_gift_room_ms[slot] > 8000) return 1;     // unknown: try (the receiver re-checks)
    return (g_gift_room[slot] >> k) & 1;
}
// the real item: given like the kept stock (give-item, then a bare add / set-total, as the Covert shiv is)
static void gift_item_set(int n) {
    uint64_t g = gift_sid();
    if (n > 0 && !inv_qty(g)) {
        if (g_give_orig) { uint64_t ret[64] = {0}, give[4] = {g, 0, 0, 1}; g_give_orig(ret, 4, give, 0); }
        if (!inv_qty(g)) dc_direct(SID_ADD_QTY, g, 1, 0);
        if (!inv_qty(g) && g_settotal_orig) { uint64_t ret[64] = {0}, set[2] = {g, 1}; g_settotal_orig(ret, 2, set, 0); }
    } else if (n <= 0 && inv_qty(g)) {
        // (the gift box item did not subtract from the inventory when given): set-total-ammo does nothing on a
        // non-ammo item (same as the medkit cap); player-inventory-consume-item (shiv_spend) removes it, set-total stays as a fallback.
        for (int i = (int)inv_qty(g); i > 0; i--) dc_direct(fnv64("player-inventory-consume-item"), g, 1, 0);
        if (inv_qty(g) && g_settotal_orig) { uint64_t ret[64] = {0}, set[2] = {g, 0}; g_settotal_orig(ret, 2, set, 0); }
        xlog("gift: item removed -> %llu left", (unsigned long long)inv_qty(g));
    }
}
static int gift_have(void) { return g_gift_kind >= 0 && inv_qty(gift_sid()) > 0; }
// The radial shows the engine item's COUNT like the other items, so the item quantity mirrors
// the carried gift + the ones waiting behind it. Needs the item's carry max raised in the data (dc_data_patches.add_gift_item, GIFT_MAX); with the old
// max 1 the engine keeps showing one and the queue still works.
static void gift_count_sync(void) {
    uint64_t g = gift_sid();
    int want = (g_gift_kind >= 0 ? 1 : 0) + g_gift_qn;
    if (want <= 0 || !inv_qty(g)) return;
    for (int i = (int)inv_qty(g); i < want; i++) { uint64_t before = inv_qty(g); dc_direct(SID_ADD_QTY, g, 1, 0); if (inv_qty(g) <= before) break; }
}
// ---- crafting side (skills.c sk_crafter_gift): returns 0 when a gift is already carried (the count waits)
static int gift_grant(int lv) {
    if (gift_have()) {      // 2013: every 3rd / 2nd craft gives a giftbox - the count does not stall while one is carried
        if (g_gift_qn >= GIFT_QMAX) return 0;
        g_gift_q[g_gift_qn++] = (uint8_t)(t2r_rand() % GIFT_NK);
        xlog("gift: Crafter %d: another gift crafted (%s) - %d waiting behind the carried one", lv, GIFT_K[g_gift_q[g_gift_qn - 1]].name, g_gift_qn);
        gift_count_sync();
        msg_hook("Crafter: You crafted another gift! It is ready after you give this one.", 4.0f, 0, 0);
        return 1;
    }
    g_gift_kind = (int)(t2r_rand() % GIFT_NK);
    gift_item_set(1);
    xlog("gift: Crafter %d: gift crafted (%s) - item gift now %llu%s", lv, GIFT_K[g_gift_kind].name, (unsigned long long)inv_qty(gift_sid()),
         inv_qty(gift_sid()) ? "" : " (UNVERIFIED: the engine did not take the item)");
    if (!inv_qty(gift_sid())) { g_gift_kind = -1; return 0; }
    msg_hook("Crafter: You crafted a gift! Give it to a teammate for parts.", 4.0f, 0, 0);
    return 1;
}
static void gift_clear(const char *why) {
    if (g_gift_kind >= 0 || inv_qty(gift_sid())) xlog("gift: gift cleared (%s)", why);
    g_gift_kind = -1; g_gift_pend_slot = 99; g_gift_anim_until = 0; g_gift_qn = 0;
    gift_item_set(0);
}
static void gift_on_spawn(void) {    // The spawn routine strips the item; the gifts (kind + queue) are kept and gift_tick re-grants the item once the life is up
    if (g_gift_kind >= 0) xlog("gift: new life - %d gift(s) kept (re-granted after the spawn)", 1 + g_gift_qn);
    g_gift_pend_slot = 99; g_gift_anim_until = 0;
}   /* The Crafter II / III count toward a gift survives deaths (it reset every life); the match end still resets it (skills.c) */
// ---- receiving
static int gift_recv(uint32_t slot, uint32_t type, const uint8_t *buf, uint64_t len) {
    if (type == MSG_SK_GIFTSTOCK) {
        if (slot < T2R_MAX_PEERS && buf && len >= 1) { g_gift_room[slot] = buf[0] & 0xF; g_gift_room_ms[slot] = GetTickCount64(); }
        return 1;
    }
    if (type == MSG_SK_GIFTACK) {
        if (slot == g_gift_pend_slot && buf && len >= 1) InterlockedExchange(&g_gift_ack, buf[0] ? 1 : 2);
        return 1;
    }
    if (type != MSG_SK_GIFT) return 0;
    uint8_t ans = 0;
    int k = buf && len >= 1 ? buf[0] : -1;
    uint64_t gn = GetTickCount64();
    float mb[16], pb[16];
    const float *me = player_locator(mb), *pp = slot < T2R_MAX_PEERS ? sk_peer_pos(slot, pb) : NULL;
    uint8_t *peer = sk_peer_ptr(slot);
    // peer msg trust: a living teammate (with Crafter II+ when its skills are known), in reach, not more often than 1 per second, a real kind
    int ok = k >= 0 && k < GIFT_NK && slot < T2R_MAX_PEERS && peer && peer[4] && !peer[5] && is_teammate(slot) && !g_peer_downed[slot] &&
             (!g_peer_sk_frame[slot] || sk_peer(slot, SK_CRAFTER) >= 2) && (!g_gift_in_ms[slot] || gn - g_gift_in_ms[slot] >= 1000) &&
             match_substate() == 6 && !g_downed && sk_hp() > 0;
    if (ok && me && pp) { float dx = pp[0] - me[0], dz = pp[2] - me[2], dy = pp[1] - me[1]; ok = dx * dx + dz * dz < 5.0f * 5.0f && dy > -3.0f && dy < 3.0f; }
    if (!ok && buf && len >= 1 && pt_deny(PTK_sk_gift, slot)) {
        static uint64_t lg; if (pt_log_due(&lg, gn)) xlog("gift: MSG_SK_GIFT from slot %u dropped (not a teammate / downed / no Crafter II / out of reach / too soon)", slot);
    }
    if (ok) {
        g_gift_in_ms[slot] = gn;
        if (inv_qty(GIFT_K[k].item) < (uint64_t)gift_cap(k)) {
            dc_direct(SID_ADD_QTY, GIFT_K[k].item, 1, 0);
            char m[120]; snprintf(m, sizeof m, "Gift: %s gave you a %s", hc_name(slot), GIFT_K[k].name);
            msg_hook(m, 3.0f, 0, 0);
            xlog("gift: %s from slot %u (now %llu)", GIFT_K[k].name, slot, (unsigned long long)inv_qty(GIFT_K[k].item));
            ans = 1;
        } else xlog("gift: %s from slot %u refused - already at the cap %d", GIFT_K[k].name, slot, gift_cap(k));
    }
    if (g_send_tramp && slot < T2R_MAX_PEERS) g_send_tramp(MSG_SK_GIFTACK, &ans, 1, slot);
    return 1;
}
// ---- giving
static void gift_give(uint32_t slot, uint64_t body) {
    uint8_t k = (uint8_t)g_gift_kind;
    if (!g_send_tramp) return;
    g_send_tramp(MSG_SK_GIFT, &k, 1, slot);
    g_gift_pend_slot = slot; g_gift_pend_kind = k; g_gift_pend_until = GetTickCount64() + 2000;
    InterlockedExchange(&g_gift_ack, 0);
    static int an = -1; if (an < 0) { FILE *f = exe_side_open("t2r-no-gift-anim.txt", "r"); an = f == NULL; if (f) fclose(f); }
    if (an && body) { ha_begin(slot); if (g_ha.on) g_gift_anim_until = GetTickCount64() + 900; }       // the revive / heal hand-out gesture
    xlog("gift: giving %s to slot %u", GIFT_K[k].name, slot);
}
static void gift_tick(void) {
    static uint64_t prev_qty; (void)prev_qty;
    g_gift_block_heal = 0;
    uint64_t now = GetTickCount64();
    if (match_substate() != 6) { gift_clear("not in a match"); g_gift_ack = 0; return; }
    int lv = skl(SK_CRAFTER);
    if (lv < 2 && g_sk_craft_n) { xlog("gift: no Crafter II / III in this class - progress toward a gift (%d) lost", g_sk_craft_n); g_sk_craft_n = 0; }
    if (gift_off()) { if (g_gift_kind >= 0) gift_clear("t2r-no-crafter-gift.txt"); return; }
    {   // our room mask to everyone: on a change, else every 2.5 s
        static uint8_t last = 0xff; static uint64_t sent;
        uint8_t m = gift_room_mask();
        if (g_send_tramp && (m != last || now - sent > 2500)) { g_send_tramp(MSG_SK_GIFTSTOCK, &m, 1, 0xff); last = m; sent = now; }
    }
    uint64_t qty = inv_qty(gift_sid());
    // the receiver's answer to our give
    LONG ack = InterlockedExchange(&g_gift_ack, 0);
    if (g_gift_pend_slot != 99 && ack) {
        uint32_t s = g_gift_pend_slot; int k = g_gift_pend_kind;
        g_gift_pend_slot = 99;
        if (ack == 1) {
            char m[120]; snprintf(m, sizeof m, "Gift: %s received a %s", hc_name(s), GIFT_K[k].name);
            msg_hook(m, 3.0f, 0, 0);
            g_gift_kind = -1; gift_item_set(0); qty = 0;
            if (g_gift_qn > 0) {      // the next waiting gift takes the slot
                g_gift_kind = g_gift_q[0]; memmove(g_gift_q, g_gift_q + 1, (size_t)(--g_gift_qn));
                gift_item_set(1); gift_count_sync(); qty = inv_qty(gift_sid());
                xlog("gift: next waiting gift (%s) in the slot, %d still waiting", GIFT_K[g_gift_kind].name, g_gift_qn);
                msg_hook("Crafter: Your next gift is ready.", 3.0f, 0, 0);
            }
            g_sk_no_collector = 1;                      // 2013: Collector / Increased Parts Earnings do not count gift parts
            award(100, sk_me(), "Gift");
            g_sk_no_collector = 0;
            xlog("gift: slot %u took the %s - +100 parts", s, GIFT_K[k].name);
        } else {
            char m[120]; snprintf(m, sizeof m, "Gift: %s can't carry any more %ss", hc_name(s), GIFT_K[k].name);
            msg_hook(m, 3.0f, 0, 0);
            g_gift_room[s] &= (uint8_t)~(1 << k); g_gift_room_ms[s] = now;
            xlog("gift: slot %u refused the %s (full) - the gift stays with us", s, GIFT_K[k].name);
        }
    } else if (g_gift_pend_slot != 99 && now > g_gift_pend_until) {
        xlog("gift: no answer from slot %u - the gift stays with us", g_gift_pend_slot);
        g_gift_pend_slot = 99;
    }
    prev_qty = qty;
    // the hand-out gesture: stopped here (sk_fat_heal leaves it alone while g_gift_anim_until runs)
    if (g_gift_anim_until) {
        if (!g_ha.on) g_gift_anim_until = 0;
        else if (now >= g_gift_anim_until) { ha_stop("gift handed over"); g_gift_anim_until = 0; }
        else { uint8_t *pe = sk_peer_ptr(g_ha.tgt); ha_update(g_ha.tgt, pe ? *(uint64_t *)(pe + 0x60) : 0); }
    }
    int alive = !g_downed && !g_down_dying && sk_hp() > 0 && local_hp() > 0.0f;
    if (g_gift_kind >= 0 && !qty && alive && !g_in_spawn && g_gift_pend_slot == 99) {     // the item was stripped (spawn / death): grant it again, at most once a second
        static uint64_t regrant;
        if (now - regrant > 1000) {
            regrant = now; gift_item_set(1); gift_count_sync(); qty = inv_qty(gift_sid());
            xlog("gift: item re-granted after the new life (%s, %d waiting) -> %llu", GIFT_K[g_gift_kind].name, g_gift_qn, (unsigned long long)qty);
        }
    }
    if (g_gift_kind < 0 || !qty || !alive || hud_hidden() || g_gift_pend_slot != 99 || psync_role() == 1 || psync_role() == 2) return;
    if (base_weapon(current_weapon()) != gift_sid()) return;      // E gives only with the gift in the hand (selected on the weapon cross)
    {   // no aim / throw / fire with the gift in the hand (frame-scoped natives, re-issued every frame)
        static const char *const CMD[4] = {"aim", "fire-press", "fire", "fire-hold"};     // (the data names no use command: the kit's use is engine code on the fire input)
        for (int i = 0; i < 4; i++) { uint64_t c = fnv64(CMD[i]); dc_call(fnv64("joypad-disable-commands"), 1, &c); }
    }
    // the teammate in front of us: the nearest standing one in heal reach with a clear line
    float mb[16], pb[16];
    const float *me = player_locator(mb);
    uint32_t nbr = 99; float bd = 1e30f;
    for (uint32_t slot = 0; slot < T2R_MAX_PEERS && me; slot++) {
        uint8_t *peer = sk_peer_ptr(slot);
        if (slot == sk_me() || !peer || !peer[4] || peer[5] || !is_teammate(slot) || g_peer_downed[slot]) continue;
        const float *p = sk_peer_pos(slot, pb);
        if (!p) continue;
        float dx = p[0] - me[0], dy = p[1] - me[1], dz = p[2] - me[2], d = dx * dx + dz * dz;
        if (d >= SKH_HOLD_XZ * SKH_HOLD_XZ || dy <= -SKH_HOLD_Y || dy >= SKH_HOLD_Y || d >= bd) continue;
        uint64_t ph = *(uint64_t *)(peer + 0x60);
        if (!los_gate(ph, me, p)) continue;
        bd = d; nbr = slot;
    }
    if (nbr == 99) return;
    uint8_t *nbp = sk_peer_ptr(nbr);
    uint64_t nh = nbp ? *(uint64_t *)(nbp + 0x60) : 0;
    if (!nh) return;
    int room = gift_peer_has_room(nbr, g_gift_kind);
    interact_down();
    if (room) {
        g_gift_block_heal = 1;                               // E gives the gift; no First-Aid hold under it
        world_prompt(nh, "Give gift", 0.0f);
        if (interact_pressed()) gift_give(nbr, nh);
    } else {
        world_prompt_grey(nh, "Can't carry more", 0);
        if (interact_pressed()) {
            char m[120]; snprintf(m, sizeof m, "Gift: %s can't carry any more %ss", hc_name(nbr), GIFT_K[g_gift_kind].name);
            msg_hook(m, 2.5f, 0, 0);
        }
    }
}
