"""In-game journal entries.

ROOT CAUSE: clan_ingame._journal_rows turned every story CARD of clan_story.journal() into its own journal entry, and a card is one written piece about
one person (portrait + name = the first member named in its text) with at most two one-liners under it.  A week of camp life therefore became ~24 entries,
each "by" a different member and each holding 1-2 events: noise, nobody to get to know.

FIX: compose_entries() regroups the SAME rows (nothing dropped) into entries.  One entry = 3..6 consecutive events (stories and one-liners alike, one clan
day or a quiet stretch of days), ONE author (two when the strongest event of the entry names exactly two members), whose name + portrait the card shows.
The author is a member the entry's events mention, picked so the voices ROTATE: whoever wrote least recently (and, among those, is mentioned most) takes
the next entry.  Event texts are laid one after the other in the body (a sentence-boundary share of the 1500-char wire budget per event, stories weigh double).

Pure functions (no db): rows = clan_story.story_rows() output (read_feed shape, newest first); roster = [{"name", "portrait"}].
"""
import re

import clan_story as CS

MIN_EVENTS, MAX_EVENTS = 3, 6
BODY_CHARS = 1450
_ARC = re.compile(r"^(?:DAY|DZIEŃ) (\d+): ([^.]*)\.\s*([\s\S]*)$")
_WB = r"(?<!\w)%s(?!\w)"


def _named(text, names):
    """Roster names that occur in text, in order of first occurrence."""
    hit = []
    for n in names:
        x = re.search(_WB % re.escape(n), text)
        if x:
            hit.append((x.start(), n))
    return [n for _, n in sorted(hit)]


def chunk(events):
    """events oldest first (list of rows).  Returns lists of 3..6 consecutive events; a day with fewer than 3 events carries into the next one, the last
    stretch may be smaller (today so far) - merged into the previous entry when that stays within MAX_EVENTS."""
    out, pend = [], []
    days = []
    for m in events:
        k = (int(m.get("week") or 0), int(m.get("day") or 0))
        if days and days[-1][0] == k:
            days[-1][1].append(m)
        else:
            days.append((k, [m]))
    for i, (_, grp) in enumerate(days):
        pend += grp
        if len(pend) < MIN_EVENTS and i < len(days) - 1:
            continue
        n = len(pend)
        k = max(1, -(-n // MAX_EVENTS))
        base, extra = divmod(n, k)
        pos = 0
        piece = []
        for j in range(k):
            sz = base + (1 if j < extra else 0)
            piece.append(pend[pos:pos + sz])
            pos += sz
        if k == 1 and n < MIN_EVENTS and out and len(out[-1]) + n <= MAX_EVENTS:
            out[-1] += pend
        else:
            out += piece
        pend = []
    return out


def _primary(ev):
    def key(m):
        r = CS._story_rank(m)
        return (3 if r is None else r, -len(str(m.get("text") or "")))
    return min(ev, key=key)


def compose_entries(rows, roster, seen_id=0):
    """-> [{"id", "primary" (row), "events" [rows oldest first], "authors" [names], "head", "body", "new", "arc"}] NEWEST first.  Every row of `rows` is in exactly one entry."""
    ppl = {p["name"]: p for p in roster}
    names = sorted(ppl, key=len, reverse=True)
    events = sorted(rows, key=lambda m: int(m["id"]))
    entries = []
    last_wrote = {}                                                  # name -> index of the entry they wrote last (rotation)
    for idx, ev in enumerate(chunk(events)):
        prim = _primary(ev)
        txt = " ".join(str(m.get("text") or "") for m in ev)
        score = {}
        for m in ev:
            for n in _named(str(m.get("text") or ""), names):
                score[n] = score.get(n, 0) + (3 if m is prim else 1)
        cand = sorted(score, key=lambda n: (last_wrote.get(n, -99), -score[n], n))
        authors = []
        if cand:
            authors = [cand[0]]
            pair = _named(str(prim.get("text") or "").split(".")[0], names)    # the headline of the strongest event names exactly two: they wrote it together
            if len(pair) == 2 and not set(pair) - set(score):
                authors = pair
        for a in authors:
            last_wrote[a] = idx
        entries.append({"prim": prim, "events": ev, "authors": authors, "score": score})
    for e in entries:
        ev, prim = e["events"], e["prim"]
        m0 = _ARC.match(str(prim.get("text") or ""))
        head = m0.group(2) if m0 else ""
        ptxt = m0.group(3) if m0 else str(prim.get("text") or "")
        if not head:                                                  # a plain camp-log piece: its first short sentence is the title
            ss = CS._sentences(ptxt, prim.get("names") or ())
            if len(ss) > 1 and len(ss[0]) <= 50:
                head, ptxt = ss[0].rstrip(".!?"), " ".join(ss[1:])
        parts = []
        weights = [2 if m.get("card") else 1 for m in ev]
        tot = sum(weights)
        for m, w in zip(ev, weights):
            share = max(90, int(BODY_CHARS * w / tot))
            t = str(m.get("text") or "")
            if m is prim:
                t = ptxt                                              # the headline is the entry's title
            elif _ARC.match(t):
                t = " ".join(CS._sentences(t, m.get("names") or ()))
            parts.append(_cut(t, share))
        e["head"], e["body"] = head, " ".join(p for p in parts if p)
        e["id"] = max(int(m["id"]) for m in ev)
        e["new"] = 1 if e["id"] > seen_id else 0
    entries.reverse()
    return entries


def _cut(t, n):
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= n:
        return t
    cut = t[:n]
    k = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:k + 1] if k > 30 else cut.rsplit(" ", 1)[0].rstrip(",;:") + "..."
