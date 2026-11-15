"""Throwaway: fetch the current-term transcript pages where one person spoke (plus continuation pages). Usage: crawl_mp.py OPENDATA_DIR ID_OSOBA SURNAME OUTDIR"""
import sys, os, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from steno_paras import read_page
D, pid, surname, out = sys.argv[1:5]
rows = lambda p: (l.rstrip("\n").split("|") for l in open(os.path.join(D, p), encoding="windows-1250", errors="replace"))
st = {r[0]: r for r in rows("steno/steno.unl") if r[1] == "174"}
pages = sorted({(int(st[r[0]][2]), int(st[r[0]][3])) for r in rows("steno/rec.unl") if r[0] in st and r[1] == pid})
def fetch(s, t):
    path = os.path.join(out, f"s{s:03d}{t:03d}.htm")
    if os.path.exists(path): return path
    url = f"https://www.psp.cz/eknih/2025ps/stenprot/{s:03d}schuz/s{s:03d}{t:03d}.htm"
    req = urllib.request.Request(url, headers={"User-Agent": "rozprava-feasibility-research (contact: sybalak1@gmail.com)"})
    try:
        data = urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        print("  ", e.code, url); return None
    open(path, "wb").write(data); time.sleep(1.0); return path
n = 0
for s, t in pages:
    p = fetch(s, t); n += 1
    while p:
        labeled = [x for x in read_page(p)["segs"] if x["r"]]
        if labeled and surname not in labeled[-1]["label"]:
            break  # someone else speaks last on this page, so the speech ended here
        t += 1; p = fetch(s, t)  # a page with no anchors is a pure continuation: keep going
print("rec pages:", len(pages), "files:", len(os.listdir(out)))
