"""Polish side of the clan feed (every clan status line also in Polish, correct grammar, shown in the game's TEXT language).

Design: the generator (tools/clan_story.py) stays language-neutral at the source. Every message it writes is stored with
  lid     "<pool>/<crc32 of the English template>"     which template said it (the English template is the identity of a line)
  params  {"p": {"A": ["Name", "g"], ...}, "s": {symbolic variables}}   the people (name + gender m / f / n) and the variables as KEYS
          (place / infected / illness as the English dictionary key, counts as integers, ...), never as words
and the English `text` as before. Any language is rendered from (lid, params) at read time: English from the English template, Polish from
the parallel Polish template of this module (tools/clan_story_pl_good.py / clan_story_pl_dark.py + the tickers below, same pools, same order,
same scopes). A message written before this change has no lid: it reads back in English in every language.

Polish grammar without declining names: the templates are phrased with the NAME IN THE NOMINATIVE only ("{A}: gangrena postępuje.") and use pronoun
forms for the other cases ({A?go|ją}, {A?mu|jej}, {A?niego|nią} ...). Gender: {A?ł|ła} picks the masculine | feminine ending of A (neutral names take the
masculine one), {AB?ili|iły} the feminine plural only when every named person is female. Variables come in the cases the templates need
({place_at} "na stadionie", {ill_gen} "zapalenia płuc", {lost_acc} "dwie osoby", ...): see expand().
"""
import re
import zlib

import clan_story_data as D
import clan_story_lines_good as LG
import clan_story_lines_dark as LD
import clan_story_pl_good as PG
import clan_story_pl_dark as PD
import clan_story_solo as SO
import clan_story_spores as SPR
import clan_story_good_rich as RG

LANGS = {"en": 0, "pl": 1}


def norm_lang(x):
    """A language request in any form (None / b'' = English, 1 / b'\\x01' / "pl" / "pol" / "pl-PL" = Polish) -> "en" | "pl"."""
    if isinstance(x, (bytes, bytearray)):
        x = x[0] if x else 0
    if isinstance(x, int):
        return "pl" if x == 1 else "en"
    s = str(x or "").strip().lower().replace("_", "-")
    return "pl" if s in ("1", "pl", "pol", "polish") or s.startswith("pl-") else "en"


def line_crc(text):
    return "%08x" % (zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)


