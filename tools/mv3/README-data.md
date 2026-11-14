# Melee v3 move data

`python tools/mv3/gen_moves.py` writes `tools/ext/mv3_moves.h` (156 rows of `mv3_move`, see `tools/ext/mv3.h`). The output is deterministic: rows in a fixed order, no timestamps, and two runs give the same file.
`gcc -std=gnu2x -I../ext tools/mv3/movestest.c` builds a check. It verifies every sid against the ext's fnv64 (`fnv("player")` = `SID_PLAYER`), the window order of every swing, the dodges, every lookup helper and the root-motion interpolation.

## What the header gives

| symbol | content |
|---|---|
| `MV3_MOVES[]`, `MV3_MOVES_N` | the contract table (non-static: `mv3.h` declares them `extern`) |
| `MV3_MOVES_COUNT`, `enum MV3_M_*` | the row count as a constant expression and row indices (`MV3_M_FIST_SWING1`, `MV3_M_DODGE_L_...`, `MV3_M_REACT_F_HEAD_FRONT_C`, `MV3_M_COUNTER_FIST_BACK`, ...) |
| `MV3_MOVES_X[]` | the extra data per row: the swing's `-hit` follow-through clip and its victim half, the `-hit` length, the swing's dodge-cancel frame, residency in the MP paks, and the blow angle / side a dodge answers |
| `MV3_MOVES_RM[][16][2]`, `mv3_move_rm_at(idx, mf, &fwd_mm, &right_mm)` | the authored root motion as 16 cumulative samples (cm), interpolated with integers only, so the sim can call it inside a step |
| `mv3_move_find(kind, wset, dir, step)` | row lookup. Swings: `step` = the combo step 0..2 with `MV3_K_SWING1`. Other kinds: `step` = the variant, resident rows first. Rows with `wset == MV3_WS_N` (dodges, misses, reactions) match every set. Returns -1 when nothing matches. |
| `mv3_move_variants`, `mv3_react_find(dir, strength, variant)`, `mv3_dodge_find(dir, ang, side, variant)` | variant count; a reaction by strength, falling back to the nearest strength; a dodge by the blow's angle and side, resident rows only |

Conventions: frames are 60 Hz from the move start. `dir` is 0 front, 1 left, 2 right, 3 back. `root_side` is positive to the character's RIGHT; the clips' align channel has +x = LEFT, and the sign is flipped. `dmg` is x10.

## Sources

