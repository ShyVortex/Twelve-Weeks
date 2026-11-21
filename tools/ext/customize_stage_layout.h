// The CUSTOMIZE stage layout made in the Scene Editor (tools/maps/editor_menu_stage.py import writes this file; customize_stage.c).
// Lines: model <sc> <0|1> x y z yaw / camera <sc> x y z yaw pitch fov / wlight <sc> <i> x y z tx ty tz r g b intensity cone shadow / spose <sc> <slot 0 front|1 back> <clip>.
// Empty = the derived layout (the menu player's spot).
static const char CZS_LAYOUT[] =
    "model 1 0 -36.219 -8.994 1042.823 -177.86\n"
    "model 1 1 -38.389 -8.990 1046.211 176.20\n"
    "camera 1 -35.613 -7.829 1036.500 -1.80 0.60 40.00\n"
    "wlight 1 0 -36.755 -7.348 1038.831 -36.043 -7.878 1042.823 1.000 0.900 0.780 6.00 40.0 1\n"
    "wlight 1 1 -35.683 -7.098 1046.815 -36.219 -7.494 1042.823 0.700 0.820 1.000 8.00 35.0 0\n"
    "wlight 1 2 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.00 0.0 0\n"
    "spose 1 0 npc-mm-ambi-buddy-idle\n"
    "spose 1 1 cap-npc-m-ambi-idle-lean-wall-loop 0.031 0.000 -0.404 0.00\n"
    "model 2 0 280.207 20.064 61.801 -65.60\n"
    "model 2 1 282.777 20.095 62.427 -71.10\n"
    "camera 2 274.204 21.594 64.607 120.00 4.20 40.00\n"
    "wlight 2 0 278.218 21.913 64.311 280.340 21.314 61.022 1.000 0.900 0.780 2.35 40.0 1\n"
    "wlight 2 1 282.195 22.163 59.290 280.207 21.564 61.801 0.700 0.820 1.000 8.00 35.0 0\n"
    "wlight 2 2 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.000 0.00 0.0 0\n"
    "spose 2 0 npc-mm-ambi-buddy-idle\n"
    "spose 2 1 efj-lounging-idle--male-b -1.200 -0.061 5.393 -147.06\n";
