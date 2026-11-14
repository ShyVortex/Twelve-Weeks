// clanroster.c - the clan roster UI page (expanded immersive clan UI with headshots, journals, portrait variety).
// Included after feature_clan / clan.c (it uses clan state). The widgets are tools/features/clan_roster_widgets.py (page to1/clan-roster);
// like gearup13.c this one is driven ENTIRELY from the tick - no winmm page handler runs for it.
//
// Layout: a grid of portrait cards (up to 60 members, 6 columns, scrollable) + detail panel at the bottom.
// Keys: W/S/A/D navigate the grid, SELECT shows the member's journal (future), BACK closes the page.
// Data: the roster comes from the daemon (0xB4 feed + 0xB7 roster dump), cached in g_cr_roster.

#define CR_MAX 60                   // max clan members
#define CR_COLS 6                   // grid columns
#define CR_VISIBLE 24               // visible cards (6x4)
#define CR_CARD_H 360               // card height for scroll calc

typedef struct {
    int used;
    char name[64];
    int status;                     // 0 = healthy, 1 = hungry, 2 = sick
    int joined_day;
    char role[128];
    char activity[256];
    int portrait_id;                // index into the portrait cast
} cr_member_t;

static cr_member_t g_cr_roster[CR_MAX];
static int g_cr_count;
static int g_cr_faction;            // 1 = WLF, 2 = Seraphites

static struct {
    int up;                         // page is on top
    int focus;                      // focused card index
    int scroll;                     // scroll offset (row * CR_COLS)
    int dirty;                      // needs redraw
    uint64_t enter_ms;
    int h_u, h_d, h_l, h_r, h_back, h_sel;
    int hv_card, mm_last;           // mouse hover
} CR;

static uint64_t cr_page_id(void) { static uint64_t id; if (!id) id = page_id("clan-roster"); return id; }

// ------------------------------------------------------------------ portrait paths
// The 85-member cast is rendered offline (tools/models/portrait_cast/), each as a 256x256 PNG.
// Portrait assignment: hash(member id) mod count-per-bucket, keyed by faction + age/sex category.

static const char *cr_portrait_path(int faction, int portrait_id) {
    static char buf[256];
    // TODO: proper portrait mapping from the cast
    // For now: placeholder empty portrait
    (void)faction; (void)portrait_id;
    snprintf(buf, sizeof buf, "streaming/t2r/clan/portraits/empty.png");
    return buf;
}

// ------------------------------------------------------------------ roster population (from 0xB7 or mock data)
static void cr_clear_roster(void) {
    memset(g_cr_roster, 0, sizeof g_cr_roster);
    g_cr_count = 0;
}

static void cr_add_member(const char *name, int status, int joined_day, const char *role, const char *activity, int portrait_id) {
    if (g_cr_count >= CR_MAX) return;
    cr_member_t *m = &g_cr_roster[g_cr_count++];
    m->used = 1;
    strncpy(m->name, name, sizeof m->name - 1);
    m->status = status;
    m->joined_day = joined_day;
    strncpy(m->role, role, sizeof m->role - 1);
    strncpy(m->activity, activity, sizeof m->activity - 1);
    m->portrait_id = portrait_id;
}

// Mock data for testing (TODO: replace with daemon 0xB7 response)
static void cr_populate_mock(void) {
    cr_clear_roster();
    g_cr_faction = g_clan.faction;
    if (!g_clan.st || g_clan.st > 3) return;
    
    // Generate mock members based on clan state
    int h = g_clan.healthy, u = g_clan.hungry, s = g_clan.sick;
    int total = h + u + s;
    if (total <= 0) return;
    
    static const char *NAMES[] = {
        "Elena", "Marcus", "Sofia", "James", "Lucia", "David", "Maya", "Carlos",
        "Anna", "Michael", "Rosa", "Daniel", "Lisa", "Omar", "Rachel", "Victor",
        "Julia", "Thomas", "Maria", "Joseph", "Nina", "Alex", "Camila", "Ryan"
    };
    static const char *ROLES[] = {
        "Former teacher", "Ex-military", "Nurse", "Mechanic", "Cook", "Scout",
        "Engineer", "Hunter", "Medic", "Guard", "Farmer", "Builder"
    };
    static const char *ACTIVITIES[] = {
        "On patrol near the north gate", "Helping repair the fence", "Resting in the barracks",
        "Training with the recruits", "Recovering in the infirmary", "Standing watch",
        "Sorting supplies", "Searching for food", "Cooking for the group", "On a supply run"
    };
    
    for (int i = 0; i < total && i < CR_MAX; i++) {
        int status = (i < h) ? 0 : (i < h + u) ? 1 : 2;
        cr_add_member(
            NAMES[i % 24],
            status,
            (g_clan.day > 1) ? (1 + (i * 7) % (g_clan.day - 1)) : 1,
            ROLES[i % 12],
            ACTIVITIES[i % 10],
            i % 85  // portrait cast index
        );
    }
}

