"""Throwaway: parse psp.cz live transcript pages into speeches with paragraphs kept (for the design-preview fixture)."""
import re, html, os

ANCHOR = re.compile(r'(?is)<b>\s*(?:<b>\s*)?<a\s+(?:href="([^"]*)"\s+)?id="r(\d+)"\s*>(.*?)</a>\s*</b>(?:\s*</b>)?\s*:?')

def clean(s):
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def paras(chunk):
    chunk = re.sub(r"(?is)<!-- sttm -->.*?<!-- ettm -->", " ", chunk)
    out = []
    for p in re.split(r"(?i)<p[^>]*>|<br\s*/?>", chunk):
        t = clean(p)
        t = re.sub(r"\s*\*{3}\s*$", "", t)
        if not t or re.fullmatch(r"\(pokračuje [^)]*\)", t):
            continue
        out.append(t)
    return out

def read_page(path):
    raw = open(path, encoding="windows-1250", errors="replace").read()
    m = re.search(r"(?s)<!-- sx -->(.*?)<!-- sy -->", raw)
    body = m.group(1) if m else ""
    st = re.search(r'<p class="status[^"]*">(.*?)</p>', body)
    tm = re.search(r"(?s)<!-- sttm -->\s*\((.*?) hodin\)", body)
    body = re.sub(r'(?s)<p class="status.*?</p>|<div class="document-nav.*?</div>', "", body)
    parts = ANCHOR.split(body)
    segs = [{"r": None, "label": None, "href": None, "paras": paras(parts[0])}]
    for i in range(1, len(parts), 4):
        segs.append({"r": parts[i + 1], "label": clean(parts[i + 2]).rstrip(":"), "href": parts[i] or "", "paras": paras(parts[i + 3])})
    return {"status": clean(st.group(1)) if st else None, "time": tm.group(1) if tm else None, "segs": segs}

def speeches(dirpath, sitting, turns):
    """Stitch consecutive pages; returns list of speeches with paragraphs tagged by page."""
    out, cur = [], None
    for t in turns:
        p = os.path.join(dirpath, f"s{sitting:03d}{t:03d}.htm")
        if not os.path.exists(p):
            cur = None
            continue
        pg = read_page(p)
        for seg in pg["segs"]:
            if seg["r"] is None:
                if cur is not None:
                    cur["paras"] += [(t, x) for x in seg["paras"]]
                continue
            cur = {"turn": t, "r": seg["r"], "label": seg["label"], "href": seg["href"], "status": pg["status"], "time": pg["time"], "paras": [(t, x) for x in seg["paras"]]}
            out.append(cur)
    return out
