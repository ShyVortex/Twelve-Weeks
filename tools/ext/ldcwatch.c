// LevelDefCollection capacity (Plaza crash). exe+0x1c31330 LevelDefCollection::AllocateLevelDef asserts '!m_table.IsFull()' ("Out of space in
// LevelDefCollection! (adding def '%s')", int3 at exe+0x1c31515) when its fixed hash table is full. The collection is the global at exe+0x360e590 (exe+0x1ab439e
// loads it for the call); its table sits at +0x5dd8: entries (0x18 bytes: hash, key, def; hash == key, empty = 0xfffffffffffffffe) at +0, an occupancy bitmap
// at +8, capacity at +0x28, count at +0x2c. Robin-hood probing from key % capacity (find exe+0x1c31a70, insert exe+0x1c32970).
// The stock capacity is 10912 (immediate 0x2aa0 at exe+0x2b0139, game init, long before the ext loads on the first match-loop frame) and stock boot already
// registers 10854 defs (every package name: SP sequences, character parts, levels). A Part I map's converted actor paks are new names added at load:
// Plaza's 71 overflowed the 58 free slots (A/B, both clients at exe+0x1c31515 on the load into Plaza).
// Fix: once, on the first frames after boot (count stable, no load running), the table is rebuilt at 14336 (new entry array and bitmap, header as the
// engine's table init lays it out) and every saved entry re-inserted with the engine's own insert, so probing order and the bitmap are exactly the
// engine's. The old arrays are left allocated (264 KB). t2r-no-ldc-grow.txt = off. t2r-ldc-names.txt = write every def name at each
// match load (diagnosis).
#define LDC_NEW_CAP 14336u
static int ldc_name_of(uint8_t *def, char *out, int cap) {
    // the def's name: the first qword in the first 0x80 bytes that points to a printable, NUL-terminated string of 3+ chars
    if (!def || IsBadReadPtr(def, 0x80)) return 0;
    for (int i = 0; i < 0x80; i += 8) {
        const char *s = *(const char **)(def + i);
        if ((uintptr_t)s < 0x10000 || IsBadReadPtr(s, 4)) continue;
        int n = 0;
        while (n < cap - 1 && !IsBadReadPtr(s + n, 1) && s[n] >= 0x20 && s[n] < 0x7f) n++;
        if (n >= 3 && !IsBadReadPtr(s + n, 1) && s[n] == 0) { memcpy(out, s, n); out[n] = 0; return 1; }
    }
    return 0;
}
static void ldc_dump(uint8_t *g, uint32_t cap, uint32_t cnt, const char *why) {
    uint8_t *tab = *(uint8_t **)(g + 0x5dd8);
    if (!tab || IsBadReadPtr(tab, (size_t)cap * 0x18)) { xlog("ldc: table %p not readable", (void *)tab); return; }
    char fn[64];
    snprintf(fn, sizeof fn, "t2r-ldc-names-%u.txt", cnt);
    FILE *f = fopen(fn, "w");
    if (!f) return;
    uint32_t used = 0;
    for (uint32_t i = 0; i < cap; i++) {
        uint64_t *e = (uint64_t *)(tab + (size_t)i * 0x18);
        if (e[0] == 0xfffffffffffffffeull) continue;
        used++;
        char nm[96] = "?";
        ldc_name_of((uint8_t *)e[2], nm, sizeof nm);
        fprintf(f, "%016llx %016llx %s\n", (unsigned long long)e[1], (unsigned long long)e[2], nm);
    }
    fclose(f);
    xlog("ldc: %s - %u of %u entries used -> %s", why, used, cap, fn);
}
static void ldc_grow(uint8_t *exe, uint8_t *g) {
    uint8_t *t = g + 0x5dd8;
    uint32_t cap = *(uint32_t *)(t + 0x28), cnt = *(uint32_t *)(t + 0x2c);
    uint8_t *ent = *(uint8_t **)t;
    static const uint8_t find_head[8] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x6c}, ins_head[6] = {0x4c, 0x8b, 0xdc, 0x49, 0x89, 0x5b},
                         init_head[5] = {0x48, 0x89, 0x5c, 0x24, 0x18};
    if (memcmp(exe + 0x1c31a70, find_head, 8) || memcmp(exe + 0x1c32970, ins_head, 6) || memcmp(exe + 0x1c31f00, init_head, 5)) {
        xlog("ldc: exe bytes differ - def table left at %u", cap); return;
    }
    if (cap >= LDC_NEW_CAP || !ent || IsBadReadPtr(ent, (size_t)cap * 0x18)) { xlog("ldc: table capacity %u (entries %p) - not grown", cap, (void *)ent); return; }
    uint64_t *save = (uint64_t *)malloc((size_t)cnt * 16 + 16);
    if (!save) return;
    uint32_t n = 0;
    for (uint32_t i = 0; i < cap && n < cnt; i++) {
        uint64_t *e = (uint64_t *)(ent + (size_t)i * 0x18);
        if (e[0] == 0xfffffffffffffffeull) continue;
        save[n * 2] = e[1]; save[n * 2 + 1] = e[2]; n++;
    }
    if (n != cnt) { xlog("ldc: %u used slots for count %u - not grown", n, cnt); free(save); return; }
    typedef void *(*fn_ins)(void *tab, void *out, uint64_t *key, uint64_t *val);
    typedef void *(*fn_find)(void *tab, void *out, uint64_t *key);
    // New arrays from our own memory: the engine's table init (exe+0x1c31f00) allocates through the current allocator scope, which only the collection's own
    // Init pushes (calling it from the tick faulted at exe+0x122fd36, A/B). The header is filled exactly as that init does (exe+0x1c32044..0x1c32083):
    // +0 entries (all keys empty), +8 bitmap (zero), +0x10 capacity, +0x18 capacity rounded up to 64, +0x20 bitmap words, +0x28 capacity, +0x2c count 0.
    // The engine never frees or re-inits this table after boot (exe+0x1c320a0 has one caller, game init), so the arrays live for the process.
    uint32_t words = (LDC_NEW_CAP + 63) / 64;
    uint8_t *ne = (uint8_t *)VirtualAlloc(NULL, (size_t)LDC_NEW_CAP * 0x18 + (size_t)words * 8, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!ne) { xlog("ldc: no memory for a %u-entry table", LDC_NEW_CAP); free(save); return; }
    for (uint32_t i = 0; i < LDC_NEW_CAP; i++) *(uint64_t *)(ne + (size_t)i * 0x18) = 0xfffffffffffffffeull;
    uint8_t old[0x30];
    memcpy(old, t, 0x30);
    *(uint8_t **)t = ne;
    *(uint8_t **)(t + 8) = ne + (size_t)LDC_NEW_CAP * 0x18;      // VirtualAlloc memory is zero
    *(uint64_t *)(t + 0x10) = LDC_NEW_CAP;
    *(uint64_t *)(t + 0x18) = ((uint64_t)LDC_NEW_CAP + 63) & ~63ull;
    *(uint32_t *)(t + 0x20) = words;
    *(uint32_t *)(t + 0x28) = LDC_NEW_CAP;
    *(uint32_t *)(t + 0x2c) = 0;
    uint8_t it[0x80];
    for (uint32_t i = 0; i < n; i++) ((fn_ins)(exe + 0x1c32970))(t, it, &save[i * 2], &save[i * 2 + 1]);
    uint32_t cnt2 = *(uint32_t *)(t + 0x2c), miss = 0;
    uint8_t *ent2 = *(uint8_t **)t;
    for (uint32_t i = 0; i < n; i++) {         // every key must be found again, holding the same def (find's iterator: slot index at +0x2c, capacity = not found)
        uint8_t fi[0x80];
        ((fn_find)(exe + 0x1c31a70))(t, fi, &save[i * 2]);
        uint32_t slot = *(uint32_t *)(fi + 0x2c);
        if (slot >= LDC_NEW_CAP || *(uint64_t *)(ent2 + (size_t)slot * 0x18 + 0x10) != save[i * 2 + 1]) miss++;
    }
    if (cnt2 != cnt || miss) {
        memcpy(t, old, 0x30);                  // something in the rebuild is off: back to the engine's own (still intact) table
        xlog("ldc: rebuild check failed (count %u -> %u, %u defs not found again) - old table kept", cnt, cnt2, miss); free(save); VirtualFree(ne, 0, MEM_RELEASE); return;
    }
    free(save);
    xlog("ldc: LevelDefCollection table grown %u -> %u (%u defs re-inserted, all found again)", cap, LDC_NEW_CAP, cnt2);
}
static void ldc_tick(void) {
    static uint32_t last, frames;
    static int named_file = -1, last_state = -1;
    if (!g_winmm) return;                      // called above t2r_tick's init block; match_substate() reads winmm memory (test_tick_top_guard)
    if (g_frame < 30) return;
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    uint8_t *g = *(uint8_t **)(exe + 0x360e590);
    if (!g || IsBadReadPtr(g + 0x5dd8, 0x30)) return;
    uint32_t cap = *(uint32_t *)(g + 0x5e00), cnt = *(uint32_t *)(g + 0x5e04);
    if (!cap) return;
    if (named_file < 0) {
        FILE *f = fopen("t2r-ldc-names.txt", "r"); named_file = f != NULL; if (f) fclose(f);
        f = fopen("t2r-no-ldc-grow.txt", "r"); int grow = f == NULL; if (f) fclose(f);
        xlog("ldc: LevelDefCollection %p capacity %u count %u at frame %llu%s", (void *)g, cap, cnt, (unsigned long long)g_frame, grow ? "" : " (t2r-no-ldc-grow.txt: not grown)");
        if (grow) ldc_grow(exe, g);
        cap = *(uint32_t *)(g + 0x5e00); last = cnt;
    }
    frames++;
    if (cnt + 64 <= last || cnt >= last + 64 || (cnt != last && (frames & 255) == 0)) {
        static int nl;
        if (LOGCAP(nl, 40)) xlog("ldc: frame %llu def count %u of %u (%+d)", (unsigned long long)g_frame, cnt, cap, (int)cnt - (int)last);
        last = cnt;
    }
    int st = (int)match_substate();
    if (named_file && st != last_state && st == 3) ldc_dump(g, cap, cnt, "match load");
    last_state = st;
}