// ------------------------------------------------------------------ widget filling
static uint64_t g_cr_w[200];        // widget handles
static int g_cr_w_ok;

static void cr_lookup(void) {
    if (g_cr_w_ok) return;
    memset(g_cr_w, 0, sizeof g_cr_w);
    uint64_t pg = cr_page_id();
    
    g_cr_w[0] = widget_lookup(pg, "anim-group.crTitle");
    g_cr_w[1] = widget_lookup(pg, "anim-group.crDay");
    g_cr_w[2] = widget_lookup(pg, "anim-group.crGrid");
    g_cr_w[3] = widget_lookup(pg, "anim-group.crDet");
    g_cr_w[4] = widget_lookup(pg, "anim-group.crUp");
    g_cr_w[5] = widget_lookup(pg, "anim-group.crDn");
    
    // cards: 10 + i*6 = card group, +1 = port, +2 = name, +3 = stat, +4 = frame
    for (int i = 0; i < CR_MAX; i++) {
        char buf[64];
        snprintf(buf, sizeof buf, "anim-group.crGrid.crCard%d", i);
        g_cr_w[10 + i * 6] = widget_lookup(pg, buf);
        snprintf(buf, sizeof buf, "anim-group.crGrid.crCard%d.crPort%d", i, i);
        g_cr_w[11 + i * 6] = widget_lookup(pg, buf);
        snprintf(buf, sizeof buf, "anim-group.crGrid.crCard%d.crName%d", i, i);
        g_cr_w[12 + i * 6] = widget_lookup(pg, buf);
        snprintf(buf, sizeof buf, "anim-group.crGrid.crCard%d.crStat%d", i, i);
        g_cr_w[13 + i * 6] = widget_lookup(pg, buf);
        snprintf(buf, sizeof buf, "anim-group.crGrid.crCard%d.crFrame%d", i, i);
        g_cr_w[14 + i * 6] = widget_lookup(pg, buf);
    }
    
    // detail panel
    g_cr_w[190] = widget_lookup(pg, "anim-group.crDet.crDetPort");
    g_cr_w[191] = widget_lookup(pg, "anim-group.crDet.crDetName");
    g_cr_w[192] = widget_lookup(pg, "anim-group.crDet.crDetRole");
    g_cr_w[193] = widget_lookup(pg, "anim-group.crDet.crDetStatus");
    g_cr_w[194] = widget_lookup(pg, "anim-group.crDet.crDetJoined");
    g_cr_w[195] = widget_lookup(pg, "anim-group.crDet.crDetCur");
    
    g_cr_w_ok = 1;
}

static const uint32_t CR_STAT_COL[] = { 0xFF5DC0DC, 0xFF9C9A9A, 0xFFFD6D51 };  // healthy, hungry, sick
static const char *CR_STAT_NAME[] = { "HEALTHY", "HUNGRY", "SICK" };

static void cr_fill_card(int i) {
    if (i < 0 || i >= CR_MAX) return;
    cr_member_t *m = &g_cr_roster[i];
    int base = 10 + i * 6;
    
    ui_visible2(g_cr_w[base], m->used);
    if (!m->used) return;
    
    ui_image(g_cr_w[base + 1], cr_portrait_path(g_cr_faction, m->portrait_id));
    ui_text2(g_cr_w[base + 2], m->name);
    ui_text2(g_cr_w[base + 3], CR_STAT_NAME[m->status]);
    ui_tint(g_cr_w[base + 3], CR_STAT_COL[m->status]);
}

