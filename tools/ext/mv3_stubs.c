// mv3_stubs.c - empty stand-ins for the melee v3 modules that are not in this tree yet (so the tree compiles without them).
// t2r-ext.c defines MV3_STUB_<module> for every module whose file is missing (or all of them with -DMV3_STUBS). A stub never starts a bubble, so v3 stays
// inert: every mv3_stand() gate answers 0 and melee runs as v2.
#ifdef MV3_STUB_MOVES
const mv3_move MV3_MOVES[1] = {{0}};
const int MV3_MOVES_N = 0;
#endif
#ifdef MV3_STUB_SIM
void     mv3_sim_init(mv3_world *w, uint32_t seed) { if (w) { memset(w, 0, sizeof *w); w->rng = seed ? seed : 1; for (int i = 0; i < MV3_MAX_F; i++) w->f[i].slot = 0xff; } }
int      mv3_sim_add(mv3_world *w, uint8_t slot, uint8_t team, const mv3_in *in) { (void)in; if (!w || w->n >= MV3_MAX_F) return -1; w->f[w->n].slot = slot; w->f[w->n].team = team; w->f[w->n].move = -1; return w->n++; }
void     mv3_sim_remove(mv3_world *w, int idx) { if (w && idx >= 0 && idx < MV3_MAX_F) { memset(&w->f[idx], 0, sizeof w->f[idx]); w->f[idx].slot = 0xff; } }
void     mv3_sim_step(mv3_world *w, const mv3_in in[MV3_MAX_F], mv3_evbuf *ev) { (void)in; if (ev) ev->n = 0; if (w) w->frame++; }
uint32_t mv3_sim_hash(const mv3_world *w) { return w ? w->frame : 0; }
#endif
#ifdef MV3_STUB_NET
static mv3_world g_mv3_stub_world;
static void mv3_net_tick(uint64_t now) { (void)now; }
static void mv3_recv(uint32_t from, const uint8_t *buf, uint64_t len) { (void)from; (void)buf; (void)len; }
static int mv3_net_propose(uint32_t slot) { (void)slot; return 0; }
static void mv3_net_end(const char *why) { (void)why; }
static int mv3_net_active(void) { return 0; }
static const mv3_world *mv3_net_world(void) { return &g_mv3_stub_world; }
static int mv3_net_local_idx(void) { return -1; }
static uint32_t mv3_net_confirmed(void) { return 0; }
static int mv3_net_idx_of_slot(uint32_t slot) { (void)slot; return -1; }
static int mv3_net_slot_of_idx(int idx) { (void)idx; return -1; }
static uint32_t mv3_net_frame_ms(uint32_t frame) { (void)frame; return (uint32_t)GetTickCount64(); }
static void mv3_net_set_hp(int idx, int16_t hp10) { (void)idx; (void)hp10; }
#endif
#ifdef MV3_STUB_ANIM
#define MV3A_US 0xffffffffu
static int mv3_anim_body_busy(uint32_t slot_or_us) { (void)slot_or_us; return 0; }
static void mv3_anim_release_all(const char *why) { (void)why; }
static void mv3_anim_test_tick(void) { }
static void mv3_anim_apply(const mv3_world *w, int local_idx, uint32_t world_frame_frac_ms) { (void)w; (void)local_idx; (void)world_frame_frac_ms; }
static void mv3_anim_release(uint32_t slot) { (void)slot; }
static void mv3_anim_suppress_engine(int on) { (void)on; }
#endif
#ifdef MV3_STUB_FX
static void mv3_fx_events(const mv3_evbuf *ev, int resim) { (void)ev; (void)resim; }
static void mv3_fx_rolled_back(uint32_t to_frame) { (void)to_frame; }
static void mv3_fx_tick(uint64_t now) { (void)now; }
#endif
