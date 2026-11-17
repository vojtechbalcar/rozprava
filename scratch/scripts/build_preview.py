"""Throwaway: build the design-preview sample data from real psp.cz pages and open data.
Every quote is checked to be an exact substring of the parsed transcript.
Usage: build_preview.py OPENDATA_DIR STENO_HTML_DIR OUT_JSON"""
import sys, os, re, json, collections, unicodedata, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from steno_paras import speeches, read_page

D, H, OUT = sys.argv[1:4]
rows = lambda p: (l.rstrip("\n").split("|") for l in open(os.path.join(D, p), encoding="windows-1250", errors="replace"))
org = {r[0]: r for r in rows("poslanci/organy.unl")}
osoby = {r[0]: r for r in rows("poslanci/osoby.unl")}
steno = {r[0]: r for r in rows("steno/steno.unl")}
st174 = {(int(r[2]), int(r[3])): r for r in steno.values() if r[1] == "174"}
rec = list(rows("steno/rec.unl"))
CLUBS = {"ANO2011": "ANO", "TOP09": "TOP 09", "MS": "Motoristé", "Nezařaz": "Nezařazení"}
club = {}
for r in rows("poslanci/zarazeni.unl"):
    o = org.get(r[1])
    if o and o[2] == "1" and o[1] == "174" and r[2] == "0" and not r[4]:
        club[r[0]] = CLUBS.get(o[3], o[3])
mps174 = {r[1]: r for r in rows("poslanci/poslanec.unl") if r[4] == "174"}
bod = {}
for r in rows("schuze/bod_schuze.unl"):
    bod.setdefault(r[0], r)

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def person(pid, label=None):
    o = osoby[pid]
    name = f"{o[3]} {o[2]}"
    role = None
    if label and not re.match(r"Poslan(ec|kyně) ", label):
        role = label[: label.rfind(o[3])].strip() if o[3] in label else None
        if role: role = role[0].lower() + role[1:]
    return {"id": int(pid), "name": name, "slug": f"{pid}-{slug(name)}", "party": club.get(pid), "role": role}

def find_pid(label, turn_key, r):
    """Person id from rec when the surname agrees with the page label, else by name among current MPs."""
    s = st174.get(turn_key)
    for x in rec:
        if s and x[0] == s[0] and x[2] == r and osoby[x[1]][2] in label:
            return x[1]
    for pid in mps174:
        if osoby[pid][2] in label and osoby[pid][3] in label:
            return pid
    raise SystemExit(f"no person for {label}")

def iso(turn_key):
    return st174[turn_key][4][:10]

SITTING = 34
sp = speeches(os.path.join(H, "live-2025-034b"), SITTING, range(636, 652))
by = {(s["turn"], s["r"]): s for s in sp}
AGENDA = bod["60222"]
agenda = {"number": 17, "title": AGENDA[5].strip(), "short": "Novela zákona o doplňkovém penzijním spoření", "print": 285, "reading": "druhé čtení"}

def card(turn, r, start, end, speech=None, sitting=SITTING):
    s = speech or by[(turn, r)]
    for i, (pg, para) in enumerate(s["paras"]):
        a = para.find(start)
        if a < 0: continue
        b = para.find(end, a)
        assert b >= 0, (turn, r, end)
        text = para[a : b + len(end)]
        assert text in para
        pid = find_pid(s["label"], (sitting, s["turn"]), s["r"])
        return {
            "speaker": person(pid, s["label"]),
            "text": text,
            "lead": a > 0 or i > 0,
            "trail": b + len(end) < len(para) or i < len(s["paras"]) - 1,
            "date": iso((sitting, pg)), "term": 10, "term_year": 2025, "sitting": sitting, "turn": s["turn"], "page": pg, "anchor": f"r{s['r']}",
            "status": s["status"],
            "psp_url": f"https://www.psp.cz/eknih/2025ps/stenprot/{sitting:03d}schuz/s{sitting:03d}{pg:03d}.htm" + (f"#r{s['r']}" if pg == s["turn"] else ""),
        }
    raise SystemExit(f"start not found {turn} {r} {start}")

RESULTS = [
    (644, "2", "No a třetí návrh", "možnost opt-outu."),
    (636, "3", "A jeho cílem je řešit situaci", "ze své mzdy."),
    (646, "2", "Já bych jenom chtěla podpořit", "jako první nebo jako automatická."),
    (646, "4", "Já v té věci a my všichni", "automatický enrollment byli."),
    (650, "4", "Dále se hlásím k dokumentu 2247", "zvýšení jejich výnosů."),
    (648, "2", "To je tak velký zásah", "možná i na menší a tak dále."),
]
results = []
for n, spec in enumerate(RESULTS, 1):
    c = card(*spec); c["n"] = n; c["agenda"] = agenda; results.append(c)