# ------------------------------------------------------------------ variables in Polish
# place: English name -> (nom, gen, at "na stadionie", to "na stadion", from "ze stadionu", ins "za stadionem")
PLACES = {
    "stadium": ("stadion", "stadionu", "na stadionie", "na stadion", "ze stadionu", "stadionem"),
    "checkpoint": ("punkt kontrolny", "punktu kontrolnego", "przy punkcie kontrolnym", "do punktu kontrolnego", "z punktu kontrolnego", "punktem kontrolnym"),
    "FOB": ("baza", "bazy", "w bazie", "do bazy", "z bazy", "bazą"),
    "east barracks": ("wschodnie koszary", "wschodnich koszar", "we wschodnich koszarach", "do wschodnich koszar", "ze wschodnich koszar", "wschodnimi koszarami"),
    "loading dock": ("rampa załadunkowa", "rampy załadunkowej", "na rampie załadunkowej", "na rampę załadunkową", "z rampy załadunkowej", "rampą załadunkową"),
    "old gym": ("stara sala gimnastyczna", "starej sali gimnastycznej", "w starej sali gimnastycznej", "do starej sali gimnastycznej", "ze starej sali gimnastycznej",
                "starą salą gimnastyczną"),
    "pharmacy block": ("blok z apteką", "bloku z apteką", "w bloku z apteką", "do bloku z apteką", "z bloku z apteką", "blokiem z apteką"),
    "island": ("wyspa", "wyspy", "na wyspie", "na wyspę", "z wyspy", "wyspą"),
    "long house": ("długi dom", "długiego domu", "w długim domu", "do długiego domu", "z długiego domu", "długim domem"),
    "kitchen house": ("dom kuchenny", "domu kuchennego", "w domu kuchennym", "do domu kuchennego", "z domu kuchennego", "domem kuchennym"),
    "harbor": ("przystań", "przystani", "na przystani", "na przystań", "z przystani", "przystanią"),
    "weaving house": ("tkalnia", "tkalni", "w tkalni", "do tkalni", "z tkalni", "tkalnią"),
    "settlement": ("osada", "osady", "w osadzie", "do osady", "z osady", "osadą"),
    "shore camp": ("obóz na brzegu", "obozu na brzegu", "w obozie na brzegu", "do obozu na brzegu", "z obozu na brzegu", "obozem na brzegu"),
}
# the opposing faction: Scars (WLF's word for the Seraphites; the game's Polish text says "Blizny") / Wolves ("Wilki")
ENEMY = {"W": ("Blizny", "Blizn", "Bliznami"), "S": ("Wilki", "Wilków", "Wilkami")}
# infected (the game's Polish names: Biegacz, Klikacz, Czyhacz, Człapacz, Purchlak): nom, gen (= acc), ins, plural nom, plural gen (= acc), "two of them"
INF = {
    "runner": ("biegacz", "biegacza", "biegaczem", "biegacze", "biegaczy", "dwóch biegaczy"),
    "clicker": ("klikacz", "klikacza", "klikaczem", "klikacze", "klikaczy", "dwóch klikaczy"),
    "stalker": ("czyhacz", "czyhacza", "czyhaczem", "czyhacze", "czyhaczy", "dwóch czyhaczy"),
    "shambler": ("człapacz", "człapacza", "człapaczem", "człapacze", "człapaczy", "dwóch człapaczy"),
    "bloater": ("purchlak", "purchlaka", "purchlakiem", "purchlaki", "purchlaków", "dwóch purchlaków"),
}
# illness key -> (nom, gen, acc, ins)  /  cure -> (nom, gen, acc, ins)
ILL = {
    "bronchitis": ("zapalenie oskrzeli", "zapalenia oskrzeli", "zapalenie oskrzeli", "zapaleniem oskrzeli"),
    "infected_wound": ("zakażona rana", "zakażonej rany", "zakażoną ranę", "zakażoną raną"),
    "fever": ("gorączka", "gorączki", "gorączkę", "gorączką"),
    "dysentery": ("czerwonka", "czerwonki", "czerwonkę", "czerwonką"),
    "pneumonia": ("zapalenie płuc", "zapalenia płuc", "zapalenie płuc", "zapaleniem płuc"),
    "broken_leg": ("złamana noga", "złamanej nogi", "złamaną nogę", "złamaną nogą"),
    "spores": ("choroba zarodnikowa", "choroby zarodnikowej", "chorobę zarodnikową", "chorobą zarodnikową"),
    "flu": ("grypa", "grypy", "grypę", "grypą"),
    "none": ("choroba", "choroby", "chorobę", "chorobą"),
}
CURE = {
    "bronchitis": ("antybiotyki", "antybiotyków", "antybiotyki", "antybiotykami"),
    "infected_wound": ("antybiotyki i czyste bandaże", "antybiotyków i czystych bandaży", "antybiotyki i czyste bandaże", "antybiotykami i czystymi bandażami"),
    "fever": ("leki przeciwgorączkowe", "leków przeciwgorączkowych", "leki przeciwgorączkowe", "lekami przeciwgorączkowymi"),
    "dysentery": ("antybiotyki i czysta woda", "antybiotyków i czystej wody", "antybiotyki i czystą wodę", "antybiotykami i czystą wodą"),
    "pneumonia": ("mocne antybiotyki", "mocnych antybiotyków", "mocne antybiotyki", "mocnymi antybiotykami"),
    "broken_leg": ("porządna szyna i środki przeciwbólowe", "porządnej szyny i środków przeciwbólowych", "porządną szynę i środki przeciwbólowe",
                   "porządną szyną i środkami przeciwbólowymi"),
    "spores": ("cud", "cudu", "cud", "cudem"),
    "flu": ("leki przeciwgorączkowe", "leków przeciwgorączkowych", "leki przeciwgorączkowe", "lekami przeciwgorączkowymi"),
    "none": ("lekarstwa", "lekarstw", "lekarstwa", "lekarstwami"),
}
AGO = {"yesterday": "wczoraj", "the other night": "dwie noce temu", "a few days back": "kilka dni temu"}

