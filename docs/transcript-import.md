---
type: problem
updated: 2026-11-18
status: current
---

# Transcript import: what the pages really look like

Related: [[feasibility-research]], [[functional-app-design]], [[functional-app-plan]], [[dev-environment]]

Findings from building `rozprava.ingest` on 18 November 2026, checked on pages
captured in `tests/fixtures/psp/`. They extend the parse test in
[[feasibility-research]].

## Page structure

- The transcript sits between `<!-- sx -->` and `<!-- sy -->`. Markup is regular
  and machine-made, but `<p>` tags are left open and nested, so a tree parser
  (BeautifulSoup) mis-nests them. **Decision:** targeted regular expressions,
  as in the research scripts; BeautifulSoup stays a dependency but is unused.
- A page that opens mid-speech says so: `<br>(pokračuje Olga Richterová)<br>`.
  Assembly joins the opening text to the previous page's last speech only when
  that page is loaded and the marker names the same speaker; otherwise the text
  becomes an incomplete fragment (anchor 0) attributed by name.
- **Agenda headings sit in the middle of the chair's speech.** A centred bold
  paragraph (`18. Vládní návrh zákona … /sněmovní tisk 352/ - prvé čtení`) comes
  after "Jako další bod … je bod číslo", and the chair carries on below it
  without a new label. Headings are stored as page segments but left out of
  speech text, and text after a heading continues the same speech.
- **Some speech labels have no `id="rN"` anchor** and no `<b>`, e.g. a
  minister's label linking to vlada.cz (2021ps s050071/s050072). psp.cz's
  speech index (`rec`) still counts them, so every later anchor on that page is
  shifted by one against `rec`. Such speeches get orders from 100 + position so
  they never take a real psp.cz anchor number.
- The first page of a sitting opens with a note such as "(Schůze zahájena v
  14.00 hodin.)"; it is not a speech.

## Attribution

Label link, then `rec`, then a unique full-name match; a link or `rec` person is
accepted only if the label ends with that person's full name. Role (chair or
speaker) and agenda item come from `rec` only when it names the same person as
the page; otherwise they stay unknown. `rec` lacks whole stretches (e.g. term 9
sittings 112–124 and the first pages of term 10's sitting 1), so most
attributions rely on the page itself.

First real import (25 pages from each term): all 139 speeches attributed (126
by link, 13 by index), every one of 1 014 stored paragraphs found verbatim in
its source page, 32 speeches spanning pages.

## Operation

- `metadata` takes about 30 s for both terms (4 dumps): 18 500 pages expected
  (13 926 + 4 574), 92 767 index entries, 418 mandates.
- Pages download at one request per second. The full backfill was started on
  18 Nov 2026 at 09:01 as PID 26257, logging to
  `~/.local/share/rozprava/log/backfill-20261118-0901.out`; the PID is also in
  `~/.local/share/rozprava/backfill.pid` and in the `import_run` table.
- Tried first and rejected: rebuilding a sitting after every page (quadratic on
  700-page sittings). Now a sitting is assembled once its pages in the run are
  done, and `source_page.assembled_revision_id` marks what still needs it.