- **MP-loaded melee paks.** `re/gamebin/actor97/anim-melee-{abby,ellie,player-shared}-t2.pak` (the game's own; read from the main checkout).
  - Clip length: ClipData +0xe frame count at 30 fps, length = (n - 1) / 30. Checked against the recorder's "length" lines: punch-2 48 f = 1.57 s, punch-3 66 f = 2.17 s.
  - Residency: a ClipData of 128 bytes or less is a streamed stub.
  - Anim events: the effect table, as `tools/part1/p1_carrier.ref_events`.
  - Root motion: the align channel, read with `re/factions2013/t1anim/t1raw.py` as in `gen_hitreact_rm.py`. One bad last key was found: `abby-1hblunt-combo-swing-1--abby` jumps 1.05 -> 5.38 m on its last frame. A last frame that jumps more than 0.3 m is held at the previous value.
  - Every clip used is present and resident.
- **SP melee recorder.** `re/sp-melee-1027/{report.md, session2/report.md, session3/report-a.md, report-b.md}` and `re/sp-melee-report-1026.txt` (switchblade).
- **Ext C source**, parsed so the table stays in sync:
  - `ctxdown.c` CD_PAIRS `dc-*` rows of kind 3;
  - `melee_hitreact.c` MHR_POOL / MHR_2H / MHR_CUT_MS;
  - `melee_dodge.c` MD_IFRAME_MS / MD_CLIP_MAX_MS / DUCK_L / DUCK_R;
  - `t2r-ext.c` melee_dmg_2013.
- **SP trace** `re/sp-sandbox-runs/nr-1025-full.log`: npc-reaction-step event spans. MP logs (a test client's `t2r-ext.log`): which miss clips are loaded.

## Measured vs estimated

### Swings: SP's first three presses from idle

| set | clips |
|---|---|
| fist | `abby-fist-combo-punch-1-left`, `-1`, `-2` (SP: left-1 -> 1 -> 2 -> 3 -> 4) |
| 1h blunt | `abby-1hblunt-combo-swing-1..3` |
| 1h blade | `ellie-machete-combo-slash-1..3` |
| 2h | `ellie-2hblunt-open-combo-1..3` |
| knife | `ellie-knife-combo-slash-1..3` |

**Contact `hit0_f`**

- **Measured** for fist 1-3, 1h blunt 1-3, machete 2, 2h 2 and knife 1-3. The value is the SP swing move's duration to the frame the engine switches to the synced `-hit` move, which is where the victim's reaction starts.
  - The value does not depend on distance: fist-2 is 321-339 ms over 0.64-1.21 m.
  - It is the median of the densest cluster.
- **Estimated** for machete 1 / 3 and 2h 1 / 3: the clip's swing-marker event (type 0x0f65d48cdf39b41b, unnamed) + 3 clip frames, or the weapon-effect event + 3 frames.
  - Measured against the 11 measured swings, this rule is off by -68..+65 ms (median -1 ms).

**Other swing fields**

- `hit1_f` = hit0 + 3. **Estimate**: SP has a single contact frame; this gives a 50 ms tolerance.
- **Chain window.** The next step starts no earlier than contact + the `-hit` minimum.
  - Fists: 331 ms, **measured** (30 chained SP `-hit` moves, 326-338 ms; presses up to 256 ms earlier were held to that point).
  - 1h blunt: 334 ms, **measured** (1 row).
  - Knife: 732 ms, a **measured upper bound** (switchblade `-hit` 732-766 ms).
  - 1h blade and 2h: 331 ms, **estimate** (no chained SP row).
  - The window is open for 300 ms. **Estimate**: SP still chained 190 ms past the minimum, left-1-hit 518 ms.
- `cancel_f` = chain1. **Estimate**: SP whiffs of fist-1 ended at 674 / 707 ms; ours is 900 ms.
- `MV3_MOVES_X.dodge_cancel_f` = contact + 100 ms. **Measured**: SP dodges cut a `-hit` 102-170 ms after contact.
- `reach` = SP's farthest contact distance (at most 2 m) + 0.15 m, with an **estimated** floor of fist 1.4 / 1h 1.6 / knife 1.5 / 2h 1.8 m. SP warps the attacker onto its target; v3 does not.
- `arc_deg`: fist / knife 60, 1h 70, 2h 75. **Estimate**: SP aligns the attacker to the target, so no arc was measured.
- `root_fwd` / `root_side` and the RM samples: **decoded** from the clips (the whole swing clip, i.e. the whiff path).
- `dmg`: melee_dmg_2013: fists 20, everything else MC_STD 34.
  - The machete's 40 is per item, not per set.
  - The knife falls to MC_STD the same way melee_dmg_now does.
- `strength` = mhr_strength: fist 0, 1h / knife 1, 2h 2.
- `sfx_n` = the sound-carrying anim events up to the contact. The events counted are sound-effect, weapon-effect, voice-effect, gear-effect upper/lower, foot-effect and the swing marker.

### Dodges

There are 57 dodge rows, all weapon sets.

| dir | rows, in pick order |
|---|---|
| forward | the open `^idle-forward` dodges, then `ellie-1h-dodge-forward-combat-a..d` |
| left / right | the duck lists of melee_dodge.c first, then every resident `ellie-1h-dodge-<dir>-combat-<angle>-<side>-<v>` |
| back | the contextual back clips, then `open^idle-back` |

- Length and root motion: **decoded**.
  - The ducks travel up to about 1.9 m; melee_dodge.c caps them at MD_DUCK_CAP 0.85 m. The cap is a gameplay choice for the sim / anim, not data.
- i-frames 0..23 (MD_IFRAME_MS 380). The value is the ext's tuning, not an SP measurement.
  - melee_dodge.c gives a forward dodge "into the blow" no immunity. The table keeps the i-frames; the sim decides.
- `cancel_f` = min(MD_CLIP_MAX_MS 680, 85 % of the clip). **Measured**: SP leaves the dodge clip at 555-674 ms.
- `chain0_f` = landing, the first frame at 90 % of the authored travel (**decoded**). `chain1_f` = landing + 36 (dcounter DC_WINDOW_MS 600).

### Misses

- `npc-reaction-step-left/right/back` are what SP plays.
  - **They are not in the MP paks**; the live MP log shows 0.00 s. They are flagged `resident = 0`.
  - Length 663 ms: an **estimate** from the SP trace event span.
  - Root motion 0.3 m: an **estimate**.
- The resident fallback is dir 0 `ellie-land-early-stumble^run` (MP log 1.87 s; cancel MD_MISS_MS 800).

### Reactions

- The 57 MHR_POOL `ellie-1h-hr-*` rows plus the 3 `ellie-2h-hr-back-center-*` rows.
- dir is remapped from MHR (0 front, 1 behind, 2 left, 3 right) to mv3 (0 front, 1 left, 2 right, 3 back). Strength comes from MHR.
- Length and root motion are **decoded**. `cancel_f` = MHR_CUT_MS of the strength (360 / 440 / 520).

### Counters

- The `dc-*` kind-3 rows of ctxdown.c, as COUNTER (attacker half, pair = victim half) plus COUNTERED (victim half).
- `hit0_f` = dmax and `cancel_f` = end_s (the hand-off), both from ctxdown.c. dir = 0 for `-fw` rows, 3 otherwise.
- `dc-fist-haymaker` and `dc-knife-palm` have two segments. Only segment 0 is in the row, and the comment says so; their hit and hand-off lie in segment 1.
- For SP comparison: SP's fist dodge-back-attack reached contact 454 ms after its press (4 rows). ctxdown's dmax 0.33 s counts from the pair clip's start.
- The root motion of paired clips is relative to the pair's start (apReference). Play them through psync placement.

## Not done / open

- The engine's melee `.bin` (melee/player-standing/player-*.bin) holds the authored per-move windows (melee-event-list, ranges), but `dconstruct` decodes those structs misaligned. Contact and chain times therefore come from the recorder, not from the `.bin`.
- No SP data exists for the machete / 2h chain times, or for steps 1 / 3 of those sets.
- The SP fist combo has 5 steps (left-1, 1, 2, 3, 4-punch/kick). The contract has 3, so step 4 (the heavy finisher with a 1.0-1.3 s `-hit`) is not in the table.
