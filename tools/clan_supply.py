"""Clan supplies per category (food, water, medicine, ammo, materials): the real numbers behind the launcher's SUPPLIES panel.  Imported by clan.apply_match.

The 2013 / PS4 engine keeps ONE number per day: supplies (bottles + parts * 0.02) against needed (clan.needed).  That number, its deficit and everything it does
to the people stay exactly clan.py's.  This module splits the same numbers into categories, so the clan screens and the saga can say WHAT ran short:

  intake  (food + water + medicine) = the day's engine supplies, split by the match the player actually played (weights, largest remainder, sum == supplies):
              food     50 + 2 * downed enemies + 3 * executions        (hunting and kills bring meat and cans home)
              water    30 + 2 * marked enemies (scouting finds the wells and filters)
              medicine 20 + 8 * revives + 2 * times downed             (every revive saves a kit, every time the raider went down costs a visit)
          ammo      = downed enemies + 2 * headshots   (shots that did not need a second one are rounds picked back up)
          materials = parts // 100 + executions        (parts are scrap: boxes, crafting)
          A match that was left early brings nothing home (engine: ProcessClanDay(0, 0)); the labels the client does not send count as 0.
  need per day  = clan.needed(N) split 50 / 30 / 20 into food / water / medicine (medicine at least 1 for a clan of 3+), the same split the launcher always drew;
          ammo = ceil(N / 3), materials = ceil(N / 4) (the people use them up: guns, repairs, fires).
  trade         = a category with more than its need lends the rest to the short ones (the camp shares), so the shortage left is exactly the engine's deficit
          (max(0, needed - supplies)); no category is short on a day the engine calls a surplus.
  stock         = per-clan goods on hand, meta["sup"]["stock"].  Leftovers of a surplus day are banked (up to 3 days of that need); on a shortage day the stock
          is drawn first (r["sup"]["drawn"]), the rest is the NET shortage; the engine's people effects are NOT changed by the stock (it banks nothing:
          *clan-vars*[+8] = 0) - the stock only shows what the camp had in the larder when the day went wrong, and it is what "days left" counts.
          Ammo and materials: stock + intake - use, never below 0, a shortage when use is not covered (no effect on the people).
  hunger/sickness cause: r["sup"]["cause"] = the category with the largest gross shortage among food / water / medicine (medicine -> the sick, food or water ->
          the hungry); the saga (clan_saga.py) writes it into the memory of every hungry / sick member.
Old results without r["sup"] stay valid; consumers fall back to their own model.
"""
CATS = ("food", "water", "med", "ammo", "mat")
SURVIVAL = ("food", "water", "med")
BANK_DAYS = 3                      # a survival stock holds at most this many days of its need
STOCK_CAP = 999


def split(total, weights):
    """Largest-remainder split of an integer by weights; the parts add up to `total`."""
    total = max(0, int(total))
    s = float(sum(weights)) or 1.0
    raw = [total * w / s for w in weights]
    out = [int(x) for x in raw]
    rest = total - sum(out)
    for _f, i in sorted(((raw[i] - out[i], i) for i in range(len(raw))), key=lambda t: (-t[0], t[1]))[:max(0, rest)]:
        out[i] += 1
    return out


def need_split(need, n=None):
    """{food, water, med} of the day's need (sums to `need`); n = clan size (medicine is at least 1 from 3 members up)."""
    need = max(0, int(need))
    nm = max(1 if (n if n is not None else need) >= 3 and need >= 3 else 0, int(round(need * 0.2)))
    nw = int(round(need * 0.3))
    nf = max(0, need - nm - nw)
    return {"food": nf, "water": nw, "med": nm}


def use_of(n):
    """What the people use up of ammo / materials in a day."""
    n = max(0, int(n))
    return {"ammo": (n + 2) // 3, "mat": (n + 3) // 4}


def intake(supplies, parts, counts, left=False):
    """The goods the match brought home per category (see the module doc)."""
    c = counts or {}
    g = lambda k: max(0, int(c.get(k, 0) or 0))                       # noqa: E731
    if left:
        return {k: 0 for k in CATS}
    kills, execs, revives, hs, marked, downed = g(1), g(2), g(3), g(4), g(5), g(21)
    f, w, m = split(supplies, [50 + 2 * kills + 3 * execs, 30 + 2 * marked, 20 + 8 * revives + 2 * downed])
    return {"food": f, "water": w, "med": m, "ammo": kills + 2 * hs, "mat": max(0, int(parts)) // 100 + execs}


def book(stock, supplies, need, n_before, parts, counts, left=False, forgive=False):
    """One day. stock = {cat: n} on hand before; returns (new stock, record). The record is what clan.apply_match stores in r["sup"] (all ints).
    forgive = the engine forgave this day's deficit (a ping / admin kick, an excused leave, a late join): the camp is not short that day, so the stock
    pays nothing."""
    stock = {k: max(0, int(dict(stock or {}).get(k, 0))) for k in CATS}
    got = intake(supplies, parts, counts, left)
    nd = need_split(need, n_before)
    nd.update(use_of(n_before))
    # trade among the survival goods: the over-supplied ones cover the short ones
    short = {k: max(0, nd[k] - got[k]) for k in SURVIVAL}
    spare = {k: max(0, got[k] - nd[k]) for k in SURVIVAL}
    pool = sum(spare.values())
    for k in sorted(SURVIVAL, key=lambda x: (-short[x], x)):
        take = min(short[k], pool)
        short[k] -= take
        pool -= take
    # whatever spare is left after covering the short ones is the leftover of the day
    left_over = {k: 0 for k in SURVIVAL}
    to_take = sum(spare.values()) - pool                              # spare goods that were lent
    for k in sorted(SURVIVAL, key=lambda x: (-spare[x], x)):
        lend = min(spare[k], to_take)
        to_take -= lend
        left_over[k] = spare[k] - lend
    if forgive:
        short = {k: 0 for k in SURVIVAL}
    gross = dict(short)
    drawn, net = {}, {}
    new = dict(stock)
    for k in SURVIVAL:
        d = min(new[k], short[k])
        drawn[k] = d
        net[k] = short[k] - d
        new[k] -= d
        new[k] = min(BANK_DAYS * max(1, nd[k]), new[k] + left_over[k])
    for k in ("ammo", "mat"):
        have = new[k] + got[k]
        if forgive:                                                    # a forgiven day uses only what the match brought, never the stock
            short[k] = gross[k] = drawn[k] = net[k] = 0
            new[k] = min(STOCK_CAP, new[k] + max(0, got[k] - nd[k]))
            continue
        short[k] = max(0, nd[k] - have)
        gross[k] = short[k]
        drawn[k] = min(new[k], max(0, nd[k] - got[k]))
        net[k] = short[k]
        new[k] = min(STOCK_CAP, max(0, have - nd[k]))
    days = {k: (new[k] // nd[k] if nd[k] > 0 else 0) for k in CATS}
    cause = ""
    sv = [k for k in SURVIVAL if gross[k] > 0]
    if sv:
        cause = max(sv, key=lambda x: (gross[x], x == "med", x))
    rec = {"got": got, "need": nd, "short": gross, "drawn": drawn, "net": net, "stock": dict(new), "days": days, "cause": cause}
    return new, rec
