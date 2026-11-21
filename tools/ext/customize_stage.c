// ------------------------------------------------------------------ the CUSTOMIZE stage (re/customize-1117.md "The stage")
// The background is a quick fade out and in to a different spot in the already loaded level, in a nice position, with the same cinematic, almost cutscene lighting on the models; a click on the other model / faction logo swaps them with a smooth animation of the models exchanging (clockwise in a way); the player models can be rotated.
// Opening the page: a quick fade to black, the menu camera cuts to the stage spot of the menu scene (feature_menu_cam via g_cz_cam), two
// characters stand there in their composed outfits (t2r-cz-* records of body T2R_US, customize_compose.c cz_compose), then the fade in.
// The edited faction's outfit stands where the page's front model area is (customize_widgets.py FRONT: x 2330, feet y 1525 of 2160), the
// other faction's where the back one is (BACK: x 3380, feet y 1345); both stand on the stage spot's ground. Spawn = the dev NPC spawner
// c-spawn-npc-debug (proven in SP, re/sp-sandbox.md round 5) + npc-set-script-mode(2, 1): no AI, no perception, an idle stance.
// A faction switch (cz_set_fac: SWITCH FACTION, a click on the back model / logo) runs the exchange: both walk one circle around their
// midpoint, clockwise seen from above, CZS_SWAP_MS long, eased; each faces the camera all the way. Rotate the front model: hold the left
// mouse button on it and drag, or the pad triggers (L2 / R2).
// Test / tuning without a rebuild, t2r-cz-stage.txt (polled every second), one "key values" per line:
//   spot <scene> x y z yaw     the stage spot of menu scene 1 (WLF) / 2 (Seraphites): front model's feet + the camera's view yaw (degrees)
//   cam fov pitch              fov (16:9 HORIZONTAL, as override-fov / execution-camera-final.md), pitch down (degrees)
//   swap ms dir                the exchange length; dir 1 = clockwise from above, -1 = the other way
//   npc <fac> class archetype  spawn class / archetype per faction 0 WLF / 1 Seraphites (defaults Pirate militia-pistol-light / scar-light)
//   look <fac> name            spawn that look instead of the composed record (data checks: any SP look name)
//   fpose <fac> <sex> clip     that faction's model (0 WLF, 1 Seraphites) with that body (0 male, 1 female) tries this clip first
//                              (the Scene Editor's pose pick; "-" = none)
//   spose <scene> <slot> clip [x y z yaw]   (the 4 numbers: the clip's apReference at frame 0, metres + degrees, tools/models/pose_apref.py.
//                              The engine puts a body at  ap o inverse(apReference): a sitting crowd clip sat 5.5 m off its stand place,
//                              A/B. With them the clip plays at  ap = stand place o apReference = the body ON the place, as the
//                              Scene Editor shows it.)
//   spose <scene> <slot> clip  menu scene 1 (WLF) / 2 (Seraphites): the model standing in front (slot 0: the edited faction) / in the
//                              back (slot 1) holds this clip, whatever its faction or body (the selected character uses it regardless of sex; on a switch they blend into the other anim); before fpose.
//                              "-" = none. A clip the body cannot play (duration 0) falls through to fpose / the pose list.
//   swapmode 0|1               1 (default) = after the exchange each model blends (CZS_SWAP_BLEND s) into its new place's clip; 0 = it keeps
//                              the clip it had. (A/B: issuing the new clip at way points with a long blend left the models off their
//                              places - the engine does not carry the ap through a blend. The models walk the circle on their old clip.)
// The slot clips' packs must be loaded in the menu world: there is no script native to load one (load-actor / is-actor-loaded? answer
// "no such native", A/B). anim-gen-crowds is always there (efj-lounging-*); the others come with the menu scene's actor list
// (tools/features/menu_scenes.py POSE_ANIM_ACTORS).
// Light (cutscenes and photo mode spawn lights): the photo-mode runtime lights. Photo mode owns
// 3 light slots in its manager (system 2, *(exe+0x4250bc0) + 0xd40, 0x70 bytes each); every frame the render state copies them and the
// "photo-mode-runtime-light" pass turns each enabled slot into a renderer light (spot, shadows optional, 25 m reach). The pass runs only
// while photo mode is active: one 2-byte gate (exe+0x3ffc82 je -> nop nop) is opened while the stage is up and closed after.
// (A/B: flashlight-carrying helper NPCs crashed the client: dropped.)
// Pose (the characters should not just A-pose; the existing model viewer poses are used instead): the
// spawned NPC has no clip of its own in the menu world, so it stands in the bind pose. The model viewer holds ONE single-frame pose clip
// per entry (dc1/model-viewer.bin, actor97/model-viewer.pak), but on each story character's own skeleton; the poses on our bodies'
// skeletons (base-male-skel / base-female-skel) are the No Return character-select poses (actor97/rogue-mode-poses.pak, added to the menu
// scene paks by menu_scenes.py POSE_ACTORS): rogue-mode-rattler-factions (male), rogue-mode-scar-archer (female); fallback: the standing
// idles of anim-gen-crowds (always in the menu world). Played with animate_ and an ap-reference bound frame that places and turns the
// body (npc-teleport stops a scripted clip: a posed model is moved by re-issuing the clip, never teleported).
// Stage freecam (F8 in the MP menu, with WASD not navigating the menu, to find a good position to place the 2 characters): only with t2r-freecam.txt next to the exe (as the match freecam), only while the stage is up.
//   F8 / Scroll Lock / pad L3 + R3   toggle (starts at the stage camera); Esc leaves it too
//   W A S D / left stick   fly along the view; Q / E, d-pad down / up: down / up (world); Shift / Ctrl fast / slow
//   mouse                  hold a mouse button and move = look; arrow keys and the right stick look too
//   Z / X, RT / LT         zoom in / out (fov)
//   F9 / pad R3            print + log the camera (position, yaw, pitch, fov) and the t2r-cz-stage.txt lines of a stage that puts the
//                          characters in front of it (also appended to t2r-cz-stage-saved.txt)
//   F10 / pad Y            put the two characters here: the stage spot = in front of this camera at the ground under it (a ray), and the
//                          stage camera follows (its pitch / fov stay the page layout's)
//   PgUp / PgDn, Home, End the pose browser (d-pad left / right, X, B): see czs_pose_browse
// While it is on, the page ignores its keys, pad and mouse (customize.c reads g_czs_fc): no menu move, no equip, no tab, no rotate.
// Scene Editor layout (the faction menus load in the scene editor to place both character models and position the lighting with a visualizer cone, plus a camera and camera preview with the UI): the editor's stage kit (tools/maps/editor_menu_stage.py)
// writes absolute lines per menu scene (1 WLF, 2 Seraphites); a scene with them ignores the derived layout above:
//   model <sc> <0 front | 1 back> x y z yaw          a stand place (feet) and its facing (degrees, 0 = +Z, atan2(fx, fz))
//   camera <sc> x y z yaw pitch fov                  the stage camera (pitch degrees DOWN, as the menu camera)
//   wlight <sc> <i> x y z tx ty tz r g b intensity cone shadow     light i at x y z aimed at tx ty tz (world)
//                                                    light 1 (rim) takes only its colour / intensity / cone from its line: its place follows
//                                                    light 0 (see czs_lights); light 2 is never lit (the back model in shadow)
// The same lines compiled in (customize_stage_layout.h, CZS_LAYOUT) are the defaults; the file next to the exe wins per scene.
// t2r-no-customize-stage.txt = off (no fade, no camera move, no characters). Log lines "customize stage:".
#define CZS_SWAP_MS_DEF 800
#define CZS_FRONT_D 4.24f              // camera to the front model (m): 1.75 m tall over 1225 of 2160 px at fov 40
#define CZS_FRONT_X 0.586f             //   right of the view line
#define CZS_FRONT_Y 0.636f             //   camera height over its feet
#define CZS_BACK_D 5.94f               // camera to the back model: 875 of 2160 px
#define CZS_BACK_X 2.92f
#define CZS_SWAP_BLEND 0.5f             // s: the blend into the new place's clip after an exchange
#define CZS_RISE_MS 320                 // ms: the model coming to the front blends into the front clip this long before it moves
#define CZS_HIDE_Y 40.0f                // m: a changed outfit's model waits this far over its place until it is posed
typedef struct { int m[2], c, l[3]; float mv[2][4], cv[6], lv[3][12]; } czs_abs_t;    // models / camera / lights given (see the head comment)
typedef struct { uint64_t proc, id; int fac, sex; uint8_t it[CZ_NCAT]; char look[0x28]; uint64_t t_spawn; int passive; float pos[3], yaw;
                 char clip[48]; int clip_tried; uint64_t t_pose; float clip_len, blend_next;
                 float apo[4]; int slot, unarmed; uint64_t t_face, t_clean, t_eyes; int eyes_on; } czs_model_t;         // apo: the held clip's apReference (x y z, yaw radians): the ap is the place o apo
static struct {
    int on, off, cam_ready, front;      // front = the faction standing in front now (follows CZ.fac through the swap)
    uint64_t t_open, swap_t0, file_at;
    int swap_ms, swap_dir;
    float fov, pitch;
    float spot[3][4];                   // per menu scene: x y z yaw (yaw 999 = not set: the menu player's spot + the scene's view)
    float lspot[4]; int lspot_sc;       // the default spot, read ONCE when the stage opens (lspot_sc = its scene, 0 = none yet)
    float pl0[3]; uint64_t pl_chk; int pl_moved;    // the hidden menu player's place at the open (a drift is logged)
    uint64_t ign;                       // the model the player ignores the collision of now (player-ignore-object-collision)
    czs_abs_t ab[3], ab_file[3];        // the absolute (Scene Editor) layout per scene: ab = in use, ab_file = the last t2r-cz-stage.txt read
    char cls[2][32], arch[2][40], look_force[2][40];
    char face[24];                      // the stage models' emotion (npc-set-emotion symbol; "-" = none: the game's own facial idle)
    float user_yaw;                     // the front model's turn (degrees)
    float z_fov, z_dp, z_dy, z_my;      // ZOOM (g_cz_zoom): the eased camera fov, pitch / yaw offsets and the front model's extra turn (degrees)
    uint64_t z_ms;
    int lights, lit;                    // lit = the slots + gate are ours now
    char pose[2][4][40];                // [sex][try order] pose clips
    float pose_yaw;
    char fpose[2][2][48];               // [faction][sex] pose clip from an fpose line (the Scene Editor's pick), before the pose list
    char spose[3][2][48];               // [menu scene][slot 0 front / 1 back] pose clip from an spose line, before fpose
    float sapo[3][2][4];                // ... and its apReference (x y z metres, yaw radians)
    czs_model_t nx[2];                  // [faction] the model of a changed outfit, spawned out of sight until it is posed (then it replaces m[])
    int pv_foc[2]; uint64_t pv_at[2];   // preview: the focused row per faction and when the focus last moved
    int swap_mode;                      // 1 = after the exchange each model blends into its new place's clip
    float lt[3][9];                     // per light: dx dy dz r g b intensity cone shadow
    int drag; float drag_x;
    czs_model_t m[2];                   // [faction]
    struct { int allowed, on, look, l3r3, ray_wait; uint64_t chk, last_ms, ray[3]; WORD pb_last; POINT anchor;
             float p[3], yaw, pitch, fov, gx, gz, ry0[3], ry1; } fc;   // the stage freecam (degrees)
} CZS = {.swap_ms = CZS_SWAP_MS_DEF, .swap_dir = 1, .fov = 40.0f, .pitch = 2.0f,
         .spot = {{0, 0, 0, 999}, {0, 0, 0, 999}, {0, 0, 0, 999}},
         .cls = {"Pirate", "Pirate"}, .arch = {"militia-pistol-light", "scar-light"}, .face = "neutral",
         .lights = 1, .swap_mode = 1,
         .spose = {{""}, {"npc-mm-ambi-buddy-idle", "cap-npc-m-ambi-idle-lean-wall-loop"}, {"npc-mm-ambi-buddy-idle", "efj-lounging-idle--male-b"}},
         .sapo = {{{0}}, {{0}, {0.031f, 0.0f, -0.404f, 0.0f}}, {{0}, {-1.2f, -0.061f, 5.393f, -2.5674f}}},
         .pose = {{"rogue-mode-rattler-factions", "efj-lounging-idle--male-a", "gen-market-group-01-buyer-m"},
                  {"rogue-mode-scar-archer", "npc-standing-ambi-idle", "efj-lounging-idle--female-a", "gen-market-group-01-buyer-f"}},
         .lt = {{-1.5f, 2.3f, 1.4f, 1.00f, 0.90f, 0.78f, 6.0f, 40.0f, 1},     // key: front left, above head height, warm
                {3.4f, 2.1f, 7.6f, 0.70f, 0.82f, 1.00f, 8.0f, 35.0f, 0},      // rim: behind the front model on the right, cool
                {-0.6f, 2.6f, 3.6f, 1.00f, 0.92f, 0.82f, 3.0f, 30.0f, 0}}};   // back model: soft key
