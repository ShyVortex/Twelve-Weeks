// ---------------------------------------------------------------- the styled HUD notification
// Included by t2r-ext.c after denynote.c (one translation unit). Log prefix 'notify:'. Widgets: notify_widgets.py (t2rNtL / t2rNtM / t2rNtR =
// soft dark feathered rectangle in three pieces, t2rNtIc = icon, all in hud-root). Off: t2r-old-notify.txt next to the exe (polled every 2 s)
// = the old paths (t2rMsg line / nametag-style line / blocked panel / engine message) as before.
//
// Every gameplay notification of ours ends here: msg_hook (the HUD message line: "Teammate is healing you", loadout, interrogation, supply
// box ... and winmm's own calls), msg_tag (nametag-style: marked, Covert Training refusal), notice.c (server notices), dn_show in the match HUD
// (gun limit "Too many of X on team", "Something is in the way"). On the picker pages dn_show keeps its panel. Outside the match HUD
// (substate != 6) the old plain message path stays.
//
// Look (restyled: the flat card looked generic; now TLOU2's own soft backing language): ONE box at a time, horizontally centred,
// vertically on the radar's centre (the radar's centre vector at winmm .rdata 0x1800A79D0, lane 0 = screen y in the 1280 x 720 text space,
// after install_radar_shift's +72), no panel and no bar: a soft uneven dark smudge = three stacked copies of the game's own soft blob texture
// (hud/status-effects/radial-gradient-arrow.png, black-tinted; NTF_BLOBS), the game's own notification badge as icon, the text
// drawn with the nametags' own routine (winmm 0x1800039D0, font + outline of every nametag; measured with 0x1800051B0) wrapped to at most 2 lines
// inside NTF_MAXW, a small icon per kind at the left. A new one that arrives while one shows waits in a queue of 4 (identical text is dropped).
// Timing like the HUD's message line: 150 ms fade in, 300 ms fade out. Strings / icon path are written while hidden and shown one frame later.
#define NTF_BLOB_W0  1000.0f     // = notify_widgets.BLOB_W (unscaled blob widget, canvas units)
#define NTF_BLOB_H0  400.0f      // = notify_widgets.BLOB_H
#define NTF_TXT_PX   18.0f       // text line height in the 1280 x 720 text space (a nametag is ~16; the killfeed 18)
#define NTF_PITCH    23.0f       // two-line pitch
#define NTF_PADX     26.0f       // padding left / right of the content (the smudge reaches well beyond it)
#define NTF_PADY     14.0f
#define NTF_ICON_PX  28.0f       // = notify_widgets.ICON / 3
#define NTF_LAST_PX  44.0f       // NTF_LAST (the 2013 Last One Standing frame): the figure is drawn this big, centred ABOVE the text (the icon widget scaled)
#define NTF_LAST_GAP 4.0f
// the smudge: per blob (width = box w * wm + wa, height = box h * hm + ha, centre offset dx * box w / dy * box h, peak alpha); same numbers as
// notify_preview.py NT_BLOBS (the offline preview of this look)
static const float NTF_BLOBS[3][7] = {{1.18f, 70.0f, 1.45f, 16.0f, 0.00f, 0.00f, 0.60f}, {0.78f, 36.0f, 1.30f, 10.0f, -0.20f, 0.07f, 0.36f},   // lighter, smaller, flatter (was 0.94 / 0.60 / 0.55)
                                      {0.64f, 24.0f, 1.20f, 8.0f, 0.24f, -0.06f, 0.32f}};