static void cr_fill_all(void) {
    cr_lookup();
    
    // title
    char buf[128];
    snprintf(buf, sizeof buf, "SURVIVORS (%d)", g_cr_count);
    ui_text2(g_cr_w[0], buf);
    
    snprintf(buf, sizeof buf, "DAY %d / WEEK %d", g_clan.day, (g_clan.day - 1) / 7 + 1);
    ui_text2(g_cr_w[1], buf);
    
    // cards
    for (int i = 0; i < CR_MAX; i++) {
        cr_fill_card(i);
    }
    
    // focus
    cr_fill_detail();
}

static void cr_fill_detail(void) {
    if (CR.focus < 0 || CR.focus >= g_cr_count) {
        ui_visible2(g_cr_w[3], 0);
        return;
    }
    
    cr_member_t *m = &g_cr_roster[CR.focus];
    ui_visible2(g_cr_w[3], 1);
    
    ui_image(g_cr_w[190], cr_portrait_path(g_cr_faction, m->portrait_id));
    
    char buf[256];
    snprintf(buf, sizeof buf, "%s (adult)", m->name);  // TODO: age from roster
    ui_text2(g_cr_w[191], buf);
    ui_text2(g_cr_w[192], m->role);
    ui_text2(g_cr_w[193], CR_STAT_NAME[m->status]);
    ui_tint(g_cr_w[193], CR_STAT_COL[m->status]);
    snprintf(buf, sizeof buf, "Joined on Day %d", m->joined_day);
    ui_text2(g_cr_w[194], buf);
    snprintf(buf, sizeof buf, "\"%s\"", m->activity);
    ui_text2(g_cr_w[195], buf);
    
    // update focus frames
    for (int i = 0; i < CR_MAX; i++) {
        ui_visible2(g_cr_w[14 + i * 6], i == CR.focus);
    }
}

// ------------------------------------------------------------------ navigation
static void cr_move(int dx, int dy) {
    if (g_cr_count <= 0) return;
    
    int col = CR.focus % CR_COLS;
    int row = CR.focus / CR_COLS;
    
    col = (col + dx + CR_COLS) % CR_COLS;
    row += dy;
    if (row < 0) row = 0;
    if (row >= (g_cr_count + CR_COLS - 1) / CR_COLS) row = (g_cr_count + CR_COLS - 1) / CR_COLS - 1;
    
    int nf = row * CR_COLS + col;
    if (nf >= g_cr_count) nf = g_cr_count - 1;
    if (nf < 0) nf = 0;
    
    if (nf != CR.focus) {
        CR.focus = nf;
        CR.dirty = 1;
        // TODO: scroll if needed
    }
}

// ------------------------------------------------------------------ tick (called from feature_clan when page is up)
static void cr_tick(void) {
    uint64_t pg = cr_page_id();
    int up = top_page() == pg;
    
    if (up && !CR.up) {
        // page just came up
        CR.enter_ms = GetTickCount64();
        CR.focus = 0;
        CR.scroll = 0;
        CR.dirty = 1;
        g_cr_w_ok = 0;
        cr_populate_mock();
        xlog("clanroster: page up, %d members", g_cr_count);
    }
    
    CR.up = up;
    if (!up) return;
    
    // input
    int u = key_edge("menu-up"), d = key_edge("menu-down"), l = key_edge("menu-left"), r = key_edge("menu-right");
    int back = key_edge("menu-back"), sel = key_edge("menu-select");
    
    if (back && !CR.h_back) {
        pop_page(pg);
        xlog("clanroster: page closed");
    }
    
    if (u && !CR.h_u) cr_move(0, -1);
    if (d && !CR.h_d) cr_move(0, 1);
    if (l && !CR.h_l) cr_move(-1, 0);
    if (r && !CR.h_r) cr_move(1, 0);
    
    CR.h_u = u; CR.h_d = d; CR.h_l = l; CR.h_r = r;
    CR.h_back = back; CR.h_sel = sel;
    
    // redraw
    if (CR.dirty) {
        cr_fill_all();
        cr_fill_detail();
        CR.dirty = 0;
    }
}

// ------------------------------------------------------------------ public: push the page from the clan panel
static void cr_open(void) {
    if (CR.up) return;
    uint64_t pg = cr_page_id();
    if (!pg) { xlog("clanroster: page id not found"); return; }
    push_page(pg);
    xlog("clanroster: opening page");
}
