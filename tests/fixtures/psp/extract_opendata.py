"""Extract the open-data rows the transcript fixtures need; see README.md beside this file.

Usage: extract_opendata.py DUMPS_DIR OUT_DIR PAGES_DIR (DUMPS_DIR holds the unzipped dumps).
"""

import re
import sys
from pathlib import Path

X, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PAGES = Path(sys.argv[3])


def lines(rel):
    return [line for line in (X / rel).read_bytes().split(b"\n") if line]


def fields(line):
    return line.decode("cp1250", "replace").split("|")


want = (
    {("174", "34", str(p)) for p in range(640, 651)}
    | {("174", "1", str(p)) for p in range(1, 5)}
    | {("173", "50", str(p)) for p in range(70, 74)}
    | {("173", "112", str(p)) for p in range(1, 3)}
)
steno = [row for row in lines("steno/steno.unl") if tuple(fields(row)[1:4]) in want]
ids = {fields(row)[0] for row in steno}
rec = [row for row in lines("steno/rec.unl") if fields(row)[0] in ids]
sbod = [row for row in lines("steno/steno_bod.unl") if fields(row)[0] in ids]
persons = {fields(row)[1] for row in rec}
for page in PAGES.glob("*.htm"):
    persons |= {m.decode() for m in re.findall(rb"detail\.sqw\?id=(\d+)", page.read_bytes())}
osoby_all = lines("poslanci/osoby.unl")
byname = {}
for row in osoby_all:
    f = fields(row)
    byname.setdefault((f[3], f[2]), []).append(f[0])
names = {(fields(row)[3], fields(row)[2]) for row in osoby_all if fields(row)[0] in persons}
names |= {("Pavel", "Blažek"), ("Jan", "Černý")}  # a minister without a link; namesakes
persons |= {i for n in names for i in byname.get(n, [])}
persons.add("6492")  # Ivo Vondrák: left the ANO club for Nezařazení on 21 Feb 2023
osoby = [row for row in osoby_all if fields(row)[0] in persons]
terms = {"173", "174"}
organy_all = lines("poslanci/organy.unl")
clubs = {fields(row)[0] for row in organy_all if fields(row)[1] in terms and fields(row)[2] == "1"}
poslanec = [
    row
    for row in lines("poslanci/poslanec.unl")
    if fields(row)[4] in terms and fields(row)[1] in persons
]
regions = {fields(row)[2] for row in poslanec}
organy = [row for row in organy_all if fields(row)[0] in terms | clubs | regions]
zarazeni = [
    row
    for row in lines("poslanci/zarazeni.unl")
    if fields(row)[0] in persons and fields(row)[1] in terms | clubs and fields(row)[2] == "0"
]
bods = {fields(row)[3] for row in rec} | {fields(row)[2] for row in sbod}
sittings = {("173", "50"), ("173", "112"), ("174", "1"), ("174", "34")}
schuze = [row for row in lines("schuze/schuze.unl") if (fields(row)[1], fields(row)[2]) in sittings]
bod = [row for row in lines("schuze/bod_schuze.unl") if fields(row)[0] in bods]
tisky_ids = {fields(row)[2] for row in bod if fields(row)[2]}
tisky = [row for row in lines("tisky/tisky.unl") if fields(row)[0] in tisky_ids]
for name, rows in [
    ("steno.unl", steno),
    ("rec.unl", rec),
    ("steno_bod.unl", sbod),
    ("osoby.unl", osoby),
    ("organy.unl", organy),
    ("poslanec.unl", poslanec),
    ("zarazeni.unl", zarazeni),
    ("schuze.unl", schuze),
    ("bod_schuze.unl", bod),
    ("tisky.unl", tisky),
]:
    (OUT / name).write_bytes(b"\n".join(rows) + b"\n")
    print(name, len(rows))