static int g_czs_log;
#include "customize_stage_layout.h"         // CZS_LAYOUT: the shipped absolute layout lines (written by tools/maps/editor_menu_stage.py)
static int g_czs_fc;                    // the stage freecam is on: customize.c drops the page's own input this frame
// ONE CLOCK per frame (the player disappeared on zoom in on some previews; the log: 'spawned', 'pose started' and
// 'model off the stage' of one preview in ONE frame). The frame's `now` was read before the spawn, the spawn stamped the model with
// a later tick count (the spawn call can cross a 15.6 ms tick), and `now - t_spawn` (unsigned) became 2^64 - 15: older than
// every wait. So the fresh model took the stage in the frame it was spawned - before an NPC accepts a clip - and stayed at its
// waiting place 40 m over the stage; the quiet time after a spawn (CZS_KILL_QUIET_MS, CZS_SPAWN_GAP_MS) was skipped the same
// way. Every time in this file is the clock read once at the top of czs_tick: a stamp can never be ahead of a `now`.
static uint64_t g_czs_clock;
static uint64_t czs_now(void) { return g_czs_clock ? g_czs_clock : GetTickCount64(); }
static uint64_t g_czs_spawn_ms;         // when the stage last spawned a model (spawn gap, removal quiet time)
// STAGE LIGHT (the light intensity can be changed live to adjust it): every stage light's intensity x g_czs_light_k. Default CZS_LIGHT_DEF; [ and ] on the CUSTOMIZE page change it live in
// steps of CZS_LIGHT_STEP (customize.c), the value is shown and kept in t2r-cz-light.txt next to the exe (per cent).
// (after trying it, 13 % stage light is good on the WLF menu - the default is 13 % now; the two stages are different places
// with their own light, so each faction's stage has its own value: [ and ] change the one on screen. File: "wlf <per cent>" /
// "scar <per cent>" lines; a bare number (the first form of the file) counts for both.)
#define CZS_LIGHT_DEF 0.13f
#define CZS_LIGHT_STEP 1.10f
static float g_czs_light_f[2] = {CZS_LIGHT_DEF, CZS_LIGHT_DEF};
// LIGHTING SETUPS (cinematic lighting for the customization scenes; the hand-placed lights looked bad at any intensity, so different lighting setups are offered). Setups to look at in the game: L on the
// CUSTOMIZE page steps through them for the stage on screen - 0 = the layout's own lights (Scene Editor), 1.. = CZS_CINE. A setup is
// three lights around the FRONT model's chest (the three photo-mode slots; the back model gets the spill): az = degrees around the
// model from the direction of the camera (0 = from the camera, + = the camera's right, 180 = straight behind), el = degrees up,
// d = metres, colour, intensity, cone degrees, shadows, softness. Each setup has its own strength per stage ([ and ] as before).
// File t2r-cz-light.txt: "wlf <per cent>" / "scar <per cent>" (layout lights), "wlf-setup <n> <per cent>" / "scar-setup <n> <per cent>".
typedef struct { float az, el, d, r, g, b, i, cone, sh, soft; } czs_cl_t;
typedef struct { const char *name; czs_cl_t l[3]; } czs_cine_t;      // key, rim, fill (a light with i = 0 is off)
static const czs_cine_t CZS_CINE[] = {
    // A: the scene's sun stays the back light (WLF stadium: from behind on the right); a soft warm key from the camera's left
    {"A  BACKLIT SUN", {{-40, 35, 3.0f, 1.00f, 0.90f, 0.78f, 0.80f, 45, 1, 0.5f}, {150, 40, 3.5f, 1.00f, 0.93f, 0.82f, 2.00f, 35, 0, 0}, {55, 10, 3.5f, 0.70f, 0.82f, 1.00f, 0.20f, 60, 0, 0}}},
    // B: a warm key where a sun over the camera's right shoulder would be, blue fill on the shade side, cool rim opposite
    {"B  SUN KEY", {{40, 45, 3.5f, 1.00f, 0.88f, 0.72f, 1.10f, 45, 1, 0}, {-150, 35, 3.5f, 0.75f, 0.85f, 1.00f, 1.50f, 35, 0, 0}, {-50, 5, 3.5f, 0.65f, 0.78f, 1.00f, 0.18f, 60, 0, 0}}},
    // C: overcast - a wide soft cool key from the front top, a small warm kicker low at the side (lantern / fire), a strong cool rim
    {"C  OVERCAST SOFTBOX", {{-15, 50, 3.0f, 0.86f, 0.92f, 1.00f, 0.70f, 70, 1, 1.0f}, {-160, 45, 3.5f, 0.70f, 0.85f, 1.00f, 1.80f, 35, 0, 0}, {100, -5, 2.5f, 1.00f, 0.72f, 0.45f, 0.40f, 50, 0, 0}}},
    // D: one hard key from the side, no fill, a strong rim
    {"D  LOW-KEY", {{70, 30, 3.0f, 1.00f, 0.96f, 0.90f, 1.30f, 35, 1, 0}, {-140, 40, 3.5f, 0.85f, 0.90f, 1.00f, 1.60f, 35, 0, 0}, {0, 0, 0, 0, 0, 0, 0, 0, 0, 0}}},
    // E: soft key + fill, a mild rim - the clothes' colours as they are
    {"E  STUDIO", {{-30, 35, 3.0f, 1.00f, 0.97f, 0.94f, 0.80f, 60, 1, 0.8f}, {180, 50, 3.5f, 1.00f, 1.00f, 1.00f, 0.80f, 40, 0, 0}, {40, 15, 3.5f, 0.95f, 0.97f, 1.00f, 0.45f, 60, 0, 0.8f}}},
};
#define CZS_NCINE ((int)(sizeof CZS_CINE / sizeof CZS_CINE[0]))
_Static_assert(sizeof CZS_CINE / sizeof CZS_CINE[0] == 5, "g_czs_cine_k holds five setups");
// The default on both stages is C OVERCAST SOFTBOX (overcast softbox for both); a t2r-cz-light.txt line
// "wlf-setup <n> ..." / "scar-setup <n> ..." (written by L / [ / ]) still picks another one per client.
#define CZS_CINE_DEF 3
_Static_assert(CZS_CINE_DEF >= 1 && CZS_CINE_DEF <= 5, "CZS_CINE_DEF is one of the setups");
static int g_czs_cine[2] = {CZS_CINE_DEF, CZS_CINE_DEF};   // per stage: 0 = the layout's lights, 1.. = CZS_CINE[n - 1]
static float g_czs_cine_k[2][5 + 1] = {{0, 1, 1, 1, 1, 1}, {0, 1, 1, 1, 1, 1}};      // [stage][setup]: its strength
static float *czs_light_kp(void) {
    const int f = CZS.front & 1, c = g_czs_cine[f];
    return c > 0 && c <= CZS_NCINE ? &g_czs_cine_k[f][c] : &g_czs_light_f[f];
}
#define g_czs_light_k (*czs_light_kp())
static void czs_light_load(void) {
    FILE *f = exe_side_open("t2r-cz-light.txt", "r");
    if (!f) return;
    char line[64];
    while (fgets(line, sizeof line, f)) {
        char k[16]; float v = 0, w = 0;
        if (sscanf(line, "%15s %f %f", k, &v, &w) == 3 && (!strcmp(k, "wlf-setup") || !strcmp(k, "scar-setup"))) {
            const int fc = k[0] == 's', n = (int)v;
            if (n >= 0 && n <= CZS_NCINE) { g_czs_cine[fc] = n; if (n && w >= 1.0f && w <= 400.0f) g_czs_cine_k[fc][n] = w / 100.0f; }
        } else if (sscanf(line, "%15s %f", k, &v) == 2 && v >= 1.0f && v <= 400.0f) {
            if (!strcmp(k, "wlf")) g_czs_light_f[0] = v / 100.0f; else if (!strcmp(k, "scar")) g_czs_light_f[1] = v / 100.0f;
        } else if (sscanf(line, "%f", &v) == 1 && v >= 1.0f && v <= 400.0f) g_czs_light_f[0] = g_czs_light_f[1] = v / 100.0f;
    }
    fclose(f);
}
static void czs_light_save(void) {
    FILE *f = exe_side_open("t2r-cz-light.txt", "w");
    if (!f) return;
    fprintf(f, "wlf %.1f\nscar %.1f\n", g_czs_light_f[0] * 100.0f, g_czs_light_f[1] * 100.0f);
    for (int fc = 0; fc < 2; fc++)
        fprintf(f, "%s-setup %d %.1f\n", fc ? "scar" : "wlf", g_czs_cine[fc], g_czs_cine[fc] ? g_czs_cine_k[fc][g_czs_cine[fc]] * 100.0f : 100.0f);
    fclose(f);
}
static const char *czs_cine_step(void) {                // the next setup for the stage on screen -> its name
    const int f = CZS.front & 1;
    g_czs_cine[f] = (g_czs_cine[f] + 1) % (CZS_NCINE + 1);
    czs_light_save();
    return g_czs_cine[f] ? CZS_CINE[g_czs_cine[f] - 1].name : "YOUR LAYOUT";
}
static void czs_light_step(int dir) {
    g_czs_light_k *= dir > 0 ? CZS_LIGHT_STEP : 1.0f / CZS_LIGHT_STEP;
    if (g_czs_light_k < 0.01f) g_czs_light_k = 0.01f;
    if (g_czs_light_k > 4.0f) g_czs_light_k = 4.0f;
    czs_light_save();
}
static float g_czs_t_fov, g_czs_t_pitch, g_czs_t_yaw;      // test file (dev builds): the page camera's fov (0 = the stage's) and pitch / yaw offsets in degrees - close shots without input
#define CZS_LOG(...) do { if (LOGCAP(g_czs_log, 1500)) xlog("customize stage: " __VA_ARGS__); } while (0)   // (120 ran out in minutes: the crash logs had no stage line near the end)