_CARD_NOM = ["", "jedna", "dwie", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć"]
_CARD_GEN = ["", "jednej", "dwóch", "trzech", "czterech", "pięciu", "sześciu", "siedmiu", "ośmiu", "dziewięciu", "dziesięciu"]


def people_phrase(n, case, new=False):
    """A count of people in Polish: case nom / acc / gen. 0 = nobody. new=True: "nowe osoby" (the newcomers of a clan event)."""
    n = int(n)
    if n <= 0:
        return {"nom": "nikt nowy" if new else "nikt", "acc": "nikogo nowego" if new else "nikogo", "gen": "nikogo nowego" if new else "nikogo"}[case]
    one = n == 1
    few = 2 <= n <= 4
    if case == "gen":
        num = _CARD_GEN[n] if n <= 10 else str(n)
        noun = ("nowej osoby" if new else "osoby") if one else ("nowych osób" if new else "osób")
        return "%s %s" % (num, noun)
    num = _CARD_NOM[n] if n <= 10 else str(n)
    if one:
        noun = ("nową osobę" if case == "acc" else "nowa osoba") if new else ("osobę" if case == "acc" else "osoba")
        num = "jedną" if case == "acc" else "jedna"
    elif few:
        noun = "nowe osoby" if new else "osoby"
    else:
        noun = "nowych osób" if new else "osób"
    return "%s %s" % (num, noun)


def expand(sym):
    """Symbolic variables of a message -> every Polish form the templates use (see the module doc)."""
    fk = sym.get("f", "W")
    v = {"day": sym.get("day", 0), "week": sym.get("week", 1)}
    if "place" in sym:
        nom, gen, at, to, frm, ins = PLACES.get(sym["place"], (sym["place"],) * 6)
        v.update(place=nom, place_gen=gen, place_at=at, place_to=to, place_from=frm, place_ins=ins)
    en = ENEMY[fk]
    v.update(enemy=en[0], enemies=en[0], enemy_gen=en[1], enemy_ins=en[2])
    if "inf" in sym:
        a = INF.get(sym["inf"], (sym["inf"],) * 6)
        v.update(inf=a[0], inf_gen=a[1], inf_ins=a[2], infs=a[3], infs_gen=a[4], inf_two=a[5])
    if "ago" in sym:
        v["ago"] = AGO.get(sym["ago"], sym["ago"])
    if "ill" in sym:
        k = sym["ill"] if sym["ill"] in ILL else "none"
        v.update(ill=ILL[k][0], ill_gen=ILL[k][1], ill_acc=ILL[k][2], ill_ins=ILL[k][3],
                 cure=CURE[k][0], cure_gen=CURE[k][1], cure_acc=CURE[k][2], cure_ins=CURE[k][3])
    for key, new in (("n", False), ("lost", False), ("gain", True)):
        if key in sym:
            n = int(sym[key])
            v[key] = people_phrase(n, "nom", new)
            v[key + "_acc"] = people_phrase(n, "acc", new)
            v[key + "_gen"] = people_phrase(n, "gen", new)
    return v


# ------------------------------------------------------------------ rendering
KEY_RE = re.compile(r"\{(\w+)\}")
SW_RE = re.compile(r"\{([A-D]+)\?([^|{}]*)\|([^|{}]*)\}")
PL_SPECIAL = {"Someone": "Ktoś"}      # clan_story writes this placeholder name for a clan that died with nobody named


def _name(p):
    return PL_SPECIAL.get(p["n"], p["n"])


def render(tpl, people, vars_):
    """Fill a Polish template. people = {"A": {"n": name, "g": "m|f|n"}}, vars_ = expand()'s dict."""
    def sw(m):
        letters = m.group(1)
        fem = all(people[ch]["g"] == "f" for ch in letters)
        return m.group(3) if fem else m.group(2)
    tpl2 = SW_RE.sub(sw, tpl)

    def sub(m):
        key = m.group(1)
        if key in people:
            return _name(people[key])
        val = str(vars_[key])
        before = tpl2[:m.start()].rstrip()
        if val[:1].islower() and (not before or before[-1] in ".!?\"'„”"):
            val = val[:1].upper() + val[1:]
        return val
    return KEY_RE.sub(sub, tpl2)


def tpl_letters(tpl):
    """Person letters a template (English or Polish) uses."""
    out = set(re.findall(r"\{([A-D])(?:_\w+)?\}", tpl))
    for m in SW_RE.finditer(tpl):
        out |= set(m.group(1))
    return out


def tpl_vars(tpl):
    """Variable families a template uses (place_at -> place, ill_gen -> ill, inf_two -> inf, lost_acc -> lost ...)."""
    out = set()
    for k in KEY_RE.findall(tpl):
        if re.fullmatch(r"[A-D](_\w+)?", k):
            continue
        k = re.sub(r"_(gen|acc|ins|at|to|from|two|a)$", "", k)
        k = {"infs": "inf", "enemies": "enemy"}.get(k, k)
        out.add(k)
    return out


# ------------------------------------------------------------------ the Polish 2013 ticker (parallel to clan_story_data.TICKER_*)
TICKER_HUNGRY = [
    "{A} umiera z głodu.", "{A} zaczyna słabnąć.", "{A} desperacko szuka jedzenia.", "{A} ogryza szczurze kości.",
    "{A} ma straszne bóle z głodu.", "{A} ledwo chodzi.", "{A} jest bardzo niedożywion{A?y|a}.", "{A} schudł{A?|a} z niedożywienia siedem kilo.",
    "{A} zaczyna rozważać kanibalizm.", "{A} rozważa zjedzenie kota.", "{A} próbuje nie myśleć o jedzeniu.",
    "{A} oskarża innych o chomikowanie jedzenia.", "{A} jest zbyt słab{A?y|a}, żeby pracować."]
TICKER_SICK = [
    "{A} jest chor{A?y|a}.", "{A} {A?zaczął|zaczęła} się modlić.", "{A} ma dreszcze.", "{A} nie wstał{A?|a} dziś rano z łóżka.",
    "{A} ostatnio dużo kaszle.", "{A}: gangrena postępuje.", "{A} potrzebuje antybiotyków, natychmiast.",
    "{A} wygląda, jakby już odchodzi{A?ł|ła}.", "{A}: wszyscy zaczynają się martwić.", "{A}: nikt nie jest pewien, jak długo jeszcze da radę.",
    "{A}: sytuacja wygląda kiepsko.", "{A} zachorował{A?|a} na botulizm od starej puszki.", "{A} ma ciężkie zakażenie.",
    "{A} ma wysoką gorączkę.", "{A} nie może przestać kasłać.", "{A} nie spał{A?|a} od kilku dni.", "{A} załamał{A?|a} się psychicznie.",
    "{A} ma silną reakcję alergiczną.", "{A} odkrztusza krew.", "{A} ma objawy zapalenia płuc.", "{A} ma poważny wstrząs mózgu.",
    "{A} ma silne halucynacje.", "{A} {A?mógł|mogła} się zarazić.", "{A} ma pierwsze objawy szkorbutu.",
    "{A} drży z gorączki.", "{A} może wymagać amputacji.", "{A} ma ciężką grypę.", "{A} złapał{A?|a} czerwonkę."]
TICKER_HEALTHY = (["{A} jest zdrow{A?y|a}."] * 13) + [
    "{A} złapał{A?|a} królika.", "{A} uczy się grać na gitarze.", "{A} uczy się szyć.", "{A} buduje nowy punkt obserwacyjny dla obozu.",
    "{A} ulepsza system filtracji wody.", "{A} kopie nową latrynę.", "{A} złowił{A?|a} rybę.", "{A} piecze szczura na ruszcie.",
    "{A} oprawia jelenia.", "{A} naprawia północne ogrodzenie.", "{A} naprawia zachodnie ogrodzenie.", "{A} naprawia wschodnie ogrodzenie.",
    "{A} naprawia południowe ogrodzenie.", "{A} kopie tunel ewakuacyjny.", "{A} uczy się pierwszej pomocy.", "{A} naprawia zbiornik na wodę.",
    "{A} smaży rybę.", "{A} oprawia szopa.", "{A} wzmacnia główną bramę.", "{A} wzmacnia tylną bramę.",
    "{A} pierze ubrania.", "{A} łata ubrania.", "{A} sprawdza zapas amunicji.", "{A} bacznie obserwuje główną drogę.",
    "{A} stoi na zmianie w punkcie obserwacyjnym.", "{A} czyści ryby.", "{A} wiąże przynęty na ryby.", "{A} złapał{A?|a} szopa.",
    "{A} buduje pułapki na szczury.", "{A} uczy się łowić na muchę.", "{A} pracuje w ogrodzie.", "{A} sadzi jarmuż w ogrodzie.",
    "{A} pieli chwasty w ogrodzie.", "{A} naprawia agregat.", "{A} piecze szopa na rożnie.", "{A} tankuje agregat.",
    "{A} naprawia destylator etanolu.", "{A} opróżnia destylator etanolu.", "{A} ma rumianą cerę.", "{A} rozpoznaje okolicę.",
    "{A} ćwiczy.", "{A} ostrzy maczetę.", "{A} zakłada alarmy obwodowe.", "{A} sprząta latrynę.",
    "{A} zbiera orzechy i jagody.", "{A} robi inwentaryzację.", "{A} rozpala ogień na kolację.", "{A} pędzi bimber.",
    "{A} uczy się malować.", "{A} robi bomby.", "{A} zjadł{A?|a} dziś rano do syta.", "{A} struga w drewnie.", "{A} wybiera się na zbieranie jedzenia.",
    "{A} znalazł{A?|a} kilka starych książek.", "{A} śpi.", "{A}: sprawy zaczynają się układać.", "{A} pogrążył{A?|a} się w zadumie.",
    "{A} czyta stare książki medyczne.", "{A} rysuje mapę okolicy.", "{A} ostrzy strzały.", "{A} buduje kurnik.", "{A} naprawia sieci rybackie.",
    "{A} opowiada historie przy ogniu.", "{A} kisi warzywa.", "{A} nosi wodę.", "{A} wędzi mięso.", "{A} zastawia sidła na króliki.",
    "{A} zbiera drewno na ogień.", "{A} {A?poszedł|poszła} na polowanie.", "{A} {A?poszedł|poszła} na ryby.", "{A} znalazł{A?|a} piłkę nożną.", "{A} zmienia cięciwę w łuku.",
    "{A} uczy się botaniki.", "{A} zbiera jagody.", "{A} znalazł{A?|a} starą książkę kucharską.", "{A} uczy się robić suszone mięso."]
TICKER_DEAD = ["{A} nie żyje."]
TICKER_RARE_SICK = "{A} zjadł{A?|a} gówno i zachorował{A?|a} na HIV."
# the Polish words of the lines a Seraphite island does not have (the parallel of clan_story_data.TICKER_NOT_SERA, which keys on the English words)
TICKER_NOT_SERA = ("agregat", "destylator", "filtracji", "bimber", "amunicji", "bomby", "maczet", "alarmy obwodowe", "piłkę nożną")


# ------------------------------------------------------------------ roster words for the CAMP view (lang=pl of /clanfeed.json)
# role key -> ((WLF masculine, feminine), (Seraphite masculine, feminine))
ROLES = {
    "scavenger": (("zbieracz", "zbieraczka"), ("zbieracz", "zbieraczka")), "medic": (("medyk", "medyczka"), ("uzdrowiciel", "uzdrowicielka")),
    "cook": (("kucharz", "kucharka"), ("kucharz", "kucharka")), "guard": (("wartownik", "wartowniczka"), ("strażnik", "strażniczka")),
    "mechanic": (("mechanik", "mechaniczka"), ("rzemieślnik", "rzemieślniczka")), "scout": (("zwiadowca", "zwiadowczyni"), ("łucznik", "łuczniczka")),
    "gardener": (("ogrodnik", "ogrodniczka"), ("ogrodnik", "ogrodniczka")), "kid": (("dzieciak", "dzieciak"), ("dziecko", "dziecko")),
    "elder": (("stary wyjadacz", "stara wyjadaczka"), ("starszy", "starsza")),
    "radio": (("radiooperator", "radiooperatorka"), ("tkacz", "tkaczka"))}
STATE = {"healthy": ("zdrowy", "zdrowa"), "hungry": ("głodny", "głodna"), "sick": ("chory", "chora")}
MOOD = {"ill": ("chory", "chora"), "hungry": ("głodny", "głodna"), "grieving": ("pogrążony w żałobie", "pogrążona w żałobie"), "cheerful": ("pogodny", "pogodna"),
        "steady": ("opanowany", "opanowana"), "tired": ("zmęczony", "zmęczona"), "hollow": ("wypalony", "wypalona")}
MORALE = {"hopeful": "pełni nadziei", "steady": "opanowani", "strained": "napięci", "grim": "ponuro"}


def people_labels(fk, g, role, state, mood, ill):
    i = 1 if g == "f" else 0
    st = {"h": "healthy", "u": "hungry", "s": "sick"}[state]
    return {"roleText": ROLES[role][0 if fk == "W" else 1][i], "stateText": STATE[st][i], "moodText": MOOD[mood][i],
            "illnessText": ILL[ill][0] if ill in ILL else ""}


# ------------------------------------------------------------------ the registry: lid -> (scope, English template, Polish template)
def _pairs(pool, en, pl):
    if len(en) != len(pl):
        raise ValueError("Polish pool %s has %d templates, English has %d" % (pool, len(pl), len(en)))
    return [(pool, e, p) for e, p in zip(en, pl)]


def _build():
    reg = {}
    rows = []
    for kind, lines in list(LG.LINES.items()) + list(LD.LINES.items()):
        pl = (PG.LINES.get(kind) if kind in PG.LINES else PD.LINES.get(kind)) or []
        if len(pl) != len(lines):
            raise ValueError("Polish pool %s has %d lines, English has %d" % (kind, len(pl), len(lines)))
        for (scope, t), p in zip(lines, pl):
            rows.append((kind, scope, t, p))
    for il, lines in LD.ONSET.items():
        pl = PD.ONSET[il]
        if len(pl) != len(lines):
            raise ValueError("Polish onset pool %s has %d lines, English has %d" % (il, len(pl), len(lines)))
        for (scope, t), p in zip(lines, pl):
            rows.append(("onset:" + il, scope, t, p))
    for pool, en, pl in (("t:u", D.TICKER_HUNGRY, TICKER_HUNGRY), ("t:s", D.TICKER_SICK, TICKER_SICK), ("t:h", D.TICKER_HEALTHY, TICKER_HEALTHY),
                         ("t:d", D.TICKER_DEAD, TICKER_DEAD), ("t:r", [D.TICKER_RARE_SICK], [TICKER_RARE_SICK])):
        if len(en) != len(pl):
            raise ValueError("Polish ticker %s has %d lines, English has %d" % (pool, len(pl), len(en)))
        for e, p in zip(en, pl):
            rows.append((pool, "*", e, p))
    rows += [("t:g", sc, e, pl) for sc, e, pl in RG.ROWS]       # the rich good-state ticker (clan_story_good_rich.py: both languages side by side)
    rows += list(SPR.ROWS)                                 # the spores: no cure, no recovery (clan_story_spores.py: both languages side by side)
    rows += list(SO.ROWS)                                  # the one- and two-survivor voices (clan_story_solo.py: both languages side by side)
    for pool, scope, t, p in rows:
        reg[lid(pool, t)] = (scope, t, p)
    return reg, rows


def lid(pool, en_tpl):
    return "%s/%s" % (pool, line_crc(en_tpl))


REG, ROWS = _build()
