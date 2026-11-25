"""Throwaway: build the design-preview sample data from real psp.cz pages and open data.
Every quote is checked to be an exact substring of the parsed transcript.

Usage: uv run python -I build_preview.py OPENDATA_DIR STENO_HTML_DIR OUT_JSON [--list]

Needs, under OPENDATA_DIR: poslanci/, steno/, schuze/, tisky/, hl-2025ps/ (unzipped dumps).
Under STENO_HTML_DIR: live-2025-034b/ (s034627–651, 6 Nov 2026), live-2025-036/ (s036001–026,
13 Nov 2026) and mp-7030/ (pages where Jan Papajanovský spoke, from crawl_mp.py).
"""

import collections
import datetime
import json
import os
import random
import re
import statistics
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from steno_paras import read_page, speeches  # noqa: E402

from rozprava.titles import short_title  # noqa: E402

D, H, OUT = sys.argv[1:4]
TERM, TERM_ORG, TERM_YEAR = 10, "174", 2025


def rows(p):
    with open(os.path.join(D, p), encoding="windows-1250", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n").split("|")


def iso_date(cz):  # "06.11.2026" -> "2026-11-06"
    d, m, y = cz.split(".")
    return f"{y}-{m}-{d}"


org = {r[0]: r for r in rows("poslanci/organy.unl")}
osoby = {r[0]: r for r in rows("poslanci/osoby.unl")}
steno = {r[0]: r for r in rows("steno/steno.unl")}
st_term = {(int(r[2]), int(r[3])): r for r in steno.values() if r[1] == TERM_ORG}
rec = list(rows("steno/rec.unl"))
schuze_org = {r[0]: r for r in rows("schuze/schuze.unl")}
bod = {}
for r in rows("schuze/bod_schuze.unl"):
    bod.setdefault(r[0], r)
tisk_ct = {r[0]: int(r[3]) for r in rows("tisky/tisky.unl") if r[3].isdigit()}
tisk_short = {r[0]: r[10] for r in rows("tisky/tisky.unl")}
CLUBS = {"ANO2011": "ANO", "TOP09": "TOP 09", "MS": "Motoristé", "Nezařaz": "Nezařazení"}
club, club_name = {}, {}
for r in rows("poslanci/zarazeni.unl"):
    o = org.get(r[1])
    if o and o[2] == "1" and o[1] == TERM_ORG and r[2] == "0" and not r[4]:
        abbr = CLUBS.get(o[3], o[3])
        club[r[0]] = abbr
        club_name[abbr] = o[4]
poslanec = {r[0]: r for r in rows("poslanci/poslanec.unl") if r[4] == TERM_ORG}  # by id_poslanec
mps_term = {r[1]: r for r in poslanec.values()}  # by id_osoba


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def person(pid, label=None):
    o = osoby[pid]
    name = f"{o[3]} {o[2]}"
    role = None
    if label and not re.match(r"Poslan(ec|kyně) ", label):
        role = label[: label.rfind(o[3])].strip() if o[3] in label else None
        if role:
            role = role[0].lower() + role[1:]
    return {"id": int(pid), "name": name, "slug": f"{pid}-{slug(name)}", "party": club.get(pid), "role": role}


def pid_by_name(label):
    """Resolve a page label to a person by name: current MPs first, then anyone unique."""
    hits = [p for p in mps_term if osoby[p][2] in label and osoby[p][3] in label]
    if len(hits) == 1:
        return hits[0]
    hits = [p for p, o in osoby.items() if o[2] and o[3] and f"{o[3]} {o[2]}" in label]
    return hits[0] if len(hits) == 1 else None


def find_pid(label, turn_key, r):
    """Person id from rec when the surname agrees with the page label, else by name."""
    s = st_term.get(turn_key)
    for x in rec:
        if s and x[0] == s[0] and x[2] == r and osoby[x[1]][2] in label:
            return x[1]
    pid = pid_by_name(label)
    if pid is None:
        raise SystemExit(f"no person for {label}")
    return pid


def is_chair(label):
    return bool(re.match(r"(Místop|P)ředsed\w+ PSP", label))


def words(paras):
    return sum(len(t.split()) for _, t in paras)


def catalog(sitting, start_page, r):
    return {"term": TERM, "sitting": sitting, "page": start_page, "order": int(r)}


def agenda_of(bod_id, reading=None):
    b = bod.get(bod_id)
    if not b:
        return None
    tisk = tisk_ct.get(b[2])
    return {
        "id": bod_id, "number": int(b[4]) if b[4] else None, "title": b[5].strip(),
        "short": short_title(b[5], tisk, tisk_short.get(b[2]), term=10), "tisk": tisk, "reading": reading,
    }


# ---------------------------------------------------------------- sitting days, activity
sitting_days = sorted({r[4][:10] for r in st_term.values()})
day_sitting = {}
for (s, _), r in st_term.items():
    day_sitting.setdefault(r[4][:10], set()).add(s)

speech_count = collections.Counter()  # (id_osoba, date) -> speeches (rec druh 3/5)
for x in rec:
    s = steno.get(x[0])
    if s and s[1] == TERM_ORG and x[4] in ("3", "5"):
        speech_count[(x[1], s[4][:10])] += 1

# 13 Nov 2026 has no rec rows yet: attribute speakers from the page labels.
LAST_DAY, LAST_SITTING, LAST_DIR = "2026-11-13", 36, "live-2025-036"
last_speeches = speeches(os.path.join(H, LAST_DIR), LAST_SITTING, range(1, 27))
for sp in last_speeches:
    sp["pid"] = pid_by_name(sp["label"])
    if sp["pid"] and not is_chair(sp["label"]):
        speech_count[(sp["pid"], LAST_DAY)] += 1
assert sitting_days[-1] == LAST_DAY

counts = sorted(v for v in speech_count.values())
Q = [counts[int(p * (len(counts) - 1))] for p in (0.25, 0.5, 0.75)]


def level(n):
    """Activity level 1–4 from global quartiles of speeches per MP per sitting day.
    The spec asks for words; until the ingest counts every speech's words, speech
    counts stand in (same quartile method, same scale for every MP)."""
    if n <= 0:
        return 0
    return 1 if n <= Q[0] else 2 if n <= Q[1] else 3 if n <= Q[2] else 4


# Roll-call votes: A yes, B no, K abstained or present without voting, @ not logged in.
votes = {r[0]: iso_date(r[5]) for r in rows("hl-2025ps/hl2025s.unl")}
vote_days = collections.defaultdict(lambda: collections.Counter())  # (osoba, day) -> codes
vote_totals = collections.defaultdict(collections.Counter)  # osoba -> codes
for id_poslanec, id_hl, code, *_ in rows("hl-2025ps/hl2025h1.unl"):
    p = poslanec.get(id_poslanec)
    if p and id_hl in votes:
        vote_days[(p[1], votes[id_hl])][code] += 1
        vote_totals[p[1]][code] += 1


def attendance(pid):
    c = vote_totals[pid]
    total = sum(c.values())
    cast = c["A"] + c["B"] + c["K"]
    return round(100 * cast / total, 1) if total else None


def day_state(pid, day):
    c = vote_days.get((pid, day))
    n = speech_count[(pid, day)]
    if n:
        return "spoke", level(n)
    if c and sum(c.values()) == c["@"]:
        return "absent", 0
    return "present", 0


# ---------------------------------------------------------------- search sample (6 Nov 2026)
SITTING = 34
sp = speeches(os.path.join(H, "live-2025-034b"), SITTING, range(627, 652))
by = {(s["turn"], s["r"]): s for s in sp}
agenda = agenda_of("60222", reading="2. čtení")


def card(turn, r, start, end, speech=None, sitting=SITTING):
    s = speech or by[(turn, r)]
    for i, (pg, para) in enumerate(s["paras"]):
        a = para.find(start)
        if a < 0:
            continue
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
            "date": st_term[(sitting, pg)][4][:10], "term": TERM, "term_year": TERM_YEAR,
            "sitting": sitting, "turn": s["turn"], "page": pg, "anchor": f"r{s['r']}",
            "catalog": catalog(sitting, s["turn"], s["r"]),
            "status": s["status"],
            "psp_url": f"https://www.psp.cz/eknih/2025ps/stenprot/{sitting:03d}schuz/s{sitting:03d}{pg:03d}.htm"
            + (f"#r{s['r']}" if pg == s["turn"] else ""),
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
    c = card(*spec)
    c["n"] = n
    c["agenda"] = agenda
    results.append(c)

term_months = sorted({d[:7] for d in sitting_days})
month_hits = collections.Counter(c["date"][:7] for c in results)
search = {
    "query": "Co zaznělo k automatické účasti v penzijním spoření?",
    "highlights": ["automatickou účast", "automatické účasti", "automatickému zapojení", "automaticky enrollment",
                   "automatický enrollment", "opt-outem", "opt-outu", "opt-out"],
    "total": len(results),
    "answer": [
        {"text": "Jan Papajanovský a Marian Jurečka představili ve druhém čtení novely o doplňkovém penzijním spoření pozměňovací návrhy na automatické zapojení zaměstnanců do spoření s právem odmítnout (opt-out).", "cites": [1, 2]},
        {"text": "Ester Weimerová argumentaci pro automatickou účast podpořila; podle ní lidé zůstávají u možnosti, která je jim nabídnuta jako první nebo jako automatická.", "cites": [3]},
        {"text": "Karel Haas a Jiří Havránek mluvili o automatickém převodu střadatelů z transformovaných fondů do strategie životního cyklu, rovněž s možností opt-outu.", "cites": [4, 5]},
        {"text": "Ministryně financí Alena Schillerová řekla, že pozměňovací návrh, který zavádí opt-out bez debaty, nepodpoří, protože znamená zásah i do středních a menších firem; debatovat o něm je ochotná, až novela projde.", "cites": [6]},
    ],
    "results": results,
    "months": [{"month": m, "count": month_hits[m]} for m in term_months],
}

# ---------------------------------------------------------------- transcript page 644 + day minimap
pg = read_page(os.path.join(H, "live-2025-034b", "s034644.htm"))
mark = results[0]["text"]
reader_speeches = []
lead = pg["segs"][0]
if lead["r"] is None and lead["paras"]:
    # The page opens mid-speech: the stitched speeches know who began it, and where.
    prev = next(x for x in sp if x["turn"] < 644 and any(p_ == 644 for p_, _ in x["paras"]))
    assert [t for p_, t in prev["paras"] if p_ == 644] == lead["paras"]
    pid = find_pid(prev["label"], (SITTING, prev["turn"]), prev["r"])
    reader_speeches.append({
        "anchor": f"s{prev['turn']}-r{prev['r']}", "speaker": person(pid, prev["label"]), "chair": False,
        "continued_from": prev["turn"], "catalog": catalog(SITTING, prev["turn"], prev["r"]),
        "paras": [{"text": x} for x in lead["paras"]],
    })
for seg in pg["segs"]:
    if seg["r"] is None:
        continue
    pid = find_pid(seg["label"], (SITTING, 644), seg["r"])
    paras = []
    for p in seg["paras"]:
        if mark in p:
            a = p.find(mark)
            paras.append({"before": p[:a], "mark": mark, "after": p[a + len(mark):]})
        else:
            paras.append({"text": p})
    reader_speeches.append({
        "anchor": f"r{seg['r']}", "speaker": person(pid, seg["label"]), "chair": is_chair(seg["label"]),
        "continued_from": None, "catalog": catalog(SITTING, 644, seg["r"]), "paras": paras,
    })
assert any("mark" in p for s in reader_speeches for p in s["paras"])

day_pages = sorted(t for (s, t), r in st_term.items() if s == SITTING and r[4][:10] == "2026-11-06")
assert day_pages == list(range(627, 652)), day_pages
minimap = []
for s in sp:
    pid = find_pid(s["label"], (SITTING, s["turn"]), s["r"])
    pages = sorted({p_ for p_, _ in s["paras"]})
    minimap.append({
        "name": f"{osoby[pid][3]} {osoby[pid][2]}", "party": club.get(pid), "chair": is_chair(s["label"]),
        "words": words(s["paras"]), "page": s["turn"], "anchor": f"r{s['r']}", "on_page": 644 in pages,
    })
transcript = {
    "term": TERM, "term_year": TERM_YEAR, "sitting": SITTING, "page": 644, "date": "2026-11-06",
    "time": pg["time"], "status": pg["status"], "agenda": agenda,
    "psp_url": "https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034644.htm",
    "prev_page": 643, "next_page": 645, "continues": True, "speeches": reader_speeches,
    "day": {"date": "2026-11-06", "first_page": day_pages[0], "last_page": day_pages[-1], "speeches": minimap},
}

# ---------------------------------------------------------------- MP profile: Jan Papajanovský
PID, SUR = "7030", "Papajanovský"
mpdir = os.path.join(H, "mp-7030")
files = collections.defaultdict(list)
for f in os.listdir(mpdir):
    files[int(f[1:4])].append(int(f[4:7]))
mine = []
for sit, turns in sorted(files.items()):
    for s in speeches(mpdir, sit, range(min(turns), max(turns) + 1)):
        if SUR in s["label"]:
            s["sitting"] = sit
            s["words"] = words(s["paras"])
            s["day"] = st_term[(sit, s["turn"])][4][:10]
            mine.append(s)
mine.sort(key=lambda s: (s["day"], s["turn"]))
bod_counts = collections.Counter()
for x in rec:
    if x[1] == PID and x[0] in steno and steno[x[0]][1] == TERM_ORG and x[3] not in ("", "0") and x[3] in bod:
        bod_counts[x[3]] += 1
topics = [{**agenda_of(b), "speeches": n} for b, n in bod_counts.most_common(4)]

if "--list" in sys.argv:
    for s in mine[-14:]:
        print("\n", s["sitting"], s["turn"], s["r"], s["day"], s["words"], s["status"])
        for _, p in s["paras"][:4]:
            print("    ", p[:500])

per_mp_speeches = collections.Counter()
for (pid, _), n in speech_count.items():
    if pid in mps_term:
        per_mp_speeches[pid] += n
median_speeches = statistics.median(per_mp_speeches.get(p, 0) for p in mps_term if p in club)

words_by_day = collections.Counter()
for s in mine:
    words_by_day[s["day"]] += s["words"]
activity = []
for day in sitting_days:
    state, lvl = day_state(PID, day)
    c = vote_days.get((PID, day), collections.Counter())
    activity.append({
        "date": day, "sittings": sorted(day_sitting[day]), "state": state, "level": lvl,
        "speeches": speech_count[(PID, day)], "words": words_by_day[day],
        "votes_cast": c["A"] + c["B"] + c["K"], "votes_total": sum(c.values()),
    })

o = osoby[PID]
mp = person(PID)
mp.update({
    "initials": o[3][0] + o[2][0], "region": org[mps_term[PID][2]][4],
    # pohlavi is M for men; women are Ž, Z (newer rows) or a mis-encoded byte.
    "title": "Poslanec" if o[6] == "M" else "Poslankyně",
    "terms": [{"number": TERM, "from": TERM_YEAR, "to": None}],
    "psp_url": f"https://www.psp.cz/sqw/detail.sqw?id={PID}",
    "stats": {
        "speeches": per_mp_speeches[PID], "median_speeches": median_speeches,
        "days_spoke": sum(1 for a in activity if a["state"] == "spoke"), "sitting_days": len(sitting_days),
        "median_days_spoke": statistics.median(
            sum(1 for d in sitting_days if speech_count[(p, d)]) for p in mps_term if p in club),
        "attendance": attendance(PID), "median_attendance": statistics.median(
            a for a in (attendance(p) for p in mps_term if p in club) if a is not None),
        "words": sum(s["words"] for s in mine), "longest_words": max(s["words"] for s in mine),
    },
    "first_speech": mine[0]["day"], "last_speech": mine[-1]["day"],
    "topics": topics, "activity": activity,
})
MP_CARDS = [
    (34, 644, "2", "Nejde o nucené spoření.", "statisíce korun místo nuly."),
    (34, 243, "5", "Nejnáročnější studium pro státní rozpočet", "třeba medicínské, obory."),
    (34, 28, "2", "Není přece možné, aby ty mimořádné náklady", "ve správný čas na správném místě."),
    (34, 16, "4", "Nová lékařská fakulta je u nás v kraji opravdu potřeba", "v jednotlivých ambulantních praxích."),
]
mp_speeches = []
for sit, turn, r, a, b in MP_CARDS:
    s = next(x for x in mine if x["sitting"] == sit and x["turn"] == turn and x["r"] == r)
    c = card(turn, r, a, b, speech=s, sitting=sit)
    rr = next((x for x in rec if x[0] == st_term[(sit, turn)][0] and x[2] == r and x[1] == PID), None)
    c["agenda"] = agenda if rr and rr[3] == "60222" else (agenda_of(rr[3]) if rr and rr[3] not in ("", "0") else None)
    mp_speeches.append(c)
mp_speeches.sort(key=lambda c: (c["date"], c["page"]), reverse=True)
mp["speeches"] = mp_speeches

# ---------------------------------------------------------------- MP index
last20 = sitting_days[-20:]
mps = []
for pid in mps_term:
    if pid not in club:
        continue
    o = osoby[pid]
    mps.append({
        "id": int(pid), "name": f"{o[3]} {o[2]}", "surname": o[2], "forename": o[3], "initials": o[3][0] + o[2][0],
        "slug": f"{pid}-{slug(o[3] + ' ' + o[2])}", "party": club[pid], "region": org[mps_term[pid][2]][4],
        "speeches": per_mp_speeches[pid], "attendance": attendance(pid),
        "strip": [{"date": d, "state": day_state(pid, d)[0], "level": day_state(pid, d)[1]} for d in last20],
    })

# ---------------------------------------------------------------- sessions (schůze) of the term
day_total = collections.Counter()
for (pid, day), n in speech_count.items():
    day_total[day] += n
day_q = sorted(day_total.values())
DQ = [day_q[int(p * (len(day_q) - 1))] for p in (0.25, 0.5, 0.75)]


def day_level(n):
    return 0 if n <= 0 else 1 if n <= DQ[0] else 2 if n <= DQ[1] else 3 if n <= DQ[2] else 4


sitting_speeches = collections.Counter()
sitting_bods = collections.defaultdict(collections.Counter)
for x in rec:
    s = steno.get(x[0])
    if s and s[1] == TERM_ORG and x[4] in ("3", "5"):
        sitting_speeches[int(s[2])] += 1
        if x[3] not in ("", "0") and x[3] in bod:
            sitting_bods[int(s[2])][x[3]] += 1
sitting_speeches[LAST_SITTING] += sum(1 for s in last_speeches if not is_chair(s["label"]))
sessions = []
for number in sorted({s for s, _ in st_term}, reverse=True):
    days = sorted({r[4][:10] for (s, _), r in st_term.items() if s == number})
    sessions.append({
        "number": number, "from": days[0], "to": days[-1], "days": len(days),
        "speeches": sitting_speeches[number],
        "top": [{**agenda_of(b), "speeches": n} for b, n in sitting_bods[number].most_common(3)],
        "day_levels": [{"date": d, "speeches": day_total[d], "level": day_level(day_total[d])} for d in days],
    })

# ---------------------------------------------------------------- home: the last sitting day
rng = random.Random(datetime.datetime.now().strftime("%Y%m%d%H"))  # re-rolled every hour
candidates = [s for s in last_speeches if not is_chair(s["label"]) and s["pid"] and words(s["paras"]) >= 60]
pick = rng.choice(candidates)


def excerpt(s, limit=330):
    """Opening whole sentences of a speech, up to about `limit` characters."""
    first = s["paras"][0][1]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ„])", first)
    text = ""
    for sentence in sentences:
        if text and len(text) + len(sentence) + 1 > limit:
            break
        text = f"{text} {sentence}".strip()
    assert text and text in first
    return text, len(text) < len(first) or len(s["paras"]) > 1


