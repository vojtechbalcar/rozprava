---
version: 1
name: Rozprava
description: >
  An editorial interface for searching what Czech MPs said in parliament.
  The layout, type and spacing are adapted from anthropic.com / claude.com:
  regular-weight serif display type, a humanist sans for interface text,
  generous spacing, colour blocks instead of shadows. The colours are our own
  "archive" palette: cool grey-green paper, green-black ink and one petrol
  accent. The app is a reading tool, so quotes are the main content: set in the
  serif, verbatim, and always traceable to a speaker, a date and a transcript.

colors:
  accent: "#1d6b65"          # petrol: wordmark, buttons, links, focus ring, citation markers
  accent-pressed: "#154f4b"  # pressed buttons, visited links
  accent-tint: "#d6e9e5"     # highlighted search terms, citation marker background
  ink: "#121a18"
  body-strong: "#212b28"
  body: "#36413e"
  muted: "#5d6965"
  muted-soft: "#85908c"      # disabled states and decorative separators only (3:1)
  hairline: "#dde2dc"
  hairline-soft: "#e7eae5"
  canvas: "#f6f7f4"
  surface-soft: "#eef0ec"
  surface-card: "#e6eae5"
  surface-strong: "#d9dfd9"
  surface-dark: "#0f1b19"
  surface-dark-elevated: "#1a2a27"
  on-dark: "#eef1ec"
  on-dark-soft: "#9aa8a3"
  on-primary: "#ffffff"
  error: "#b3261e"
  success: "#2e7d4f"

