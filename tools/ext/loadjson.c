// loadjson.c - the launcher's GEAR UP <-> the game's custom loadouts, by NAME (t2r-ext include, after skills.c).
//
// Two files next to tlou-ii.exe (contract: release/launcher/API.md "Loadout files"):
//   t2r-loadout.json           written by the game: the 6 custom loadouts + active pick, weapon ids ("rifle-mpx5", "pistol-beretta" +
//                              "supp":1 for the suppressed row) and skill keys ("SK_REVIVER" + level). Rewritten whenever it changes (and once
//                              at start), atomically (tmp + rename). Also records "launcher_rev": the launcher file rev applied last.
//   t2r-loadout-launcher.json  written by the launcher (same shape, rev = unix ms). When its rev is newer than "launcher_rev" the game applies
//                              it in a menu (not in a match, not on the GEAR UP pages, no pending mid-match pick): names -> rows of the
//                              live tables, unknown ids keep that slot's current value, a loadout over 13 LP keeps its old value, then
//                              the same path as an in-game save (g_lo / g_sk4 -> t2r-loadout.txt + t2r-skills.txt, lobby object -> the
//                              server PROFILE as usual), then t2r-loadout.json is rewritten so both agree.
// The row indexes (t2r-loadout.txt) are never exposed: they depend on tables built at run time.

#define LJ_K(x) [x] = #x
static const char *const LJ_SK[SK_COUNT] = {
    LJ_K(SK_ZOOM), LJ_K(SK_EXPLO), LJ_K(SK_REVIVER), LJ_K(SK_BRAWLER), LJ_K(SK_COVERT), LJ_K(SK_EARS), LJ_K(SK_STRAT), LJ_K(SK_HAWK), LJ_K(SK_CRAFTER),
    LJ_K(SK_FAT), LJ_K(SK_SHARP), LJ_K(SK_MARATHON), LJ_K(SK_COLLECTOR), LJ_K(SK_EXEC), LJ_K(SK_DMGMARK), LJ_K(SK_GUNSLINGER), LJ_K(SK_BOMB),
    LJ_K(SK_SCAV), LJ_K(SK_AWARE), LJ_K(SK_FORT), LJ_K(SK_AGILITY), LJ_K(SK_LONEWOLF), LJ_K(SK_SECOND), LJ_K(SK_JACK), LJ_K(SK_LUCKY), LJ_K(SK_LETHAL),
    LJ_K(SK_RIPOSTE), LJ_K(SK_GRIP), LJ_K(SK_BLADE), LJ_K(SK_HEAVY), LJ_K(SK_STEADY), LJ_K(SK_FOOTWORK),
#if T2R_BODYSHIELD
    LJ_K(SK_BODYSHIELD),
#endif
};

