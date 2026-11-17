---
type: decision
updated: 2026-11-17
status: current
---

# Design preview

Related: [[design-direction]], [[stack-decision]], [[feasibility-research]], [[dev-environment]]

The redesign follows the replacement root DESIGN.md. It renders the real Jinja
components with cached psp.cz source data, without fetching data on web requests.

## Run

```sh
uv run python scripts/render_preview.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory preview/site
```

Open `http://127.0.0.1:8000/`. All generated files are ignored by git.
`/_design/` (also `design.html`) is the component review page; do not expose it as
a production route. `scripts/build_tokens.py` derives tokens from the specification
sections/tables and §14.1 CSS, no longer from YAML frontmatter.

## Implemented

- Ten pages: home, search, transcript, profile, 200-MP directory, 36-session index,
  methodology, quote composer, 404, component review.
- Paper/ink themes with cookie persistence and an explicit light/dark comparison.
  Locally hosted Cooper Hewitt, Source Serif 4 and IBM Plex Mono cover Czech glyphs;
  Schibsted Grotesk remains the fallback.
- Catalogue identities, verbatim excerpts, source links, citation previews, four-line
  excerpts with an omission mark inside the quotes, and a distinct sans AI summary.
- Keyboard palette with accent-insensitive search, recent visits, focus confinement,
  Escape dismissal and restoration of focus. Mobile menu and facet drawer likewise.
- URL-backed sample search filters, sorting, date-range selection via histogram or
  date fields, empty states, MP party/region/name filtering and sortable columns.
- Profile medians, attendance, activity calendar/compact month strips, period/day
  filtering, local speech search and a screen-reader table with visible toggle.
- Transcript paragraph links and selection toolbar. Quote composer accepts only
  spans of stored sources, checks 280 characters and available line space, and
  downloads PNG in all three specified dimensions using the local fonts.

## Evidence

`uv run pytest`, `uv run ruff check .`, `uv run pyright`, token freshness, and JS
syntax checks. The tests cover exact transcript/excerpt text, omission markers,
invalid summary citations, Czech fonts, identity normalization and activity layout.
Browser checks include desktop/tablet/phone widths, dark/light themes, keyboard
palette focus, search filters, profile periods/table, transcript-to-card selection,
and actual PNG export.

The interrupted redesign expected `median_days_spoke` but the fixture had not been
rebuilt. Rebuilding from cached open-data dumps supplied the real median (15),
instead of inventing a fallback value. Use this command to refresh the fixture:

```sh
uv run python scratch/scripts/build_preview.py scratch/dl/opendata scratch/dl/steno-html preview/data.json
```

## Deliberate limits

The search page filters six stored sample speeches locally; semantic retrieval,
live summaries and production FastAPI/Postgres routes are not implemented. The
preview banner explains that MP/transcript navigation uses sample pages. Copied
source links point to the actual psp.cz source. No guessed public short-link domain.

Party colours await official brand-manual verification. Activity levels currently
use global quartiles of speech counts (1/2/3), clearly described in the methodology;
word quartiles need full ingest. The fourth profile tile is the most frequent
agenda item until a topic taxonomy exists. The featured quote is sampled when the
fixture is rebuilt, using an hourly seed; a static page does not reroll itself.
Full session word totals, automatic nightly ingestion, server OG endpoints, and
Phase 2 annotations/live data remain production work.