ftext, ftrail = excerpt(pick)
# No rec rows yet for the last day, so take the agenda item from steno_bod: the latest
# item that started on or before the picked page.
page_bod = {r[0]: r[2] for r in rows("steno/steno_bod.unl")}
fbod = None
for t in range(pick["turn"], 0, -1):
    fbod = page_bod.get(st_term[(LAST_SITTING, t)][0])
    if fbod:
        break
featured = {
    "speaker": person(pick["pid"], pick["label"]), "text": ftext, "lead": False, "trail": ftrail,
    "date": LAST_DAY, "term": TERM, "term_year": TERM_YEAR, "sitting": LAST_SITTING, "turn": pick["turn"],
    "page": pick["turn"], "anchor": f"r{pick['r']}", "catalog": catalog(LAST_SITTING, pick["turn"], pick["r"]),
    "status": pick["status"], "agenda": agenda_of(fbod) if fbod and fbod != "0" else None,
    "psp_url": f"https://www.psp.cz/eknih/2025ps/stenprot/{LAST_SITTING:03d}schuz/s{LAST_SITTING:03d}{pick['turn']:03d}.htm#r{pick['r']}",
    "words": words(pick["paras"]), "pool": len(candidates),
}
home = {
    "last_day": {
        "date": LAST_DAY, "sitting": LAST_SITTING, "pages": 26,
        "speeches": sum(1 for s in last_speeches if not is_chair(s["label"])),
        "words": sum(words(s["paras"]) for s in last_speeches),
        "strip": [{"date": d, "speeches": day_total[d], "level": day_level(day_total[d])} for d in last20],
    },
    "featured": featured,
    "browse": {
        "mps": len(mps), "parties": len({m["party"] for m in mps} - {"Nezařazení"}),
        "tisky": sum(1 for r in rows("tisky/tisky.unl") if r[7] == TERM_ORG), "sittings": len(sessions),
    },
}

