"""Throwaway: list rec rows (speaker attributions) for given term org id, sitting and turns. Usage: rec_join.py OPENDATA_DIR ID_ORG SCHUZE TURN..."""
import sys, os
D, org, schuze, turns = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4:])
def rows(p):
    with open(os.path.join(D, p), encoding="windows-1250", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n").split("|")
osoby = {r[0]: r for r in rows("poslanci/osoby.unl")}
st = {r[0]: r for r in rows("steno/steno.unl") if r[1] == org and r[2] == schuze and r[3] in turns}
for r in rows("steno/rec.unl"):
    if r[0] in st:
        o = osoby.get(r[1], ["?"] * 4)
        print(f"turn {st[r[0]][3]} {st[r[0]][4]} od_t={st[r[0]][6]} aname=r{r[2]} id_osoba={r[1]} {o[3]} {o[2]} druh={r[4]} id_bod={r[3]}")
