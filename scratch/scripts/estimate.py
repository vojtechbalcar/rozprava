"""Throwaway: archive size and embedding cost estimates from measured ratios (see feasibility note)."""
turns = {"1993ps": 1149, "1996ps": 3421, "1998ps": 10021, "2002ps": 10139, "2006ps": 7546, "2010ps": 6508, "2013ps": 10461, "2017ps": 11961, "2021ps": 13926, "2025ps": 4548}
wpp = {"1993ps": 3529, "1996ps": 2307, "1998ps": 964, "2002ps": 1092, "2006ps": 1033, "2010ps": 1077, "2013ps": 1213, "2017ps": 1158, "2021ps": 1227, "2025ps": 1138}
tpw = {"bge-m3/XLM-R": 1.72, "o200k": 2.09, "cl100k (text-embedding-3)": 2.83, "Qwen3": 2.83}
words = {t: turns[t] * wpp[t] for t in turns}
scopes = {"current term (2025-)": ["2025ps"], "2021- (two terms)": ["2021ps", "2025ps"], "2013- (ParlaMint era + since)": ["2013ps", "2017ps", "2021ps", "2025ps"], "full 1993-": list(turns)}
prices = {"text-embedding-3-small": (0.02, "cl100k (text-embedding-3)"), "text-embedding-3-large": (0.13, "cl100k (text-embedding-3)"), "voyage-4-lite*": (0.02, "o200k"), "voyage-4*": (0.06, "o200k"), "gemini-embedding-001*": (0.15, "o200k")}
for t in turns: print(f"{t}: {words[t]/1e6:6.2f}M words")
print()
for name, ts in scopes.items():
    w = sum(words[t] for t in ts) * 0.9  # ParlaMint cross-check suggests ~10% overcount
    toks = {k: w * v for k, v in tpw.items()}
    chunks = w / 300 * 1.15
    print(f"{name}: ~{w/1e6:.1f}M words, ~{chunks/1e3:.0f}k chunks (300 words, 15% overlap), vectors 1024-d fp32 ~{chunks*4096/1e9:.2f} GB")
    print("   tokens:", {k: f"{v*1.15/1e6:.0f}M" for k, v in toks.items()})
    print("   one-off embed $:", {p: round(w * 1.15 * tpw[tk] / 1e6 * pr, 2) for p, (pr, tk) in prices.items()})
