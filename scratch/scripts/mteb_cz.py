"""Throwaway: pull Czech subset scores from embeddings-benchmark/results for given models. Usage: mteb_cz.py OUTDIR MODEL..."""
import sys, json, os, urllib.request, time
out, models = sys.argv[1], sys.argv[2:]
TASKS = ["BelebeleRetrieval", "WikipediaRetrievalMultilingual", "WebFAQRetrieval", "MIRACLRetrieval", "MultiLongDocRetrieval", "CzechProductReviewSentimentClassification", "SIB200ClusteringS2S"]
API = "https://api.github.com/repos/embeddings-benchmark/results/contents/results/"
RAW = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/results/"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "rozprava-research"}), timeout=60) as r:
        return r.read()
for m in models:
    revs = [x["name"] for x in json.loads(get(API + m))]
    for rev in revs:
        files = {x["name"] for x in json.loads(get(f"{API}{m}/{rev}"))}
        for t in TASKS:
            if t + ".json" not in files: continue
            d = json.loads(get(f"{RAW}{m}/{rev}/{t}.json"))
            for split, subs in d.get("scores", {}).items():
                for s in subs:
                    langs = " ".join(s.get("languages", [])) + " " + s.get("hf_subset", "")
                    if "ces" in langs or s.get("hf_subset", "") in ("cs", "ces"):
                        print(f"{m:45} {rev[:8]:8} {t:42} {split:6} {s.get('hf_subset'):28} main={s.get('main_score'):.4f}")
        time.sleep(0.3)