search = {
    "query": "Co zaznělo k automatické účasti v penzijním spoření?",
    "highlights": ["automatickou účast", "automatické účasti", "automatickému zapojení", "automaticky enrollment", "automatický enrollment", "opt-outem", "opt-outu", "opt-out"],
    "total": len(results),
    "answer": [
        {"text": "Jan Papajanovský a Marian Jurečka představili ve druhém čtení novely o doplňkovém penzijním spoření pozměňovací návrhy na automatické zapojení zaměstnanců do spoření s právem odmítnout (opt-out).", "cites": [1, 2]},
        {"text": "Ester Weimerová argumentaci pro automatickou účast podpořila; podle ní lidé zůstávají u možnosti, která je jim nabídnuta jako první nebo jako automatická.", "cites": [3]},
        {"text": "Karel Haas a Jiří Havránek mluvili o automatickém převodu střadatelů z transformovaných fondů do strategie životního cyklu, rovněž s možností opt-outu.", "cites": [4, 5]},
        {"text": "Ministryně financí Alena Schillerová řekla, že pozměňovací návrh, který zavádí opt-out bez debaty, nepodpoří, protože znamená zásah i do středních a menších firem; debatovat o něm je ochotná, až novela projde.", "cites": [6]},
    ],
    "results": results,
}

# Transcript reader: page 644 of sitting 34, with the first result's passage marked.
pg = read_page(os.path.join(H, "live-2025-034b", "s034644.htm"))
mark = results[0]["text"]
reader_speeches = []
lead = pg["segs"][0]
if lead["r"] is None and lead["paras"]:
    # The page opens mid-speech: credit it to whoever spoke last on the previous page.
    # The speech may have started several pages earlier; the stitched speeches know where.
    prev = next(x for x in sp if x["turn"] < 644 and any(pg_ == 644 for pg_, _ in x["paras"]))
    assert [t for pg_, t in prev["paras"] if pg_ == 644] == lead["paras"]
    pid = find_pid(prev["label"], (SITTING, prev["turn"]), prev["r"])
    reader_speeches.append({"anchor": f"s{prev['turn']}-r{prev['r']}", "speaker": person(pid, prev["label"]), "chair": False,
                            "continued_from": prev["turn"], "paras": [{"text": x} for x in lead["paras"]]})
for seg in pg["segs"]:
    if seg["r"] is None: continue
    pid = find_pid(seg["label"], (SITTING, 644), seg["r"])
    paras = []
    for p in seg["paras"]:
        if mark in p:
            a = p.find(mark)
            paras.append({"before": p[:a], "mark": mark, "after": p[a + len(mark):]})
        else:
            paras.append({"text": p})
    chair = bool(re.match(r"(Místop|P)ředsed\w+ PSP", seg["label"]))
    reader_speeches.append({"anchor": f"r{seg['r']}", "speaker": person(pid, seg["label"]), "chair": chair, "paras": paras})
assert any("mark" in p for s in reader_speeches for p in s["paras"])
transcript = {
    "term": 10, "term_year": 2025, "sitting": SITTING, "page": 644, "date": iso((SITTING, 644)), "time": pg["time"],
    "status": pg["status"], "agenda": agenda,
    "psp_url": "https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034644.htm",
    "prev_page": 643, "next_page": 645, "continues": True, "speeches": reader_speeches,
}

# MP profile: Jan Papajanovský, from the pages where he spoke this term.
PID, SUR = "7030", "Papajanovský"
mpdir = os.path.join(H, "mp-7030")
files = collections.defaultdict(list)
for f in os.listdir(mpdir):
    files[int(f[1:4])].append(int(f[4:7]))
mine = []
for sit, turns in sorted(files.items()):
    for s in speeches(mpdir, sit, range(min(turns), max(turns) + 1)):
        if SUR in s["label"]:
            s["sitting"] = sit; s["words"] = sum(len(x.split()) for _, x in s["paras"]); mine.append(s)
mine.sort(key=lambda s: (iso((s["sitting"], s["turn"])), s["turn"]))
bod_counts = collections.Counter()
for x in rec:
    if x[1] == PID and x[0] in steno and steno[x[0]][1] == "174" and x[3] not in ("", "0") and x[3] in bod:
        bod_counts[x[3]] += 1
