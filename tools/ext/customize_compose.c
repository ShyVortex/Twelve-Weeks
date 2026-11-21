// customize_compose.c - the outfit worn in a match (re/customize-1117.md "Wearing it in a match"). Included from customize.c.
//
// Data (tools/features/customize_looks.py): one look2 record per (faction, sex, body) "t2r-cz-<f><s>-<b>" (b = peer slot 0..7, 8 = us), a
// copy of that (faction, sex)'s default pool look's armoured twin whose mesh / prop arrays hold the SUPERSET of parts (every pool twin's
// parts + every tier-1 item part). Before a body spawns, cz_compose writes the outfit's subset to the front of that body's record arrays
// (cz_select, customize_core.h), sets the counts, copies the chosen face's skin tint into the record's palette entry (Seraphites), and the
// spawn hook spawns the body with the record's name instead of the pool look (the field swap the armour twins use, restored after the call).
//
// Everything keyed by a pool look row keeps working through cz_row_of_look / cz_row_of_name: the armour rig answers the row of the look whose
// torso the outfit wears (+ this body's own swap pairs, cz_body_pair, and its own hat / hood clash), the pistol points and second holster the
// row whose lower (belt, holsters) it wears, the TAB backpack prop the row whose bag it wears.
//
// Who wears what: our own body = our profile (t2r-customize.txt) for the faction we play; a puppet = the outfit its player sends
// (MSG_CUSTOM_LOOK, cz_net_*), else the random pool look as before. Off: t2r-no-customize-look.txt next to the exe (also stops sending).
// Winter maps keep the winter pool looks (their garments are other paks). A build without the records (dc lookup fails) changes nothing.
// Logs "customize look: ...".

#define MSG_CUSTOM_LOOK 0x59      // peer msg (ours): customize_core.h cz_msg (CZ_MSG_LEN bytes) - the sender's outfit per faction
#define CZB_N (T2R_MAX_PEERS + 1)
#define CZ_SUP_MAX 256             // (the WLF male superset is 171 parts; the gas masks' under-hat shapes add 18 per class)
#define CZ_PSUP_MAX 16
#define CZ_LOG(...) do { static int nl_; if (nl_ < 600) { nl_++; xlog(__VA_ARGS__); } } while (0)     // (80 ran out in one CUSTOMIZE visit: the outfit of a crash frame was not in the log)

typedef struct { uint64_t *arr; uint32_t n; uint64_t m[CZ_SUP_MAX]; uint64_t *parr; uint32_t pn; uint64_t p[CZ_PSUP_MAX]; } cz_snap_t;
static cz_snap_t g_czs[CZ_NFAC][CZ_NSEX][CZB_N];
typedef struct {
    int on, fac, sex, row_torso, row_lower, row_bag;
    uint64_t sid;
    int npair;
    armor_body_t pair[ARMOR_RIG_BODY_N];
    char pn[ARMOR_RIG_BODY_N][2][0x30];
    char clash[0x30];
    // the outfit's HAIR parts (the bare-head copies' hair as separate parts, customize_items.HAIRPARTS; KELLIE's crown hair) and
    // its SECOND head part (a hat-fitted head, customize_items.FACEFIT; FACE 10's second pak): under the armour helmet the head
    // swaps to its pushed copy, which has its own hair - these would stand through the helmet beside it
    int nhair;
    char hair[CZ_HAIR_CLASH_N][0x30];
    // a hat-fitted head that REPLACES the stock head (a crown hat hides the stock head, the face's 't2r-hh-' copy draws instead) and whose
    // stock head has no pushed copy (only WLF female 13 has one): under the helmet nothing would draw a head, so the stock head comes
    // back on instead (as for the same face without a hat). Empty = none.
    char head_fit[0x30], head_stock[0x30];
    char name[0x28];
    int voice;          // the face's own voice letter index (cz_face_voice), -1 = the pool look's (VX_LOOK_VOICE)
} cz_body_t;
static cz_body_t g_czb[CZB_N];
static struct { cz_wire_t w; uint64_t at; } g_czw[T2R_MAX_PEERS];
static uint8_t g_cz_tx_counter;
static int cz_face_voice(int fac, int sex, const cz_item_t *face);   // (defined below the body composer that calls it)