// ---- a tiny JSON reader (objects, arrays, strings, numbers, true / false / null), in place on a buffer
typedef struct lj_n { char t; double num; const char *s, *key; struct lj_n *kid, *next; } lj_n;   // t: o a s n b z(null)
static struct { char *p; lj_n pool[640]; int n, err; } lj;
static void lj_ws(void) { while (*lj.p == ' ' || *lj.p == '\t' || *lj.p == '\r' || *lj.p == '\n') lj.p++; }
static lj_n *lj_new(char t) {
    static lj_n dummy;
    if (lj.n >= (int)(sizeof lj.pool / sizeof *lj.pool)) { lj.err = 1; memset(&dummy, 0, sizeof dummy); dummy.t = 'z'; return &dummy; }
    lj_n *n = &lj.pool[lj.n++];
    memset(n, 0, sizeof *n);
    n->t = t;
    return n;
}
static char *lj_str(void) {
    char *w, *s;
    if (*lj.p != '"') { lj.err = 1; return (char *)""; }
    lj.p++;
    s = w = lj.p;
    while (*lj.p && *lj.p != '"') {
        if (*lj.p == '\\' && lj.p[1]) {
            lj.p++;
            switch (*lj.p) {
            case 'n': *w++ = '\n'; break;
            case 't': *w++ = '\t'; break;
            case 'r': *w++ = '\r'; break;
            case 'u': *w++ = '?'; for (int i = 0; i < 4 && lj.p[1] && lj.p[1] != '"'; i++) lj.p++; break;
            default: *w++ = *lj.p; break;
            }
            lj.p++;
        } else *w++ = *lj.p++;
    }
    if (*lj.p != '"') { lj.err = 1; *w = 0; return s; }
    *w = 0;
    lj.p++;
    return s;
}
static lj_n *lj_val(int depth) {
    lj_ws();
    if (depth > 8 || lj.err) { lj.err = 1; return lj_new('z'); }
    if (*lj.p == '{' || *lj.p == '[') {
        int obj = *lj.p == '{';
        char close = obj ? '}' : ']';
        lj_n *o = lj_new(obj ? 'o' : 'a'), *last = NULL;
        lj.p++;
        lj_ws();
        if (*lj.p == close) { lj.p++; return o; }
        for (;;) {
            const char *key = NULL;
            lj_ws();
            if (obj) { key = lj_str(); lj_ws(); if (*lj.p != ':') { lj.err = 1; break; } lj.p++; }
            lj_n *v = lj_val(depth + 1);
            v->key = key;
            if (last) last->next = v; else o->kid = v;
            last = v;
            lj_ws();
            if (lj.err) break;
            if (*lj.p == ',') { lj.p++; continue; }
            if (*lj.p == close) { lj.p++; break; }
            lj.err = 1;
            break;
        }
        return o;
    }
    if (*lj.p == '"') { lj_n *n = lj_new('s'); n->s = lj_str(); return n; }
    if (!strncmp(lj.p, "true", 4)) { lj.p += 4; lj_n *n = lj_new('b'); n->num = 1; return n; }
    if (!strncmp(lj.p, "false", 5)) { lj.p += 5; return lj_new('b'); }
    if (!strncmp(lj.p, "null", 4)) { lj.p += 4; return lj_new('z'); }
    char *e;
    double d = strtod(lj.p, &e);
    if (e == lj.p) { lj.err = 1; return lj_new('z'); }
    lj.p = e;
    lj_n *n = lj_new('n');
    n->num = d;
    return n;
}
static lj_n *lj_parse(char *buf) {
    lj.p = buf; lj.n = 0; lj.err = 0;
    lj_n *r = lj_val(0);
    return lj.err || r->t != 'o' ? NULL : r;
}
static lj_n *lj_get(const lj_n *o, const char *key) {
    if (!o || o->t != 'o') return NULL;
    for (lj_n *k = o->kid; k; k = k->next) if (k->key && !strcmp(k->key, key)) return k;
    return NULL;
}
static lj_n *lj_idx(const lj_n *a, int i) {
    if (!a || a->t != 'a') return NULL;
    lj_n *k = a->kid;
    while (k && i-- > 0) k = k->next;
    return k;
}

// ---- paths, files
static void lj_path(char *p, size_t n, const char *name) {
    snprintf(p, n, "%s", g_loadout_path);
    char *s = strrchr(p, '\\');
    if (s) snprintf(s + 1, n - (size_t)(s + 1 - p), "%s", name);
}
static int lj_read(const char *path, char *buf, size_t cap) {      // whole file (<= cap-1 bytes) -> buf, NUL-terminated; -1 on failure
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    size_t n = fread(buf, 1, cap - 1, f);
    int big = fgetc(f) != EOF;
    fclose(f);
    if (big) return -1;
    buf[n] = 0;
    return (int)n;
}
static long long lj_now_ms(void) {
    FILETIME ft; ULARGE_INTEGER u;
    GetSystemTimeAsFileTime(&ft);
    u.LowPart = ft.dwLowDateTime; u.HighPart = ft.dwHighDateTime;
    return (long long)(u.QuadPart / 10000ULL) - 11644473600000LL;
}

