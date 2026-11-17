---
type: decision
updated: 2026-11-17
status: current
---

# Design preview

Related: [[design-direction]], [[stack-decision]], [[feasibility-research]], [[dev-environment]]

A static preview of the five main screens plus a states page, built from the app's real Jinja templates and real psp.cz excerpts. It's the first code in `src/rozprava`.

## What exists (17 Nov 2026)

- **Pages:** home, search results with a cited summary, transcript reader, MP profile, MP directory, and states (suggestions dropdown, loading, empty, error, chips and buttons).
- **Data:** `preview/data.json`, built by `scratch/scripts/build_preview.py` from the open-data dumps and live transcript pages. Every quote is checked as an exact substring of its transcript, and a test checks every rendered quote against the data, character for character.
- **Rendering:** `scripts/render_preview.py` writes `preview/site/` (gitignored). Templates call `link()` and `static()` globals, so the FastAPI app can reuse them unchanged by supplying its own versions.
- **CSS:** `tokens.css` is generated from the `DESIGN.md` frontmatter by `scripts/build_tokens.py`. `app.css` holds the components. Fonts are self-hosted by `scripts/fetch_fonts.py`.
- **Czech typesetting:** `rozprava/typography.py`, used as Jinja filters: non-breaking spaces, dates, numbers, plurals, term highlighting and Czech alphabetical order.

## Decisions

- **Static render, not FastAPI routes.** The hard rule says web requests read Postgres only, so the preview is rendered to files instead of being served from a fixture.
- **Sidebars on the right.** A left sidebar was tried first and pushed the results into the narrow column. On the right, the reading column lines up with the wordmark.
- **No automatic hyphenation in verbatim text.** The browser's hyphens looked like the speaker's own, next to real ones such as "opt-out".
- **Ellipsis only for cuts inside a sentence.** Whole-sentence excerpts get none, so the "…" always means something was cut mid-thought.
- **Parties listed alphabetically**, with "Nezařazení" last, never by size.
- **Profile cards drop the speaker line** and lead with the agenda item.
- **The UI explains "verbatim":** psp.cz edits transcripts (grammar, hesitations), so we quote the transcript exactly, not the spoken word.
- **Czech interface copy** in the preview. This doesn't settle the open decision on interface language.

## Open

- Charts (speech frequency over time) are still unspecified.
- MPs who changed club mid-term: which badge to show on older speeches.
- Agenda items need short names ("Novela zákona o doplňkovém penzijním spoření"). Official titles run to 200 characters. Where the short name comes from is open.
- Next step: scaffold the FastAPI app around these templates and swap the fixture for Postgres.