# ---------------------------------------------------------------- archive figures (9th + 10th term)
terms = {"173", TERM_ORG}
sp_rows = [x for x in rec if x[0] in steno and steno[x[0]][1] in terms and x[4] in ("3", "5")]
dates = sorted({steno[x[0]][4][:10] for x in rec if x[0] in steno and steno[x[0]][1] in terms})
archive = {"speeches": len(sp_rows), "speakers": len({x[1] for x in sp_rows}), "days": len(dates),
           "sittings": len({(steno[x[0]][1], steno[x[0]][2]) for x in sp_rows}), "from": dates[0], "to": dates[-1]}

party_rows = collections.Counter(m["party"] for m in mps)
dump_time = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(D, "steno/steno.unl")))
data = {
    "meta": {"note": "Sample data for the design preview. Real excerpts from psp.cz transcripts and open data; not a live index.",
             "source": "Poslanecká sněmovna Parlamentu ČR, www.psp.cz", "retrieved": datetime.date.today().isoformat(),
             "updated": dump_time.strftime("%Y-%m-%dT%H:%M"),
             "activity_proxy": "Activity levels use global quartiles of speeches per MP per sitting day "
                               f"(q25/q50/q75 = {Q}); the spec's words-based quartiles need the full ingest."},
    "term": {"number": TERM, "from": TERM_YEAR, "sitting_days": len(sitting_days), "first_day": sitting_days[0],
             "last_day": sitting_days[-1], "quartiles": Q},
    "parties": [{"abbr": p, "name": club_name[p], "members": n} for p, n in party_rows.most_common()],
    "archive": archive, "search": search, "transcript": transcript, "mp": mp, "mps": mps,
    "sessions": sessions, "home": home,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("results", len(results), "| reader speeches", len(reader_speeches), "| minimap", len(minimap),
      "| mp", mp["name"], mp["stats"], "| mps", len(mps), "| sessions", len(sessions))
print("quartiles", Q, DQ, "| featured", featured["speaker"]["name"], featured["words"], "of", len(candidates),
      "| home", home["last_day"]["speeches"], home["last_day"]["words"], home["browse"])
print("topics", [(t["tisk"], t["short"], t["speeches"]) for t in topics])
