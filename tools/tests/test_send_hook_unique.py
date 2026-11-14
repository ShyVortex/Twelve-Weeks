"""Regression (re/look-spawn-1019.md): winmm's SendEvent (FUN_18005dc60) must be hooked by exactly ONE installer.

A second installer (the 'respawn log' hook) ran first and rewrote the prologue, so install_send_hook's prologue check failed
('send hook: prologue mismatch, not installed'), g_send_tramp stayed NULL and no ext message (faction look, stow, ...) was ever sent.
Source-level check: every function that patches the function entry (VMA(0x18005DC60) with a prologue memcmp) is counted.
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "ext", "t2r-ext.c")
s = open(SRC, "rb").read().decode("utf-8", "replace")
fails = []
inst = [m.start() for m in re.finditer(r"uint8_t \*f = \(uint8_t \*\)VMA\(0x18005DC60\);", s)]
if len(inst) != 1:
    fails.append("expected exactly 1 entry patcher of 0x18005DC60, found %d" % len(inst))
if "install_send_hook();" not in s:
    fails.append("install_send_hook is never called")
if "install_sendevent_hook" in s:
    fails.append("the second SendEvent installer is back")
if "sendev_log(type, len, slot);" not in s:
    fails.append("send_hook no longer logs the respawn request/grant events")
if fails:
    print("FAIL\n" + "\n".join(fails)); sys.exit(1)
print("ok: one SendEvent hook")
