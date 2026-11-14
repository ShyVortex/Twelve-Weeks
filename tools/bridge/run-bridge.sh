#!/bin/bash
# Launch t2r-bridge.exe under Proton in the TLOU2 prefix, forced to Spacewar
# appid 480 (steam_appid.txt + SteamAppId) so it never touches TLOU2's Steam
# context (2531310). Reports the real Steam persona name to the daemon and runs
# the local-UDP <-> Steam-P2P gameplay bridge.
#
# Runs from THIS dir (its own steam_appid.txt=480, copied steam_api64.dll, and
# tlou-ii-mp.json token) — the game install is not touched.
export STEAM_COMPAT_DATA_PATH="${STEAM_COMPAT_DATA_PATH:-$HOME/.steam/steam/steamapps/compatdata/2531310}"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="/home/lavan/.local/share/Steam"
export SteamAppId=480
export SteamGameId=480
PROTON="/usr/share/steam/compatibilitytools.d/proton-cachyos-slr/proton"
cd "$(dirname "$0")"
exec "$PROTON" run ./t2r-bridge.exe