def short_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= 110 else t[:107].rsplit(" ", 1)[0] + "…"
topics = [{"title": short_title(bod[b][5]), "speeches": n} for b, n in bod_counts.most_common(4)]
o = osoby[PID]
mp = person(PID)
mp.update({
    # pohlavi is M for men; women are Ž, Z (newer rows) or a mis-encoded byte.
    "initials": o[3][0] + o[2][0], "region": org[mps174[PID][2]][4], "title": "Poslanec" if o[6] == "M" else "Poslankyně", "terms": [{"number": 10, "from": 2025, "to": None}],
    "stats": {"speeches": len(mine), "words": sum(s["words"] for s in mine), "days": len({iso((s["sitting"], s["turn"])) for s in mine}), "longest_words": max(s["words"] for s in mine)},
    "first_speech": iso((mine[0]["sitting"], mine[0]["turn"])), "last_speech": iso((mine[-1]["sitting"], mine[-1]["turn"])),
    "topics": topics, "rec_speeches": sum(1 for x in rec if x[1] == PID and x[0] in steno and steno[x[0]][1] == "174"),
})
if "--list" in sys.argv:
    for s in mine[-14:]:
        print("\n", s["sitting"], s["turn"], s["r"], iso((s["sitting"], s["turn"])), s["words"], s["status"])
        for _, p in s["paras"][:4]: print("    ", p[:500])
MP_CARDS = [
    (34, 644, "2", "Nejde o nucené spoření.", "statisíce korun místo nuly."),
    (34, 243, "5", "Nejnáročnější studium pro státní rozpočet", "třeba medicínské, obory."),
    (34, 28, "2", "Není přece možné, aby ty mimořádné náklady", "ve správný čas na správném místě."),
    (34, 16, "4", "Nová lékařská fakulta je u nás v kraji opravdu potřeba", "v jednotlivých ambulantních praxích."),
]
extra = os.environ.get("MP_CARDS")
if extra: MP_CARDS += [tuple(x) for x in json.loads(extra)]
mp_speeches = []
for sit, turn, r, a, b in MP_CARDS:
    s = next(x for x in mine if x["sitting"] == sit and x["turn"] == turn and x["r"] == r)
    c = card(turn, r, a, b, speech=s, sitting=sit)
    rr = next((x for x in rec if x[0] == st174[(sit, turn)][0] and x[2] == r and x[1] == PID), None)
    b_ = bod.get(rr[3]) if rr and rr[3] not in ("", "0") else None
    if b_ and b_[0] == AGENDA[0]:
        c["agenda"] = agenda  # the same bill as the search sample, with its short name
    else:
        c["agenda"] = {"short": short_title(b_[5]), "number": int(b_[4]) if b_[4] else None} if b_ else None
    mp_speeches.append(c)
mp_speeches.sort(key=lambda c: (c["date"], c["page"]), reverse=True)
mp["speeches"] = mp_speeches

# MP index: current members with a club.
mps = []
for pid in mps174:
    if pid in club:
        o = osoby[pid]
        mps.append({"id": int(pid), "name": f"{o[3]} {o[2]}", "surname": o[2], "forename": o[3], "slug": f"{pid}-{slug(o[3] + ' ' + o[2])}", "party": club[pid]})
import locale
mps.sort(key=lambda m: (slug(m["surname"]), slug(m["forename"])))

# Archive figures for the two terms recommended as the first scope (open data, 9th + 10th term).
terms = {"173", "174"}
sp_rows = [x for x in rec if x[0] in steno and steno[x[0]][1] in terms and x[4] in ("3", "5")]
dates = sorted({steno[x[0]][4][:10] for x in rec if x[0] in steno and steno[x[0]][1] in terms})
archive = {"speeches": len(sp_rows), "speakers": len({x[1] for x in sp_rows}), "days": len(dates), "sittings": len({(steno[x[0]][1], steno[x[0]][2]) for x in sp_rows}), "from": dates[0], "to": dates[-1]}

home_cards = [card(650, "6", "Já se jdu přihlásit k pozměňovacímu návrhu číslo 2201", "dlouhodobého investičního produktu."),
              card(650, "8", "Přihlašuji se ke svému pozměňovacímu návrhu", "rodičovský příspěvek.")]
for c in home_cards: c["agenda"] = agenda

data = {
    "meta": {"note": "Sample data for the design preview. Real excerpts from psp.cz transcripts and open data; not a live index.",
             "source": "Poslanecká sněmovna Parlamentu ČR, www.psp.cz", "retrieved": datetime.date.today().isoformat()},
    "parties": [c for c, _ in collections.Counter(m["party"] for m in mps).most_common()],
    "archive": archive, "search": search, "transcript": transcript, "mp": mp, "mps": mps, "home_cards": home_cards,
}
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("results", len(results), "| reader speeches", len(reader_speeches), "| mp", mp["name"], mp["party"], mp["region"], mp["stats"], "rec says", mp["rec_speeches"], "| mps", len(mps), "| archive", archive)
print("topics", topics)