static int cz_wear_off(void) {
    static uint64_t next; static int off;
    uint64_t now = GetTickCount64();
    if (now >= next) {
        next = now + 2000;
        FILE *f = exe_side_open("t2r-no-customize-look.txt", "r");
        int o = f != NULL;
        if (f) fclose(f);
        if (o != off) xlog("customize look: %s", o ? "OFF (t2r-no-customize-look.txt) - pool looks" : "on");
        off = o;
    }
    return off;
}
// the look2 record of that name (the typed lookup dc_look_exists uses), NULL = not loaded
static uint8_t *cz_rec(const char *name) {
    typedef uint64_t (*fn_lookup3)(uint64_t sid, uint64_t type, uint64_t dflt);
    static const uint8_t expect[15] = {0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xEC, 0x20};
    uint8_t *f = (uint8_t *)GetModuleHandleW(NULL) + 0x13578a0;
    if (memcmp(f, expect, sizeof expect)) return NULL;
    uint64_t sid = fnv64(name), T_LOOK2 = 0xbf24e1b6bade9dccULL;
    uint64_t *p = (uint64_t *)((fn_lookup3)f)(sid, T_LOOK2, 0);
    if (!p || IsBadReadPtr(p - 1, 0x1d8) || p[-1] != T_LOOK2 || p[0] != sid) return NULL;
    return (uint8_t *)p;
}
static const char *cz_mesh_name(uint64_t m) {
    if (!m || IsBadReadPtr((void *)m, 0x50)) return NULL;
    const char *s = *(const char **)(m + 0x10);
    return s && !IsBadReadPtr(s, 8) ? s : NULL;
}
static int cz_writable(void *p, size_t n) {
    MEMORY_BASIC_INFORMATION mi;
    if (!VirtualQuery(p, &mi, sizeof mi)) return 0;
    DWORD pr = mi.Protect & 0xff;
    if (pr == PAGE_READWRITE || pr == PAGE_EXECUTE_READWRITE || pr == PAGE_WRITECOPY || pr == PAGE_EXECUTE_WRITECOPY) return 1;
    DWORD old;
    return VirtualProtect(p, n, PAGE_READWRITE, &old) != 0;
}
// pool rows (ARMOR_RIG_BASES index) of one (faction, sex)
static int cz_pool_rows(int fac, int sex, int *out) {
    int n = 0;
    if (!sex) for (int i = fac ? 0 : 6, e = i + 6; i < e; i++) out[n++] = i;        // Seraphite males 0..5, WLF males 6..11
    else for (int i = fac ? 12 : 14, e = i + 2; i < e; i++) out[n++] = i;           // Seraphite females 12, 13, WLF females 14, 15
    return n;
}
static int cz_rec_has(const uint8_t *p, const char *part) {
    if (!p || !part) return 0;
    uint64_t *a = *(uint64_t **)(p + 0xa0);
    uint32_t n = *(uint32_t *)(p + 0xa8);
    if (!a || n > CZ_SUP_MAX || IsBadReadPtr(a, n * 8)) return 0;
    for (uint32_t i = 0; i < n; i++) { const char *s = cz_mesh_name(a[i]); if (s && !strcmp(s, part)) return 1; }
    return 0;
}
static uint8_t *cz_twin_rec(int row) {
    char tw[0x40];
    snprintf(tw, sizeof tw, "%s%s", ARMOR_RIG_BASES[row], ARMOR_RIG_SUFFIX);
    return cz_rec(tw);
}
// the pool row whose look wears the first part of that item (else the default row)
static int cz_match_row(int fac, int sex, int cat, int idx) {
    int rows[8], n = cz_pool_rows(fac, sex, rows);
    const cz_item_t *it = cz_item(fac, sex, cat, idx);
    const char *p0 = it && it->parts ? it->parts[0] : NULL;
    for (int r = 0; p0 && r < n; r++) if (cz_rec_has(cz_twin_rec(rows[r]), p0)) return rows[r];
    return rows[0];
}
static int cz_rec_names(const uint8_t *p, const char **out, int cap) {   // a record's part names, NULL-terminated
    int k = 0;
    uint64_t *a = p ? *(uint64_t **)(p + 0xa0) : NULL;
    uint32_t n = p ? *(uint32_t *)(p + 0xa8) : 0;
    if (a && n <= CZ_SUP_MAX && !IsBadReadPtr(a, n * 8))
        for (uint32_t i = 0; i < n && k < cap - 1; i++) { const char *s = cz_mesh_name(a[i]); if (s) out[k++] = s; }
    out[k] = NULL;
    return k;
}
// Seraphite skin by the chosen face (customize_looks.patch_customize_tints): the record's palette pointer array (look2 +0xe0, count 1)
// is [the one in use, the default look's, face 0's, face 1's, ...] - slot 0 = the face's own palette, a block nothing edits.
// (the first design rewrote one entry's colour here; the hands kept the first colour and the skin did not change.)
// A build without the face palettes (the array ends after slot 0): the old entry copy below.
static void cz_tint(uint8_t *p, uint64_t own_sid, const char *head, int face_idx, int nface) {
    char fl[0x40];
    if (!head || !cz_face_look(head, fl, sizeof fl) || *(uint32_t *)(p + 0xe8) < 1) return;
    uint64_t *pa = *(uint64_t **)(p + 0xe0);
    if (!pa || IsBadReadPtr(pa, 8) || !pa[0] || IsBadReadPtr((void *)pa[0], 16)) return;
    if (face_idx >= 0 && face_idx < nface && !IsBadReadPtr(pa, (size_t)(nface + 2) * 8)) {
        const uint64_t T = fnv64("look2-tint-palette");
        int ok = 1;
        for (int i = 1; i < nface + 2 && ok; i++) ok = pa[i] && !IsBadReadPtr((void *)(pa[i] - 8), 0x18) && *(uint64_t *)(pa[i] - 8) == T;
        if (ok && cz_writable(pa, 8)) {
            if (pa[0] != pa[2 + face_idx]) CZ_LOG("customize look: skin tint palette of %s (face %d of %d)", fl, face_idx, nface);
            pa[0] = pa[2 + face_idx];
            return;
        }
    }
    uint8_t *pal = (uint8_t *)pa[0];
    uint64_t *ents = *(uint64_t **)pal;
    uint32_t n = *(uint32_t *)(pal + 8);
    if (!ents || n > 256 || IsBadReadPtr(ents, n * 8)) return;
    uint64_t want = fnv64(fl);
    uint8_t *own = NULL, *src = NULL;
    for (uint32_t i = 0; i < n; i++) {
        uint8_t *e = (uint8_t *)ents[i];
        if (!e || IsBadReadPtr(e, 0x18)) continue;
        if (*(uint64_t *)e == own_sid) own = e;
        if (*(uint64_t *)e == want) src = e;
    }
    if (own && src && cz_writable(own + 8, 0x10)) memcpy(own + 8, src + 8, 0x10);
    else CZ_LOG("customize look: no skin tint for %s (own entry %p, %s entry %p)", head, (void *)own, fl, (void *)src);
}
// compose body b's record for that outfit; out = the record name to spawn with. 0 = not possible (the pool look stays)
static int cz_compose(int body, int fac, int sex, const uint8_t *it, char out[0x28]) {
    char name[0x28];
    if (body < 0 || body >= CZB_N || !cz_look_name(fac, sex, body, name, sizeof name)) return 0;
    uint8_t *p = cz_rec(name);
    if (!p) { CZ_LOG("customize look: record %s not loaded (build without customize looks) - pool look", name); return 0; }
    // Seraphite skin tint by face: the record "<name>-<face index>" (customize_looks.face_name: the same arrays, its own static palette
    // entry with that face's skin colour). A build without them keeps the body record (the default look's skin).
    int skin_rec = 0;       // the face's own record is in use: its palette IS the face's skin colour, nothing to copy (cz_tint below)
    {   // (the WLF too - their tops' hand-tint copies take the face's colour from the face record's palette)
        char vn[0x28];
        int fk = (int)it[CZ_FACE];
#ifdef CZ_WLF_TONES     // (WLF: the record of the face's skin TONE GROUP - customize_items.h CZ_WLF_TONE; the level def holds 512 symbols)
        if (fac == 0) fk = fk < CZ_WLF_TONES ? CZ_WLF_TONE[sex][fk] : 0;
#endif
        if (snprintf(vn, sizeof vn, "%s-%d", name, fk) < (int)sizeof vn) {
            uint8_t *vp = cz_rec(vn);
            if (vp && *(uint64_t **)(vp + 0xa0) == *(uint64_t **)(p + 0xa0)) { p = vp; memcpy(name, vn, strlen(vn) + 1); skin_rec = 1; }
            else CZ_LOG("customize look: no skin record %s (%s) - %s keeps the default look's skin", vn, vp ? "other arrays" : "not loaded", name);
        }
    }
    cz_snap_t *s = &g_czs[fac][sex][body];
    uint64_t *arr = *(uint64_t **)(p + 0xa0), *parr = *(uint64_t **)(p + 0xb0);
    uint32_t n = *(uint32_t *)(p + 0xa8), pn = parr ? *(uint32_t *)(p + 0xb8) : 0;
    if (s->arr != arr) {          // first use (or the module was reloaded): the arrays hold the full superset
        if (!arr || n > CZ_SUP_MAX || pn > CZ_PSUP_MAX || IsBadReadPtr(arr, n * 8) || (pn && IsBadReadPtr(parr, pn * 8))) {
            CZ_LOG("customize look: %s superset unreadable (%u parts, %u props) - pool look", name, n, pn); return 0;
        }
        memcpy(s->m, arr, n * 8); s->n = n; s->arr = arr;
        if (pn) memcpy(s->p, parr, pn * 8);
        s->pn = pn; s->parr = parr;
        CZ_LOG("customize look: %s superset %u parts, %u props", name, n, pn);
    }
    cz_part_t sup[CZ_SUP_MAX];
    uint8_t keep[CZ_SUP_MAX], pkeep[CZ_PSUP_MAX];
    for (uint32_t i = 0; i < s->n; i++) {
        const char *nm = cz_mesh_name(s->m[i]);
        sup[i].name = nm ? nm : "";
        sup[i].hidden = nm ? *(uint8_t *)(s->m[i] + 0x48) != 0 : 1;
    }
    cz_body_t *B = &g_czb[body];
    int rt = cz_match_row(fac, sex, CZ_TORSO, it[CZ_TORSO]), rl = cz_match_row(fac, sex, CZ_LOWER, it[CZ_LOWER]);
    int rb = cz_match_row(fac, sex, CZ_BACKPACK, it[CZ_BACKPACK]);
    const char *tx[48], *lx[48];
    cz_rec_names(cz_twin_rec(rt), tx, 48);
    cz_rec_names(cz_twin_rec(rl), lx, 48);
    int k = cz_select(fac, sex, it, sup, (int)s->n, tx, lx, keep);
    if (k <= 0) { CZ_LOG("customize look: %s - an item part is not in the superset (%d) - pool look", name, k); return 0; }
    const char *pnm[CZ_PSUP_MAX];
    for (uint32_t i = 0; i < s->pn; i++) { const char *nm = cz_mesh_name(s->p[i]); pnm[i] = nm ? nm : ""; }
    int kp = s->pn ? cz_select_props(fac, sex, it, pnm, (int)s->pn, pkeep) : 0;
    if (!cz_writable(arr, s->n * 8) || (s->pn && !cz_writable(parr, s->pn * 8)) || !cz_writable(p + 0xa8, 0x14)) {
        CZ_LOG("customize look: %s arrays not writable - pool look", name); return 0;
    }
    uint32_t j = 0;
    for (uint32_t i = 0; i < s->n; i++) if (keep[i]) arr[j++] = s->m[i];
    for (uint32_t i = j; i < s->n; i++) arr[i] = s->m[i];      // (the rest stays the superset, past the count)
    *(uint32_t *)(p + 0xa8) = j;
    if (s->pn) {
        uint32_t q = 0;
        for (uint32_t i = 0; i < s->pn; i++) if (pkeep[i]) parr[q++] = s->p[i];
        for (uint32_t i = 0; i < s->pn; i++) if (!pkeep[i]) parr[q++] = s->p[i];
        *(uint32_t *)(p + 0xb8) = (uint32_t)kp;
    }
    const cz_item_t *face = cz_item(fac, sex, CZ_FACE, it[CZ_FACE]);
    // (cz_tint = the two older designs, for a build whose data has no skin records. With a skin record it found neither a palette
    // array nor an own entry and logged "no skin tint for <head>" on every compose - build #21's A/B: 100+ lines that read like a
    // hands / face mismatch and were none.)
    if (!skin_rec) cz_tint(p, fnv64(name), face && face->parts ? face->parts[0] : NULL, it[CZ_FACE], cz_count(fac, sex, CZ_FACE));
    // this body's armour pairs + clash (the armour rig asks cz_body_pair / cz_body_clash while it wears the record)
    const char *o[ARMOR_RIG_BODY_N], *c[ARMOR_RIG_BODY_N];
    int m[ARMOR_RIG_BODY_N];
    memset(B, 0, sizeof *B);
    B->voice = cz_face_voice(fac, sex, face);
    B->npair = cz_armour_pairs(sup, keep, (int)s->n, o, c, m, ARMOR_RIG_BODY_N);
    for (int i = 0; i < B->npair; i++) {
        snprintf(B->pn[i][0], sizeof B->pn[i][0], "%s", o[i]); snprintf(B->pn[i][1], sizeof B->pn[i][1], "%s", c[i]);
        B->pair[i].orig = B->pn[i][0]; B->pair[i].copy = B->pn[i][1]; B->pair[i].mask = m[i];
    }
    const cz_item_t *hat = cz_item(fac, sex, CZ_HAT, it[CZ_HAT]);
    if (fac) snprintf(B->clash, sizeof B->clash, "scar-%s-hoodup", sex ? "female" : "male");         // (the helmet hides the hood, as the pool looks)
    else if (hat && hat->parts && hat->parts[0]) snprintf(B->clash, sizeof B->clash, "%s", hat->parts[0]);
    // Only the hair parts this outfit DRAWS: kept with the record shown at spawn. A hat / mask hide list keeps its parts as the record
    // hidden at spawn (cz_select: cz_take(.., 1)), and the armour rig turns every listed part on whenever the helmet is off - a listed
    // hidden part would come on beside the drawn one (two crowns: KELLIE's bare and gas-mask crowns, a fitted face's bare and under-hat
    // hair). KELLIE's face carries ten hair parts of which the rules leave one; a first-N list could also miss the drawn one (hair
    // through the helmet).
    // (live 189, a player: WLF female FACE 14 + FOLDED BEANIE, armour bought): the beanie hides the stock head
    // 'militia-female-head-14' (kept as a record hidden at spawn) and the fitted 't2r-hh--female-head-14' draws. That fitted head was
    // listed here as a hair part, so the helmet hid it and NO head was drawn; the half mask, skinned to the face joints, spiked out.
    // Such a head is not hair: it swaps with the stock head under the helmet (head_fit / head_stock), unless the stock head has an
    // armour pair (its pushed copy takes over, the old rule). FACE 10's second head draws BESIDE a drawn stock head: still listed.
    const char *stock = face && face->parts ? face->parts[0] : NULL;
    int stock_hidden = 0, stock_paired = 0;
    for (uint32_t i = 0; stock && i < s->n; i++) if (keep[i] && !strcmp(sup[i].name, stock)) stock_hidden = sup[i].hidden != 0;
    for (int i = 0; stock && i < B->npair; i++) if (!strcmp(B->pair[i].orig, stock)) stock_paired = 1;
    for (const char *const *fp = face && face->parts ? face->parts : NULL; fp && *fp && B->nhair < CZ_HAIR_CLASH_N; fp++) {
        // per-hat hair (9228acaec / c28b96fdc) is named without "-hair": t2r-fh-*-hh-patrol---x, -bahhx, -cwhhx, KELLIE t2r-kl-?-h-ball-cap-00.
        // Every non-head part of a t2r-fh- face is hair; a KELLIE part is hair when named -hair or -h- (her acc / hands parts are not).
        int perhat = fp != face->parts && !strstr(*fp, "-head-") &&
                     (!strncmp(*fp, "t2r-fh-", 7) || (!strncmp(*fp, "t2r-kl-", 7) && strstr(*fp, "-h-")));
        if (!((strstr(*fp, "-hair") && !strstr(*fp, "-head-")) || perhat || (fp != face->parts && strstr(*fp, "-head-")))) continue;
        int drawn = 0;
        for (uint32_t i = 0; i < s->n && !drawn; i++) drawn = keep[i] && !sup[i].hidden && !strcmp(sup[i].name, *fp);
        if (!drawn) continue;
        if (fp != face->parts && strstr(*fp, "-head-") && stock_hidden && !stock_paired && !B->head_fit[0]) {
            snprintf(B->head_fit, sizeof B->head_fit, "%s", *fp);
            snprintf(B->head_stock, sizeof B->head_stock, "%s", stock);
            continue;
        }
        snprintf(B->hair[B->nhair++], sizeof B->hair[0], "%s", *fp);
    }
    if (B->head_fit[0]) CZ_LOG("customize look: %s - under the helmet the stock head %s replaces the hat-fitted %s", name, B->head_stock, B->head_fit);
    B->on = 1; B->fac = fac; B->sex = sex; B->row_torso = rt; B->row_lower = rl; B->row_bag = rb;
    B->sid = fnv64(name);
    snprintf(B->name, sizeof B->name, "%s", name);
    memcpy(out, name, strlen(name) + 1);
    CZ_LOG("customize look: body %d -> %s (%u of %u parts, %d props; rows torso %s, lower %s, bag %s; %d armour pairs)", body, name, j, s->n, kp,
           ARMOR_RIG_BASES[rt], ARMOR_RIG_BASES[rl], ARMOR_RIG_BASES[rb], B->npair);
    return 1;
}
// ---- what t2r-ext asks (all -1 / NULL when the body / look is not a composed one)
static int cz_body_of_sid(uint64_t look) {
    for (int b = 0; look && b < CZB_N; b++) if (g_czb[b].on && g_czb[b].sid == look) return b;
    return -1;
}
// which: 0 torso (armour rig), 1 lower (pistol points, second holster), 2 bag (TAB backpack prop)
static int cz_row_of_look(uint64_t look, int which) {
    int b = cz_body_of_sid(look);
    if (b < 0) return -1;
    return which == 0 ? g_czb[b].row_torso : which == 1 ? g_czb[b].row_lower : g_czb[b].row_bag;
}
static int cz_row_of_name(const char *look, int which) {
    if (!look || strncmp(look, "t2r-cz-", 7)) return -1;
    return cz_row_of_look(fnv64(look), which);
}
static const armor_body_t *cz_body_pair(int idx, int k) {
    static const armor_body_t none = {NULL, NULL, 0};
    if (idx < 0 || idx >= CZB_N || !g_czb[idx].on) return NULL;
    return k < g_czb[idx].npair ? &g_czb[idx].pair[k] : &none;
}
static const char *cz_body_clash(int idx, int look_i) {
    if (idx >= 0 && idx < CZB_N && g_czb[idx].on) return g_czb[idx].clash[0] ? g_czb[idx].clash : NULL;
    return look_i >= 0 ? ARMOR_RIG_CLASH[look_i] : NULL;
}
// the k-th hair part of a composed body (hidden while the helmet shows, like the clash part), NULL = no more
// the helmet's head swap of a composed body (see head_fit): 1 = *fit / *stock set
static int cz_body_head_swap(int idx, const char **fit, const char **stock) {
    if (idx < 0 || idx >= CZB_N || !g_czb[idx].on || !g_czb[idx].head_fit[0]) return 0;
    *fit = g_czb[idx].head_fit; *stock = g_czb[idx].head_stock;
    return 1;
}
static const char *cz_body_hair(int idx, int k) {
    return idx >= 0 && idx < CZB_N && g_czb[idx].on && k >= 0 && k < g_czb[idx].nhair ? g_czb[idx].hair[k] : NULL;
}
// KELLIE speaks female voice C (voice letter index 2) in every outfit, on both sides - WLF mltfc (picked from the audition)
// and Seraphite scrfc (picked from the both-sides audition: no take is shared between the
// factions, so it was chosen by ear). Keyed by the face the composed body wears, so every client that shows the composed KELLIE body
// (ours from the profile, a peer's from its wire outfit, msg 0x59) hears voice C; a client that shows the pool look hears the pool look's voice.
// -1 = no own voice (every other face: the pool look's voice, VX_LOOK_VOICE).
static int cz_face_voice(int fac, int sex, const cz_item_t *face) {
    (void)fac;
    if (sex != 1 || !face || !face->parts || !face->parts[0]) return -1;
    return !strcmp(face->parts[0], "t2r-kl-f-head-kellie01") || !strcmp(face->parts[0], "t2r-kl-s-head-kellie01") ? 2 : -1;      // WLF / Seraphite KELLIE head (69111c2a8: own Seraphite kit)
}
// the voice letter index body idx (a peer slot / T2R_US) speaks while it wears its composed outfit, -1 = not composed / the look's voice.
// vfac = the vox faction the body speaks in on this client (0 Seraphites, 1 WLF); the composed outfit must be that side's (customize fac 0 = WLF,
// 1 = Seraphites), else a stale outfit of the other side would pick the voice.
static int cz_body_voice(int idx, int vfac) {
    return idx >= 0 && idx < CZB_N && g_czb[idx].on && (vfac == 0 || vfac == 1) && g_czb[idx].fac == !vfac ? g_czb[idx].voice : -1;
}
static uint64_t cz_bag_look_sid(uint64_t look) {
    int r = cz_row_of_look(look, 2);
    return r >= 0 ? fnv64(ARMOR_RIG_BASES[r]) : 0;
}
// ---- the spawn: fac from the pool look the faction-look picker chose (its prefix), the outfit from the profile / the wire
static int cz_fac_of_look(const char *look) {
    if (!look) return -1;
    if (!strncmp(look, "scar-", 5)) return 1;
    if (!strncmp(look, "militia-", 8)) return 0;
    return -1;
}
// The body's sex is the one of the pool look this life wears (own_female / slot_female: the voice, female anims, knife and camera follow it on
// every client); the player's CUSTOMIZE sex steers our own picks (cz_pick_range), so the two only differ for a life picked before our side
// was known. The worn items are the profile's (or the wire's) for that sex.
static int cz_outfit(int body, int fac, int *sex, uint8_t *it) {
    if (body == T2R_US) {
        cz_load();
        *sex = own_female() ? 1 : 0;
        for (int c = 0; c < CZ_NWEAR; c++) it[c] = g_cz.it[fac][*sex][c];
        return 1;
    }
    if (body < 0 || body >= T2R_MAX_PEERS || !g_czw[body].w.ok) return 0;
    *sex = slot_female((uint32_t)body) ? 1 : 0;
    if (*sex != g_czw[body].w.sex[fac]) {          // (the wire carries one sex's items per faction: the other sex wears its defaults)
        for (int c = 0; c < CZ_NWEAR; c++) it[c] = (uint8_t)CZ_DEFAULT[fac][*sex][c];
        return 1;
    }
    memcpy(it, g_czw[body].w.it[fac], CZ_NWEAR);
    return 1;
}
// MELEE STYLE decides the unarmed melee (FISTS / KNIFE) for both sexes (own_knife, t2r-ext.c). The pick of the faction and sex this
// body wears (cz_outfit: ours from the profile, a peer's from its wire, else the defaults = FISTS); our own KNIFE only once earned.
// CUSTOMIZE looks off (t2r-no-customize-look.txt) = the old rule: female bodies fight with the knife.
static int cz_body_knife(int body) {
    int own = body == T2R_US || (uint32_t)body == g_fl.me, r = 0;
    if (cz_wear_off()) return own ? own_female() : body >= 0 && body < T2R_MAX_PEERS && slot_female((uint32_t)body);
    const char *lk = NULL;
    if (own) lk = fl_name(g_fl.team, g_fl.seq ? g_fl.cur : g_fl.next);
    else if (body >= 0 && body < T2R_MAX_PEERS) { int team, idx = fl_core_shown(&g_fl, (uint32_t)body, &team); lk = idx >= 0 ? fl_name(team, idx) : NULL; }
    int fac = cz_fac_of_look(lk), sex = 0;
    uint8_t it[CZ_NWEAR];
    if (fac >= 0 && cz_outfit(own ? T2R_US : body, fac, &sex, it)) {
        const cz_item_t *ci = cz_item(fac, sex, CZ_MELEE, it[CZ_MELEE]);
        r = ci && !strcmp(ci->label, "KNIFE") && (!own || cz_unlocked(&g_cz, ci));
    }
    if (own) {
        static int last = -1; static const char *lastlk;
        if (r != last || lk != lastlk) { last = r; lastlk = lk; xlog("melee style: %s (CUSTOMIZE pick of %s, %s body, look %s)", r ? "KNIFE" : "FISTS", fac == 1 ? "Seraphites" : fac == 0 ? "WLF" : "no faction", sex ? "female" : "male", lk ? lk : "-"); }
    }
    return r;
}
static void cz_pick_range(int *lo, int *hi) {
    if (cz_wear_off() || faction_looks_off()) return;
    int fac = cz_cur_side();
    if (fac < 0) return;
    cz_load();
    if (g_cz.sex[fac] == 1 && g_fem_mode >= FEM_SHOW) { *lo = FL_MALE_N; *hi = FL_N; }
    else if (g_cz.sex[fac] == 0) { *lo = 0; *hi = FL_MALE_N; }
}
// spawn hook helper: the look this body is about to spawn with (pool look / winmm default) -> its composed record name in out, or 0
static int cz_spawn_name(int body, const char *look, char out[0x28]) {
    if (body < 0 || body >= CZB_N) return 0;
    int fac = cz_fac_of_look(look), sex;
    uint8_t it[CZ_NWEAR];
    int ok = !cz_wear_off() && fac >= 0 && !faction_looks_off() && !mpsnow_winter_looks_now() && cz_outfit(body, fac, &sex, it);
    if (!ok || !cz_compose(body, fac, sex, it, out)) { g_czb[body].on = 0; return 0; }
    return 1;
}
// a look field (0x28 bytes, winmm peer record +0x1e) holds the composed name while `spawn` runs; saved -> restored by the caller
static int cz_spawn_field(char *fld, char saved[0x28], int body) {
    static char nm[0x28];
    if (!fld || !fld[0]) { if (body >= 0 && body < CZB_N) g_czb[body].on = 0; return 0; }
    if (!cz_spawn_name(body, fld, nm)) return 0;
    memcpy(saved, fld, 0x28);
    memset(fld, 0, 0x28);
    strcpy(fld, nm);
    return 1;
}
// ---- net: our outfit with the faction look message (fl_send / fl_send_to); receivers keep the newest per slot
static void cz_net_send(uint8_t to) {
    if (!g_send_tramp || cz_wear_off()) return;
    cz_load();
    uint8_t b[CZ_MSG_LEN];
    int n = cz_msg(&g_cz, g_cz_tx_counter, b);
    g_send_tramp(MSG_CUSTOM_LOOK, b, (uint64_t)n, to);
}
static void cz_net_changed(void) { g_cz_tx_counter++; }          // the page equipped something (the next send carries a new counter)
static void cz_net_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (slot >= T2R_MAX_PEERS || !buf) return;
    cz_wire_t w;
    if (!cz_recv(buf, (int)len, &w)) { CZ_LOG("customize look: slot %u outfit rejected (len %llu, version %u: other item lists)", slot, (unsigned long long)len, len ? buf[0] : 0); return; }
    int changed = !g_czw[slot].w.ok || memcmp(&g_czw[slot].w.sex, &w.sex, sizeof w.sex) || memcmp(&g_czw[slot].w.it, &w.it, sizeof w.it);
    g_czw[slot].w = w; g_czw[slot].at = GetTickCount64();
    if (changed) CZ_LOG("customize look: slot %u outfit WLF %s %u/%u/%u/%u/%u, SERAPHITES %s %u/%u/%u/%u/%u (applies at its next spawn)", slot,
                        w.sex[0] ? "f" : "m", w.it[0][0], w.it[0][1], w.it[0][2], w.it[0][3], w.it[0][4],
                        w.sex[1] ? "f" : "m", w.it[1][0], w.it[1][1], w.it[1][2], w.it[1][3], w.it[1][4]);
}
