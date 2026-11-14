"""Server notices: messages the daemon shows to players in game (match + menus) and in the launcher. Pure logic, no sockets.

Kinds (language-neutral: the client renders its own English / Polish text from kind + param; free text is shown as-is):
  u  update available      param 0                    per player: only those whose reported build is not the target build
  v  update required       param 0                    per player: build differs from the server's and the player is not in a match, so its searches are refused
  r  planned restart       param = seconds left       admin-scheduled (POST /shutdown {minutes, reason}); counts down; cancel removes it
  s  shutting down now     param 0                    SIGTERM / Ctrl+C / console close, or the end of a scheduled countdown
  t  free text             param = seconds on screen  admin free text (POST /notice {text, seconds}); kept max(seconds + 20, 60) s for the polls

Wire (t2r-ext short TCP connection, polled every ~6 s in a match and in the menus):
  ext -> server  0xBA [64B token][u8 ver=1][u8 lang 0 en / 1 pl]
  server -> ext  0xBB ASCII/UTF-8 "n=<k>\\n<id>|<kind>|<param>|<text>\\n..."   (<= 4 lines; text empty for u / r / s; no '|' / newline inside)
An old client never sends 0xBA; an old server ignores it (the ext stops after 2 unanswered tries). Menu clients that hold a session socket also get the text
as an op 0x11 note when a notice is created (the existing menu note path).
"""
import threading
import time

OP_REQ, OP_REPLY = 0xBA, 0xBB
MAX_TEXT = 140
MAX_LINES = 4


def clean(s, n=MAX_TEXT):
    s = "".join(" " if (ord(c) < 32 or ord(c) in (0x7f, 0x2028, 0x2029, 0x85)) else c for c in str(s or ""))
    return s.replace("|", "/").strip()[:n]


class Notices:
    def __init__(self, now=time.time):
        self.now = now
        self.lock = threading.Lock()
        self.seq = 0
        self.texts = {}          # id -> {"text", "until"}
        self.shutdown = None     # {"id", "at", "reason", "restart"}
        self.final = None        # {"id", "until"}: 'shutting down now'

    def _id(self):
        self.seq += 1
        return self.seq

    def add_text(self, text, minutes=30.0, seconds=None, text_pl=None):
        """seconds: time ON SCREEN (param of kind t, 2..600 s). Clients poll every ~6 s,
        so the notice stays available max(seconds + 20, 60) s for everyone to pick it up once. Without seconds: the old minutes window, 8 s on screen."""
        text = clean(text)
        text_pl = clean(text_pl)
        if not text and not text_pl:
            return None
        text = text or text_pl                       # only a Polish text typed: English readers get it as typed
        with self.lock:
            i = self._id()
            if seconds is not None:
                show = int(max(2, min(float(seconds), 600)))
                keep = max(show + 20.0, 60.0)
            else:
                show = 8
                keep = max(0.5, min(float(minutes), 24 * 60)) * 60.0
            self.texts[i] = {"text": text, "text_pl": text_pl, "until": self.now() + keep, "show": show}
            return i

    def clear(self, nid):
        with self.lock:
            if self.texts.pop(int(nid), None) is not None:
                return True
            if self.shutdown and self.shutdown["id"] == int(nid):
                self.shutdown = None
                return True
            return False

    def schedule(self, minutes, reason="", restart=True, reason_pl=None):
        minutes = max(0.0, min(float(minutes), 24 * 60))
        with self.lock:
            self.shutdown = {"id": self._id(), "at": self.now() + minutes * 60.0, "reason": clean(reason), "reason_pl": clean(reason_pl), "restart": bool(restart)}
            return dict(self.shutdown)

    def cancel(self):
        with self.lock:
            had = self.shutdown is not None
            self.shutdown = None
            return had

    def go_final(self, hold=60.0):
        with self.lock:
            self.final = {"id": self._id(), "until": self.now() + hold}

    def due(self):
        """The scheduled shutdown if its time has come (the daemon then exits), else None."""
        with self.lock:
            s = self.shutdown
            return dict(s) if s and self.now() >= s["at"] else None

    def active(self, stale_build=False, refused=False, lang="en"):
        """[(id, kind, param, text)] for one player. stale_build: this player's build is not the target one (kind u).
        lang "pl": admin free text / restart reason come in their Polish form when the admin typed one (else as typed)."""
        pl = lang == "pl"
        now = self.now()
        out = []
        with self.lock:
            for i in [i for i, t in self.texts.items() if t["until"] <= now]:
                del self.texts[i]
            if self.final and now < self.final["until"]:
                out.append((self.final["id"], "s", 0, ""))
            s = self.shutdown
            if s:
                out.append((s["id"], "r", max(0, int(round(s["at"] - now))), (s.get("reason_pl") if pl else "") or s["reason"]))
            if refused:
                out.append((1, "v", 0, ""))             # id 1 = 'update required' (replaces u: the searches fail until the launcher updates the game)
            elif stale_build:
                out.append((0, "u", 0, ""))             # id 0 = the player's own 'update available' (stable id for the client's shown-once set)
            for i, t in sorted(self.texts.items()):
                out.append((i, "t", int(t.get("show", 8)), (t.get("text_pl") if pl else "") or t["text"]))
        return out[:MAX_LINES]

    def public(self):
        """Player-independent list for the status file / launcher: [{"id","kind","param","text","endsAt"}]."""
        now = self.now()
        out = []
        for i, k, p, t in self.active(False):
            ends = None
            if k == "r":
                ends = now + p
            elif k == "t":
                ends = self.texts.get(i, {}).get("until")
            e = {"id": i, "kind": k, "param": p, "text": t, "endsAt": ends}
            pt = (self.texts.get(i, {}).get("text_pl") if k == "t" else (self.shutdown or {}).get("reason_pl") if k == "r" else "")
            if pt:
                e["text_pl"] = pt                      # the launcher's status.json fallback picks it for a Polish UI
            out.append(e)
        return out

    @staticmethod
    def reply_text(items):
        lines = ["%d|%s|%d|%s" % (i, k, p, clean(t)) for i, k, p, t in items]
        return ("n=%d\n" % len(lines) + "\n".join(lines)).encode("utf-8")