// ---- names <-> rows
static const char *lj_row_id(int slot, uint32_t r) {              // the id string of a row of the live tables (NULL: none / out of range)
    const uint32_t *cnt = (const uint32_t *)VMA(0x1800A0DA4);
    if (slot < 0 || slot > 2 || r == 0xffffffffu || r >= cnt[slot]) return NULL;
    const uint8_t *row = slot == 2 ? lo_purch_tab() + r * 0x40
                       : slot == 0 && !g_large_tab ? (const uint8_t *)VMA(0x1800A0DB0) + r * 0x38 : weapon_row(slot, r);
    const char *id = *(const char **)(row + 0x10);
    if (!id) return NULL;
    for (const char *c = id; *c; c++) if (*c == '"' || *c == '\\' || (uint8_t)*c < 0x20) return NULL;
    return id;
}
static int lj_wsel(char *b, size_t n, int slot, uint32_t r) {
    const char *id = lj_row_id(slot, r);
    if (!id) return snprintf(b, n, "null");
    size_t L = strlen(id);
    int supp = L > 5 && !strcmp(id + L - 5, "-supp");
    return snprintf(b, n, "{\"id\":\"%.*s\",\"supp\":%d}", (int)(supp ? L - 5 : L), id, supp);
}
static int lj_ssel(char *b, size_t n, uint64_t v) {
    v = sk_norm(v);
    int id = sk_id(v), lv = sk_lv(v);
    if (!id || !lv || !LJ_SK[id]) return snprintf(b, n, "null");
    return snprintf(b, n, "{\"id\":\"%s\",\"lv\":%d}", LJ_SK[id], lv);
}
// the part of the file that depends on the loadouts only (compared to skip rewrites)
// (b is a pointer here: SNLEFT(b, o) would be sizeof(char *) - o = 8 - o, i.e. every append after the first 8 bytes wrote nothing and the file ended after "custom":[ )
#define LJ_LEFT(o) ((size_t)(o) < n ? n - (size_t)(o) : (size_t)0)
static int lj_body(char *b, size_t n) {
    lo_nm_load();
    int o = snprintf(b, n, "\"active\":{\"kind\":\"%s\",\"i\":%d},\"custom\":[", lo_slot(g_lo_active) >= 0 ? "custom" : "class", lo_slot(g_lo_active) >= 0 ? lo_slot(g_lo_active) : lo_cls(g_lo_active));
    for (int i = 0; i < g_lo_n && o < (int)n; i++) {     // by custom slot: the CREATE LOADOUT ones follow the first six (the array is g_lo_n long)
        const loadout_t *l = &g_lo[i];
        uint64_t s4 = *sk4_slot(l);
        o += snprintf(b + o, LJ_LEFT(o), "%s{\"small\":", i ? "," : "");
        o += lj_wsel(b + o, LJ_LEFT(o), 1, l->w[1]);
        o += snprintf(b + o, LJ_LEFT(o), ",\"large\":");
        o += lj_wsel(b + o, LJ_LEFT(o), 0, l->w[0]);
        o += snprintf(b + o, LJ_LEFT(o), ",\"purch\":");
        o += lj_wsel(b + o, LJ_LEFT(o), 2, l->w[2]);
        o += snprintf(b + o, LJ_LEFT(o), ",\"skills\":[");
        for (int j = 0; j < 4 && o < (int)n; j++) {
            if (j) o += snprintf(b + o, LJ_LEFT(o), ",");
            o += lj_ssel(b + o, LJ_LEFT(o), j < 3 ? l->k[j] : s4);
        }
        // the name (t2r-ext.c lo_nm_*): lo_nm_clean keeps no quote, backslash or control byte, so it goes in as it is ("" = the default label)
        o += snprintf(b + o, LJ_LEFT(o), "],\"lp\":%d,\"name\":\"%s\"}", lo_cost(l), g_lo_nm[i]);
    }
    o += snprintf(b + o, LJ_LEFT(o), "]");
    return o;
}
#undef LJ_LEFT

