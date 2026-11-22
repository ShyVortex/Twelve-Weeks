"""ping_fit: a far player (all known pings over the limit) is not kept by a host whose ping to it is unknown."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hostmig

fails = 0
def check(name, cond):
    global fails
    print(("  ok  " if cond else "FAIL  ") + name)
    if not cond:
        fails += 1

def mk(table):
    def pair(a, b):
        return table.get((a, b), table.get((b, a)))
    return pair

# shape: M far from A, B, C, D (known), E and F just queued (no ping to M yet); the others are close to each other
P = ["M", "A", "B", "C", "D", "E", "F"]
t = {("M", "A"): 414, ("M", "B"): 246, ("M", "C"): 260, ("M", "D"): 382}
for i, a in enumerate("ABCDEF"):
    for b in "ABCDEF"[i + 1:]:
        t[(a, b)] = 120
kept, dropped, h, info = hostmig.ping_fit(P, mk(t), 190)
check("far M dropped although E/F have no ping to it", dropped == ["M"] and h != "M")
check("the rest kept", kept == ["A", "B", "C", "D", "E", "F"])

# a newcomer with only one known ping over the limit is not far (not enough known)
t2 = {("N", "A"): 230, ("A", "B"): 100, ("A", "C"): 100, ("B", "C"): 100}
kept, dropped, h, info = hostmig.ping_fit(["N", "A", "B", "C"], mk(t2), 190)
check("one known high ping: N not judged far, kept via a host with no ping to it", "N" in kept)

# everybody far from everybody: nobody is matched with anybody (each host keeps itself only)
t3 = {("X", "Y"): 300, ("X", "Z"): 300, ("Y", "Z"): 300}
kept, dropped, h, info = hostmig.ping_fit(["X", "Y", "Z"], mk(t3), 190)
check("all far: a host keeps only itself", len(kept) == 1)

# a far party is dropped whole
t4 = dict(t); t4[("M", "A")] = 414
kept, dropped, h, info = hostmig.ping_fit(["M", "Q", "A", "B", "C", "D", "E"], mk({**t, ("Q", "A"): 400, ("Q", "B"): 400, ("Q", "C"): 400, ("Q", "D"): 400, ("M", "Q"): 20}), 190,
                                          units_fn=lambda x: ["M", "Q"] if x in ("M", "Q") else [x])
check("far party M+Q dropped whole", set(dropped) == {"M", "Q"})

# nothing far: old behaviour (unknowns not judged)
t5 = {("A", "B"): 100}
kept, dropped, h, info = hostmig.ping_fit(["A", "B", "C"], mk(t5), 190)
check("no far player: all kept", kept == ["A", "B", "C"])

print("failures:", fails)
sys.exit(1 if fails else 0)
