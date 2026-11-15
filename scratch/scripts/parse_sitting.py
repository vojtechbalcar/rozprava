"""Throwaway: parse every sNNNTTT.htm page of one sitting into speeches, stitch across pages,
join to open-data rec table. Usage: parse_sitting.py SITTING_DIR OPENDATA_DIR ID_ORG SCHUZE"""
import sys, os, re, html, glob, collections
d, D, org, schuze = sys.argv[1:5]
def rows(p):
    with open(os.path.join(D, p), encoding="windows-1250", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n").split("|")
osoby = {r[0]: r for r in rows("poslanci/osoby.unl")}
steno = {r[3]: r for r in rows("steno/steno.unl") if r[1] == org and r[2] == schuze}
rec = {}
for r in rows("steno/rec.unl"):
    rec[(r[0], r[2])] = r
ANCHOR = re.compile(r'(?is)<b>\s*(?:<b>\s*)?<a\s+(?:href="([^"]*)"\s+)?id="r(\d+)"\s*>(.*?)</a>\s*</b>(?:\s*</b>)?\s*:?')
def clean(s):
    s = re.sub(r"(?is)<[^>]+>", " ", s); s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()
speeches, status = [], collections.Counter()
cur = None
pages = sorted(glob.glob(os.path.join(d, "s*.htm")))
for p in pages:
    turn = str(int(os.path.basename(p)[4:7]))
    raw = open(p, encoding="windows-1250", errors="replace").read()
    m = re.search(r'(?s)<!-- sx -->(.*?)<!-- sy -->', raw)
    body = m.group(1) if m else raw
    st = re.search(r'<p class="status[^"]*">(.*?)</p>', body); status[st.group(1) if st else "(no status line = final)"] += 1
    parts = ANCHOR.split(body)
    pre = clean(re.sub(r'(?s)<div class="document-nav.*?</div>|<p class="status.*?</p>', "", parts[0]))
    if cur and pre: cur["text"] += " " + pre; cur["pages"].add(turn)
    for i in range(1, len(parts), 4):
        href, rid, label, text = parts[i], parts[i+1], clean(parts[i+2]).rstrip(":"), clean(parts[i+3])
        cur = {"turn": turn, "r": rid, "href": href or "", "label": label, "text": text, "pages": {turn}}
        speeches.append(cur)
matched = nonmp_href = 0; bad = []
words = collections.Counter(); druhs = collections.Counter()
for s in speeches:
    stn = steno.get(s["turn"]); r = rec.get((stn[0], s["r"])) if stn else None
    s["osoba"] = r[1] if r else None; s["druh"] = r[4] if r else None
    if r:
        matched += 1
        m = re.search(r"id=(\d+)", s["href"])
        if m and m.group(1) != r[1]: bad.append((s["label"], m.group(1), r[1]))
        if not m: nonmp_href += 1
    druhs[s["druh"]] += 1
    words["all"] += len(s["text"].split())
    if s["druh"] in ("3", "5"): words["speaker"] += len(s["text"].split())
print(f"pages={len(pages)} speech segments={len(speeches)} matched_to_rec={matched} ({matched/len(speeches):.1%})")
print("href-id vs rec id_osoba mismatches:", len(bad), bad[:5])
print("segments without psp person link in HTML but resolved via rec:", nonmp_href)
print("druh counts:", dict(druhs)); print("words:", dict(words), "avg words/segment:", words['all']//len(speeches))
print("multi-page speeches:", sum(1 for s in speeches if len(s['pages']) > 1), "longest (words):", max(len(s['text'].split()) for s in speeches))
print("status lines:", dict(status))
print("unmatched examples:", [(s['turn'], s['r'], s['label']) for s in speeches if not s['osoba']][:8])
nm = [s for s in speeches if s['osoba'] and not re.search(r'detail\.sqw', s['href'])]
print("non-psp-linked speakers:", sorted({(s['label'], s['href'][:60], s['osoba']) for s in nm})[:10])
def norm(x): return re.sub(r"[^a-záčďéěíňóřšťúůýž]", "", x.lower())
mism = [(s['turn'], s['r'], s['label'], " ".join(osoby[s['osoba']][3:1:-1])) for s in speeches if s['osoba'] and norm(osoby[s['osoba']][2]) not in norm(s['label'])]
print("label surname != rec person surname:", len(mism), mism[:6])
if len(sys.argv) > 5:
    import json
    with open(sys.argv[5], "w", encoding="utf-8") as f:
        for s in speeches:
            f.write(json.dumps({k: (sorted(v) if isinstance(v, set) else v) for k, v in s.items()}, ensure_ascii=False) + "\n")
