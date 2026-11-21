// Launch notice: once per game start, the unfinished-state notice (to1/launch-notice, tools/features/notice_widgets.py; look =
// launch_notice_preview.py mockup v2). It is pushed on the MP menu while the TWELVE WEEKS entry page (loadseq.c, TITLE stack, drawn over the
// menu stack) still covers the screen, and loadseq holds its hand-off fade until the notice is up - so when the title fades out the notice
// is already there (it happens under the twelve weeks loading screen).
//   - I ACKNOWLEDGE is locked for LN_READ_MS from the moment the title has gone (countdown in its label, a bar along the box's bottom edge
//     empties); CLOSE / CLOSE, DON'T SHOW AGAIN are greyed until it is ticked. Back does nothing (the notice must be acknowledged).
//   - CLOSE, DON'T SHOW AGAIN writes t2r-notice.txt ("seen <LN_VER>") next to the exe; LN_VER goes up when the text changes enough to show
//     it to everyone again. After the first close the notice never comes back in this run (not after matches).
//   - while it is due / up, the clan pages (side pick, event, post-match ...) wait (feature_clan: ln_busy()).
//   - text: English with <font color> emphasis; the loc layer translates it piece by piece (tools/loc/pl/11-notice.txt).
//   - keyboard / pad: up / down / left / right + select; mouse: hover focuses, a click acts on the control under the cursor.
// t2r-test-autofind.txt (A/B automation): ticks + closes itself once unlocked.   Logs: 'notice: ...'.   Included from t2r-ext.c before the clan event code.
#define LN_READ_MS 10000
#define LN_VER 2                       // 2 = public release: shown again once to everyone, even after DON'T SHOW AGAIN on 1
#define LN_EM "<font color=\"#ECE9E2\">"
static struct { int st, pushes; uint64_t pushed_at, hold_t0; } g_ln;    // st: 0 unknown, 1 due, 2 pushed, 3 up, 4 done
static uint64_t g_ln_page;
static int ln_seen(void) {
    FILE *f = exe_side_open("t2r-notice.txt", "r");
    if (!f) return 0;
    int v = 0; if (fscanf(f, "seen %d", &v) != 1) v = 0;
    fclose(f);
    return v >= LN_VER;
}
static void ln_init(void) {
    if (g_ln.st) return;
    if (!g_ln_page) g_ln_page = page_id("launch-notice");
    if (ln_seen()) { g_ln.st = 4; xlog("notice: not shown (t2r-notice.txt: seen, version %d)", LN_VER); }
    else { g_ln.st = 1; xlog("notice: due this launch (version %d)", LN_VER); }
}
static int ln_busy(void) { ln_init(); return g_ln.st >= 1 && g_ln.st <= 3; }
// loadseq.c: hold the entry page's hand-off fade while the notice is due but not up yet (at most 4 s: a notice that never comes must not
// keep the title on screen)
static int ln_hold_fade(uint64_t now) {
    ln_init();
    if (g_ln.st != 1 && g_ln.st != 2) return 0;
    if (!g_ln.hold_t0) { g_ln.hold_t0 = now; xlog("notice: the title's hand-off fade waits for the notice"); }
    if (now - g_ln.hold_t0 < 4000) return 1;
    static int nl; if (LOGCAP(nl, 1)) xlog("notice: not up 4 s after the hand-off - the title fades anyway");
    return 0;
}
static int ui_select_is_mouse(void);
static void ln_fill(int left_s) {
    char b[160];
    ui_text("anim-group.lnBox.lnP0", "TWELVE WEEKS IS OUT, BUT IT IS STILL " LN_EM "UNFINISHED</font>. THIS IS AN EARLY, WORK-IN-PROGRESS RELEASE, " LN_EM "NOT THE FINISHED GAME</font>.");
    ui_text("anim-group.lnBox.lnHead", "WHAT THAT MEANS");
    ui_text("anim-group.lnBox.lnB0", "PERFORMANCE IS " LN_EM "NOT FINAL</font>: STUTTERS, LONG LOADS AND FRAME DROPS CAN HAPPEN.");
    ui_text("anim-group.lnBox.lnB1", "GAMEPLAY IS " LN_EM "NOT FINAL</font>: WEAPONS, MELEE, MAPS AND BALANCE STILL CHANGE FROM UPDATE TO UPDATE.");
    ui_text("anim-group.lnBox.lnB2", "EXPECT " LN_EM "BUGS AND CRASHES</font>, DISCONNECTS, BROKEN ANIMATIONS AND ROUGH EDGES.");
    ui_text("anim-group.lnBox.lnB3", "SOME FEATURES ARE " LN_EM "MISSING OR PLACEHOLDER</font>.");
    ui_text("anim-group.lnBox.lnP1", "BY PLAYING, YOU AGREE TO REPORT THE BUGS YOU FIND WITH " LN_EM "REPORT A BUG</font> IN THE LAUNCHER. SAY WHAT HAPPENED AND WHERE. EVERY REPORT HELPS.");
    // (the countdown flickered every second - the timer fix: double-buffered through the hidden twin lnAckB)
    if (left_s > 0) { snprintf(b, sizeof b, "I ACKNOWLEDGE (%d)", left_s); ui_text_db("anim-group.lnBox.lnCheck.lnAck", b); }
    else ui_text_db("anim-group.lnBox.lnCheck.lnAck", "I ACKNOWLEDGE");
    ui_text("anim-group.lnBox.lnBtn0.lnBtn0Tx", "CLOSE");
    ui_text("anim-group.lnBox.lnBtn1.lnBtn1Tx", "CLOSE, DON'T SHOW AGAIN");
}
static void ln_put(const char *path, float *last, float a) {      // alpha writes only on change (re-asserted every 30 frames)
    if (*last == a && g_frame % 30) return;
    *last = a; w_alpha(ui_w(path), a);
}
static void ln_vis(const char *path, int *last, int on) {
    if (*last == on && g_frame % 30) return;
    *last = on; ui_visible(path, on);
}
static void ln_close(int never) {
    if (never) {
        FILE *f = exe_side_open("t2r-notice.txt", "w");
        if (f) { fprintf(f, "seen %d\n", LN_VER); fclose(f); }
        xlog("notice: closed - don't show again (t2r-notice.txt %s)", f ? "written" : "NOT written");
    } else xlog("notice: closed");
}
static void ln_page(int entered) {
    static uint64_t t0, read_t0, out_at; static int focus, ticked, h_sel, h_back, h_u, h_d, h_l, h_r, refill, gone, last_left, hov_last, never;
    static float a_ck, a_b0, a_b1, a_fr, a_grp, a_dim, a_tm; static int v_tick, v_fo0, v_fo1, v_icon;
    uint64_t now = GetTickCount64();
    if (entered) {
        g_ln.st = 3; g_ln.pushes = 0;
        t0 = now; read_t0 = 0; out_at = 0; focus = 0; ticked = 0; gone = 0; refill = 10; last_left = -1; hov_last = -1; never = 0;
        h_sel = h_back = h_u = h_d = h_l = h_r = 1;              // whatever is held when the page opens
        a_ck = a_b0 = a_b1 = a_fr = a_grp = a_dim = a_tm = -1.0f; v_tick = v_fo0 = v_fo1 = v_icon = -1;
        ln_fill(LN_READ_MS / 1000);
        xlog("notice: page up (%s)", g_lds_hold ? "under the TWELVE WEEKS title" : "over the MP menu");
    } else if (refill && !--refill) ln_fill(last_left > 0 ? last_left : 0);
    if (gone) { w_alpha(ui_w("anim-group"), 0.0f); w_alpha(ui_w("lnDimG"), 0.0f); return; }
    // the reading clock starts once the title has gone (the page may come up under it)
    if (!read_t0 && !g_lds_hold) { read_t0 = now; xlog("notice: on screen - %d s reading lock", LN_READ_MS / 1000); }
    int64_t rd = read_t0 ? (int64_t)(now - read_t0) : 0;
    int locked = !read_t0 || rd < LN_READ_MS;
    int left = locked ? (int)((LN_READ_MS - rd + 999) / 1000) : 0;
    if (left != last_left) { last_left = left; ln_fill(left); }
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &h_sel);
    int back = menu_edge(fnv64("menu-back"), &h_back);
    int up = menu_edge(0xb470a102b9a3f2d0ULL /* menu-up */, &h_u), dn = menu_edge(0x14d6eedde980c845ULL /* menu-down */, &h_d);
    int lf = menu_edge(0xe087ad207d99e6a0ULL /* menu-left */, &h_l), rt = menu_edge(0xa23d5059e72fc835ULL /* menu-right */, &h_r);
    if (out_at) {                                   // leaving: box + dim fade out in 0.3 s, then the page pops
        float f = 1.0f - (float)(now - out_at) / 300.0f;
        if (f < 0.0f) f = 0.0f;
        w_alpha(ui_w("anim-group"), f); w_alpha(ui_w("lnDimG"), f);
        if (now - out_at >= 300) { gone = 1; g_ln.st = 4; pop_page(); ln_close(never); }
        return;
    }
    // mouse: the control under the cursor takes the focus when the cursor moves onto it; a click acts on the control under the cursor
    int hov = -1;
    if (!locked) {
        if (ui_mouse_over("anim-group.lnBox.lnCheck", 1)) hov = 0;
        else if (ticked && ui_mouse_over("anim-group.lnBox.lnBtn0", 1)) hov = 1;
        else if (ticked && ui_mouse_over("anim-group.lnBox.lnBtn1", 1)) hov = 2;
    }
    if (hov >= 0 && hov != hov_last && hov != focus) { focus = hov; ui_sfx("sfx-cycle"); }
    hov_last = hov;
    int act = -1;
    if (g_click_edge && hov >= 0) act = hov;
    else if (sel && !ui_select_is_mouse()) act = focus;
    if (g_test_autofind && !locked && now - read_t0 > LN_READ_MS + 1000) { if (!ticked) act = 0; else { act = 1; xlog("test autofind: notice closed"); } }
    if (back || (sel && act < 0 && !ui_select_is_mouse())) ui_sfx("sfx-menu-error");
    if (act == 0) {
        if (locked) ui_sfx("sfx-menu-error");
        else { ticked = !ticked; focus = ticked ? 1 : 0; ui_sfx("sfx-select"); xlog("notice: %s", ticked ? "acknowledged" : "unticked"); }
    } else if (act == 1 || act == 2) {
        if (ticked) { never = act == 2; out_at = now; ui_sfx("sfx-select"); }
        else ui_sfx("sfx-menu-error");
    }
    if (!locked && act < 0) {                        // keyboard / pad focus moves (the buttons only once ticked)
        int f0 = focus;
        if (ticked) {
            if (up && focus > 0) focus = 0;
            else if (dn && focus == 0) focus = 1;
            else if (lf && focus == 2) focus = 1;
            else if (rt && focus == 1) focus = 2;
        } else focus = 0;
        if (focus != f0) ui_sfx("sfx-cycle");
    }
    // look
    float fin = (float)(now - t0) / 300.0f; if (fin > 1.0f) fin = 1.0f;
    ln_put("anim-group", &a_grp, fin);
    ln_put("lnDimG", &a_dim, fin);
    ln_put("anim-group.lnBox.lnCheck", &a_ck, locked ? 0.4f : 1.0f);
    ln_put("anim-group.lnBox.lnCheck.lnCheckFr", &a_fr, locked ? 0.35f : focus == 0 ? 1.0f : 0.45f);
    ln_put("anim-group.lnBox.lnBtn0", &a_b0, ticked ? 1.0f : 0.35f);
    ln_put("anim-group.lnBox.lnBtn1", &a_b1, ticked ? 1.0f : 0.35f);
    ln_vis("anim-group.lnBox.lnCheck.lnTick", &v_tick, ticked);
    ln_vis("anim-group.lnBox.lnBtn0.lnBtn0Fo", &v_fo0, ticked && focus == 1);
    ln_vis("anim-group.lnBox.lnBtn1.lnBtn1Fo", &v_fo1, ticked && focus == 2);
    ln_vis("anim-group.lnHint.lnHintIcon", &v_icon, !locked);
    ui_text_db("anim-group.lnHint.lnHintTx", locked ? "READ THE NOTICE" : ticked ? "SELECT" : "TICK");
    float tm = !read_t0 ? 1.0f : locked ? 1.0f - (float)rd / LN_READ_MS : 0.0f;
    if (fabsf(tm - a_tm) > 0.002f || (tm == 0.0f && a_tm != 0.0f)) {
        a_tm = tm;
        uint64_t w = ui_w("anim-group.lnBox.lnTimer");
        if (tm > 0.0f) { w_visible(w, 1); w_scale(w, tm, 1.0f); } else w_visible(w, 0);
    }
}
// the click gate (ui_click_gate_tick): the notice's clickable controls under the cursor
static int ln_click_hit(void) {
    return ui_mouse_over("anim-group.lnBox.lnCheck", 1) || ui_mouse_over("anim-group.lnBox.lnBtn0", 1) || ui_mouse_over("anim-group.lnBox.lnBtn1", 1);
}
// once a frame (main tick): push the notice when the MP menu is on top
static void ln_tick(void) {
    ln_init();
    uint64_t top = top_page(), now = GetTickCount64();
    if (g_ln.st == 4) {      // done: a popped page can still be drawn 1-2 frames - kept at alpha 0 (no ghost, never re-entered)
        if (top == g_ln_page) { w_alpha(ui_w("anim-group"), 0.0f); w_alpha(ui_w("lnDimG"), 0.0f); }
        return;
    }
    static uint64_t PMAIN, last_top;
    if (!PMAIN) PMAIN = page_id("main-menu");
    int entered = top != last_top;
    last_top = top;
    if (top == g_ln_page) { ln_page(entered || g_ln.st != 3); return; }
    if (g_ln.st == 3) { g_ln.st = 4; xlog("notice: page gone (closed another way)"); return; }
    if (top != PMAIN) return;
    if (g_ln.st == 2) {
        if (now - g_ln.pushed_at <= 1500) return;
        if (g_ln.pushes >= 3) { g_ln.st = 4; xlog("notice: to1/launch-notice never came up - dropped"); return; }
    }
    push_page("to1/launch-notice");
    g_ln.st = 2; g_ln.pushes++; g_ln.pushed_at = now;
    xlog("notice: to1/launch-notice pushed (try %d, entry %s)", g_ln.pushes, g_lds_hold ? "title still up" : "title gone");
}
