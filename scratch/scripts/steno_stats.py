"""Throwaway: per-term coverage stats from psp.cz open data (steno + poslanci). Usage: steno_stats.py OPENDATA_DIR"""
import sys, collections, os
D = sys.argv[1]
def rows(p):
    with open(os.path.join(D, p), encoding="windows-1250", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n").split("|")
org = {r[0]: r for r in rows("poslanci/organy.unl")}
terms = {k: v for k, v in org.items() if v[2] == "11" and v[3].startswith("PSP")}
mp_by_term = collections.defaultdict(set)
for r in rows("poslanci/poslanec.unl"):
    mp_by_term[r[4]].add(r[1])
osoby = {r[0]: r for r in rows("poslanci/osoby.unl")}
steno = {r[0]: r for r in rows("steno/steno.unl")}
per = collections.defaultdict(lambda: {"turns": 0, "sittings": set(), "recs": 0, "speakers": set(), "min": "9", "max": "0", "druh": collections.Counter()})
for s in steno.values():
    p = per[s[1]]; p["turns"] += 1; p["sittings"].add(s[2])
    if s[4]: p["min"] = min(p["min"], s[4]); p["max"] = max(p["max"], s[4])
unknown_steno = 0
nonmp = collections.defaultdict(collections.Counter)
for r in rows("steno/rec.unl"):
    s = steno.get(r[0])
    if not s: unknown_steno += 1; continue
    p = per[s[1]]; p["recs"] += 1; p["speakers"].add(r[1]); p["druh"][r[4] or "null"] += 1
    if r[1] not in mp_by_term[s[1]]:
        nonmp[s[1]][r[1]] += 1
print("term_org zkratka   od          do          sittings turns  recs    speakers nonMP_speakers nonMP_recs  first_steno last_steno")
for k in sorted(per, key=lambda x: int(x)):
    p = per[k]; t = terms.get(k, [k, "", "", "?", "", "", "", ""])
    print(f"{k:8} {t[3]:9} {t[6]:11} {t[7]:11} {len(p['sittings']):8} {p['turns']:6} {p['recs']:7} {len(p['speakers']):8} {len(nonmp[k]):14} {sum(nonmp[k].values()):10}  {p['min']} {p['max']}")
print("rec rows with unknown id_steno:", unknown_steno)
for k in ["172","173","174"]:
    print("\nterm", k, "druh counts:", dict(per[k]["druh"]))
    print("top non-MP speakers:", [(" ".join(osoby.get(i, ['?','','?','?'])[2:4]), n) for i, n in nonmp[k].most_common(12)])
