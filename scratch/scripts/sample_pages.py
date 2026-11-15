"""Throwaway: print N random (term_dir, schuze, turn) URLs per term from steno.unl. Usage: sample_pages.py OPENDATA_DIR N"""
import sys, random, collections, os
random.seed(7)
dirs = {"165": "1993ps", "166": "1996ps", "167": "1998ps", "168": "2002ps", "169": "2006ps", "170": "2010ps", "171": "2013ps", "172": "2017ps", "173": "2021ps", "174": "2025ps"}
by = collections.defaultdict(list)
for l in open(os.path.join(sys.argv[1], "steno/steno.unl"), encoding="cp1250"):
    r = l.split("|")
    if r[1] in dirs: by[r[1]].append((int(r[2]), int(r[3])))
for org, lst in sorted(by.items()):
    for s, t in random.sample(lst, int(sys.argv[2])):
        print(f"{dirs[org]} https://www.psp.cz/eknih/{dirs[org]}/stenprot/{s:03d}schuz/s{s:03d}{t:03d}.htm")