typography:
  display-xl:   { fontFamily: "Newsreader, Georgia, serif", fontSize: 64px, fontWeight: 400, lineHeight: 1.05, letterSpacing: -1.5px }
  display-lg:   { fontFamily: "Newsreader, Georgia, serif", fontSize: 48px, fontWeight: 400, lineHeight: 1.1,  letterSpacing: -1px }
  display-md:   { fontFamily: "Newsreader, Georgia, serif", fontSize: 36px, fontWeight: 400, lineHeight: 1.15, letterSpacing: -0.5px }
  display-sm:   { fontFamily: "Newsreader, Georgia, serif", fontSize: 28px, fontWeight: 400, lineHeight: 1.2,  letterSpacing: -0.3px }
  quote-lg:     { fontFamily: "Newsreader, Georgia, serif", fontSize: 22px, fontWeight: 400, lineHeight: 1.5,  letterSpacing: 0 }
  quote-md:     { fontFamily: "Newsreader, Georgia, serif", fontSize: 19px, fontWeight: 400, lineHeight: 1.6,  letterSpacing: 0 }
  title-lg:     { fontFamily: "Inter, system-ui, sans-serif", fontSize: 22px, fontWeight: 500, lineHeight: 1.3, letterSpacing: 0 }
  title-md:     { fontFamily: "Inter, system-ui, sans-serif", fontSize: 18px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }
  title-sm:     { fontFamily: "Inter, system-ui, sans-serif", fontSize: 16px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }
  body-md:      { fontFamily: "Inter, system-ui, sans-serif", fontSize: 16px, fontWeight: 400, lineHeight: 1.55, letterSpacing: 0 }
  body-sm:      { fontFamily: "Inter, system-ui, sans-serif", fontSize: 14px, fontWeight: 400, lineHeight: 1.55, letterSpacing: 0 }
  caption:      { fontFamily: "Inter, system-ui, sans-serif", fontSize: 13px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }
  meta:         { fontFamily: "JetBrains Mono, ui-monospace, monospace", fontSize: 13px, fontWeight: 400, lineHeight: 1.4, letterSpacing: 0 }
  button:       { fontFamily: "Inter, system-ui, sans-serif", fontSize: 14px, fontWeight: 500, lineHeight: 1, letterSpacing: 0 }
  nav-link:     { fontFamily: "Inter, system-ui, sans-serif", fontSize: 14px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  pill: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 96px

layout:
  content-max: 1200px
  reading-max: 680px          # quotes, answers and transcripts never run wider

components:
  top-nav:            { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", typography: "{typography.nav-link}", height: 64px }
  button-primary:     { backgroundColor: "{colors.accent}", textColor: "{colors.on-primary}", typography: "{typography.button}", rounded: "{rounded.md}", padding: 12px 20px, height: 40px }
  button-secondary:   { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", border: "1px {colors.hairline}", typography: "{typography.button}", rounded: "{rounded.md}", padding: 12px 20px, height: 40px }
  text-link:          { textColor: "{colors.accent}", typography: "{typography.body-md}" }
  search-field:       { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", border: "1px {colors.hairline}", typography: "{typography.title-md}", rounded: "{rounded.lg}", height: 56px, padding: 0 20px }
  search-field-focused: { border: "1px {colors.accent}", ring: "3px rgba(29,107,101,0.15)" }
  filter-chip:        { backgroundColor: "{colors.surface-card}", textColor: "{colors.ink}", typography: "{typography.caption}", rounded: "{rounded.pill}", padding: 6px 12px }
  filter-chip-active: { backgroundColor: "{colors.ink}", textColor: "{colors.on-dark}" }
  party-badge:        { backgroundColor: "transparent", textColor: "{colors.muted}", border: "1px {colors.hairline}", typography: "{typography.caption}", rounded: "{rounded.pill}", padding: 2px 8px }
  quote-card:         { backgroundColor: "{colors.canvas}", border: "1px {colors.hairline}", rounded: "{rounded.lg}", padding: 32px }
  answer-panel:       { backgroundColor: "{colors.surface-card}", textColor: "{colors.body-strong}", typography: "{typography.body-md}", rounded: "{rounded.lg}", padding: 32px }
  citation-marker:    { backgroundColor: "{colors.accent-tint}", textColor: "{colors.accent}", typography: "{typography.meta}", rounded: "{rounded.xs}", padding: 0 4px }
  term-highlight:     { backgroundColor: "{colors.accent-tint}", textColor: "{colors.ink}" }
  speaker-line:       { textColor: "{colors.ink}", typography: "{typography.title-sm}" }
  meta-line:          { textColor: "{colors.muted}", typography: "{typography.meta}" }
  mp-header:          { backgroundColor: "{colors.canvas}", typography: "{typography.display-lg}", padding: 64px 0 }
  transcript-reader:  { backgroundColor: "{colors.canvas}", typography: "{typography.quote-md}", maxWidth: "{layout.reading-max}" }
  stat-tile:          { backgroundColor: "{colors.surface-soft}", rounded: "{rounded.lg}", padding: 24px }
  cta-band-dark:      { backgroundColor: "{colors.surface-dark}", textColor: "{colors.on-dark}", typography: "{typography.display-sm}", rounded: "{rounded.lg}", padding: 64px }
  footer:             { backgroundColor: "{colors.surface-dark}", textColor: "{colors.on-dark-soft}", typography: "{typography.body-sm}", padding: 64px }
---

## Overview

Rozprava borrows the *structure* of anthropic.com and claude.com:
regular-weight serif headlines with tight tracking, a humanist sans for
everything functional, generous editorial spacing, depth from colour blocks
rather than shadows, and one accent used sparingly. On anthropic.com that
voice says "considered, literary, trustworthy". That is exactly what a civic
search tool needs. It should feel like a good newspaper's archive, not like a
chatbot and not like a campaign site.

The colours are deliberately **not** Anthropic's. Instead of cream paper and
coral, Rozprava uses an "archive" palette: cool grey-green paper, green-black
ink and a single petrol accent, like a well-kept reading room or a
library-bound volume.

The other difference from the source: Anthropic's site is marketing; Rozprava
is a reading and search tool. Most screens are lists of quotes and a
transcript reader, so the system adds quote typography, citation markers,
filter chips and a reading column, and drops pricing cards, code windows and
full-bleed callout bands.

**Key characteristics**
- Grey-green paper `{colors.canvas}` with green-black ink `{colors.ink}`. Never
  pure white, never warm cream.
- Newsreader serif at weight 400 for display headlines **and for quoted speech**.
  Anything an MP actually said is set in the serif; everything the interface or
  the AI says is set in the sans. That split is how readers tell evidence from
  commentary at a glance.
- One accent: petrol `{colors.accent}`. It passes WCAG AA as text on every light
  surface and behind white button text, so one colour does every job.
- Depth comes from surface steps (canvas → surface-card → dark), not shadows.
- Dates, session numbers and transcript references in JetBrains Mono, so
  sources read like references.

## What we take from anthropic.com, and what we change

| Anthropic | Rozprava | Why |
|---|---|---|
| Copernicus / Tiempos display serif | **Newsreader** (Google Fonts, open source) | Copernicus is licensed. Newsreader has optical sizes, so the same family works for 64px headlines and 19px quotes, and it covers Czech diacritics (ě š č ř ž ý á í é ů ú ň ť ď). |
| StyreneB sans | **Inter** | Closest open humanist sans; full Czech support. |
| Layout, type scale, spacing, radii, colour-block depth | **Kept** | This is what makes the editorial feel. |
| Cream canvas, coral accent, warm greys | **Replaced** with the archive palette | Our own identity; not an Anthropic look-alike. |
| Spike-mark logo | Own wordmark: "Rozprava" in Newsreader 400 with a petrol full stop | The spike mark is Anthropic's; never use it. |
| Full-bleed accent callout cards | Not used | Large blocks of accent colour would start to read as a party colour (see rules below). |
| Dark product mockups | Dark surface only for the landing page's "how it works" band and the footer | The product itself stays on paper. |

## Colors

### Accent
- **Petrol** `{colors.accent}` — wordmark full stop, primary buttons, inline
  text links, citation markers, the focus ring. About 5.8:1 on the canvas;
  white on petrol about 6.3:1.
- **Petrol pressed** `{colors.accent-pressed}` — pressed buttons, visited links.
- **Petrol tint** `{colors.accent-tint}` — background of matched search terms
  inside quotes and of citation markers.

Petrol was chosen because it sits away from the primary colours Czech parties
campaign in (the blues, reds, oranges, yellows and purples), and it reads as
"archive, ink, institution" rather than "brand".

### Neutral, political, and never
Petrol is the brand only. It never marks a party, a side, agreement,
disagreement or sentiment. **Parties never get colours.** Party badges are
outlined neutral pills with the party's abbreviation, identical for every party.
Charts that compare parties use one neutral ink series, or shades of
`{colors.muted}`, labelled directly. Green and red appear only as form
success/error states.

### Surfaces and text
The ladder runs `canvas` (page) → `surface-soft` (stat tiles, quiet bands) →
`surface-card` (answer panel, chips) → `surface-strong` (selected state) →
`surface-dark` (footer, landing band only). Every surface carries the same
slight green-grey tint, so the page never mixes warm and cool neutrals. Text
runs `ink` (headlines, speaker names) → `body-strong` (answer text) → `body`
(running text) → `muted` (metadata, 5.3:1) → `muted-soft` (disabled states and
decorative separators only; it is 3:1 and must not carry readable text).

## Typography

### The serif/sans rule
- **Serif (Newsreader):** display headlines, MP names on profile pages, and every
  verbatim quote.
- **Sans (Inter):** navigation, buttons, filters, labels, AI-generated summaries,
  explanatory text.
- **Mono (JetBrains Mono):** dates, session and sitting numbers, transcript
  references, citation markers `[3]`.

Display sizes stay at weight 400 with negative tracking. Emphasis comes from
size, never bold serif.

### Czech typesetting
- Quotation marks are Czech: „takto“. Never "straight" or “English” quotes in
  Czech text.
- Non-breaking space after one-letter prepositions and conjunctions
  (k, s, v, z, o, u, a, i) so they never end a line.
- Dates: `12. 11. 2026` with non-breaking spaces; times `14:05`.
- Numbers: thin or non-breaking space as the thousands separator (`12 480`),
  comma as decimal separator.
- Set `lang="cs"` on Czech content so screen readers behave.
- Numbers stay with what they count and with their digit groups ("10 let",
  "200 000 korun", "č. 427/2011 Sb.").
- Reference separators " · " are bound to the item before them, so a line never
  starts with a dot.
- Alphabetical lists use Czech order: "Ch" is a letter after "H", and Č, Ř, Š,
  Ž are letters of their own; accented vowels sort with their base letter.

## Layout

- Base unit 4px; tokens as in the frontmatter.
- `{layout.content-max}` 1200px for page chrome and grids.
- `{layout.reading-max}` 680px for quotes, answers and transcripts. Readable
  line length matters more than filling the screen.
- `{spacing.section}` 96px between landing-page bands; inside the app, 48px
  between page sections and 16px between result cards.
- Generous card padding (32px). Let quotes breathe.
- Sidebars (search facets, a transcript page's speakers, an MP's frequent agenda
  items) sit to the right of the reading column from 1024px, so the reading
  column lines up with the wordmark. Below 1024px they follow the main content
  or are left out where the chips already cover them.

## Elevation

Colour-block first, shadow rare. Cards on canvas use a 1px `{colors.hairline}`
border; panels use `{colors.surface-card}` with no border. The only shadow is
`0 1px 3px rgba(20,20,19,0.08)` on the open search suggestions dropdown.

## Components

### Search field
The centre of the home page and pinned in the top nav elsewhere. 56px tall,
`{typography.title-md}`, hairline border, `{rounded.lg}`. Focus: petrol border and
a 3px petrol ring at 15%. Placeholder is a real example question, not "Search…".
Filter chips sit directly below it.

### Filter chips
`{component.filter-chip}` for MP, party, term, date range. Active chips flip to
ink with `{colors.on-dark}` text and carry a × to remove. Filters also live in the URL.

### Quote card (the core result)
Order, top to bottom:
1. **Speaker line** — MP name in `{typography.title-sm}`, the neutral party
   badge, and their role at the time if relevant.
2. **The quote** — `{typography.quote-md}` in the serif, Czech quotation marks,
   matched terms in `{component.term-highlight}`. Trim with an ellipsis "…",
   never by rewording.
3. **Meta line** — `{typography.meta}`: date · sitting/session · "Open in
   transcript →" as a `{component.text-link}`.

Details:
- An ellipsis marks a cut only when the excerpt starts or ends inside a
  sentence. Excerpts made of whole sentences get none.
- Above the meta line, the agenda item in `{typography.body-sm}` muted:
  "Bod 17: Novela zákona o doplňkovém penzijním spoření".
- Transcripts that psp.cz hasn't authorised yet carry "neautorizováno" in the
  meta line, with a dotted underline and a tooltip saying the wording may change.
- On search results the card shows its citation number `[1]` top right, so it
  matches the marker in the answer panel.
- On an MP's own profile the speaker line would repeat on every card, so the
  card drops it and leads with the agenda item instead. When psp.cz gives no
  agenda item, say so ("Bod pořadu není v datech Sněmovny uveden") rather than
  guessing.

### Answer panel
For questions that get an AI summary. `{colors.surface-card}` background,
sans text, so it never looks like a quote. Starts with a small caption "Summary
from N speeches". Every sentence that makes a claim ends with one or more
`{component.citation-marker}` (`[1]`, `[2]`) linking to the quote card below.
If nothing is cited, nothing is shown.

### Transcript reader
Single reading column at `{layout.reading-max}`, serif `{typography.quote-md}`.
Speaker changes are marked by the speaker line in the sans. The cited passage is
highlighted with `{colors.accent-tint}` and scrolled into view. Sticky meta line at
the top with date, sitting and a link to the original on psp.cz.

- A petrol-tint label ("↓ Hledaná pasáž, výsledek [1]") sits above the paragraph
  with the cited passage and is the scroll target, so it's visible on arrival.
- No automatic hyphenation in verbatim text. A hyphen added by the browser would
  look like part of the transcript (and some words, like "opt-out", really have one).
- A page that opens mid-speech credits the speaker and says "Pokračování projevu
  ze s. 642". Never drop or orphan that text.
- The chair's procedural speeches are set in `{colors.body}` rather than ink.
- From 1024px a "Na této straně" list of speakers sits to the right.

### MP profile
`{component.mp-header}`: name in `{typography.display-lg}` serif, party badge,
terms served in mono. Below: a row of `{component.stat-tile}`s (speeches,
words spoken, most frequent topics), then their speeches as quote cards.
Portrait photos, if used, crop to circles at 64px; no large hero photos.

### Navigation and footer
64px top nav on the canvas: wordmark left, nav links, search field on inner pages. Dark
`{component.footer}` closes every page with sources, methodology and a
non-partisanship statement.

### States
- **Loading:** skeleton blocks in `{colors.surface-soft}` the shape of
  quote cards. No spinners on the main results.
- **Empty:** a serif sentence ("Nikdo to tak neřekl.") plus suggestions to
  broaden filters.
- **Error:** plain sans text in `{colors.body}` with a retry; the error colour
  only on form fields.

## Do

- Keep every page on the grey-green paper canvas.
- Set what MPs said in the serif and what the app says in the sans.
- Show the source with every quote: speaker, date, sitting, link.
- Use petrol for interactive elements and the wordmark, and nowhere decorative.
- Use Czech typographic conventions in Czech content.
- List parties alphabetically in Czech order, with "Nezařazení" last. Never by
  size, seats or side.

## Don't

- Don't colour parties, ever, and don't let petrol touch political meaning.
- Don't put AI text in quotation marks or in the serif.
- Don't bold the serif display.
- Don't use the Anthropic spike mark, Anthropic's fonts, or copy their pages.
- Don't add shadows, gradients, or a fourth surface tone.
- Don't bring back Anthropic's cream and coral, or any warm neutrals.
- Don't run reading text wider than 680px.

## Responsive

| Name | Width | Changes |
|---|---|---|
| Mobile | < 768px | Display-xl 64 → 36px; nav collapses to a full-screen canvas sheet; filter chips scroll horizontally; quote cards drop to 20px padding |
| Tablet | 768–1024px | Stat tiles 2-up |
| Desktop | ≥ 1024px | Stat tiles 4-up; optional filter sidebar on results |

Touch targets at least 44px, including chips (pad the hit area if the visual pill
is smaller).

## Known gaps

- Fonts are self-hosted by `scripts/fetch_fonts.py` (Latin + Latin Extended,
  variable weights, Newsreader with its optical-size axis). The Latin subset has
  no arrows, so a tiny arrows-only file covers Inter and JetBrains Mono.
  Newsreader has no arrow glyphs at all: never put an arrow in serif text.
- Interface language is still open. The design preview uses Czech.
- MPs who changed club during a term: which badge to show on older speeches.
- Chart styling (speech frequency over time, topic breakdowns) is not specified
  yet beyond "neutral ink, no party colours".
- Dark mode is not specified.