static long long g_lj_applied = -1;     // the launcher file rev applied last (persisted as "launcher_rev" in t2r-loadout.json)
static char g_lj_last[8192];
static void lj_state_load(void) {
    static int done;
    if (done) return;
    done = 1;
    g_lj_applied = 0;
    char p[MAX_PATH]; static char buf[16384];
    lj_path(p, sizeof p, "t2r-loadout.json");
    if (lj_read(p, buf, sizeof buf) < 0) return;
    // A build wrote this file cut after "custom":[ (lj_body bug) - it does not parse, but "launcher_rev" sits in its first bytes: read it raw first so
    // the in-game edits made since that launcher file are not overwritten by one more re-apply of it (the logs show "applied rev ..." on every start)
    const char *raw = strstr(buf, "\"launcher_rev\":");
    long long rawrev = raw ? strtoll(raw + 15, NULL, 10) : 0;
    lj_n *r = lj_parse(buf), *v = lj_get(r, "launcher_rev");
    if (v && v->t == 'n' && v->num > 0) g_lj_applied = (long long)v->num;
    else if (!r && rawrev > 0) { g_lj_applied = rawrev; xlog("launcher loadouts: t2r-loadout.json did not parse (PT80 cut file) - launcher_rev %lld kept", rawrev); }
}
// perf (feature_loadout_persist showed 290-700 ms stalls in reports): the tmp write + MoveFileEx(WRITE_THROUGH) = a disk flush ran on the
// tick thread (antivirus / a busy disk = a frozen frame). The file is written by a one-shot worker from a heap copy; one write at a time (a change
// that arrives while one is in flight clears g_lj_last so the next tick sends it).
typedef struct { char p[MAX_PATH], t[MAX_PATH + 8], *txt; size_t len; int cls, idx; } lj_wr_t;
static volatile LONG g_lj_wr_busy;
static DWORD WINAPI lj_write_worker(LPVOID u) {
    lj_wr_t *w = (lj_wr_t *)u;
    FILE *f = fopen(w->t, "wb");
    int ok = 0;
    if (f) {
        size_t n = fwrite(w->txt, 1, w->len, f);
        fclose(f);
        ok = n == w->len && MoveFileExA(w->t, w->p, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
        if (!ok) DeleteFileA(w->t);
    }
    if (ok) xlog("launcher loadouts: t2r-loadout.json written (%d custom loadouts, active %s %d)", g_lo_n, w->cls ? "class" : "custom", w->idx);
    free(w->txt); free(w);
    InterlockedExchange(&g_lj_wr_busy, 0);
    return 0;
}
static void lj_export(int force) {
    static char body[8192], full[8300];
    lj_state_load();
    if (lj_body(body, sizeof body) >= (int)sizeof body) return;
    if (!force && !strcmp(body, g_lj_last)) return;
    if (InterlockedCompareExchange(&g_lj_wr_busy, 1, 0)) { g_lj_last[0] = 0; return; }   // a write is still in flight: the next tick retries
    snprintf(g_lj_last, sizeof g_lj_last, "%s", body);
    snprintf(full, sizeof full, "{\"format\":1,\"rev\":%lld,\"launcher_rev\":%lld,%s}\n", lj_now_ms(), g_lj_applied, body);
    lj_wr_t *w = (lj_wr_t *)calloc(1, sizeof *w);
    if (w) { w->txt = (char *)malloc(strlen(full) + 1); }
    if (!w || !w->txt) { if (w) free(w); InterlockedExchange(&g_lj_wr_busy, 0); g_lj_last[0] = 0; return; }
    strcpy(w->txt, full); w->len = strlen(full);
    lj_path(w->p, sizeof w->p, "t2r-loadout.json");
    snprintf(w->t, sizeof w->t, "%s.tmp", w->p);
    w->cls = lo_slot(g_lo_active) < 0; w->idx = (w->cls ? lo_cls(g_lo_active) : lo_slot(g_lo_active)) + 1;
    HANDLE th = CreateThread(NULL, 0, lj_write_worker, w, 0, NULL);
    if (th) CloseHandle(th);
    else { free(w->txt); free(w); InterlockedExchange(&g_lj_wr_busy, 0); g_lj_last[0] = 0; }
}

// ---- import
static int lj_pick_w(int slot, const lj_n *n, int allow_none, uint32_t *w, int ci, const char *what) {   // 1 = slot kept
    if (!n) { xlog("launcher loadouts: custom %d %s missing, kept", ci + 1, what); return 1; }
    if (n->t == 'z') {
        if (!allow_none) { xlog("launcher loadouts: custom %d %s empty, kept", ci + 1, what); return 1; }
        *w = 0xffffffffu;
        return 0;
    }
    const char *id = n->t == 's' ? n->s : NULL;
    int supp = 0;
    if (n->t == 'o') {
        const lj_n *i = lj_get(n, "id"), *s = lj_get(n, "supp");
        id = i && i->t == 's' ? i->s : NULL;
        supp = s && ((s->t == 'n' || s->t == 'b') && s->num != 0);
    }
    char spec[96];
    if (!id || !*id || strlen(id) > 70) { xlog("launcher loadouts: custom %d %s: bad id, kept", ci + 1, what); return 1; }
    snprintf(spec, sizeof spec, "%s%s", id, supp ? "-supp" : "");
    uint32_t r = lo_class_row(slot, spec);
    if (r == 0xffffffffu) { xlog("launcher loadouts: custom %d %s: unknown id %s, kept", ci + 1, what, spec); return 1; }
    *w = r;
    return 0;
}
static int lj_pick_sk(const lj_n *n, uint64_t *v, uint32_t *used, int ci, int j) {   // 1 = slot kept (or cleared for a duplicate)
    if (!n) { xlog("launcher loadouts: custom %d skill %d missing, kept", ci + 1, j + 1); return 1; }
    if (n->t == 'z') { *v = 0; return 0; }
    const lj_n *i = lj_get(n, "id"), *l = lj_get(n, "lv");
    int id = 0, lv = l && l->t == 'n' ? (int)l->num : 0;
    if (i && i->t == 's') for (int k = 1; k < SK_COUNT; k++) if (LJ_SK[k] && !strcmp(LJ_SK[k], i->s)) id = k;
    if (!id || lv < 1 || lv > SK[id].nlv) { xlog("launcher loadouts: custom %d skill %d: unknown skill or level, kept", ci + 1, j + 1); return 1; }
    if (*used & (1u << id)) { xlog("launcher loadouts: custom %d skill %d: %s twice, cleared", ci + 1, j + 1, LJ_SK[id]); *v = 0; return 1; }
    *used |= 1u << id;
    *v = SK_V(id, lv);
    return 0;
}
// launcher edits apply in real time, in menus AND mid-match. Only while one of our loadout pages is open the file waits (the page
// shows / edits the table itself). Mid-match the table is updated at once and the active loadout becomes a pending pick for the next spawn
// (the same path as picking on the mid-match page: the lobby object is not touched while the old guns are still held).
static int lj_gate_open(void) {
    if (g_lo_state != LO_NONE) return 0;
    return match_substate() == 6 || (!g_lo_pending && !g_lo_snap.ok);
}
static int lj_import(void) {
    static FILETIME seen_t; static DWORD seen_sz = 0xffffffffu;
    static char buf[16384];
    char p[MAX_PATH];
    WIN32_FILE_ATTRIBUTE_DATA a;
    lj_path(p, sizeof p, "t2r-loadout-launcher.json");
    if (fa_poll(p) == INVALID_FILE_ATTRIBUTES || !GetFileAttributesExA(p, GetFileExInfoStandard, &a)) return 0;   // (no launcher file = answered from the fa_poll cache)
    if (a.ftLastWriteTime.dwLowDateTime == seen_t.dwLowDateTime && a.ftLastWriteTime.dwHighDateTime == seen_t.dwHighDateTime && a.nFileSizeLow == seen_sz) return 0;
    if (!lj_gate_open()) return 0;      // look again when the menu is free
    seen_t = a.ftLastWriteTime; seen_sz = a.nFileSizeLow;
    lj_state_load();
    if (lj_read(p, buf, sizeof buf) < 0) { xlog("launcher loadouts: t2r-loadout-launcher.json unreadable (or over 16 KB)"); return 0; }
    lj_n *root = lj_parse(buf), *rv = lj_get(root, "rev"), *cu = lj_get(root, "custom");
    if (!root || !rv || rv->t != 'n' || !cu || cu->t != 'a') { xlog("launcher loadouts: t2r-loadout-launcher.json is not a loadout file, ignored"); return 0; }
    long long rev = (long long)rv->num;
    if (rev <= g_lj_applied) return 0;
    int fixed = 0;
    const int had_n = g_lo_n;
    for (int i = 0; i < N_CUSTOM_MAX; i++) {
        const lj_n *n = lj_idx(cu, i);
        if (i >= g_lo_n) {                      // CREATE LOADOUT in the launcher: the next slot (an older launcher writes six; nothing is ever removed)
            if (!n || n->t != 'o') break;
            g_lo[i] = (loadout_t){{0xffffffffu, 0, 0xffffffffu}, {0, 0, 0}};
            *sk4_slot(&g_lo[i]) = 0;
            lo_nm_set(i, "", "launcher create");
            g_lo_n = i + 1;
            xlog("launcher loadouts: custom %d created", i + 1);
        }
        loadout_t old = g_lo[i], nl = old;
        uint64_t *sk4 = sk4_slot(&g_lo[i]), old4 = *sk4, s[4] = {old.k[0], old.k[1], old.k[2], old4};
        int fx = 0;
        if (!n || n->t != 'o') { xlog("launcher loadouts: custom %d missing, kept", i + 1); fixed++; continue; }
        {   // the name: a launcher older than names writes none (kept); "" = back to the default label
            const lj_n *nm = lj_get(n, "name");
            if (nm && nm->t == 's') lo_nm_set(i, nm->s, "launcher");
        }
        fx += lj_pick_w(1, lj_get(n, "small"), 0, &nl.w[1], i, "small firearm");
        fx += lj_pick_w(0, lj_get(n, "large"), 1, &nl.w[0], i, "large firearm");
        fx += lj_pick_w(2, lj_get(n, "purch"), 1, &nl.w[2], i, "purchasable");
        const lj_n *sa = lj_get(n, "skills");
        uint32_t used = 0;
        for (int j = 0; j < 4; j++) fx += lj_pick_sk(lj_idx(sa, j), &s[j], &used, i, j);
        for (int j = 0; j < 3; j++) nl.k[j] = s[j];
        g_lo[i] = nl; *sk4 = s[3];
        if (!lo_valid(&g_lo[i])) {      // over 13 LP, or a row / skill the game refuses: the whole loadout stays as it was
            xlog("launcher loadouts: custom %d is %d LP (max 13) or invalid, kept as it was", i + 1, lo_cost(&g_lo[i]));
            g_lo[i] = old; *sk4 = old4;
            fx++;
        }
        fixed += fx;
    }
    int in_match = match_substate() == 6, was = g_lo_active;
    const lj_n *ac = lj_get(root, "active"), *ak = lj_get(ac, "kind"), *ai = lj_get(ac, "i");
    if (ak && ak->t == 's' && ai && ai->t == 'n') {
        int k = (int)ai->num, want = -1;
        if (!strcmp(ak->s, "custom") && k >= 0 && k < g_lo_n) want = lo_slot_idx(k);
        else if (!strcmp(ak->s, "class") && k >= 0 && k < N_CLASSES) want = N_CUSTOM + k;
        else { xlog("launcher loadouts: bad active pick, kept"); fixed++; }
        if (want >= 0 && in_match && want != was && gl_pick_refused(want)) { xlog("launcher loadouts: active pick %d refused mid-match (team gun limit), kept %d", want, was); fixed++; want = -1; }
        if (want >= 0) g_lo_active = want;
    }
    g_lj_applied = rev;
    lo_save();
    sk4_save();
    if (in_match) {
        g_lo_pending = g_lo_active + 1;         // spawnkit_hook gives the (updated) table's loadout at the next spawn
        msg_hook("Loadout updated - applies on your next life", 2.5f, 0, 0);
    } else lo_write_obj(lo_of(g_lo_active));
    lj_export(1);
    xlog("launcher loadouts: applied rev %lld (%d custom loadouts, %d created, %d slots fixed)%s", rev, g_lo_n, g_lo_n - had_n, fixed, in_match ? " mid-match - pending to the next spawn" : "");
    return 1;
}
// the player edited a loadout on our GEAR UP pages: a launcher file not applied yet is older than that edit, so it must not overwrite it
// (its rev counts as applied; t2r-loadout.json then reports launcher_rev = that rev and the launcher adopts the game's loadouts)
static void lj_user_edit(void) {
    static char buf[16384];
    char p[MAX_PATH];
    lj_state_load();
    lj_path(p, sizeof p, "t2r-loadout-launcher.json");
    if (lj_read(p, buf, sizeof buf) < 0) return;
    lj_n *rv = lj_get(lj_parse(buf), "rev");
    if (rv && rv->t == 'n' && (long long)rv->num > g_lj_applied) {
        g_lj_applied = (long long)rv->num;
        xlog("launcher loadouts: in-game edit after launcher rev %lld - the launcher file is dropped", g_lj_applied);
    }
}
// from feature_loadout_persist (twice a second, in menus and matches): 1 = a launcher file was applied (the lobby object was rewritten)
static int lj_tick(int first) {
    if (!g_loadout_path[0]) return 0;
    lj_state_load();
    int applied = lj_import();
    if (!applied) lj_export(first);
    return applied;
}
