"""Throwaway: print an HTML file as text with link targets. Usage: h2t.py FILE [encoding]"""
import re, html, sys
enc = sys.argv[2] if len(sys.argv) > 2 else "windows-1250"
s = open(sys.argv[1], encoding=enc, errors="replace").read()
s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", s)
s = re.sub(r'(?i)<a [^>]*href="([^"]*)"[^>]*>', r" [\1] ", s)
s = re.sub(r"(?i)<(br|p|tr|li|h\d|div)[^>]*>", "\n", s)
t = html.unescape(re.sub(r"<[^>]+>", " ", s))
t = re.sub(r"[ \t\r\xa0]+", " ", t)
print("\n".join(l.strip() for l in t.split("\n") if l.strip()))
