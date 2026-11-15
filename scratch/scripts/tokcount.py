"""Throwaway: words/chars/tokens per word for parsed Czech speeches. Usage: tokcount.py TOKDIR JSONL..."""
import sys, json, tiktoken
from tokenizers import Tokenizer
tokdir, files = sys.argv[1], sys.argv[2:]
texts = [json.loads(l)["text"] for f in files for l in open(f, encoding="utf-8")]
words = sum(len(t.split()) for t in texts); chars = sum(len(t) for t in texts)
print(f"speeches={len(texts)} words={words} chars={chars} chars/word={chars/words:.2f}")
for name in ("o200k_base", "cl100k_base"):
    enc = tiktoken.get_encoding(name); n = sum(len(enc.encode(t)) for t in texts)
    print(f"{name:12} tokens={n} tokens/word={n/words:.2f}")
for name in ("bge-m3", "qwen3"):
    tk = Tokenizer.from_file(f"{tokdir}/{name}/tokenizer.json"); n = sum(len(tk.encode(t, add_special_tokens=False).ids) for t in texts)
    print(f"{name:12} tokens={n} tokens/word={n/words:.2f}")