#define NTF_TOP_Y    105.0f      // vertical centre in the 1280 x 720 text space
#define NTF_GAP      10.0f
#define NTF_MAXW     430.0f      // widest line before wrapping
#define NTF_HARDW    760.0f      // a line wider than this (one long word) shrinks the whole text
#define NTF_QN       6
// (the 2013 Interrogation banner): a LONG thin bar with the SAME background as the toast (the three soft blobs), ONE long line of gold text, no icon, centred
// at 1080p x 960 / text cap top y 286 .. baseline 310 (centre line 298 px = 198.7 in the 1280 x 720 text space), font 33 px at 1080p (= 22 text px), colour #E1B23C. Pops in on one
// frame (no fade-in), holds, fades in 0.15 s; queued like the toasts so no two overlap (ntf_banner). The geometry numbers are mirrored by tools/lockbox_banner_preview.py.
#define NTF_BAN_PX   26.5f
#define NTF_BAN_CY   198.7f
#define NTF_BAN_PADX 34.0f
#define NTF_BAN_PADY 4.5f
// the banner's bar = three flat overlapping pieces of the same blob (a long rectangle with straight top / bottom, feathered ends) instead of the toast's oval smudge
static const float NTF_BAN_BLOBS[3][7] = {{0.62f, 60.0f, 0.0f, 34.0f, -0.30f, -0.08f, 0.62f}, {0.62f, 60.0f, 0.0f, 34.0f, 0.0f, -0.08f, 0.62f}, {0.62f, 60.0f, 0.0f, 34.0f, 0.30f, -0.08f, 0.62f}};
#define NTF_BAN_COL  0x00DCE6EAu  // the toast's own text colour (not yellow)
// the game's own notification badges where it has one (TLOU2 hud/notification/notifications_icons: confirmed decodable in gui2-textures-common.pak, the
// pak the picker pages draw from too - empty-slot.png is used there), our thin copies of their ring style for the '!' / 'i' otherwise
static const char *const NTF_ICON[NTF_N] = {
    "streaming/t2r/icons/notify-info.png",                                            // INFO
    "streaming/t2r/icons/notify-heal.png",                // HEAL
    "streaming/t2r/icons/notify-revive.png",     // REVIVE (handshake)
    "streaming/t2r/icons/notify-warn.png",                                            // WARN ('!' ring)
    "streaming/t2r/icons/notify-info.png",                    // SERVER (the info icon, not the notice book)
    "streaming/t2r/icons/notify-loadout.png",           // LOADOUT (wrench + screwdriver)
    "streaming/t2r/icons/notify-covert.png",            // COVERT (hooded)
    "streaming/t2r/icons/notify-move.png",   // MOVE (chevrons: vault / traversal)
    "streaming/t2r/icons/notify-craft.png",           // CRAFT (supplies jar)
    "streaming/t2r/icons/notify-blade.png",              // BLADE (shiv: interrogation / execute)
    "streaming/t2r/icons/notify-bomb.png",          // BOMB
    "streaming/t2r/icons/notify-supply.png",
    "streaming/t2r/icons/notify-last.png",          // LAST
    // LB1O..LB3T (an icon with every lockbox stage notification, like Last One Standing; white, with the ENEMY faction's logo; lockbox_stage_icon.py):
    // the lockbox marker's ring with the stages filled around the wolf head / scar mark. These are the WLF ones; ntf_icon_of() swaps in the Seraphite set
    // when the enemy team wears Seraphites. Ours and theirs share the icon (the enemy is on it either way).
    "streaming/t2r/icons/notify-lb1-wlf.png", "streaming/t2r/icons/notify-lb2-wlf.png", "streaming/t2r/icons/notify-lb3-wlf.png",
    "streaming/t2r/icons/notify-lb1-wlf.png", "streaming/t2r/icons/notify-lb2-wlf.png", "streaming/t2r/icons/notify-lb3-wlf.png"};  // (LAST (Last One Standing: the 2013 standing figure ABOVE the text; last_standing_icon.py)       // SUPPLY (the clan supply satchel: 2013 supplies glyph, off-white, satchel_icon.py)
static const char *ntf_icon_path(int kind) { return kind >= 0 && kind < NTF_N ? NTF_ICON[kind] : NTF_ICON[NTF_INFO]; }
static const char *const NTF_KIND[NTF_N] = {"info", "heal", "revive", "warn", "server", "loadout", "covert", "move", "craft", "blade", "bomb", "supply", "last",
                                            "lb1-ours", "lb2-ours", "lb3-ours", "lb1-theirs", "lb2-theirs", "lb3-theirs"};
