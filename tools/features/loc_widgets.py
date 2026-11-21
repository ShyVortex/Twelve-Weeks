"""Static widget texts -> text-table ciphers (the game's own way of localising a widget label).

A Text widget of the mod (a page tools/features/*widgets*.py builds, or a label added to a game page) carries its English string in
the widget file, so it never changes with the game's language. apply() (called by widgets_patch.patch_widgets before the pak is
built) gives every such Text widget whose text is a key of the translation table the cipher T2RL_<hash of the text> instead
(`cipherId`, the `text` field dropped: the engine then reads the label from the loaded language's text2/<lang>.common, exactly like
the game's own widgets). REGISTRY remembers cipher -> English text; loc_tables.add_widget_ciphers() writes the ciphers into every
language table (English text, or the translation where the language has one)."""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "loc"))
import locdata  # noqa: E402

REGISTRY = {}      # cipher name -> English text (raw, with its blanks)


def cipher_name(text):
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return "T2RL_%08X" % h


def fnv64(name):
    h = 0xCBF29CE484222325
    for ch in name.encode("ascii"):
        h = ((h ^ ch) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def apply(wdir, code="pl"):
    """cipherId for every Text widget whose text is a (non-pattern) translation key. Returns the number of widgets changed."""
    keys = {k for _, k, v, _, _ in locdata.load(code) if "%" not in k and "{" not in k}
    n = 0
    for f in glob.glob(os.path.join(wdir, "**", "*.widget.json"), recursive=True):
        try:
            w = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        changed = False
        for it in w.get("items", []):
            t = it.get("text")
            if not isinstance(t, str) or "pointSize" not in it or it.get("cipherId"):
                continue
            if t.strip() not in keys:
                continue
            name = cipher_name(t)
            it["cipherId"] = name
            del it["text"]
            REGISTRY[name] = t
            changed = True
            n += 1
        if changed:
            json.dump(w, open(f, "w", encoding="utf-8"), indent=4)
    return n