// an fpose line (see the head comment); 1 = it was one
static int czs_fpose_line(const char *ln) {
    int fc, sx; char c[48];
    if (sscanf(ln, "fpose %d %d %47s", &fc, &sx, c) != 3 || fc < 0 || fc > 1 || sx < 0 || sx > 1) return 0;
    snprintf(CZS.fpose[fc][sx], sizeof CZS.fpose[0][0], "%s", strcmp(c, "-") ? c : "");
    return 1;
}
// an spose line (see the head comment); 1 = it was one
static int czs_spose_line(const char *ln) {
    int sc, sl; char c[48]; float a[4] = {0, 0, 0, 0};
    int n = sscanf(ln, "spose %d %d %47s %f %f %f %f", &sc, &sl, c, &a[0], &a[1], &a[2], &a[3]);
    if ((n != 3 && n != 7) || sc < 1 || sc > 2 || sl < 0 || sl > 1) return 0;
    snprintf(CZS.spose[sc][sl], sizeof CZS.spose[0][0], "%s", strcmp(c, "-") ? c : "");
    a[3] *= 3.14159265f / 180.0f;
    memcpy(CZS.sapo[sc][sl], a, sizeof a);
    return 1;
}
// one absolute layout line (see the head comment) into L[]; 1 = it was one
static int czs_abs_line(const char *ln, czs_abs_t *L) {
    int sc, k; float v[12];
    if (sscanf(ln, "model %d %d %f %f %f %f", &sc, &k, &v[0], &v[1], &v[2], &v[3]) == 6 && sc >= 1 && sc <= 2 && (k == 0 || k == 1)) {
        memcpy(L[sc].mv[k], v, 16); L[sc].m[k] = 1; return 1;
    }
    if (sscanf(ln, "camera %d %f %f %f %f %f %f", &sc, &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) == 7 && sc >= 1 && sc <= 2 && v[5] > 5.0f && v[5] < 120.0f) {
        memcpy(L[sc].cv, v, 24); L[sc].c = 1; return 1;
    }
    if (sscanf(ln, "wlight %d %d %f %f %f %f %f %f %f %f %f %f %f %f", &sc, &k, &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7], &v[8], &v[9],
               &v[10], &v[11]) == 14 && sc >= 1 && sc <= 2 && k >= 0 && k < 3) {
        memcpy(L[sc].lv[k], v, 48); L[sc].l[k] = 1; return 1;
    }
    return 0;
}
static int g_czs_eyes = 1;             // the standing models look at the camera (czs_eyes; file line "eyes 0" = off)
static void czs_read_file(void) {
    uint64_t now = czs_now();
    if (now < CZS.file_at) return;
    CZS.file_at = now + 1000;
    FILE *f = exe_side_open("t2r-no-customize-stage.txt", "r");
    CZS.off = f != NULL; if (f) fclose(f);
    static int built;
    if (!built) {                                   // the compiled-in layout, once
        built = 1;
        char t[sizeof CZS_LAYOUT];
        memcpy(t, CZS_LAYOUT, sizeof t);
        for (char *sv = NULL, *ln = strtok_r(t, "\n", &sv); ln; ln = strtok_r(NULL, "\n", &sv)) {
            if (!czs_abs_line(ln, CZS.ab) && !czs_spose_line(ln)) czs_fpose_line(ln);     // (the shipped pose picks)
        }
        for (int s = 1; s < 3; s++) if (CZS.ab[s].m[0]) CZS_LOG("scene %d: the shipped editor layout (front %.2f %.2f %.2f)", s, CZS.ab[s].mv[0][0], CZS.ab[s].mv[0][1], CZS.ab[s].mv[0][2]);
    }
    f = exe_side_open("t2r-cz-stage.txt", "r");
    if (!f) return;
    char ln[160];
    memset(CZS.ab_file, 0, sizeof CZS.ab_file);
    while (fgets(ln, sizeof ln, f)) {
        int sc, fc, ms, dir; float v[4], w[9]; char a[40], b[40];
        if (czs_abs_line(ln, CZS.ab_file)) continue;
        if (sscanf(ln, "spot %d %f %f %f %f", &sc, &v[0], &v[1], &v[2], &v[3]) == 5 && sc >= 0 && sc < 3) memcpy(CZS.spot[sc], v, sizeof v);
        else if (sscanf(ln, "cam %f %f", &v[0], &v[1]) == 2 && v[0] > 5.0f && v[0] < 120.0f) { CZS.fov = v[0]; CZS.pitch = v[1]; }
        else if (sscanf(ln, "swap %d %d", &ms, &dir) == 2 && ms >= 100 && ms <= 5000) { CZS.swap_ms = ms; CZS.swap_dir = dir < 0 ? -1 : 1; }
        else if (sscanf(ln, "face %23s", a) == 1) snprintf(CZS.face, sizeof CZS.face, "%s", a);
        else if (sscanf(ln, "eyes %d", &fc) == 1) g_czs_eyes = fc != 0;
        else if (sscanf(ln, "npc %d %39s %39s", &fc, a, b) == 3 && (fc == 0 || fc == 1)) { snprintf(CZS.cls[fc], sizeof CZS.cls[fc], "%s", a); snprintf(CZS.arch[fc], sizeof CZS.arch[fc], "%s", b); }
        else if (sscanf(ln, "lights %d", &fc) == 1) CZS.lights = fc != 0;
        else if (sscanf(ln, "poseyaw %f", &v[0]) == 1) CZS.pose_yaw = v[0];
        else if (czs_fpose_line(ln) || czs_spose_line(ln)) {}
        else if (sscanf(ln, "swapmode %d", &fc) == 1) CZS.swap_mode = fc != 0;
        else if (!strncmp(ln, "pose ", 5) && (ln[5] == '0' || ln[5] == '1')) {
            int sx = ln[5] - '0', k = 0; char *t = ln + 6, *sv = NULL;
            memset(CZS.pose[sx], 0, sizeof CZS.pose[sx]);
            for (char *w = strtok_r(t, " \t\r\n", &sv); w && k < 4; w = strtok_r(NULL, " \t\r\n", &sv))
                if (strcmp(w, "-")) snprintf(CZS.pose[sx][k++], sizeof CZS.pose[sx][0], "%s", w);
        }
        else if (sscanf(ln, "light %d %f %f %f %f %f %f %f %f %f", &fc, &w[0], &w[1], &w[2], &w[3], &w[4], &w[5], &w[6], &w[7], &w[8]) == 10 && fc >= 0 && fc < 3)
            memcpy(CZS.lt[fc], w, sizeof w);
        else if (sscanf(ln, "look %d %39s", &fc, a) == 2 && (fc == 0 || fc == 1)) snprintf(CZS.look_force[fc], sizeof CZS.look_force[fc], "%s", strcmp(a, "-") ? a : "");
    }
    fclose(f);
    for (int s = 1; s < 3; s++)                     // a scene the file lays out wins over the compiled-in one
        if (CZS.ab_file[s].m[0] && CZS.ab_file[s].c) CZS.ab[s] = CZS.ab_file[s];
}
// the editor layout of scene sc is complete enough to use (front model + camera)
static int czs_abs_on(int sc) { return sc >= 1 && sc <= 2 && CZS.ab[sc].m[0] && CZS.ab[sc].c; }
// the stage spot of this scene: front model's feet + view yaw (radians). Not set in the file: the menu player's spot (known ground in every
// scene) looking along the scene camera's view - read ONCE per stage (A/B: the player model started flying to the left until it flew down the hill: read every frame, the spot followed the hidden player, the front model was placed on it again, pushed it again - the
// player slid 40 m down the slope, died, and the menu lost its UI). czs_off forgets it.
static int czs_spot(int sc, float *p, float *yaw) {
    if (sc < 0 || sc > 2) return 0;
    if (czs_abs_on(sc)) { memcpy(p, CZS.ab[sc].mv[0], 12); *yaw = CZS.ab[sc].cv[3] * 3.14159265f / 180.0f; return 1; }
    if (CZS.spot[sc][3] < 900.0f) { p[0] = CZS.spot[sc][0]; p[1] = CZS.spot[sc][1]; p[2] = CZS.spot[sc][2]; *yaw = CZS.spot[sc][3] * 3.14159265f / 180.0f; return 1; }
    if (CZS.lspot_sc != sc) {
        float mb[16];
        const float *pl = player_locator(mb);
        if (!pl) return 0;
        const float *d = MS_POSE[sc];
        float fx = d[3] - d[0], fz = d[5] - d[2];
        if (fx * fx + fz * fz < 1e-6f) return 0;
        CZS.lspot[0] = pl[0]; CZS.lspot[1] = pl[1]; CZS.lspot[2] = pl[2]; CZS.lspot[3] = atan2f(fx, fz); CZS.lspot_sc = sc;
    }
    p[0] = CZS.lspot[0]; p[1] = CZS.lspot[1]; p[2] = CZS.lspot[2]; *yaw = CZS.lspot[3];
    return 1;
}
// The hidden menu player stands at the default spot: the models must never push it. The player ignores the collision of the model nearest
// to it (the native holds one object, re-set every frame as finpos does; 0 clears), and its place at the open is watched: a drift > 0.3 m
// is logged (once per stage) with the player's place.
static int czs_alive(const czs_model_t *m);
static void czs_player_guard(void) {
    float mb[16];
    const float *pl = player_locator(mb);
    if (!pl) return;
    uint64_t now = czs_now();
    if (!CZS.pl_chk) { memcpy(CZS.pl0, pl, 12); CZS.pl_chk = now + 1000; CZS.pl_moved = 0; }
    uint64_t best = 0; float bd = 1e9f;
    for (int f = 0; f < 2; f++) {
        const czs_model_t *m = &CZS.m[f];
        if (!czs_alive(m)) continue;
        float dx = m->pos[0] - pl[0], dz = m->pos[2] - pl[2], d = dx * dx + dz * dz;
        if (d < bd) { bd = d; best = m->id; }
    }
    if (best) {
        uint64_t a = best, r = dc_call(fnv64("player-ignore-object-collision"), 1, &a);
        if (best != CZS.ign) { CZS.ign = best; CZS_LOG("player ignores the collision of model %llx (%.2f m from it) -> %llx", (unsigned long long)best, sqrtf(bd), (unsigned long long)r); }
    }
    if (now >= CZS.pl_chk) {
        CZS.pl_chk = now + 1000;
        float dx = pl[0] - CZS.pl0[0], dy = pl[1] - CZS.pl0[1], dz = pl[2] - CZS.pl0[2];
        if (!CZS.pl_moved && dx * dx + dy * dy + dz * dz > 0.09f) {
            CZS.pl_moved = 1;
            CZS_LOG("WARNING the hidden menu player moved %.2f m since the stage opened: %.2f %.2f %.2f -> %.2f %.2f %.2f", sqrtf(dx * dx + dy * dy + dz * dz),
                    CZS.pl0[0], CZS.pl0[1], CZS.pl0[2], pl[0], pl[1], pl[2]);
        }
    }
}
static void czs_player_guard_off(void) {
    if (!CZS.ign) return;
    uint64_t z = 0, r = dc_call(fnv64("player-ignore-object-collision"), 1, &z);
    CZS_LOG("player collision with the models back (ignore cleared -> %llx)", (unsigned long long)r);
    CZS.ign = 0;
}
static float czs_ease(float t) { t = t < 0 ? 0 : t > 1 ? 1 : t; return t * t * (3.0f - 2.0f * t); }
// the two stand places + the camera for this spot. yaw = view yaw (forward = (sin, 0, cos)), right = (cos, 0, -sin)
static void czs_layout(const float *g, float yaw, float *cam, float *front, float *back) {
    float fx = sinf(yaw), fz = cosf(yaw), rx = cosf(yaw), rz = -sinf(yaw);
    cam[0] = g[0] - fx * CZS_FRONT_D - rx * CZS_FRONT_X; cam[1] = g[1] + CZS_FRONT_Y; cam[2] = g[2] - fz * CZS_FRONT_D - rz * CZS_FRONT_X;
    memcpy(front, g, 12);
    back[0] = g[0] + fx * (CZS_BACK_D - CZS_FRONT_D) + rx * (CZS_BACK_X - CZS_FRONT_X); back[1] = g[1];
    back[2] = g[2] + fz * (CZS_BACK_D - CZS_FRONT_D) + rz * (CZS_BACK_X - CZS_FRONT_X);
}
static uint64_t czs_bf(const float *pos, float yaw) {
    static __attribute__((aligned(16))) float tp[4], tr[4];
    tp[0] = pos[0]; tp[1] = pos[1]; tp[2] = pos[2]; tp[3] = 1.0f;
    tr[0] = 0; tr[1] = sinf(yaw * 0.5f); tr[2] = 0; tr[3] = cosf(yaw * 0.5f);
    uint64_t a[5] = {(uint64_t)tp, (uint64_t)tr, 0, 0, 0};
    uint64_t bf = dc_call(0x871ec52cc86b7427ULL /* alloc-bound-frame */, 5, a);
    return bf == ~0ULL ? 0 : bf;
}
// REMOVAL AT THE FRAME'S QUIET POINT (the seventh game end, ext cz49: EXCEPTION 80000003 at exe+1b018bd, thread 24644, in the
// frame of a removal done by the tick on thread 436; the compaction pass was held back, so nothing had moved - and still a lookup
// by exe+1b01817 found the removed model's attach table full of other data). Every one of these ends is some engine job of that
// frame still working on the model our tick removes: t2r_tick is itself one of the frame's process updates and runs beside the
// model's own update. The engine has one point per frame where no process update runs at all - ProcessMgr::CompactProcessMemory
// moves process memory, so it must be alone. The stage's removals are queued (czs_kill_request) and done there, from cm_hook
// (t2r-ext.c), one per frame, before the pass; dc_call then holds that pass and the next two back, so the freed block is not
// reused by a move either. No model is spawned while a removal waits or within CZS_KILL_CLEAR frames after one. If the hook is
// not running (t2r-no-cm-watch.txt), the removal is done at once, as before.
#define CZS_KILLQ 12
#define CZS_KILL_CLEAR 4
static volatile uint64_t g_czs_killq[CZS_KILLQ];
static volatile uint64_t g_czs_kill_frame;
static volatile LONG g_czs_kill_n;
// (logging that names the removal path on a crash) the last removals, each with the path it took - 'Q' at the
// compaction point (czs_kill_drain), 'D' at once from the tick (no hook / queue full) - its frame, thread and model, and the frame
// it was asked for; the EXCEPTION report prints them with the stage's last spawn and the pool (czs_crash_report).
static struct { uint64_t id, frame, asked; DWORD tid; char path; } g_czs_klog[8];
static volatile LONG g_czs_klog_n;
static uint64_t g_czs_kq_asked[CZS_KILLQ];
static volatile uint64_t g_czs_spawn_frame;
static void czs_klog(uint64_t id, uint64_t asked, char path) {
    LONG k = (InterlockedIncrement(&g_czs_klog_n) - 1) & 7;
    g_czs_klog[k].id = id; g_czs_klog[k].frame = g_frame; g_czs_klog[k].asked = asked; g_czs_klog[k].tid = GetCurrentThreadId(); g_czs_klog[k].path = path;
}
static void czs_kill_request(uint64_t id) {
    if (!id) return;
    if (g_cm_frame + 5 >= g_frame)                       // the compaction hook ran in the last frames: queue for it
        for (int i = 0; i < CZS_KILLQ; i++) if (!g_czs_killq[i]) { g_czs_kq_asked[i] = g_frame; g_czs_killq[i] = id; return; }
    uint64_t a = id;                                    // no hook / queue full: at once
    dc_call(fnv64("kill-entity"), 1, &a);
    g_czs_kill_frame = g_frame;
    czs_klog(id, g_frame, 'D');
    static int nl; if (LOGCAP(nl, 6)) xlog("customize stage: removal done at once (the compaction hook is not running or %d removals wait)", CZS_KILLQ);
}
static int czs_kill_pending(void) { for (int i = 0; i < CZS_KILLQ; i++) if (g_czs_killq[i]) return 1; return 0; }
// REAP AT ONCE (the eighth game end: ext cz51, the automated stress - 180 removals at the compaction point, then a
// fault in our attach lookup hook one frame after a removal).
// The reader this time has a name: AI knowledge code (knowledge-full.cpp, the function after AiFullKnowledge::ShareKnowledge,
// exe+6c5f22) of ANOTHER stage model resolves a handle - the pid test at exe+6c5ed5 passes - and asks NdGameObject::FindAttachPoint
// (exe+1b017f0) of that object, whose attach table is garbage. A handle that still resolves to a torn-down object is a process that
// was KILLED but not yet DESTROYED: the engine's kill (KillProcess exe+1341480 -> Process::KillTree exe+13414c0) runs OnKillProcess
// at once and only puts the process on the dead list; Process::CleanupDeadList (exe+133f260) destroys it later, and until then
// every handle to it is good. The engine's own kills come from process updates and are followed by its cleanup before the next
// readers run; ours comes at the compaction point, and the next cleanup is somewhere in the next frame - after the first AI jobs.
// So the removal is followed, in the same call, by the engine's own Process::CleanupDeadList(): the model is destroyed, its handles
// are dead, the knowledge code skips it like any despawned NPC. The function is static, takes nothing and guards itself against
// re-entry (g_cleanupDeadListInProgress, read here first); no process update runs at the compaction point (DestroyProcess asserts
// !IsProcessUpdating). t2r-no-cz-reap.txt next to the exe = off. Log: the removal lines carry 'dead list cleaned 1'.
static int czs_reap(void) {
    static int off = -1, ok = -1;
    if (off < 0) { FILE *f_ = exe_side_open("t2r-no-cz-reap.txt", "r"); off = f_ != NULL; if (f_) fclose(f_); }
    if (off) return 0;
    uint8_t *fn = (uint8_t *)GetModuleHandleW(NULL) + 0x133f260;
    if (ok < 0) {
        // mov [rsp+8],rbx; mov [rsp+10h],rbp; mov [rsp+18h],rsi; push rdi ... +2e: cmp byte [rip+disp], r15b (the re-entry flag)
        static const uint8_t P[] = {0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x6C, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x57};
        ok = !IsBadReadPtr(fn, 0x40) && !memcmp(fn, P, sizeof P) && fn[0x2e] == 0x44 && fn[0x2f] == 0x38 && fn[0x30] == 0x3D;
        if (!ok) xlog("customize stage: Process::CleanupDeadList not recognised at exe+133f260 - a removal is not reaped at once");
    }
    if (!ok) return 0;
    uint8_t *busy = fn + 0x35 + *(int32_t *)(fn + 0x31);          // g_cleanupDeadListInProgress
    if (IsBadReadPtr(busy, 1) || *busy) {
        static int nl; if (LOGCAP(nl, 6)) xlog("customize stage: the dead list cleanup is running (flag %p) - this removal is not reaped at once", (void *)busy);
        return 0;
    }
    ((void (*)(void))fn)();
    return 1;
}
static void czs_kill_drain(void) {                      // cm_hook: one removal, then that pass is held back (dc_call sets g_cm_skip_until)
    for (int i = 0; i < CZS_KILLQ; i++) {
        uint64_t a = g_czs_killq[i];
        if (!a) continue;
        g_czs_killq[i] = 0;
        uint64_t r = dc_call(fnv64("kill-entity"), 1, &a);
        g_czs_kill_frame = g_frame;
        czs_klog(a, g_czs_kq_asked[i], 'Q');
        const int reaped = czs_reap();
        LONG n = InterlockedIncrement(&g_czs_kill_n);
        if (n <= 8 || n % 100 == 0) xlog("customize stage: removal %ld done at the compaction point (frame %llu, thread %lu, kill-entity -> %llx, dead list cleaned %d)", (long)n,
                                         (unsigned long long)g_frame, (unsigned long)GetCurrentThreadId(), (unsigned long long)r, reaped);
        return;
    }
}
static int czs_parked(void);
static void czs_crash_report(void) {
    LONG n = g_czs_klog_n;
    if (!n && !g_czs_spawn_frame) return;
    xlog("  customize stage: frame %llu, last spawn frame %llu, last removal frame %llu, %d removal(s) waiting, %d model(s) in the pool, %ld removals so far (%ld at the compaction point)",
         (unsigned long long)g_frame, (unsigned long long)g_czs_spawn_frame, (unsigned long long)g_czs_kill_frame, czs_kill_pending(), czs_parked(), (long)n, (long)g_czs_kill_n);
    for (LONG j = 0; j < 8 && j < n; j++) {
        LONG k = (n - 1 - j) & 7;
        xlog("  customize stage: removal -%ld: model %016llx path %c (%s), done frame %llu (%llu frames ago) on thread %lu, asked frame %llu", (long)j,
             (unsigned long long)g_czs_klog[k].id, g_czs_klog[k].path, g_czs_klog[k].path == 'Q' ? "compaction point" : "at once from the tick",
             (unsigned long long)g_czs_klog[k].frame, (unsigned long long)(g_frame - g_czs_klog[k].frame), (unsigned long)g_czs_klog[k].tid, (unsigned long long)g_czs_klog[k].asked);
    }
}
static void czs_kill(czs_model_t *m, const char *why) {
    if (m->id) { czs_kill_request(m->id); CZS_LOG("%s model removed (%s)", CZ_FAC_NAME[m->fac], why); }
    m->proc = m->id = 0; m->passive = 0;
}
static int czs_alive(const czs_model_t *m) { return m->proc && m->id && !IsBadReadPtr((void *)(m->proc + 0x94), 4); }
static void czs_spawn_as(czs_model_t *m, int slot, int fac, const char *look, const float *pos, float yaw) {
    uint64_t bf = czs_bf(pos, yaw);
    if (!bf) { CZS_LOG("alloc-bound-frame failed"); return; }
    // (every spawn its own name: a model that left the stage lives on, hidden, until it is CZS_KILL_AGE_MS old (czs_retire), and a spawn
    // under a name a live NPC holds returns nothing: the model on the stage stayed the old one)
    static char name[32][32], lk[32][0x28];
    static unsigned seq;
    const unsigned k = seq++ % 32;
    snprintf(name[k], sizeof name[k], "t2r-cz-stage-%d-%u", slot, seq);
    snprintf(lk[k], sizeof lk[k], "%s", look);
    uint64_t args[8] = {bf, (uint64_t)name[k], (uint64_t)lk[k], fnv64(CZS.cls[fac]), fnv64(CZS.arch[fac]), 0, 0, 0};
    uint64_t proc = dc_call(fnv64("c-spawn-npc-debug"), 8, args);
    uint64_t id = 0;
    if (proc && proc != ~0ULL && !IsBadReadPtr((void *)(proc + 0x94), 4)) { uint64_t a = proc; id = dc_call(fnv64("get-process-user-id"), 1, &a); }
    snprintf(m->look, sizeof m->look, "%s", look);
    m->slot = slot;
    m->t_spawn = czs_now(); m->passive = 0; memcpy(m->pos, pos, 12); m->yaw = yaw; m->clip[0] = 0; m->clip_tried = 0; m->t_pose = 0; m->clip_len = 0;
    m->unarmed = 0; m->t_face = 0; m->t_clean = 0; m->t_eyes = 0; m->eyes_on = 0;
    g_czs_spawn_ms = m->t_spawn;
    g_czs_spawn_frame = g_frame;
    if (!id || id == ~0ULL) { m->proc = m->id = 0; CZS_LOG("slot %d: c-spawn-npc-debug(look %s, %s / %s) -> %llx: no process (look art or the NPC archetype not loaded in the menu world?)",
                                                      slot, look, CZS.cls[fac], CZS.arch[fac], (unsigned long long)proc); return; }
    m->proc = proc; m->id = id;
    CZS_LOG("%s spawned: look %s (%s / %s) at %.2f %.2f %.2f yaw %.1f -> process %llx", slot < 2 ? CZ_FAC_NAME[fac] : slot == 2 ? "key light helper" : "rim light helper",
            look, CZS.cls[fac], CZS.arch[fac], pos[0], pos[1], pos[2], yaw * 57.29578f, (unsigned long long)proc);
}
// the outfit the stage shows for a faction: what is equipped, with the FOCUSED row of the open category in its place once the focus has
// rested CZS_PV_MS (a locked item can still be previewed). Only rows whose
// parts are in the MP data (tier 1) can be shown.
#define CZS_PV_MS 220
// D (flipping between two tops to compare ended the game; second time in the attach-point lookup of a job thread, the
// stage quiet for 3 s): every model that was removed around a crash had left the stage UNDER 1 s old (656 ms in this log, 1 s in the
// first). A fresh NPC of these archetypes puts its pistol away first (npc-quick/slow-holster-gesture, about a second); a model moved
// off the stage inside that keeps a half-attached weapon, and its removal later sends the weapon's attach to a table that is gone.
// Sweeps that showed each model for 3 s removed hundreds without a crash. So: (1) the stage model's weapon is taken away once it
// exists (npc-destroy-weapon, winmm's own call at every puppet weapon switch) - nothing to holster, nothing attached when it goes;
// (2) a standing model is not replaced before it is CZS_MIN_LIFE_MS old (fast flipping updates the preview that often).
#define CZS_MIN_LIFE_MS 1200
#define CZS_UNARM_MS 120
// THE FACE (the characters looked angry and squinted; offline: it is the game's own TENSE facial idle - brows down and together, eyes narrowed - and a stock
// head wears the same; the zoom shows it). The stage models get an emotion of their own, CZS.face ("neutral"; t2r-cz-stage.txt line
// `face <symbol>`: neutral joy uneasy tense stealth combat ..., `face -` = the game's idle), re-issued before it runs out:
// npc-set-emotion(npc, symbol, duration, fade-in, weight), the call of the execution faces.
#define CZS_FACE_SECS 4.0f
#define CZS_FACE_EVERY_MS 2000
static void czs_face_set(czs_model_t *m, uint64_t now) {
    if (!CZS.face[0] || CZS.face[0] == '-' || !czs_alive(m) || now - m->t_spawn < 150 || (m->t_face && now - m->t_face < CZS_FACE_EVERY_MS)) return;
    uint64_t a[8] = {0}; float secs = CZS_FACE_SECS, fade = m->t_face ? 0.0f : 0.1f, weight = 1.0f;
    a[0] = m->id; a[1] = fnv64(CZS.face); memcpy(&a[2], &secs, 4); memcpy(&a[3], &fade, 4); memcpy(&a[4], &weight, 4);
    uint64_t r = dc_call(fnv64("npc-set-emotion"), 5, a);
    static int nl; if (LOGCAP(nl, 4)) CZS_LOG("%s model: emotion %s (npc-set-emotion -> %llx)", CZ_FAC_NAME[m->fac & 1], CZS.face, (unsigned long long)r);
    m->t_face = now;
}
// DIRT (zoomed in: dirt-like brown smudges on all characters on the cheeks,
// jaw and neck of her own head and of stock faces alike): not the head's texture - the engine's per-character mud mask (shader sampler
// MudMaskSampler; bloodbuild.c notes) is the candidate: the stage models are NPCs, and a player body in a match does not show it.
// Not proven when this change was made. Their mud and wet mask opacity is set to 0 (set-character-mud-mask-value / set-character-wet-mask-value (char,
// float), the natives of SP's scripts) from the spawn on, again every CZS_CLEAN_EVERY_MS in case a spawn step sets it back.
#define CZS_CLEAN_EVERY_MS 1000
static void czs_clean(czs_model_t *m, uint64_t now) {
    if (!czs_alive(m) || (m->t_clean && now - m->t_clean < CZS_CLEAN_EVERY_MS)) return;
    uint64_t a[2] = {m->id, 0}, b[2] = {m->id, 0}; float z = 0.0f;
    memcpy(&a[1], &z, 4); memcpy(&b[1], &z, 4);
    uint64_t r1 = dc_call(fnv64("set-character-mud-mask-value"), 2, a);
    uint64_t r2 = dc_call(fnv64("set-character-wet-mask-value"), 2, b);
    static int nl; if (LOGCAP(nl, 4)) CZS_LOG("%s model: mud / wet mask opacity 0 (set-character-mud-mask-value -> %llx, set-character-wet-mask-value -> %llx)",
                                              CZ_FAC_NAME[m->fac & 1], (unsigned long long)r1, (unsigned long long)r2);
    m->t_clean = now;
    // (after two wrong runtime guesses - these opacities and the blood wipe group, which does not spawn in the menu world: the
    // smudges are the skin MATERIALS' own dirt layer, g_dirtStrength 1.0 on the heads of kits 10 / 13 and on KELLIE's head built from
    // kit 10, 0.36 / 0.34 on the clean-looking kits 15 / 05. A pak fix (the KELLIE set), nothing to call here.)
}
// EYES (KELLIE's face read derpy: the eyes drift up
// and to the side on the stage): the standing model looks at the camera - npc-look-at-point(npc, alloc-point(x, y, z, 0), seconds),
// the call of SP's scripts, renewed every second for 3 s - while it faces the camera within CZS_EYES_DEG (turned further, e.g. the
// BACKPACK zoom, the look is cleared: no head twisted over the shoulder). t2r-cz-stage.txt line "eyes 0" = off.
#define CZS_EYES_DEG 55.0f
static void czs_eyes(czs_model_t *m, const float *cam, uint64_t now) {
    if (!g_czs_eyes || !czs_alive(m) || now - m->t_spawn < 400 || (m->t_eyes && now - m->t_eyes < 1000)) return;
    m->t_eyes = now;
    float d = atan2f(cam[0] - m->pos[0], cam[2] - m->pos[2]) - m->yaw;      // (= czs_face: the yaw that faces the camera)
    while (d > 3.14159265f) d -= 6.2831853f;
    while (d < -3.14159265f) d += 6.2831853f;
    const int want = fabsf(d) < CZS_EYES_DEG * 3.14159265f / 180.0f;
    if (want) {
        uint64_t pa[4] = {0, 0, 0, 0};
        memcpy(&pa[0], &cam[0], 4); memcpy(&pa[1], &cam[1], 4); memcpy(&pa[2], &cam[2], 4);
        uint64_t pt = dc_call(fnv64("alloc-point"), 4, pa);
        if (pt && pt != ~0ULL) {
            uint64_t a[3] = {m->id, pt, 0}; float secs = 3.0f;
            memcpy(&a[2], &secs, 4);
            uint64_t r = dc_call(fnv64("npc-look-at-point"), 3, a);
            static int nl; if (LOGCAP(nl, 4)) CZS_LOG("%s model: looks at the camera (alloc-point -> %llx, npc-look-at-point -> %llx)", CZ_FAC_NAME[m->fac & 1],
                                                      (unsigned long long)pt, (unsigned long long)r);
        }
    } else if (m->eyes_on) { uint64_t c = m->id; dc_call(fnv64("npc-clear-look-at"), 1, &c); }
    m->eyes_on = want;
}
static void czs_unarm(czs_model_t *m, uint64_t now) {
    if (m->unarmed || !czs_alive(m) || now - m->t_spawn < CZS_UNARM_MS) return;
    uint64_t da[2] = {m->id, 0};
    uint64_t r = dc_call(fnv64("npc-destroy-weapon"), 2, da);
    m->unarmed = 1;
    static int nl; if (LOGCAP(nl, 6)) CZS_LOG("%s model: weapon taken away (npc-destroy-weapon -> %llx)", CZ_FAC_NAME[m->fac & 1], (unsigned long long)r);
}
// (the game ended in Npc::RefreshSnapshot, exe+15f52d7, the open "snapshot table null" crash of a spawn racing the snapshot job -
// re/crash-sites.md - after minutes of fast browsing: every focus move spawned a model, and a superseded one was removed and replaced in
// the same frame. Now: one preview spawn at a time (the next waits until the last one took its place) and CZS_SPAWN_GAP_MS between spawns.)
#define CZS_SPAWN_GAP_MS 500
static void czs_want(int fac, int sex, uint8_t *out) {
    memcpy(out, g_cz.it[fac][sex], CZ_NCAT);
    if (!CZ.up || fac != CZ.fac || CZ.cat == CZ_SEX || CZ.cat < 0 || CZ.cat >= CZ_NCAT) return;
    const int foc = CZ.foc[CZ.cat];
    uint64_t now = czs_now();
    if (foc != CZS.pv_foc[fac]) { CZS.pv_foc[fac] = foc; CZS.pv_at[fac] = now; }
    const int fk = cz_r2k(fac, sex, CZ.cat, foc);                // (CZ.foc is a row position on the page; the look takes the table index)
    const cz_item_t *it = fk >= 0 ? cz_item(fac, sex, CZ.cat, fk) : NULL;
    if (!it || it->tier > 1 || now - CZS.pv_at[fac] < CZS_PV_MS) return;
    if (cz_conflict_cat(fac, sex, g_cz.it[fac][sex], CZ.cat, fk) >= 0) return;      // (a row the worn outfit cannot take is not previewed either)
    out[CZ.cat] = (uint8_t)fk;
}
static void czs_spawn_it(czs_model_t *m, int slot, int fac, int sex, const uint8_t *it, const float *pos, float yaw) {
    char look[0x28];
    m->fac = fac; m->sex = sex; memcpy(m->it, it, CZ_NCAT); m->look[0] = 0; m->t_spawn = czs_now();
    g_czs_spawn_ms = m->t_spawn;
    g_czs_spawn_frame = g_frame;
    if (CZS.look_force[fac][0]) snprintf(look, sizeof look, "%s", CZS.look_force[fac]);
    else {
        cz_no_pushed_props = 1;                              // (a stage model: nothing hides the coat's armour copy)
        int ok = cz_compose(T2R_US, fac, sex, it, look);
        cz_no_pushed_props = 0;
        if (!ok) { CZS_LOG("%s: no composed record (old data?) - no model", CZ_FAC_NAME[fac]); return; }
    }
    czs_spawn_as(m, slot, fac, look, pos, yaw);
}
static void czs_spawn(czs_model_t *m, int fac, const float *pos, float yaw) {
    const int sex = g_cz.sex[fac] < CZ_NSEX ? g_cz.sex[fac] : 0;
    uint8_t it[CZ_NCAT];
    czs_want(fac, sex, it);
    czs_spawn_it(m, fac, fac, sex, it, pos, yaw);
}
// the held pose: animate_(entity, clip, {28 blend-in, 10 ap-reference BoundFrame, 32 hold}) - the scripts' recipe (re-viewer-poses.md 2)
static uint64_t czs_pose_play(czs_model_t *m, const float *pos, float yaw, float blend) {
    static psync_bf bf[2];                                   // (animate_ copies it, 0x141dd1b30)
    float yp = yaw + CZS.pose_yaw * 3.14159265f / 180.0f, cy = cosf(yp), sy = sinf(yp);
    float y = yp + m->apo[3];                                // ap = place o apReference (see spose)
    float ap7[7] = {pos[0] + m->apo[0] * cy + m->apo[2] * sy, pos[1] + m->apo[1], pos[2] - m->apo[0] * sy + m->apo[2] * cy,
                    0, sinf(y * 0.5f), 0, cosf(y * 0.5f)};
    psync_bf *loc = &bf[m->fac & 1];
    psync_bf_make(loc, ap7);
    uint64_t aa[4] = {fnv64("single-frame"), 16, 3, 1};
    uint64_t arr = dc_call(fnv64("#%alloc-array"), 4, aa);
    if (!arr || arr == ~0ULL || IsBadReadPtr((void *)arr, 8)) return ~0ULL;
    uint64_t *tab = *(uint64_t **)arr;
    if (!tab || IsBadReadPtr(tab, 24)) return ~0ULL;
    uint8_t *e[3] = {(uint8_t *)tab[0], (uint8_t *)tab[1], (uint8_t *)tab[2]};
    for (int k = 0; k < 3; k++) if (!e[k] || alloc_entry_bad((void *)arr, e[k], 16)) return ~0ULL;
    *(int32_t *)e[0] = 28; memcpy(e[0] + 8, &blend, 4);
    *(int32_t *)e[1] = 10; *(uint64_t *)(e[1] + 8) = (uint64_t)loc;
    *(int32_t *)e[2] = 32; *(uint8_t *)(e[2] + 8) = 1;
    uint64_t a[3] = {m->id, fnv64(m->clip), arr};
    return dc_call(fnv64("animate_"), 3, a);
}
// The pose data (A/B: every rogue-mode-* clip had duration 0 with rogue-mode-poses in the menu scene paks' pak68 blocks, and
// the female bodies had no anim-gen-crowds clip either: no difference was seen). Once per stage: log what is loaded (is-actor-loaded? /
// is-level-loaded? of the pose actor, the crowd anims and the scene pak), and when the pose actor is not loaded ask the engine for it
// (load-actor, the script command "Loads actor(s) and returns their loaded state"); poll for 10 s, and when it arrives every model that holds
// a fallback clip picks again. Log lines "pose data: ...". A native that does not exist answers ~0 (dc_call logs it once).
static struct { int state, logged; uint64_t at, t0; } CZP;
static uint64_t czs_actor_loaded(const char *actor) {
    uint64_t s = fnv64(actor), r = dc_call(fnv64("is-actor-loaded?"), 1, &s);
    if (r == ~0ULL) { s = fnv64(actor); r = dc_call(fnv64("is-actor-loaded"), 1, &s); }
    return r;
}
static void czs_pose_data(int sc) {
    uint64_t now = czs_now();
    if (CZP.state == 0) {                              // stage just opened: the inventory
        static const char *const A[] = {"rogue-mode-poses", "anim-gen-crowds", "crow-t2", "base-male-skel", "base-female-skel"};
        char t[400] = ""; size_t o = 0;
        for (int i = 0; i < 5; i++) o += (size_t)snprintf(t + o, sizeof t - o, "%s%s %llx", i ? ", " : "", A[i], (unsigned long long)czs_actor_loaded(A[i]));
        uint64_t lv = fnv64(sc == 1 ? "to1-menu-wlf" : "to1-menu-ser"), ll = dc_call(fnv64("is-level-loaded?"), 1, &lv);
        CZS_LOG("pose data: is-actor-loaded? %s; is-level-loaded? %s %llx", t, sc == 1 ? "to1-menu-wlf" : "to1-menu-ser", (unsigned long long)ll);
        uint64_t r = czs_actor_loaded("rogue-mode-poses");
        if (r != ~0ULL && (r & 0xff)) { CZP.state = 3; return; }
        uint64_t s = fnv64("rogue-mode-poses"), q = dc_call(fnv64("load-actor"), 1, &s);
        CZS_LOG("pose data: rogue-mode-poses not loaded - load-actor -> %llx", (unsigned long long)q);
        CZP.state = q == ~0ULL ? 4 : 1; CZP.t0 = now; CZP.at = now + 500;
        return;
    }
    if (CZP.state != 1 || now < CZP.at) return;
    CZP.at = now + 500;
    uint64_t r = czs_actor_loaded("rogue-mode-poses");
    int ok = r != ~0ULL && (r & 0xff);
    for (int f = 0; f < 2 && !ok; f++) {                // (no is-actor-loaded? native: a clip that answers is proof enough)
        czs_model_t *m = &CZS.m[f];
        if (czs_alive(m) && anim_len(m->id, CZS.pose[m->sex == 1 ? 1 : 0][0]) > 0.0f) ok = 1;
    }
    if (ok) {
        CZP.state = 2;
        CZS_LOG("pose data: rogue-mode-poses loaded after %llu ms - the models pick again", (unsigned long long)(now - CZP.t0));
        for (int f = 0; f < 2; f++) { CZS.m[f].clip_tried = 0; CZS.m[f].t_pose = 0; }
    } else if (now - CZP.t0 > 10000) { CZP.state = 4; CZS_LOG("pose data: rogue-mode-poses still not loaded 10 s after load-actor (%llx)", (unsigned long long)r); }
}
// The pose browser (to preview animations): while the stage freecam is on,
//   PgDn / PgUp, pad d-pad right / left   the next / previous clip for the selected model (only the clips its body can play: probed with
//                                         get-animation-duration, so a clip whose pack is not loaded in the menu world is skipped)
//   Home / pad X                          select the other model
//   End / pad B                           save "pose <sex> <clip>" to t2r-cz-stage-saved.txt (copy it into t2r-cz-stage.txt to keep it)
// The pick also holds for that sex through outfit respawns (until the game closes). Candidates: CZS_POSES (standing / leaning / idle
// loops from rogue-mode-poses, anim-gen-crowds and the sp-common NPC packs) plus one clip per line
// of t2r-cz-poses.txt next to the exe (read when the freecam turns on).
static const char *const CZS_POSES[] = {
    "rogue-mode-rattler-factions", "rogue-mode-scar-archer", "rogue-mode-bosses--rattler-king",
    "npc-m-nw-mm-ambi-idle", "npc-m-nw-mm-uneasy-idle", "npc-m-nw-mm-aggr-idle", "npc-m-p-mm-aggr-idle", "npc-m-lg-mm-aggr-idle",
    "npc-m-lg-tilt-mm-aggr-idle", "npc-m-1hblade-mm-aggr-idle", "npc-m-1hblade-melee-idle", "npc-mm-ambi-buddy-idle", "npc-m-p-mm-injured-idle",
    "npc-m-nw-mm-panic-idle", "npc-m-p-crouch-idle", "npc-m-p-ambi-investigate-idle",
    "cap-npc-m-wait-arms-folded-loop", "cap-npc-m-wait-shoulder-lean-loop", "cap-npc-m-ambi-idle-shoulder-on-wall-loop",
    "cap-npc-m-stand-talking-fw-a-loop", "cap-npc-m-ambi-idle-lean-wall-loop", "cap-npc-m-wall-lean-back-loop", "cap-npc-m-share-booze-wait-a",
    "cap-npc-m-share-booze-wait-b", "cap-npc-m-lean-fw-wall-1m-loop", "cap-npc-m-explore-wait-lean-1m-loop", "cap-lead-npc-lean-rail-loop",
    "cap-lead-npc-lean-wall-loop", "cap-npc-m-ambi-lean-on-table-0-9m-loop", "cap-npc-m-sit-on-1m-idle",
    "npc-pap-nw-uneasy-idle-look-around-a", "npc-pap-nw-uneasy-idle-look-around-b", "npc-pap-nw-uneasy-idle-look-around-c",
    "npc-pap-nw-uneasy-idle-look-around-d", "npc-pap-nw-uneasy-idle-look-around-e", "npc-pap-nw-uneasy-idle-look-around-f",
    "npc-pap-nw-uneasy-idle-look-around-g", "npc-pap-nw-uneasy-idle-guard-door-lt-a", "npc-pap-nw-uneasy-idle-guard-door-rt-a",
    "npc-pap-nw-ambi-idle-look-around-small-a", "npc-pap-nw-ambi-idle-look-around-small-b", "npc-pap-nw-ambi-idle-look-around-small-c",
    "npc-pap-nw-ambi-idle-look-around-small-d", "npc-pap-nw-ambi-idle-look-around-small-e", "npc-pap-nw-ambi-idle-look-around-small-f",
    "efj-lounging-idle--male-a", "efj-lounging-idle--male-b", "efj-lounging-idle--female-a", "npc-standing-ambi-idle",
    "gen-market-seller-01-m", "gen-market-search-lean-down-m", "gen-market-search-02-m", "gen-market-search-03-m", "gen-market-search-08-m",
    "gen-market-search-09-m", "gen-market-search-05-f", "gen-market-vendor-01-f",
    "gen-market-group-01-buyer-m", "gen-market-group-03-buyer-m", "gen-market-group-04-buyer-m", "gen-market-group-05-buyer-m",
    "gen-market-group-10-buyer-m", "gen-market-group-11-buyer-m", "gen-market-group-01-vendor", "gen-market-group-05-vendor",
    "gen-market-group-07-vendor", "gen-market-group-10-vendor",
    "gen-market-group-01-buyer-f", "gen-market-group-03-buyer-f", "gen-market-group-04-buyer-f", "gen-market-group-11-buyer-f",
};
#define CZS_NPOSE ((int)(sizeof CZS_POSES / sizeof CZS_POSES[0]))
#define CZS_NEXTRA 48
static struct { int sel, idx[2], nextra; char extra[CZS_NEXTRA][48]; char pick[2][48]; } CZB = {.idx = {-1, -1}};
static const char *czs_pose_name(int i) { return i < CZS_NPOSE ? CZS_POSES[i] : CZB.extra[i - CZS_NPOSE]; }
static void czs_pose_extra(void) {
    CZB.nextra = 0;
    FILE *f = exe_side_open("t2r-cz-poses.txt", "r");
    if (!f) return;
    char ln[128];
    while (CZB.nextra < CZS_NEXTRA && fgets(ln, sizeof ln, f)) {
        char w[48];
        if (sscanf(ln, " %47s", w) == 1 && w[0] != '#') snprintf(CZB.extra[CZB.nextra++], sizeof CZB.extra[0], "%s", w);
    }
    fclose(f);
    CZS_LOG("pose browser: %d extra clips from t2r-cz-poses.txt", CZB.nextra);
}
// the slot a model stands in (0 front, 1 back); through an exchange: the one it is going to
static int czs_slot(const czs_model_t *m) { int front = (m->fac & 1) == CZS.front; if (CZS.swap_t0) front = !front; return front ? 0 : 1; }
static const char *czs_slot_clip(const czs_model_t *m) { return g_ms_cur >= 1 && g_ms_cur <= 2 ? CZS.spose[g_ms_cur][czs_slot(m)] : ""; }
// for 15 s after the open a model whose slot clip has arrived (its pack streamed in late) picks again
static struct { uint64_t at; } CZK;
static void czs_pose_paks(uint64_t now) {
    if (now < CZK.at || now - CZS.t_open > 15000 || CZS.swap_t0) return;
    CZK.at = now + 500;
    for (int f = 0; f < 2; f++) {
        czs_model_t *m = &CZS.m[f];
        const char *sp = czs_alive(m) && m->clip_tried ? czs_slot_clip(m) : "";
        if (sp[0] && strcmp(m->clip, sp) && !CZB.pick[m->sex == 1 ? 1 : 0][0] && anim_len(m->id, sp) > 0.0f) {
            CZS_LOG("pose pak: %s can play %s now (%llu ms after the open) - picks again", CZ_FAC_NAME[m->fac], sp, (unsigned long long)(now - CZS.t_open));
            m->clip_tried = 0; m->t_pose = 0;
        }
    }
}
// pick the first pose clip this body can play (get-animation-duration > 0 = loaded for its skeleton); the browser's pick for this sex first
static void czs_pose_pick(czs_model_t *m) {
    if (m->clip_tried || !czs_alive(m)) return;
    m->clip_tried = 1;
    memset(m->apo, 0, sizeof m->apo);
    const int sx = m->sex == 1 ? 1 : 0;
    if (CZB.pick[sx][0]) {
        float len = anim_len(m->id, CZB.pick[sx]);
        if (len > 0.0f) { snprintf(m->clip, sizeof m->clip, "%s", CZB.pick[sx]); m->clip_len = len; CZS_LOG("%s pose: %s (the browser's pick)", CZ_FAC_NAME[m->fac], m->clip); return; }
    }
    const char *sp = czs_slot_clip(m);
    if (sp[0]) {
        float len = anim_len(m->id, sp);
        if (len > 0.0f) {
            snprintf(m->clip, sizeof m->clip, "%s", sp); m->clip_len = len;
            memcpy(m->apo, CZS.sapo[g_ms_cur][czs_slot(m)], sizeof m->apo);
            CZS_LOG("%s pose: %s (spose, scene %d %s slot, %.1f s, apReference %.2f %.2f %.2f yaw %.0f)", CZ_FAC_NAME[m->fac], m->clip, g_ms_cur,
                    czs_slot(m) ? "back" : "front", len, m->apo[0], m->apo[1], m->apo[2], m->apo[3] * 57.29578f);
            return;
        }
        CZS_LOG("%s pose: spose %s is not loaded for this body (duration 0) - fpose / the pose list", CZ_FAC_NAME[m->fac], sp);
    }
    const char *fp = CZS.fpose[m->fac & 1][sx];
    if (fp[0]) {
        float len = anim_len(m->id, fp);
        if (len > 0.0f) { snprintf(m->clip, sizeof m->clip, "%s", fp); m->clip_len = len; CZS_LOG("%s pose: %s (fpose line)", CZ_FAC_NAME[m->fac], m->clip); return; }
        CZS_LOG("%s pose: fpose %s is not loaded for this body (duration 0) - the pose list", CZ_FAC_NAME[m->fac], fp);
    }
    char tried[200] = ""; size_t o = 0;
    for (int k = 0; k < 4 && CZS.pose[sx][k][0]; k++) {
        float len = anim_len(m->id, CZS.pose[sx][k]);
        o += (size_t)snprintf(tried + o, sizeof tried - o, "%s%s %.2f", k ? ", " : "", CZS.pose[sx][k], len);
        if (len > 0.0f) { snprintf(m->clip, sizeof m->clip, "%s", CZS.pose[sx][k]); m->clip_len = len; break; }
        if (o >= sizeof tried) break;
    }
    CZS_LOG("%s pose: %s (tried %s)", CZ_FAC_NAME[m->fac], m->clip[0] ? m->clip : "NONE - bind pose", tried[0] ? tried : "nothing");
}
static void czs_place(czs_model_t *m, const float *pos, float yaw) {
    if (!czs_alive(m)) return;
    int same = fabsf(pos[0] - m->pos[0]) + fabsf(pos[1] - m->pos[1]) + fabsf(pos[2] - m->pos[2]) < 0.002f && fabsf(yaw - m->yaw) < 0.002f;
    if (m->clip[0]) {                                        // posed: the clip's ap places and turns it (a teleport would stop the clip)
        uint64_t now = czs_now();
        // (re-issued every 2 s standing still: a 1-frame pose holds; a longer idle plays to its end first, then again with a blend)
        const int lng = m->clip_len > 2.0f;
        uint64_t hold = lng ? (uint64_t)(m->clip_len * 1000.0f) - 50 : 2000;
        if (same && m->t_pose && now - m->t_pose < hold) return;
        uint64_t r = czs_pose_play(m, pos, yaw, m->t_pose && !(lng && same) ? 0.0f : m->blend_next > 0.0f ? m->blend_next : 0.2f);
        m->blend_next = 0.0f;
        if (!m->t_pose) CZS_LOG("%s pose %s started -> %llx", CZ_FAC_NAME[m->fac], m->clip, (unsigned long long)r);
        m->t_pose = now;
        memcpy(m->pos, pos, 12); m->yaw = yaw;
        return;
    }
    if (same) return;
    uint64_t bf = czs_bf(pos, yaw);
    if (!bf) return;
    uint64_t a[2] = {m->id, bf};
    uint64_t r = dc_call(fnv64("npc-teleport"), 2, a);
    static int nl; if (LOGCAP(nl, 6)) CZS_LOG("npc-teleport %s -> %llx", CZ_FAC_NAME[m->fac], (unsigned long long)r);
    memcpy(m->pos, pos, 12); m->yaw = yaw;
}
// A model leaves the stage: off it at once (its clip re-issued CZS_HIDE_Y over the place), REMOVED only once it is CZS_KILL_AGE_MS old.
// (three times in minutes with the stock garments new in the level: the game ended in Npc::RefreshSnapshot, exe+15f52d7, on
// OUR tick thread in the frame "model removed (outfit changed)" was logged - an attach table with no entries, re/crash-sites.md
// "snapshot table null". The removed model was 0.7 s old each time: a preview that was itself replaced. A model of a kit that is not
// resident is still being put together then; removing it there leaves the frame's NPC update with a half-built object.)
// (a top was picked and the game ended 9 frames later): access violation in the attach-point lookup of a job thread (pist_resolve
// = the engine's 0x1415f5200, the table's entries pointer garbage) at frame 48860 - the frame the hidden model spawned at 48560 turned
// CZS_KILL_AGE_MS old and was removed, 9 frames after the picked outfit's model had been spawned (48851). The crash family of the match
// corpses (t2r-ext.c the corpse crash reports: a kill-entity next to an NPC creation; there: CK_QUIET / CK_GAP). So the same rule here: a model
// is removed only when no stage model was spawned for CZS_KILL_QUIET_MS and nothing was removed for CZS_KILL_GAP_MS, one per pass, and
// never at the moment it leaves the stage (an old model used to be removed right then - right after its replacement's spawn).
// The waiting models take CZS_GRAVE_N places; a new preview spawns only while CZS_GRAVE_ROOM of them are free (czs_grave_room).
#define CZS_GRAVE_N 20
#define CZS_GRAVE_ROOM 6
// REUSE: a removal is the one dangerous thing the stage does, and flipping between two items made one per flip. While the
// page is up the last CZS_POOL_KEEP waiting models stay (held over the stage as before); an outfit that one of them wears is not
// spawned again - that model comes back down (czs_pool_take). Only what the pool cannot hold is removed, the one that has waited
// longest first; when the page closes they all go, one per CZS_KILL_GAP_MS.
#define CZS_POOL_KEEP 10
#define CZS_KILL_AGE_MS 5000
#define CZS_KILL_QUIET_MS 2000
#define CZS_KILL_GAP_MS 800
// C (build 11: extra npcs fell from the sky and shifted next to the standing character): a waiting model was put
// over the stage ONCE; with the longer wait its clip ran out (or it never had one: a preview replaced before it was posed) and it
// fell onto the stage in the bind pose. Now every waiting model is held where it waits until it is removed: its clip re-issued there
// (czs_place does that when the clip runs out), a model without a clip teleported back every CZS_HOLD_FRAMES frames.
#define CZS_HOLD_FRAMES 6
static struct { uint64_t id, proc, t_spawn, t_park; czs_model_t m; float hp[3]; } g_czs_grave[CZS_GRAVE_N];
static int czs_parked(void) { int n = 0; for (int i = 0; i < CZS_GRAVE_N; i++) n += g_czs_grave[i].id != 0; return n; }
// a waiting model that wears exactly this outfit -> taken out of the pool into *out (1), else 0
static int czs_pool_take(int fac, int sex, const uint8_t *it, czs_model_t *out) {
    for (int i = 0; i < CZS_GRAVE_N; i++) {
        if (!g_czs_grave[i].id) continue;
        const czs_model_t *w = &g_czs_grave[i].m;
        if (w->fac != fac || w->sex != sex || memcmp(w->it, it, CZ_NCAT) || !czs_alive(w)) continue;
        *out = *w;
        memcpy(out->pos, g_czs_grave[i].hp, 12);          // (where it waits: czs_place moves it from there)
        g_czs_grave[i].id = 0;
        static int nl; if (LOGCAP(nl, 400)) CZS_LOG("%s model back from the pool (place %d, spawned %llu ms ago): no spawn for this outfit", CZ_FAC_NAME[fac & 1], i,
                                                    (unsigned long long)(czs_now() - w->t_spawn));
        return 1;
    }
    return 0;
}
static uint64_t g_czs_kill_ms;
static int czs_grave_room(void) {
    int n = 0;
    for (int i = 0; i < CZS_GRAVE_N; i++) n += !g_czs_grave[i].id;
    return n >= CZS_GRAVE_ROOM;
}
static void czs_grave_tick(void) {
    uint64_t now = czs_now();
    // (the removal is chosen BEFORE the hold: a model that goes this frame gets no clip / teleport request in it)
    int parked = 0, old = -1;
    for (int i = 0; i < CZS_GRAVE_N; i++) {
        if (!g_czs_grave[i].id) continue;
        parked++;
        if (now - g_czs_grave[i].t_spawn >= CZS_KILL_AGE_MS && (old < 0 || g_czs_grave[i].t_park < g_czs_grave[old].t_park)) old = i;
    }
    const int keep = CZS.on ? CZS_POOL_KEEP : 0;
    const int go = old >= 0 && parked > keep && !czs_kill_pending() && now - g_czs_spawn_ms >= CZS_KILL_QUIET_MS && now - g_czs_kill_ms >= CZS_KILL_GAP_MS;
    for (int i = 0; i < CZS_GRAVE_N; i++) {              // hold every waiting model in its place over the stage
        if (!g_czs_grave[i].id || (go && i == old)) continue;
        czs_model_t *w = &g_czs_grave[i].m;
        if (!czs_alive(w)) continue;
        if (w->clip[0]) czs_place(w, g_czs_grave[i].hp, w->yaw);
        else if (!(g_frame % CZS_HOLD_FRAMES)) {
            uint64_t bf = czs_bf(g_czs_grave[i].hp, w->yaw);
            if (bf) { uint64_t a[2] = {w->id, bf}; dc_call(fnv64("npc-teleport"), 2, a); }
        }
    }
    if (!go) return;
    for (int i = old; i <= old; i++) {
        const int live = !IsBadReadPtr((void *)(g_czs_grave[i].proc + 0x94), 4);
        {   // (own budget: the removals around a crash must be in the log - process + attach table, to match a freed table to its model)
            static int nk;
            const uint8_t *tab = live && !IsBadReadPtr((void *)(g_czs_grave[i].proc + 0x1f0), 8) ? *(const uint8_t *const *)(g_czs_grave[i].proc + 0x1f0) : NULL;
            if (LOGCAP(nk, 600)) xlog("customize stage: waiting model removed (place %d, %llu ms old, look %s, process %llx, attach table %p%s)", i,
                                      (unsigned long long)(now - g_czs_grave[i].t_spawn), g_czs_grave[i].m.look, (unsigned long long)g_czs_grave[i].proc, (const void *)tab, live ? "" : ", already gone");
        }
        if (live) czs_kill_request(g_czs_grave[i].id);
        g_czs_grave[i].id = 0;
        g_czs_kill_ms = now;
        return;                                  // one per pass
    }
}
static void czs_retire(czs_model_t *m, const char *why) {
    uint64_t now = czs_now();
    if (!m->id) { czs_kill(m, why); return; }    // (nothing spawned: only the record is cleared)
    int k = 0;
    for (int i = 0; i < CZS_GRAVE_N; i++) {
        if (!g_czs_grave[i].id) { k = i; break; }
        if (g_czs_grave[i].t_spawn < g_czs_grave[k].t_spawn) k = i;          // (full: the oldest one goes now)
    }
    if (g_czs_grave[k].id && !IsBadReadPtr((void *)(g_czs_grave[k].proc + 0x94), 4)) {      // (every place taken - the spawn gate keeps room, so: not expected)
        czs_kill_request(g_czs_grave[k].id); g_czs_kill_ms = now;
        xlog("customize stage: no place left for a model off the stage - the oldest waiting one removed now");
    }
    float p[3] = {m->pos[0], m->pos[1] + CZS_HIDE_Y + 5.0f * (float)(k + 1), m->pos[2]};
    czs_place(m, p, m->yaw);
    g_czs_grave[k].id = m->id; g_czs_grave[k].proc = m->proc; g_czs_grave[k].t_spawn = m->t_spawn; g_czs_grave[k].t_park = now;
    g_czs_grave[k].m = *m; memcpy(g_czs_grave[k].hp, p, 12);
    CZS_LOG("%s model off the stage (%s; %llu ms old, removed once %d ms old and the stage is quiet)", CZ_FAC_NAME[m->fac], why, (unsigned long long)(now - m->t_spawn), CZS_KILL_AGE_MS);
    m->proc = m->id = 0; m->passive = 0;
}
static void czs_lights_off(void);
static void czs_off(const char *why, int fade) {
    if (!CZS.on) return;
    czs_player_guard_off();
    for (int f = 0; f < 2; f++) {
        czs_retire(&CZS.m[f], why);
        if (CZS.nx[f].t_spawn) czs_retire(&CZS.nx[f], why);
        memset(&CZS.nx[f], 0, sizeof CZS.nx[f]);
    }
    czs_lights_off();
    CZS.lspot_sc = 0; CZS.pl_chk = 0;
    CZS.on = 0; CZS.cam_ready = 0; CZS.drag = 0;
    if (CZS.fc.on) { CZS.fc.on = 0; g_czs_fc = 0; CZS_LOG("freecam off (stage off)"); }
    g_cz_cam_on = 0;
    if (fade) fade_to_black(0.0f, 0.12f, 0.35f);     // black at once, the scene camera comes back under it
    CZS_LOG("off (%s)", why);
}
static float czs_face(const float *from, const float *cam) { return atan2f(cam[0] - from[0], cam[2] - from[2]); }
// the photo-mode light slots (re-photomode-lights.md 1.3 / 1.5): enabled dword +0, skip byte +4 (0), position +0x10, aim target +0x20,
// rgb +0x30, intensity +0x40, +0x44 nonzero (else the light is dropped), cone degrees +0x48 / +0x4c, softness +0x50, shadows +0x54, near +0x64
#define CZS_PM_MGR 0x4250bc0
#define CZS_PM_GATE 0x3ffc82
static uint8_t *czs_pm_slots(void) {
    uint8_t *base = (uint8_t *)GetModuleHandleW(NULL), *mgr;
    if (IsBadReadPtr(base + CZS_PM_MGR, 8) || !(mgr = *(uint8_t **)(base + CZS_PM_MGR)) || IsBadWritePtr(mgr + 0xd40, 3 * 0x70)) return NULL;
    return mgr + 0xd40;
}
static int czs_pm_gate(int open) {             // 74 0e (je: photo mode off -> skip the pass) <-> 90 90
    static int bad;
    uint8_t *g = (uint8_t *)GetModuleHandleW(NULL) + CZS_PM_GATE;
    const uint8_t want[2] = {open ? 0x90 : 0x74, open ? 0x90 : 0x0e}, from[2] = {open ? 0x74 : 0x90, open ? 0x0e : 0x90};
    if (g[0] == want[0] && g[1] == want[1]) return 1;
    if (g[-2] != 0x84 || g[-1] != 0xc0 || g[0] != from[0] || g[1] != from[1]) {
        if (!bad) { bad = 1; CZS_LOG("photo-mode light gate: unexpected bytes %02x %02x %02x %02x at exe+%x - no stage lights", g[-2], g[-1], g[0], g[1], CZS_PM_GATE); }
        return 0;
    }
    DWORD old;
    if (!VirtualProtect(g, 2, PAGE_EXECUTE_READWRITE, &old)) return 0;
    g[0] = want[0]; g[1] = want[1];
    VirtualProtect(g, 2, old, &old);
    FlushInstructionCache(GetCurrentProcess(), g, 2);
    CZS_LOG("photo-mode light gate %s", open ? "opened (stage lights on)" : "closed");
    return 1;
}
static void czs_lights_off(void) {
    if (!CZS.lit) return;
    uint8_t *s = czs_pm_slots();
    if (s) for (int i = 0; i < 3; i++) *(uint32_t *)(s + i * 0x70) = 0;
    czs_pm_gate(0);
    CZS.lit = 0;
}
static void czs_lights(int sc, const float *cam, float yaw, const float *fp, const float *bp) {
    if (!CZS.lights) { czs_lights_off(); return; }
    uint8_t *s = czs_pm_slots();
    if (!s) return;
    if (!CZS.lit) { if (!czs_pm_gate(1)) { CZS.lights = 0; return; } CZS.lit = 1; }
    float fx = sinf(yaw), fz = cosf(yaw), rx = cosf(yaw), rz = -sinf(yaw);
    const int ab = czs_abs_on(sc);
    const int cine = g_czs_cine[CZS.front & 1];
    if (cine > 0 && cine <= CZS_NCINE) {            // a lighting setup: three lights around the front model's chest (see CZS_CINE)
        const float C[3] = {fp[0], fp[1] + 1.35f, fp[2]};
        float hx = cam[0] - fp[0], hz = cam[2] - fp[2], hl = sqrtf(hx * hx + hz * hz);
        if (hl < 0.01f) { hx = -fx; hz = -fz; hl = 1.0f; }
        hx /= hl; hz /= hl;                         // model -> camera on the ground plane; the camera's right = (-hz, hx)
        for (int i = 0; i < 3; i++) {
            const czs_cl_t *P = &CZS_CINE[cine - 1].l[i];
            uint8_t *q = s + i * 0x70;
            memset(q, 0, 0x70);
            if (P->i <= 0.0f) continue;
            const float az = P->az * 3.14159265f / 180.0f, el = P->el * 3.14159265f / 180.0f;
            const float dx = hx * cosf(az) - hz * sinf(az), dz = hz * cosf(az) + hx * sinf(az);
            float *pos = (float *)(q + 0x10), *tgt = (float *)(q + 0x20), *col = (float *)(q + 0x30);
            pos[0] = C[0] + P->d * cosf(el) * dx; pos[1] = C[1] + P->d * sinf(el); pos[2] = C[2] + P->d * cosf(el) * dz; pos[3] = 1.0f;
            tgt[0] = C[0]; tgt[1] = C[1] + (i == 1 ? 0.15f : 0.0f); tgt[2] = C[2]; tgt[3] = 1.0f;
            col[0] = P->r; col[1] = P->g; col[2] = P->b;
            *(float *)(q + 0x40) = P->i * g_czs_light_k;
            *(float *)(q + 0x44) = 1.0f;
            *(float *)(q + 0x48) = P->cone;
            *(float *)(q + 0x4c) = P->cone * 0.7f;
            *(float *)(q + 0x50) = P->soft;
            *(uint32_t *)(q + 0x54) = P->sh > 0.5f;
            *(float *)(q + 0x64) = 0.1f;
            *(uint32_t *)(q + 0x00) = 1;
        }
        static int nc, lc = -1; if (lc != cine) { lc = cine; if (LOGCAP(nc, 40)) CZS_LOG("lights: setup %s (strength %.0f %%)", CZS_CINE[cine - 1].name, g_czs_light_k * 100.0f); }
        return;
    }
    for (int i = 0; i < 3; i++) {
        const float *L = CZS.lt[i], *aim = i < 2 ? fp : bp;
        uint8_t *q = s + i * 0x70;
        memset(q, 0, 0x70);
        float *pos = (float *)(q + 0x10), *tgt = (float *)(q + 0x20), *col = (float *)(q + 0x30);
        if (i == 2) continue;                       // (no back-model light - the back character stands almost in the shadow)
        if (ab && i == 1) {                         // the rim follows the key: the key's offset from the front chest, mirrored
            if (!CZS.ab[sc].l[0]) continue;         // through the chest on the ground plane, 25 cm higher; aimed at the upper back
            const float *K = CZS.ab[sc].lv[0];      // (Scene Editor MenuStage.RimLight: the same formula)
            float C[3] = {fp[0], fp[1] + 1.35f, fp[2]};
            pos[0] = 2 * C[0] - K[0]; pos[1] = K[1] + 0.25f; pos[2] = 2 * C[2] - K[2]; pos[3] = 1.0f;
            tgt[0] = C[0]; tgt[1] = C[1] + 0.15f; tgt[2] = C[2]; tgt[3] = 1.0f;
            if (CZS.ab[sc].l[1] && CZS.ab[sc].lv[1][9] > 0.0f) L = CZS.ab[sc].lv[1] + 3;     // the editor's rim colour / intensity / cone
        } else if (ab) {                            // the editor's light: world position + aim point; a light the layout has not = off
            if (!CZS.ab[sc].l[i]) continue;
            const float *W = CZS.ab[sc].lv[i];
            pos[0] = W[0]; pos[1] = W[1]; pos[2] = W[2]; pos[3] = 1.0f;
            tgt[0] = W[3]; tgt[1] = W[4]; tgt[2] = W[5]; tgt[3] = 1.0f;
            L = W + 3;                              // r g b intensity cone shadow at L[3..8], as in CZS.lt
        } else {
            pos[0] = cam[0] + rx * L[0] + fx * L[2]; pos[1] = aim[1] + L[1]; pos[2] = cam[2] + rz * L[0] + fz * L[2]; pos[3] = 1.0f;
            tgt[0] = aim[0]; tgt[1] = aim[1] + 1.25f; tgt[2] = aim[2]; tgt[3] = 1.0f;
        }
        col[0] = L[3]; col[1] = L[4]; col[2] = L[5];
        *(float *)(q + 0x40) = L[6] * g_czs_light_k;
        *(float *)(q + 0x44) = 1.0f;
        *(float *)(q + 0x48) = L[7];
        *(float *)(q + 0x4c) = L[7] * 0.7f;
        *(uint32_t *)(q + 0x54) = L[8] > 0.5f;
        *(float *)(q + 0x64) = 0.1f;
        *(uint32_t *)(q + 0x00) = L[6] > 0.0f;
    }
    static int nl; if (LOGCAP(nl, 2)) CZS_LOG("lights: 3 photo-mode slots at %p written (key %.2f %.2f %.2f)", (void *)s,
                                             cam[0] + rx * CZS.lt[0][0] + fx * CZS.lt[0][2], fp[1] + CZS.lt[0][1], cam[2] + rz * CZS.lt[0][0] + fz * CZS.lt[0][2]);
}
// one frame of the pose browser (freecam on; pe = the pad buttons pressed this frame)
static void czs_pose_browse(WORD pe) {
    int dir = (fc_edge(VK_NEXT) || (pe & 0x0008)) ? 1 : (fc_edge(VK_PRIOR) || (pe & 0x0004)) ? -1 : 0;
    int other = fc_edge(VK_HOME) || (pe & 0x4000), save = fc_edge(VK_END) || (pe & 0x2000);
    if (other) {
        CZB.sel = !CZB.sel;
        czs_model_t *m = &CZS.m[CZB.sel];
        char t[160];
        snprintf(t, sizeof t, "POSE BROWSER: %s model selected (%s)  PGUP / PGDN change pose, END save", CZ_FAC_NAME[CZB.sel], m->clip[0] ? m->clip : "bind pose");
        msg_hook(t, 4.0f, 0, 0);
    }
    czs_model_t *m = &CZS.m[CZB.sel & 1];
    if (!czs_alive(m)) { if (dir || save) msg_hook("POSE BROWSER: that model is not spawned", 3.0f, 0, 0); return; }
    const int sx = m->sex == 1 ? 1 : 0, n = CZS_NPOSE + CZB.nextra;
    if (dir) {
        int i = CZB.idx[CZB.sel & 1];
        if (i < 0) for (int k = 0; k < n; k++) if (!strcmp(czs_pose_name(k), m->clip)) { i = k; break; }
        float len = 0.0f;
        int found = -1, playable = 0, pos = 0;
        for (int step = 1; step <= n; step++) {
            int k = ((i < 0 ? (dir > 0 ? -1 : 0) : i) + dir * step + n * 4) % n;
            len = anim_len(m->id, czs_pose_name(k));
            if (len > 0.0f) { found = k; break; }
        }
        if (found < 0) { msg_hook("POSE BROWSER: no candidate clip is loaded for this body", 4.0f, 0, 0); CZS_LOG("pose browser: no playable clip for %s", CZ_FAC_NAME[m->fac]); return; }
        for (int k = 0; k < n; k++) if (anim_len(m->id, czs_pose_name(k)) > 0.0f) { playable++; if (k <= found) pos++; }
        CZB.idx[CZB.sel & 1] = found;
        snprintf(m->clip, sizeof m->clip, "%s", czs_pose_name(found));
        m->clip_len = len; m->clip_tried = 1; m->t_pose = 0;
        snprintf(CZB.pick[sx], sizeof CZB.pick[0], "%s", m->clip);
        czs_place(m, m->pos, m->yaw);
        char t[200];
        snprintf(t, sizeof t, "%s POSE %d / %d: %s (%.1f s)  END saves", CZ_FAC_NAME[m->fac], pos, playable, m->clip, len);
        msg_hook(t, 6.0f, 0, 0);
        CZS_LOG("pose browser: %s (sex %d) -> %s, %.2f s, %d / %d playable", CZ_FAC_NAME[m->fac], sx, m->clip, len, pos, playable);
    }
    if (save) {
        FILE *o = exe_side_open("t2r-cz-stage-saved.txt", "a");
        if (o) { fprintf(o, "# pose browser: %s model\npose %d %s\n", CZ_FAC_NAME[m->fac], sx, m->clip[0] ? m->clip : "-"); fclose(o); }
        char t[160];
        snprintf(t, sizeof t, "SAVED: pose %d %s (t2r-cz-stage-saved.txt)", sx, m->clip[0] ? m->clip : "-");
        msg_hook(t, 4.0f, 0, 0);
        CZS_LOG("pose browser: saved pose %d %s", sx, m->clip);
    }
}
// the stage freecam (see the head comment)
static void czs_fc_set(int on, const float *cam, float yaw, const char *why) {
    if (on == CZS.fc.on) return;
    CZS.fc.on = on; g_czs_fc = on; CZS.fc.look = 0; CZS.fc.ray_wait = 0; CZS.fc.last_ms = 0;
    if (on) {
        memcpy(CZS.fc.p, cam, 12); CZS.fc.yaw = yaw * 57.29578f; CZS.fc.pitch = CZS.pitch; CZS.fc.fov = CZS.fov;
        czs_pose_extra(); CZB.sel = CZS.front;
        CZS_LOG("freecam ON (%s) at %.2f %.2f %.2f yaw %.1f - F8 off, WASD QE fly, hold a mouse button to look, Z/X fov, F9 print, F10 put the characters here",
                why, cam[0], cam[1], cam[2], CZS.fc.yaw);
        msg_hook("FREECAM: WASD / QE fly, hold mouse to look, F9 print position, F10 place characters here, PGUP / PGDN poses, HOME other model, END save pose, F8 exit", 6.0f, 0, 0);
    } else CZS_LOG("freecam off (%s)", why);
}
// the t2r-cz-stage.txt lines of a stage whose camera is this pose (czs_layout backwards; the feet at y_feet)
static void czs_fc_spot(const float *p, float yaw_deg, float y_feet, float *g) {
    float y = yaw_deg / 57.29578f, fx = sinf(y), fz = cosf(y), rx = cosf(y), rz = -sinf(y);
    g[0] = p[0] + fx * CZS_FRONT_D + rx * CZS_FRONT_X; g[1] = y_feet; g[2] = p[2] + fz * CZS_FRONT_D + rz * CZS_FRONT_X;
}
// one frame of the freecam: input -> CZS.fc pose; returns 1 while it is on (the caller renders CZS.fc instead of the stage camera)
static int czs_fc_tick(int sc, const float *cam, float yaw) {
    uint64_t now = czs_now();
    if (!CZS.fc.chk || now >= CZS.fc.chk) {
        CZS.fc.chk = now + 2000;
        FILE *f = exe_side_open("t2r-freecam.txt", "r");
        int a = f != NULL; if (f) fclose(f);
        if (a != CZS.fc.allowed) { CZS.fc.allowed = a; if (a) CZS_LOG("freecam available (t2r-freecam.txt): F8 / pad L3+R3 on the stage"); }
    }
    if (!CZS.fc.allowed) {
        if (CZS.fc.on) czs_fc_set(0, cam, yaw, "t2r-freecam.txt removed");
        if (fc_edge(VK_F8)) CZS_LOG("F8 pressed - no stage freecam: t2r-freecam.txt is not next to the exe");
        return 0;
    }
    WORD pb = 0; BYTE lt = 0, rt = 0; SHORT lx = 0, ly = 0;
    int pad = pad_state(&pb, &lt, &rt, &lx, &ly);
    WORD pe = (WORD)(pb & ~CZS.fc.pb_last);
    CZS.fc.pb_last = pb;
    int f8 = fc_edge(VK_F8), sl = fc_edge(VK_SCROLL), toggle = f8 | sl;     // (Scroll Lock too, as the match freecam: F8 may be an OBS hotkey)
    if ((pb & 0x00c0) == 0x00c0) { if (!CZS.fc.l3r3) { CZS.fc.l3r3 = 1; toggle = 1; } } else if (!(pb & 0x00c0)) CZS.fc.l3r3 = 0;
    if (CZS.fc.on && fc_edge(VK_ESCAPE)) { czs_fc_set(0, cam, yaw, "Esc"); return 0; }
    if (toggle) { czs_fc_set(!CZS.fc.on, cam, yaw, f8 ? "F8" : sl ? "Scroll Lock" : "pad L3+R3"); if (!CZS.fc.on) return 0; }
    if (!CZS.fc.on) return 0;
    float dt = CZS.fc.last_ms ? (now - CZS.fc.last_ms) / 1000.0f : 0.016f;
    CZS.fc.last_ms = now;
    dt = dt < 0.001f ? 0.001f : dt > 0.1f ? 0.1f : dt;
    float k = fc_key(VK_SHIFT) ? 4.0f : fc_key(VK_CONTROL) ? 0.15f : 1.0f;
    // look: a mouse button held = drag-look (the cursor is held at the point where the drag began), arrows, the right stick
    int mb = game_focused() && ((GetAsyncKeyState(VK_LBUTTON) | GetAsyncKeyState(VK_RBUTTON)) & 0x8000);
    POINT cp;
    if (mb && GetCursorPos(&cp)) {
        if (!CZS.fc.look) { CZS.fc.look = 1; CZS.fc.anchor = cp; }
        else {
            CZS.fc.yaw -= (cp.x - CZS.fc.anchor.x) * 0.12f;      // (yaw grows to the LEFT, as the match freecam)
            CZS.fc.pitch += (cp.y - CZS.fc.anchor.y) * 0.12f;
            SetCursorPos(CZS.fc.anchor.x, CZS.fc.anchor.y);
        }
    } else CZS.fc.look = 0;
    float rsx = g_pad_rs[0] / 32767.0f, rsy = g_pad_rs[1] / 32767.0f;
    if (!pad || (rsx * rsx + rsy * rsy) < 0.24f * 0.24f) rsx = rsy = 0.0f;
    float lsx = lx / 32767.0f, lsy = ly / 32767.0f;
    if (!pad || (lsx * lsx + lsy * lsy) < 0.24f * 0.24f) lsx = lsy = 0.0f;
    CZS.fc.yaw += (((fc_key(VK_LEFT) ? 1.0f : 0) - (fc_key(VK_RIGHT) ? 1.0f : 0)) * 40.0f * k - rsx * 90.0f) * dt;
    CZS.fc.pitch += (((fc_key(VK_DOWN) ? 1.0f : 0) - (fc_key(VK_UP) ? 1.0f : 0)) * 40.0f * k - rsy * 60.0f) * dt;
    if (CZS.fc.pitch > 89) CZS.fc.pitch = 89; if (CZS.fc.pitch < -89) CZS.fc.pitch = -89;
    while (CZS.fc.yaw > 180) CZS.fc.yaw -= 360; while (CZS.fc.yaw < -180) CZS.fc.yaw += 360;
    if (fc_key('Z')) CZS.fc.fov *= powf(0.45f, dt);
    if (fc_key('X')) CZS.fc.fov /= powf(0.45f, dt);
    if (rt > 30) CZS.fc.fov *= powf(0.45f, dt * (rt - 30) / 225.0f);
    if (lt > 30) CZS.fc.fov /= powf(0.45f, dt * (lt - 30) / 225.0f);
    if (CZS.fc.fov < 5.0f) CZS.fc.fov = 5.0f; if (CZS.fc.fov > 120.0f) CZS.fc.fov = 120.0f;
    {   // fly: W A S D along the view, Q / E down / up (world)
        float y = CZS.fc.yaw / 57.29578f, pp = CZS.fc.pitch / 57.29578f;
        float fw[3] = {sinf(y) * cosf(pp), -sinf(pp), cosf(y) * cosf(pp)}, rtv[3] = {-cosf(y), 0, sinf(y)};
        float mf = (fc_key('W') ? 1.0f : 0) - (fc_key('S') ? 1.0f : 0) + lsy, mr = (fc_key('D') ? 1.0f : 0) - (fc_key('A') ? 1.0f : 0) + lsx;
        float mu = (fc_key('E') ? 1.0f : 0) - (fc_key('Q') ? 1.0f : 0) + ((pb & 0x0001) ? 1.0f : 0) - ((pb & 0x0002) ? 1.0f : 0);
        float sp = 3.0f * k * dt;
        for (int i = 0; i < 3; i++) CZS.fc.p[i] += (fw[i] * mf + rtv[i] * mr) * sp;
        CZS.fc.p[1] += mu * sp;
    }
    // F9 / R3: print the camera + the stage lines that put the characters in front of it (feet at the stage's current ground height)
    if (fc_edge(VK_F9) || (pe & 0x0080)) {
        float g[3], sg[3], sy;
        if (!czs_spot(sc, sg, &sy)) sg[1] = CZS.fc.p[1] - CZS_FRONT_Y;
        czs_fc_spot(CZS.fc.p, CZS.fc.yaw, sg[1], g);
        CZS_LOG("freecam SHOT scene %d: camera %.3f %.3f %.3f yaw %.2f pitch %.2f fov %.2f | t2r-cz-stage.txt: spot %d %.3f %.3f %.3f %.2f / cam %.1f %.1f",
                sc, CZS.fc.p[0], CZS.fc.p[1], CZS.fc.p[2], CZS.fc.yaw, CZS.fc.pitch, CZS.fc.fov, sc, g[0], g[1], g[2], CZS.fc.yaw, CZS.fc.fov, CZS.fc.pitch);
        FILE *o = exe_side_open("t2r-cz-stage-saved.txt", "a");
        if (o) { fprintf(o, "# camera %.3f %.3f %.3f yaw %.2f pitch %.2f fov %.2f\nspot %d %.3f %.3f %.3f %.2f\ncam %.1f %.1f\n",
                         CZS.fc.p[0], CZS.fc.p[1], CZS.fc.p[2], CZS.fc.yaw, CZS.fc.pitch, CZS.fc.fov, sc, g[0], g[1], g[2], CZS.fc.yaw, CZS.fc.fov, CZS.fc.pitch); fclose(o); }
        char t[200];
        snprintf(t, sizeof t, "CAMERA %.2f %.2f %.2f  YAW %.1f  PITCH %.1f  FOV %.0f  (saved to t2r-cz-stage-saved.txt)", CZS.fc.p[0], CZS.fc.p[1], CZS.fc.p[2],
                 CZS.fc.yaw, CZS.fc.pitch, CZS.fc.fov);
        msg_hook(t, 6.0f, 0, 0);
    }
    // F10 / Y: the characters here. The ground under the front spot: a ray from 1 m above the camera to 30 m below, read 2 frames later
    if (!CZS.fc.ray_wait && (fc_edge(VK_F10) || (pe & 0x8000))) {
        float g[3];
        czs_fc_spot(CZS.fc.p, CZS.fc.yaw, CZS.fc.p[1] - CZS_FRONT_Y, g);
        // three rays from different heights (the log: the one from camera + 1 m read t 0.000 on every F10 = it started inside something
        // or never ran); the first that hits below its own start (t > 0.002) wins. Read 2 frames later (containers.c reads after ~60 ms).
        static const float up[3] = {1.0f, 0.1f, -1.2f};
        CZS.fc.gx = g[0]; CZS.fc.gz = g[2]; CZS.fc.ry1 = CZS.fc.p[1] - 30.0f;
        for (int k = 0; k < 3; k++) {
            float a[3] = {g[0], CZS.fc.p[1] + up[k], g[2]}, b[3] = {g[0], CZS.fc.ry1, g[2]};
            CZS.fc.ry0[k] = a[1];
            CZS.fc.ray[k] = world_ray_kick(a, b);
        }
        CZS.fc.ray_wait = 2;
    }
    if (CZS.fc.ray_wait && --CZS.fc.ray_wait == 0) {
        float tk[3], t = -3.0f, gy = CZS.fc.p[1] - CZS_FRONT_Y;
        int hit = 0, err[3];
        for (int k = 0; k < 3; k++) { tk[k] = ray_t(CZS.fc.ray[k]); err[k] = g_ray_err; CZS.fc.ray[k] = 0; }
        for (int k = 0; k < 3 && !hit; k++)
            if (tk[k] > 0.002f && tk[k] <= 1.0f) { hit = 1; t = tk[k]; gy = CZS.fc.ry0[k] + (CZS.fc.ry1 - CZS.fc.ry0[k]) * t; }
        CZS_LOG("freecam: ground rays t %.4f%s %.4f%s %.4f%s (starts camera +1.0 / +0.1 / -1.2 m)", tk[0], err[0] ? " ERR" : "", tk[1],
                err[1] ? " ERR" : "", tk[2], err[2] ? " ERR" : "");
        CZS.spot[sc][0] = CZS.fc.gx; CZS.spot[sc][1] = gy; CZS.spot[sc][2] = CZS.fc.gz; CZS.spot[sc][3] = CZS.fc.yaw;
        float g[3] = {CZS.fc.gx, gy, CZS.fc.gz}, c2[3], f2[3], b2[3];
        czs_layout(g, CZS.fc.yaw / 57.29578f, c2, f2, b2);
        memcpy(CZS.fc.p, c2, 12); CZS.fc.pitch = CZS.pitch; CZS.fc.fov = CZS.fov;      // the page's shot from the new spot
        CZS_LOG("freecam: characters placed - spot %d %.3f %.3f %.3f %.2f (ground %s, ray t %.3f); camera now %.3f %.3f %.3f", sc, g[0], g[1], g[2],
                CZS.fc.yaw, hit ? "from the ray" : "NOT found - camera height - 0.64 m", t, c2[0], c2[1], c2[2]);
        FILE *o = exe_side_open("t2r-cz-stage-saved.txt", "a");
        if (o) { fprintf(o, "# placed (F10)%s\nspot %d %.3f %.3f %.3f %.2f\n", hit ? "" : " - no ground found under it", sc, g[0], g[1], g[2], CZS.fc.yaw); fclose(o); }
        char m[160];
        snprintf(m, sizeof m, "CHARACTERS PLACED: SPOT %.2f %.2f %.2f  YAW %.1f%s", g[0], g[1], g[2], CZS.fc.yaw, hit ? "" : "  (NO GROUND FOUND)");
        msg_hook(m, 5.0f, 0, 0);
    }
    czs_pose_browse(pe);
    return 1;
}
// every frame while the CUSTOMIZE page (or its CHALLENGES page) is up
static void czs_tick(int page_up, int edit_fac) {
    g_czs_clock = GetTickCount64();
    czs_grave_tick();
    czs_read_file();
    int sc = g_ms_cur;
    if (!page_up || CZS.off || sc < 1 || sc > 2) { czs_off(!page_up ? "page left" : CZS.off ? "t2r-no-customize-stage.txt" : "no faction scene", page_up && !CZS.off ? 0 : 1); return; }
    uint64_t now = czs_now();
    float g[3], yaw;
    if (!czs_spot(sc, g, &yaw)) { czs_off("no stage spot", 1); return; }
    float cam[3], fp[3], bp[3];
    czs_layout(g, yaw, cam, fp, bp);
    const int ab = czs_abs_on(sc);
    float pitch = CZS.pitch, fov = CZS.fov, ry[2];          // ry: each stand place's facing at rest
    if (ab) {
        memcpy(cam, CZS.ab[sc].cv, 12); pitch = CZS.ab[sc].cv[4]; fov = CZS.ab[sc].cv[5];
        memcpy(fp, CZS.ab[sc].mv[0], 12);
        if (CZS.ab[sc].m[1]) memcpy(bp, CZS.ab[sc].mv[1], 12);
    }
    ry[0] = ab ? CZS.ab[sc].mv[0][3] * 3.14159265f / 180.0f : czs_face(fp, cam);
    ry[1] = ab && CZS.ab[sc].m[1] ? CZS.ab[sc].mv[1][3] * 3.14159265f / 180.0f : czs_face(bp, cam);
    if (!CZS.on) {
        CZS.on = 1; CZS.t_open = now; CZS.cam_ready = 0; CZP.state = 0; CZK.at = 0; CZS.pv_foc[0] = CZS.pv_foc[1] = -1; CZS.front = edit_fac; CZS.swap_t0 = 0; CZS.user_yaw = 0; CZS.drag = 0;
        g_cz_zoom = 0; g_cz_zoom_u = 1.0f; CZS.z_fov = CZS.z_dp = CZS.z_dy = CZS.z_my = 0; CZS.z_ms = 0;
        czs_light_load();
        g_czs_t_fov = g_czs_t_pitch = g_czs_t_yaw = 0;       // (test-file camera offsets never outlive a visit)
        if (!(g_cz_show_at > now)) fade_to_black(0.18f, 0.25f, 0.45f);      // (an open through cz_open_start is black already)
        CZS_LOG("on: scene %d spot %.2f %.2f %.2f yaw %.1f, camera %.2f %.2f %.2f", sc, g[0], g[1], g[2], yaw * 57.29578f, cam[0], cam[1], cam[2]);
    }
    if (!CZS.cam_ready && now - CZS.t_open >= (g_cz_show_at > now ? 0u : 180u)) {           // under the black: camera cut + both models
        CZS.cam_ready = 1;
        czs_spawn(&CZS.m[CZS.front], CZS.front, fp, ry[0]);
        czs_spawn(&CZS.m[!CZS.front], !CZS.front, bp, ry[1]);
    }
    if (!CZS.cam_ready) return;
    czs_player_guard();
    // the camera: at cam, looking along the view yaw, pitched down a little
    float pose[6] = {cam[0], cam[1], cam[2], ab ? CZS.ab[sc].cv[3] : yaw * 57.29578f, pitch, fov};
    if (czs_fc_tick(sc, cam, yaw)) { pose[0] = CZS.fc.p[0]; pose[1] = CZS.fc.p[1]; pose[2] = CZS.fc.p[2]; pose[3] = CZS.fc.yaw; pose[4] = CZS.fc.pitch; pose[5] = CZS.fc.fov; }
    else {
        // ZOOM IN ON ITEM: the camera stays where it is and turns / narrows onto the part of the front model the shown category is about.
        // y = the framed point's height over the feet (m, male; female x 0.955), w = the picture's width there (m), turn = the model's
        // extra turn (BACKPACK: its back to the camera). The model keeps its place across the picture (right of the list): the view
        // aims beside the point by the same part of the half width as un-zoomed. Everything is eased (a hard cut / teleport of the camera looked wrong).
        static const struct { float y, w, turn; } ZF[CZ_NCAT] = {
            [CZ_HAT] = {1.70f, 1.25f, 0}, [CZ_TORSO] = {1.24f, 2.30f, 0}, [CZ_LOWER] = {0.52f, 2.30f, 0}, [CZ_BACKPACK] = {1.26f, 2.00f, 180.0f},
            [CZ_FACE] = {1.63f, 1.00f, 0}, [CZ_MELEE] = {0.90f, 1.80f, 0}, [CZ_MASK] = {1.63f, 1.00f, 0}, [CZ_SEX] = {0, 0, 0}};
        const float rad = 3.14159265f / 180.0f, base_yaw = pose[3], base_pitch = pose[4], base_fov = pose[5];
        float tf = base_fov, tp = 0, ty = 0, tm = 0;
        const int zc = CZ.cat;
        if (g_cz_zoom && zc >= 0 && zc < CZ_NCAT && ZF[zc].w > 0 && base_fov > 1.0f) {
            const float hy = ZF[zc].y * (CZS.m[CZS.front].sex ? 0.955f : 1.0f);
            const float dx = fp[0] - cam[0], dz = fp[2] - cam[2], dy = fp[1] + hy - cam[1], d = sqrtf(dx * dx + dz * dz);
            if (d > 0.5f) {
                float feet = atan2f(dx, dz) / rad - base_yaw;                 // where the model stands across the un-zoomed picture
                while (feet > 180.0f) feet -= 360.0f;
                while (feet < -180.0f) feet += 360.0f;
                const float part = tanf(feet * rad) / tanf(base_fov * 0.5f * rad);
                tf = 2.0f * atanf(ZF[zc].w * 0.5f / sqrtf(d * d + dy * dy)) / rad;
                if (tf > base_fov) tf = base_fov;
                tf = base_fov * powf(tf / base_fov, g_cz_zoom_u);        // the wheel / right stick: closer or less close (customize.c)
                if (tf < 3.0f) tf = 3.0f;
                ty = feet - atanf(part * tanf(tf * 0.5f * rad)) / rad;
                tp = -atan2f(dy, d) / rad - base_pitch;
                tm = ZF[zc].turn;
            }
        }
        float dt = CZS.z_ms ? (float)(now - CZS.z_ms) : 0.0f;
        if (dt > 100.0f) dt = 100.0f;
        CZS.z_ms = now;
        const float k = 1.0f - expf(-dt / 110.0f);
        if (CZS.z_fov < 1.0f) CZS.z_fov = base_fov;
        CZS.z_fov += (tf - CZS.z_fov) * k; CZS.z_dp += (tp - CZS.z_dp) * k; CZS.z_dy += (ty - CZS.z_dy) * k; CZS.z_my += (tm - CZS.z_my) * k;
        pose[5] = CZS.z_fov; pose[4] += CZS.z_dp; pose[3] += CZS.z_dy;
        if (g_czs_t_fov > 1.0f) pose[5] = g_czs_t_fov;
        pose[4] += g_czs_t_pitch; pose[3] += g_czs_t_yaw;
    }
    memcpy(g_cz_cam, pose, sizeof pose);
    g_cz_cam_on = 1;
    // an outfit edit: respawn that faction's model in its new look (same place)
    for (int f = 0; f < 2; f++) {
        czs_model_t *m = &CZS.m[f];
        int sex = g_cz.sex[f] < CZ_NSEX ? g_cz.sex[f] : 0;
        // (switching between male / female showed an A pose for a second: a fresh spawn stands in the bind pose until its
        // clip starts. The changed outfit spawns CZS_HIDE_Y over the place, is posed there, then takes the place and the old model goes.)
        czs_model_t *nx = &CZS.nx[f];
        uint8_t want[CZ_NCAT];
        czs_want(f, sex, want);
        const czs_model_t *cur = nx->t_spawn ? nx : m;
        if (m->t_spawn && !CZS.swap_t0 && !nx->t_spawn && czs_alive(m) && (cur->sex != sex || memcmp(cur->it, want, CZ_NCAT)) && czs_pool_take(f, sex, want, nx)) {
            // (a waiting model wears this outfit: it is the next one - the swap below brings it down, the standing one goes to the pool)
        } else
        if (m->t_spawn && !CZS.swap_t0 && !nx->t_spawn && now - g_czs_spawn_ms >= CZS_SPAWN_GAP_MS && czs_grave_room() &&
            !czs_kill_pending() && g_frame - g_czs_kill_frame > CZS_KILL_CLEAR &&
            (!czs_alive(m) || now - m->t_spawn >= CZS_MIN_LIFE_MS) && (cur->sex != sex || memcmp(cur->it, want, CZ_NCAT))) {
            if (!czs_alive(m)) {                                 // nothing standing there: straight onto the place
                float p[3]; memcpy(p, m->pos, 12); float y = m->yaw;
                czs_retire(m, "outfit changed");
                czs_spawn_it(m, f, f, sex, want, p, y);
            } else {
                memset(nx, 0, sizeof *nx);
                // (models looked wet: under the Seraphite stage is the sea - a model that waited down there came
                // up wet, the wetter the longer its kit took. It waits ABOVE the place now, out of the camera's view.)
                float p[3] = {m->pos[0], m->pos[1] + CZS_HIDE_Y, m->pos[2]};
                czs_spawn_it(nx, m->slot == f ? 2 + f : f, f, sex, want, p, m->yaw);       // (the spawn name the standing model does not hold)
                if (!nx->id) { memset(nx, 0, sizeof *nx); memcpy(m->it, want, CZ_NCAT); m->sex = sex; }      // (no record: do not retry every frame)
            }
        }
        if (nx->t_spawn) {
            if (!czs_alive(nx)) { if (now - nx->t_spawn > 3000) memset(nx, 0, sizeof *nx); }
            else {
                uint64_t a[3] = {nx->id, 2, 1}, c = nx->id;
                dc_call(fnv64("npc-set-script-mode"), 3, a);
                c = nx->id; dc_call(fnv64("npc-disable-perception"), 1, &c);
                c = nx->id; dc_call(fnv64("npc-request-dont-attack"), 1, &c);
                c = nx->id; dc_call(fnv64("npc-disable-character-collider"), 1, &c);
                czs_unarm(nx, now);
                czs_face_set(nx, now);
                czs_clean(nx, now);
                // (the previews showed with a 1 s delay: the waits are as short as the spawn allows - the pose is asked for from
                // 60 ms on, the model takes the place 60 ms after its clip started)
                if (!nx->clip_tried && now - nx->t_spawn > 60) czs_pose_pick(nx);
                if (nx->clip_tried) czs_place(nx, nx->pos, nx->yaw);                 // (starts the clip down there)
                if (nx->clip_tried && (now - nx->t_spawn > 1200 || (now - nx->t_spawn > 150 && (!nx->clip[0] || (nx->t_pose && now - nx->t_pose > 60))))) {
                    float p[3]; memcpy(p, m->pos, 12); float y = m->yaw;
                    czs_retire(m, "outfit changed");
                    *m = *nx; memset(nx, 0, sizeof *nx);
                    m->passive = 0;
                    czs_place(m, p, y);                                              // (the clip again at the real place: no blend)
                }
            }
        }
        // passive (the npcs reacted to the player when switching factions / sex, startled then 'Got you!'): the hidden menu player
        // stands at the stage spot, so a fresh spawn sees it at once. The SP tester's full set (t2r-sp.c dummy_passive mode 3): script only,
        // no perception, don't attack, stop; every frame for the first 1.5 s (the spawn may finish frames later and a later spawn step can
        // turn perception back on), then once a second. Collider off: the stage spot may be the hidden menu player's.
        czs_unarm(m, now);
        czs_face_set(m, now);
        czs_clean(m, now);
        czs_eyes(m, cam, now);
        if (czs_alive(m) && (now - m->t_spawn < 1500 || g_frame % 60 == 0)) {
            uint64_t a[3] = {m->id, 2, 1}, c = m->id;
            uint64_t r1 = dc_call(fnv64("npc-set-script-mode"), 3, a);
            c = m->id; uint64_t r2 = dc_call(fnv64("npc-disable-perception"), 1, &c);
            c = m->id; dc_call(fnv64("npc-request-dont-attack"), 1, &c);
            if (!m->clip[0]) { c = m->id; dc_call(fnv64("npc-stop"), 1, &c); }     // (posed: the stop could end the clip)
            if (!m->passive) {
                c = m->id; uint64_t r3 = dc_call(fnv64("npc-disable-character-collider"), 1, &c);
                m->passive = 1;
                CZS_LOG("%s model passive: npc-set-script-mode -> %llx, npc-disable-perception -> %llx, collider off -> %llx", CZ_FAC_NAME[f],
                        (unsigned long long)r1, (unsigned long long)r2, (unsigned long long)r3);
            }
        }
        if (czs_alive(m) && !m->clip_tried && now - m->t_spawn > 150) czs_pose_pick(m);    // (the next czs_place starts it)
    }
    if (CZS.m[0].t_spawn && CZS.m[1].t_spawn) { czs_pose_data(sc); czs_pose_paks(now); }
    // the exchange: CZ.fac changed (SWITCH FACTION / a click on the back model or its logo)
    if (edit_fac != CZS.front && !CZS.swap_t0) {
        CZS.swap_t0 = now; CZS_LOG("swap to %s (%d ms, dir %d, mode %d)", CZ_FAC_NAME[edit_fac], CZS.swap_ms, CZS.swap_dir, CZS.swap_mode);
        // (on a faction switch the sitting pose already started getting up, but the one already standing waited for the switch end and only sat down (or leaned back) after) the model coming to the FRONT blends into the front
        // clip where it sits, CZS_RISE_MS before it starts to move (a clip re-issued along the circle cannot blend); the one leaving keeps
        // its clip until it has arrived.
        czs_model_t *in = &CZS.m[!CZS.front];
        if (CZS.swap_mode && czs_alive(in)) {
            char was[48]; snprintf(was, sizeof was, "%s", in->clip);
            in->clip_tried = 0; czs_pose_pick(in);               // (czs_slot answers the place it is going to)
            if (in->clip[0] && strcmp(was, in->clip)) {
                uint64_t r = czs_pose_play(in, in->pos, in->yaw, (float)CZS_RISE_MS / 1000.0f);
                in->t_pose = now;
                CZS_LOG("swap: %s rises into %s where it is (%d ms blend, then it moves) -> %llx", CZ_FAC_NAME[in->fac], in->clip, CZS_RISE_MS, (unsigned long long)r);
            }
        }
    }
    float pf[3], pb[3];                                          // where the front / back faction's model stands this frame
    if (CZS.swap_t0) {
        float t = czs_ease((float)(now - CZS.swap_t0) / (float)CZS.swap_ms);
        // the model coming to the front leaves CZS_RISE_MS later (it rises first); both arrive together
        const uint64_t el = now - CZS.swap_t0, rise = CZS.swap_mode ? CZS_RISE_MS : 0;
        float t2 = el <= rise ? 0.0f : czs_ease((float)(el - rise) / (float)(CZS.swap_ms > rise + 100 ? CZS.swap_ms - rise : 100));
        float mx = (fp[0] + bp[0]) * 0.5f, mz = (fp[2] + bp[2]) * 0.5f;
        float a = -(float)CZS.swap_dir * 3.14159265f * t;      // clockwise from above (Y up): a negative turn
        float c = cosf(a), s = sinf(a);
        float ox = fp[0] - mx, oz = fp[2] - mz;
        pf[0] = mx + ox * c + oz * s; pf[2] = mz - ox * s + oz * c; pf[1] = fp[1] + (bp[1] - fp[1]) * t;   // the old front -> back
        { float a2 = -(float)CZS.swap_dir * 3.14159265f * t2, c2 = cosf(a2), s2 = sinf(a2);
          pb[0] = mx - ox * c2 - oz * s2; pb[2] = mz + ox * s2 - oz * c2; pb[1] = bp[1] + (fp[1] - bp[1]) * t2; }   // the old back -> front
        if (now - CZS.swap_t0 >= (uint64_t)CZS.swap_ms) {
            CZS.front = !CZS.front; CZS.swap_t0 = 0; CZS.user_yaw = 0; memcpy(pf, fp, 12); memcpy(pb, bp, 12);
            if (CZS.swap_mode) {                                 // arrived: each model blends into its new place's clip (same ap: a pose blend)
                for (int f = 0; f < 2; f++) {
                    czs_model_t *m = &CZS.m[f];
                    char was[48]; snprintf(was, sizeof was, "%s", m->clip);
                    m->clip_tried = 0; czs_pose_pick(m);
                    if (strcmp(was, m->clip)) { m->t_pose = 0; m->blend_next = CZS_SWAP_BLEND; }
                }
            }
        }
        else {
            czs_place(&CZS.m[CZS.front], pf, czs_face(pf, cam));
            if (el > rise) czs_place(&CZS.m[!CZS.front], pb, czs_face(pb, cam));     // (still rising: its blend runs untouched)
            czs_lights(sc, cam, yaw, fp, bp); return;
        }
    }
    // rotate the front model: drag with the left button held on it (czHitF), or L2 / R2
    float cx, cy; int lb = game_focused() && (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0, have = ui_cursor_canvas(&cx, &cy);
    if (g_czs_fc) lb = 0;
    if (lb && have) {
        if (!CZS.drag && CZ.hv_f) { CZS.drag = 1; CZS.drag_x = cx; }
        else if (CZS.drag) { CZS.user_yaw += (cx - CZS.drag_x) * 0.25f; CZS.drag_x = cx; }
    } else CZS.drag = 0;
    { WORD pb_ = 0; BYTE l = 0, r = 0; SHORT lx, ly;
      if (!g_czs_fc && pad_state(&pb_, &l, &r, &lx, &ly)) CZS.user_yaw += ((float)r - (float)l) / 255.0f * 3.0f; }
    if (CZS.user_yaw > 360.0f) CZS.user_yaw -= 360.0f; else if (CZS.user_yaw < -360.0f) CZS.user_yaw += 360.0f;
    czs_place(&CZS.m[CZS.front], fp, ry[0] + (CZS.user_yaw + CZS.z_my) * 3.14159265f / 180.0f);
    czs_place(&CZS.m[!CZS.front], bp, ry[1]);
    czs_lights(sc, cam, yaw, fp, bp);
}