static int ntf_is_lb(int kind) { return kind >= NTF_LB1O && kind <= NTF_LB3T; }
static int ntf_icon_up(int kind) { return kind == NTF_LAST || ntf_is_lb(kind); }       // the icon drawn big ABOVE the text (NTF_LAST_PX), not at its left
static int music_faction(void);       // t2r-ext.c: the faction OUR team wears here (0 WLF, 1 Seraphites); the enemy team wears the other (client-side faction looks)
static const char *ntf_icon_of(int kind) {
    static const char *const SCAR[3] = {"streaming/t2r/icons/notify-lb1-scar.png", "streaming/t2r/icons/notify-lb2-scar.png", "streaming/t2r/icons/notify-lb3-scar.png"};
    if (ntf_is_lb(kind) && music_faction() == 0) return SCAR[(kind - NTF_LB1O) % 3];   // we wear WLF -> the enemy is Seraphite
    return NTF_ICON[kind];
}
typedef struct { int kind; float secs; char text[200]; uint64_t t_enq; int banner; } ntf_item_t;
static ntf_item_t g_ntfq[NTF_QN];
static int g_ntfqn;
static volatile LONG g_ntf_lock;
static uint64_t g_ntfw[4];                      // t2rNtL, t2rNtM, t2rNtR, t2rNtIc
static int g_ntf_ok;                            // widgets resolved for this match
static int g_ntf_old_flag; static uint64_t g_ntf_old_chk;
static struct { int st, kind, nl, banner; char text[200], line[2][160]; float lw[2], tbw, size, th, innerw, boxh, cy, tcy, a, la; int up; uint64_t t0, until, set_frame, key; int menu; ntf_item_t it; } g_ntf;   // st 0 idle, 1 written (hidden, waits a frame), 2 shown
static void ntf_lock(void) { while (__sync_lock_test_and_set(&g_ntf_lock, 1)) YieldProcessor(); }
static void ntf_unlock(void) { __sync_lock_release(&g_ntf_lock); }
static int ntf_has(const char *s, const char *w) {      // case-insensitive substring
    size_t n = strlen(w);
    for (; *s; s++) if (!_strnicmp(s, w, n)) return 1;
    return 0;
}
static int ntf_kind_of(const char *t) {
    // the icon follows the CONTEXT: the '!' ring only for real alerts (marked, interrogated, lockbox stolen / leaking, defend);
    // checked in this order, first match wins
    if (!t) return NTF_INFO;
    if (!_stricmp(t, "Last One Standing")) return NTF_LAST;                         // lms.c's popup: the 2013 figure over the text
    if (!_strnicmp(t, "Gift:", 5) || ntf_has(t, "crafted a gift")) return NTF_CRAFT;       // Crafter gifts (gift.c)
    if (ntf_has(t, "Covert")) return NTF_COVERT;                                   // "Player can't be marked due to Covert Training III"
    if (ntf_has(t, "been marked")) return NTF_WARN;                                // "You've been marked!"
    if (ntf_has(t, "revive") || ntf_has(t, "reviving")) return NTF_REVIVE;
    if (ntf_has(t, "heal") || ntf_has(t, "health") || ntf_has(t, "medkit") || ntf_has(t, "first aid") || ntf_has(t, "Second Chance")) return NTF_HEAL;
    if (ntf_has(t, "bomb")) return NTF_BOMB;                                       // "TOO MANY BOMBS PLACED", "CAN'T PLACE THE BOMB HERE"
    if (ntf_has(t, "Loadout") || ntf_has(t, "Too many") || ntf_has(t, "Not enough") || ntf_has(t, "per team") || ntf_has(t, "equipped") ||
        ntf_has(t, "on team") || ntf_has(t, "limit")) return NTF_LOADOUT;          // refusals of the pickers / gun limits, loadout changes
    if (ntf_has(t, "in the way") || ntf_has(t, "vault")) return NTF_MOVE;          // "Something is in the way. Vault it first."
    if (ntf_has(t, "being interrogated") || ntf_has(t, "you were interrogated") || ntf_has(t, "stole") || ntf_has(t, "is leaking") ||
        ntf_has(t, "knows where") || ntf_has(t, "defend")) return NTF_WARN;        // real alerts
    if (ntf_has(t, "interrogat") || ntf_has(t, "execute") || ntf_has(t, "shiv")) return NTF_BLADE;   // interrogation / execution / shiv prompts
    if (ntf_has(t, "Crafter") || ntf_has(t, "Scavenger") || ntf_has(t, "Lucky Break") || ntf_has(t, "Gift box") || ntf_has(t, "lockbox") ||
        ntf_has(t, "crafting") || ntf_has(t, "supplies") || ntf_has(t, "ammo")) return NTF_CRAFT;
    if (ntf_has(t, "can't") || ntf_has(t, "cannot")) return NTF_MOVE;
    return NTF_INFO;
}
static int ntf_resolve(void) {
    static uint64_t last_try;
    uint64_t now = GetTickCount64();
    if (last_try && now - last_try < 1000) return 0;
    last_try = now;
    static const char *const N[4] = {"t2rNtL", "t2rNtM", "t2rNtR", "t2rNtIc"};
    for (int i = 0; i < 4; i++) { g_ntfw[i] = hudw(N[i]); if (!g_ntfw[i]) { static int nl; if (LOGCAP(nl, 2)) xlog("notify: %s not in hud-root (older gui2-widgets.pak) - old notification paths stay", N[i]); return 0; } }
    g_ntf_ok = 1;
    xlog("notify: widgets found - styled notifications on");
    return 1;
}
// Called by every notification path. Returns 1 when the styled notification takes the message (the caller does nothing more), 0 for the old path.
// (May be called off the main thread: only queues; the widgets are driven from feature_notify.)
static int ntf_push2(int kind, const char *text, float secs, int banner);
static int ntf_push(int kind, const char *text, float secs) { return ntf_push2(kind, text, secs, 0); }
static int ntf_banner(const char *text, float secs) { return ntf_push2(NTF_INFO, text, secs, 1); }      // the 2013 centre banner (see NTF_BAN_*)
// An urgent toast: queued AHEAD of the waiting toasts (after the banners) and a plain
// toast on screen is cut to its fade-out, so it shows within ~0.3 s.
static int g_ntf_urgent;
static int ntf_alert(int kind, const char *text, float secs) {
    g_ntf_urgent = 1;
    int r = ntf_push2(kind, text, secs, 0);
    g_ntf_urgent = 0;
    return r;
}
static int ntf_push2(int kind, const char *text, float secs, int banner) {
    if (!text || !text[0] || IsBadReadPtr(text, 2)) return 0;
    if (ov_off("t2r-old-notify.txt", &g_ntf_old_flag, &g_ntf_old_chk)) return 0;
    // in the match HUD every kind; on the menu pages server notices only - the other callers keep their menu paths (picker panel, plain line)
    if (match_substate() == 6 ? !g_ntf_ok : kind != NTF_SERVER) return 0;
    if (kind < 0 || kind >= NTF_N) kind = ntf_kind_of(text);
    ntf_lock();
    uint64_t now = GetTickCount64();
    int dup = g_ntf.st && !strncmp(g_ntf.text, text, sizeof g_ntf.text - 1) && now + 500 < g_ntf.until;
    for (int i = 0; i < g_ntfqn && !dup; i++) dup = !strncmp(g_ntfq[i].text, text, sizeof g_ntfq[i].text - 1);
    if (!dup) {
        if (g_ntfqn >= NTF_QN) { memmove(g_ntfq, g_ntfq + 1, sizeof g_ntfq[0] * (NTF_QN - 1)); g_ntfqn = NTF_QN - 1; }   // full: the oldest waiting one gives way
        int at = g_ntfqn;
        if (banner) { at = 0; while (at < g_ntfqn && g_ntfq[at].banner) at++; memmove(g_ntfq + at + 1, g_ntfq + at, sizeof g_ntfq[0] * (size_t)(g_ntfqn - at)); }   // banners go before the toasts, in order among themselves
        else if (g_ntf_urgent) {                                 // urgent: after the banners and the urgent ones already waiting, before the plain toasts
            at = 0; while (at < g_ntfqn && (g_ntfq[at].banner || ntf_is_lb(g_ntfq[at].kind))) at++;
            memmove(g_ntfq + at + 1, g_ntfq + at, sizeof g_ntfq[0] * (size_t)(g_ntfqn - at));
            if (g_ntf.st && !g_ntf.banner && !g_ntf.menu && !ntf_is_lb(g_ntf.kind) && g_ntf.kind != NTF_SERVER && g_ntf.until > now) g_ntf.until = now;   // the plain toast on screen fades out now
        }
        g_ntfqn++;
        ntf_item_t *q = &g_ntfq[at];
        q->kind = kind; q->secs = secs; q->t_enq = now; q->banner = banner;
        snprintf(q->text, sizeof q->text, "%s", text);
    }
    ntf_unlock();
    if (!dup) xlog("notify: %s %s \"%.120s\" %.1f s", banner ? "BANNER" : "kind", NTF_KIND[kind], text, secs);
    return 1;
}
static float ntf_w(const char *s, float size) {
    typedef uint64_t (*fn_meas)(const char *, float);
    if (!s[0]) return 0.0f;
    uint64_t m = ((fn_meas)VMA(0x1800051B0))(s, size);
    float w; uint32_t ml = (uint32_t)m; memcpy(&w, &ml, 4);
    return w > 0.0f && w < 4000.0f ? w : 0.0f;
}
static float ntf_text_size(float px) {                 // nametag-font size for a text line height of `px` in the 1280 x 720 text space (interrogation.c's persistent lines)
    typedef uint64_t (*fn_meas)(const char *, float);
    static float lineh;
    if (!lineh) {
        uint64_t m = ((fn_meas)VMA(0x1800051B0))("Mg", 2.0f);
        float hh; uint32_t mh = (uint32_t)(m >> 32); memcpy(&hh, &mh, 4);
        lineh = hh > 1.0f && hh < 400.0f ? hh / 2.0f : 40.0f;
    }
    return px / lineh;
}
static void ntf_start(const ntf_item_t *it, uint64_t now) {
    typedef uint64_t (*fn_meas)(const char *, float);
    static float lineh;
    if (!lineh) {                                          // the nametag font's line height per size unit ("Mg" at size 2, as kf_measure)
        uint64_t m = ((fn_meas)VMA(0x1800051B0))("Mg", 2.0f);
        float hh; uint32_t mh = (uint32_t)(m >> 32); memcpy(&hh, &mh, 4);
        lineh = hh > 1.0f && hh < 400.0f ? hh / 2.0f : 40.0f;
        xlog("notify: nametag font line height %.2f px per size unit -> text size %.3f for %.0f px", lineh, NTF_TXT_PX / lineh, NTF_TXT_PX);
    }
    float size = (it->banner ? NTF_BAN_PX : NTF_TXT_PX) / lineh;
    const char *tr = loc_tr_draw(it->text);                // localisation (diacritics folded for the raw draw)
    char buf[200]; snprintf(buf, sizeof buf, "%s", tr ? tr : it->text);
    // one line when it fits NTF_MAXW, else the most balanced split into 2 lines (no orphan last word)
    char l0[160] = "", l1[160] = "";
    int nl = 1;
    snprintf(l0, sizeof l0, "%s", buf);
    if (!it->banner && ntf_w(l0, size) > NTF_MAXW) {          // (a banner is ONE long line)
        char *sp[48]; int ns = 0;
        for (char *q = buf; *q && ns < 48; q++) if (*q == ' ' && q > buf && q[-1] != ' ') sp[ns++] = q;
        float best = 1e9f; int bk = -1;
        for (int k = 0; k < ns; k++) {
            char c0[160], c1[160];
            size_t n0 = (size_t)(sp[k] - buf); if (n0 > sizeof c0 - 1) n0 = sizeof c0 - 1;
            memcpy(c0, buf, n0); c0[n0] = 0;
            snprintf(c1, sizeof c1, "%s", sp[k] + 1);
            float m0 = ntf_w(c0, size), m1 = ntf_w(c1, size), mm = m0 > m1 ? m0 : m1;
            if (mm < best) { best = mm; bk = k; }
        }
        if (bk >= 0) {
            size_t n0 = (size_t)(sp[bk] - buf); if (n0 > sizeof l0 - 1) n0 = sizeof l0 - 1;
            memcpy(l0, buf, n0); l0[n0] = 0;
            snprintf(l1, sizeof l1, "%s", sp[bk] + 1);
            nl = 2;
        }
    }
    float w0 = ntf_w(l0, size), w1 = ntf_w(l1, size);
    float mx = w0 > w1 ? w0 : w1;
    if (mx > NTF_HARDW) { size *= NTF_HARDW / mx; w0 *= NTF_HARDW / mx; w1 *= NTF_HARDW / mx; mx = NTF_HARDW; }   // one huge word: shrink, never run off the screen
    memcpy(g_ntf.line[0], l0, sizeof l0); memcpy(g_ntf.line[1], l1, sizeof l1);
    g_ntf.nl = nl; g_ntf.lw[0] = w0; g_ntf.lw[1] = w1; g_ntf.tbw = mx; g_ntf.size = size;
    g_ntf.th = (it->banner ? NTF_BAN_PX : NTF_TXT_PX) * size / ((it->banner ? NTF_BAN_PX : NTF_TXT_PX) / lineh);   // = the nominal px unless shrunk
    g_ntf.banner = it->banner;
    g_ntf.kind = it->kind; g_ntf.menu = 0; g_ntf.it = *it; g_ntf.banner = it->banner;
    snprintf(g_ntf.text, sizeof g_ntf.text, "%s", it->text);
    int up = !it->banner && ntf_icon_up(it->kind);          // the icon above the text, not at its left (NTF_LAST, NTF_LB*)
    float icw = (it->banner || up) ? 0.0f : NTF_ICON_PX + NTF_GAP;
    float innerw = mx + icw;
    float texth = (float)(nl - 1) * NTF_PITCH + g_ntf.th;
    float innerh = texth;
    if (up) { innerh = NTF_LAST_PX + NTF_LAST_GAP + texth; if (innerw < NTF_LAST_PX) innerw = NTF_LAST_PX; }
    else if (innerh < NTF_ICON_PX && !it->banner) innerh = NTF_ICON_PX;
    g_ntf.up = up;
    float boxw = innerw + 2.0f * (it->banner ? NTF_BAN_PADX : NTF_PADX);
    float boxh = innerh + 2.0f * (it->banner ? NTF_BAN_PADY : NTF_PADY);
    g_ntf.innerw = innerw; g_ntf.boxh = boxh;
    // vertical centre = the radar's centre (text space y of the radar's centre vector, read live)
    // moved up to the top centre (the old match timer's place is free) - was the radar's centre (winmm .rdata 0x1800A79D0, ~177)
    float cy = it->banner ? NTF_BAN_CY : NTF_TOP_Y;
    g_ntf.cy = cy;
    g_ntf.tcy = up ? cy + innerh * 0.5f - texth * 0.5f : cy;   // the text block's centre line (under the figure for NTF_LAST)
    // widgets (canvas units = 3 x text px; x is the offset from the screen centre; the blobs are top-left pivoted, scaled about it)
    uint64_t *w = g_ntfw;
    for (int i = 0; i < 4; i++) w_visible(w[i], 0);
    for (int i = 0; i < 4; i++) feed_alpha(w[i], 0.0f);
    for (int i = 0; i < 3; i++) {
        const float *b = it->banner ? NTF_BAN_BLOBS[i] : NTF_BLOBS[i];
        float wp = (boxw * b[0] + b[1]) * 3.0f, hp = (boxh * b[2] + b[3]) * 3.0f;
        w_scale(w[i], wp / NTF_BLOB_W0, hp / NTF_BLOB_H0);
        w_pivot(w[i], b[4] * boxw * 3.0f - wp * 0.5f, (cy + b[5] * boxh) * 3.0f - hp * 0.5f);
    }
    ((fn_settext_t)VMA(0x180068260))(w[3], ntf_icon_of(it->kind));
    if (up) { w_scale(w[3], NTF_LAST_PX / NTF_ICON_PX, NTF_LAST_PX / NTF_ICON_PX); w_pivot(w[3], -NTF_LAST_PX * 1.5f, (cy - innerh * 0.5f) * 3.0f); }   // top-left pivot: scaled about it
    else { w_scale(w[3], 1.0f, 1.0f); w_pivot(w[3], -innerw * 1.5f, (cy - NTF_ICON_PX * 0.5f) * 3.0f); }
    g_ntf.st = 1; g_ntf.set_frame = g_frame; g_ntf.la = -1.0f; g_ntf.a = 0.0f;
    float secs = it->secs;
    g_ntf.until = now + (uint64_t)((secs > 0 && secs < (it->kind == NTF_SERVER ? 600.0f : 30.0f) ? secs : 5.0f) * 1000);
    if (it->banner) ((fn_settext_t)VMA(0x180068260))(w[3], NTF_ICON[NTF_INFO]);   // (the icon widget stays at alpha 0 for a banner)
    xlog("notify: show %s \"%.100s\" %d line(s) box %.0f x %.0f px at y %.1f (radar centre), %.1f s", NTF_KIND[it->kind], g_ntf.text, nl, boxw, boxh, cy,
         (double)(g_ntf.until - now) / 1000.0);
}
// The sound of a toast: our toasts had none, so it is the game's own "new item / journal entry added" chime
// (sfx-tutorial-journal-entry-added, bank gbl-hud, re/journal-notify-1020.md), falling back to the stock menu tick (sfx-cycle, gbl-menu) where that
// event is not loaded (menus). Played once when the toast turns visible. Logs "notify: sound ..." (first 12).
static void ntf_sound(void) {
    static const char *const S[] = {"sfx-tutorial-journal-entry-added", "sfx-cycle"};
    static int nl;
    for (int i = 0; i < 2; i++) {
        uint64_t a[2] = {fnv64(S[i]), 0};
        uint64_t r = dc_call(fnv64("play-sound"), 2, a);
        if (r != 0 && r != ~0ULL) { if (LOGCAP(nl, 12)) xlog("notify: sound %s -> %llx", S[i], (unsigned long long)r); return; }
        if (LOGCAP(nl, 12)) xlog("notify: sound %s not available (%llx)", S[i], (unsigned long long)r);
    }
}
// Menu pages (notify_widgets.add_notify_menu): the same five widgets under each page's anim-group. key = page + its anim-group handle (a rebuilt page = new key).
#define NTF_MENU_CY 95.0f        // vertical centre in text px: top centre - the title blocks are top-left and the lists start at ~170 px (510 units); a 2-line toast ends at ~130
static int ntf_menu_resolve(uint64_t w[5], uint64_t *key) {
    static const char *const N[5] = {"anim-group.t2rNfL", "anim-group.t2rNfM", "anim-group.t2rNfR", "anim-group.t2rNfIc", "anim-group.t2rNfTx"};
    uint64_t tp = top_page();
    if (!tp) return 0;
    for (int i = 0; i < 5; i++) { w[i] = ui_w(N[i]); if (!w[i]) return 0; }
    *key = tp ^ ui_w("anim-group") * 0x9E3779B97F4A7C15ULL ^ 3;
    return 1;
}
static void ntf_start_menu(const ntf_item_t *it, uint64_t now, uint64_t *w, uint64_t key) {
    const char *tr = loc_tr(it->text);
    char buf[320]; int nl = dn_wrap_w(tr ? tr : it->text, buf, sizeof buf, NTF_MAXW * 3.0f);
    float mxu = 0.0f;
    for (char *p = buf; *p; ) {
        char *e = strchr(p, '\n'); char seg[200]; size_t n = e ? (size_t)(e - p) : strlen(p); if (n > sizeof seg - 1) n = sizeof seg - 1;
        memcpy(seg, p, n); seg[n] = 0;
        float lw = feed_text_w(seg, 36.0f / 30.0f); if (lw > mxu) mxu = lw;
        if (!e) break;
        p = e + 1;
    }
    // measured on A: the 30-glyph line drew ~243 px wide against the 206 estimated (the text widget's font runs wider than the feed's),
    // so the centred text spilled left over the icon - widen the estimate to the measured width
    float mx = mxu / 3.0f * 1.18f;
    float innerw = mx + NTF_ICON_PX + NTF_GAP, innerh = (float)nl * 20.0f; if (innerh < NTF_ICON_PX) innerh = NTF_ICON_PX;
    float boxw = innerw + 2.0f * NTF_PADX, boxh = innerh + 2.0f * NTF_PADY, cy = NTF_MENU_CY;
    g_ntf.innerw = innerw; g_ntf.boxh = boxh; g_ntf.cy = cy; g_ntf.tcy = cy; g_ntf.up = 0; g_ntf.nl = nl;
    for (int i = 0; i < 5; i++) { w_visible(w[i], 0); feed_alpha(w[i], 0.0f); }
    for (int i = 0; i < 3; i++) {
        const float *b = NTF_BLOBS[i];
        float wp = (boxw * b[0] + b[1]) * 3.0f, hp = (boxh * b[2] + b[3]) * 3.0f;
        w_scale(w[i], wp / NTF_BLOB_W0, hp / NTF_BLOB_H0);
        w_pivot(w[i], b[4] * boxw * 3.0f - wp * 0.5f, (cy + b[5] * boxh) * 3.0f - hp * 0.5f);
    }
    ((fn_settext_t)VMA(0x180068260))(w[3], ntf_icon_of(it->kind));
    w_pivot(w[3], -innerw * 1.5f, (cy - NTF_ICON_PX * 0.5f) * 3.0f);
    ((void (*)(uint64_t, const char *))VMA(0x180064450))(w[4], buf);                        // the text widget: 1500 x 250 units, centred in both axes
    w_pivot(w[4], (-innerw * 0.5f + NTF_ICON_PX + NTF_GAP + mx * 0.5f) * 3.0f - 750.0f, cy * 3.0f - 125.0f);
    g_ntf.menu = 1; g_ntf.key = key; g_ntf.it = *it; g_ntf.kind = it->kind; g_ntf.banner = 0;
    snprintf(g_ntf.text, sizeof g_ntf.text, "%s", it->text);
    g_ntf.st = 1; g_ntf.set_frame = g_frame; g_ntf.la = -1.0f; g_ntf.a = 0.0f;
    g_ntf.until = now + (uint64_t)((it->secs > 0 && it->secs < 600.0f ? it->secs : 5.0f) * 1000);
    xlog("notify: show %s \"%.100s\" in the menus (page 0x%llx) %d line(s) box %.0f x %.0f px at y %.1f, %.1f s", NTF_KIND[it->kind], g_ntf.text,
         (unsigned long long)top_page(), nl, boxw, boxh, cy, (double)(g_ntf.until - now) / 1000.0);
}
static void ntf_requeue_front(const ntf_item_t *it, float secs) {
    ntf_lock();
    if (g_ntfqn < NTF_QN) { memmove(g_ntfq + 1, g_ntfq, sizeof g_ntfq[0] * (size_t)g_ntfqn); g_ntfq[0] = *it; g_ntfq[0].secs = secs; g_ntfqn++; }
    ntf_unlock();
}
// drops a notification by its text: still queued -> removed; showing -> fades out right away (~100 ms). (melee_dodge.c: the "DODGE" fallback must not outlive its window)
static void ntf_cancel(const char *text) {
    if (!text) return;
    ntf_lock();
    int k = 0;
    for (int i = 0; i < g_ntfqn; i++) if (strncmp(g_ntfq[i].text, text, sizeof g_ntfq[i].text - 1)) g_ntfq[k++] = g_ntfq[i];
    g_ntfqn = k;
    if (g_ntf.st && !strncmp(g_ntf.it.text, text, sizeof g_ntf.it.text - 1)) { uint64_t now = GetTickCount64(); if (g_ntf.until > now - 200) g_ntf.until = now - 200; }
    ntf_unlock();
}
static void ntf_drop_nonserver(void) {
    ntf_lock();
    int k = 0;
    for (int i = 0; i < g_ntfqn; i++) if (g_ntfq[i].kind == NTF_SERVER) g_ntfq[k++] = g_ntfq[i];
    g_ntfqn = k;
    ntf_unlock();
}
static void feature_notify(void) {
    uint64_t now = GetTickCount64();
    int hud = match_substate() == 6;
    if (!hud && g_ntf_ok) {
        g_ntf_ok = 0;
        if (g_ntf.st && !g_ntf.menu) {
            // the match HUD is gone: a server toast (admin kick) that was cut moves on to the menu pages instead of vanishing
            float left = (float)((int64_t)g_ntf.until - (int64_t)now) / 1000.0f;
            int kick = msg_is_kick(g_ntf.it.text);
            g_ntf.st = 0;
            if (g_ntf.kind == NTF_SERVER && (kick || left > 1.0f)) { ntf_requeue_front(&g_ntf.it, kick && left < 8.0f ? 8.0f : left); xlog("notify: server toast cut by the match end - carried to the menu (%.1f s)", kick && left < 8.0f ? 8.0f : left); }
        }
        ntf_drop_nonserver();
    }   // (hud-root is rebuilt per level: re-resolved each match)
    if (hud && g_ntf.st && g_ntf.menu) g_ntf.st = 0;                                                  // the menu page's widgets are gone
    if (hud && !g_ntf_ok && !ntf_resolve()) { ntf_lock(); g_ntfqn = 0; ntf_unlock(); return; }
    uint64_t mw[5], key = 0, *w = g_ntfw;
    int nw = 4;
    if (!hud) {
        w = mw; nw = 5;
        if (g_ntf.st) {                                                                               // a toast is up: the page it sits on must still be there
            if (!ntf_menu_resolve(mw, &key)) {                                                        // page closed / no widgets: it moves on to the next page
                float left = (float)((int64_t)g_ntf.until - (int64_t)now) / 1000.0f;
                g_ntf.st = 0;
                if (left > 1.0f) ntf_requeue_front(&g_ntf.it, left);
                return;
            }
            if (key != g_ntf.key) {                                                                   // another page (or the same one rebuilt): start again there
                float left = (float)((int64_t)g_ntf.until - (int64_t)now) / 1000.0f;
                g_ntf.st = 0;
                if (left > 1.0f) { ntf_item_t it = g_ntf.it; it.secs = left; ntf_start_menu(&it, now, mw, key); }
                return;
            }
        }
    }
    if (!g_ntf.st) {
        ntf_item_t it; int have = 0;
        if (hud) {
            ntf_lock();
            if (g_ntfqn) { it = g_ntfq[0]; memmove(g_ntfq, g_ntfq + 1, sizeof g_ntfq[0] * (size_t)(--g_ntfqn)); have = 1; }
            ntf_unlock();
            if (!have) return;
            ntf_start(&it, now);
            return;
        }
        ntf_lock();
        if (g_ntfqn) { it = g_ntfq[0]; have = 1; }
        ntf_unlock();
        if (!have) return;
        if (!ntf_menu_resolve(mw, &key)) {                                                            // booting / loading / a page without the widgets: stay queued (never the plain line)
            if (now - it.t_enq > 120000u) { ntf_lock(); if (g_ntfqn) memmove(g_ntfq, g_ntfq + 1, sizeof g_ntfq[0] * (size_t)(--g_ntfqn)); ntf_unlock(); }   // kept lifetime 120 s; its own seconds count from when it first shows
            return;
        }
        ntf_lock(); if (g_ntfqn) memmove(g_ntfq, g_ntfq + 1, sizeof g_ntfq[0] * (size_t)(--g_ntfqn)); ntf_unlock();
        ntf_start_menu(&it, now, mw, key);
        return;
    }
    if (g_ntf.st == 1) {
        if (g_frame <= g_ntf.set_frame) return;            // the icon path / string has had no frame yet
        for (int i = 0; i < nw; i++) w_visible(w[i], 1);
        g_ntf.st = 2; g_ntf.t0 = now;
        if (ntf_is_lb(g_ntf.kind)) int_stage_sting(g_ntf.kind);   // the stage's own stinger instead of the toast chime (interrogation.c)
        else if (!g_ntf.banner) ntf_sound();
    }
    float a = 1.0f;
    if (!g_ntf.banner && now - g_ntf.t0 < 150) a = 0.1f + 0.9f * (float)(now - g_ntf.t0) / 150.0f;     // (a banner pops in on one frame)
    if (now > g_ntf.until) { float o = 1.0f - (float)(now - g_ntf.until) / (g_ntf.banner ? 150.0f : 300.0f); if (o < a) a = o; }
    if (a <= 0.0f) { for (int i = 0; i < nw; i++) { feed_alpha(w[i], 0.0f); w_visible(w[i], 0); } g_ntf.st = 0; g_ntf.a = 0.0f; return; }
    if (hud_menu_up()) a = 0.0f;                       // a menu over the HUD (hud_menu_up): the toast keeps ageing, drawn again when it closes
    g_ntf.a = a;
    if (__builtin_fabsf(a - g_ntf.la) > 0.01f) { for (int i = 0; i < nw; i++) feed_alpha(w[i], i < 3 ? a * (g_ntf.banner ? NTF_BAN_BLOBS[i][6] : NTF_BLOBS[i][6]) : (g_ntf.banner && i == 3) ? 0.0f : a); g_ntf.la = a; }
}
static void feature_notify_draw(void) {
    typedef void (*fn_text_va)(...);
    if (g_ntf.st != 2 || g_ntf.menu || g_ntf.a <= 0.0f || match_substate() != 6) return;
    uint32_t al = (uint32_t)(g_ntf.a * 255.0f + 0.5f) << 24;
    float left = g_ntf.up ? 640.0f - g_ntf.tbw * 0.5f : 640.0f - g_ntf.innerw * 0.5f + (g_ntf.banner ? 0.0f : NTF_ICON_PX + NTF_GAP);   // right of the icon (centred under it for NTF_LAST)
    float y0 = g_ntf.tcy - (float)(g_ntf.nl - 1) * NTF_PITCH * 0.5f - g_ntf.th * 0.5f;
    for (int i = 0; i < g_ntf.nl; i++) {
        if (g_ntf.lw[i] <= 0.0f) continue;
        float x = left + (g_ntf.tbw - g_ntf.lw[i]) * 0.5f;
        ((fn_text_va)VMA(0x1800039D0))(fbits(x), fbits(y0 + (float)i * NTF_PITCH), fbits(g_ntf.size), (uint64_t)((g_ntf.banner ? NTF_BAN_COL : 0x00DCE6EAu) | al), "%s", g_ntf.line[i]);
    }
}
