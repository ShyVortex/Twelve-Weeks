"""One-way ground (ledges) on a map's navmesh: where a player can drop down but not climb back (Jackson Suburbs: two boxes on a ledge
behind a team's spawn). Rules: re/maps/layout-rules-2013.md section 9."""
import math

CLIMB_MAX = 0.9        # the most a player climbs between two neighbouring navmesh polygons (m); more is a drop he cannot come back up


def can_walk(nav, u, v, climb_max=CLIMB_MAX, steep=False):
    """u -> v on the navmesh: drops are fine, a climb over climb_max (or steeper than 0.7 + 0.25 m) is not. Stair wells whose steps
    are merged into big polygons (Capitol Hill shops: 1.2-1.5 m per link) need the map spec's "climb_max". steep (map spec "climb_steep": true):
    a ledge up to climb_max is climbed whatever its slope (Into the City: the sinkhole rim between the sunken park and the street is a
    0.9-1.6 m ledge, a single navmesh link of 1.15 m over 0.8 m; the player climbs it, the slope rule made the street one-way)."""
    dy = nav.cen[v][1] - nav.cen[u][1]
    d = math.hypot(nav.cen[v][0] - nav.cen[u][0], nav.cen[v][2] - nav.cen[u][2]) or 0.1
    return not (dy > climb_max or (not steep and dy > 0.7 * d + 0.25))


def mutual_region(ctx):
    """polygons of the play space inside the LARGEST strongly connected part of the walk graph (you can get there AND back, no one-way drops
    off a ledge). Cached on the ctx."""
    if getattr(ctx, "_mutual", None) is not None:
        return ctx._mutual
    nav, play = ctx.nav, ctx.play
    cm = float(ctx.spec.get("climb_max", CLIMB_MAX))
    steep = bool(ctx.spec.get("climb_steep"))
    fw = {u: [v for v in nav.adj[u] if v in play and can_walk(nav, u, v, cm, steep)] for u in play}
    rv = {u: [] for u in play}
    for u, vs in fw.items():
        for v in vs:
            rv[v].append(u)
    order, seen = [], set()
    for s in play:                                   # Kosaraju, iterative
        if s in seen:
            continue
        seen.add(s)
        st = [(s, iter(fw[s]))]
        while st:
            u, it = st[-1]
            for v in it:
                if v not in seen:
                    seen.add(v)
                    st.append((v, iter(fw[v])))
                    break
            else:
                order.append(u)
                st.pop()
    comp, best = {}, (0.0, set())
    for s in reversed(order):
        if s in comp:
            continue
        members, st = [], [s]
        comp[s] = s
        while st:
            u = st.pop()
            members.append(u)
            for v in rv[u]:
                if v not in comp:
                    comp[v] = s
                    st.append(v)
        a = sum(nav.area[i] for i in members)
        if a > best[0]:
            best = (a, set(members))
    ctx._mutual = best[1]
    return ctx._mutual
