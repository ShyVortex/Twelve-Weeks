// fac13ui.c - the 2013 Factions page header of the clan event and post-match pages ("factions +
// modernization, not pure modernization"). Widgets: tools/features/clan_widgets.py f13_header (one set per page, under anim-group):
//   f13IcW / f13IcS   the faction's person pictogram (WLF pale blue / Seraphite red), one shown
//   f13Day            "WEEK n: DAY d"            f13Lab   the page's label, right aligned ("INCOMING EVENT", "SUPPLIES", ...)
//   f13Sv             "DAYS SURVIVED n | 84"     f13Pip0..83  one tick per day of the 12 weeks (survived bright, the rest faint)
//   f13Today          the cyan tick on today's day
// Included before the post-match page code (t2r-ext.c, next to pmsfx.c). The MISSIONS page keeps the No Return header (pmnr_header).

#define F13_PIP_STEP 8.0f                 // clan_widgets.py F13_PIP_* (x of day k = X0 + (k / 7) * WEEK_STEP + (k % 7) * STEP)
#define F13_WEEK_STEP 68.0f
#define F13_PIP_X0 (3700.0f - 12.0f * F13_WEEK_STEP + 12.0f)
#define F13_PIP_Y 198.0f
#define F13_PIP_ON (230.0f / 255.0f)      // gui2-set-widget-alpha is absolute: the built alpha is 40
#define F13_PIP_OFF (40.0f / 255.0f)

static float f13_pip_x(int k) { return F13_PIP_X0 + (k / 7) * F13_WEEK_STEP + (k % 7) * F13_PIP_STEP; }

static void f13_header(int fac, const char *label, int day, int survived) {
    char b[64], p[48];
    int d = day < 0 ? 0 : day > 83 ? 83 : day, sv = survived < 0 ? 0 : survived > 84 ? 84 : survived;
    ui_visible("anim-group.f13IcW", fac != 2);
    ui_visible("anim-group.f13IcS", fac == 2);
    snprintf(b, sizeof b, "WEEK %d: DAY %d", d / 7 + 1, d % 7 + 1);
    ui_text("anim-group.f13Day", b);
    ui_text("anim-group.f13Lab", label ? label : "");
    snprintf(b, sizeof b, "DAYS SURVIVED %d | 84", sv);
    ui_text("anim-group.f13Sv", b);
    for (int k = 0; k < 84; k++) {
        snprintf(p, sizeof p, "anim-group.f13Pip%d", k);
        uint64_t w = ui_w(p);
        if (w) w_alpha(w, k < sv ? F13_PIP_ON : F13_PIP_OFF);
    }
    ui_visible("anim-group.f13Today", sv < 84);
    uint64_t t = ui_w("anim-group.f13Today");
    if (t) w_pivot(t, f13_pip_x(sv < 84 ? sv : 83), F13_PIP_Y - 4.0f);
}
