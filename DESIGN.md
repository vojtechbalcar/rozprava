# Rozprava — Design Specification

> Version 1.0 · 2026-11-17
> This file is the single source of truth for the visual and interaction design of Rozprava. Any coding agent or human implementing UI must follow it. If something is not covered here, follow the **Principles** (§2) and add the decision back to this file.

---

## 0. TL;DR

- **Metaphor:** Rozprava is a **museum collection of what was said in the Sněmovna**. Every speech excerpt is a cataloged *object* with exact provenance (term, session, page, order, authorization status). Visual base: **Cooper Hewitt** (collection pages, catalog labels, browse-by-facet).
- **Signature accent:** **dot-matrix rendering for numbers and live data only** (borrowed from Nothing). Never for running text.
- **Color:** monochrome ink on archival paper. The only brand color is **highlighter yellow** used for search matches and annotations. Party colors exist only as small, normalized identity swatches.
- **Shape:** square. **Zero border radius everywhere.** Hairline rules instead of boxed cards.
- **Signature features:** ⌘K command palette, session-day activity graph (GitHub-style, dot-matrix), shareable quote cards, Genius-style annotations (phase 2).
- **Tone:** neutral, exact, institutional. Never editorializes.

---

## 1. Product positioning (decide before building)

Rozprava currently is a **searchable, readable record** of Sněmovna transcripts with AI-generated, cited summaries. It does not yet fact-check. The design supports a two-phase path:

| Phase | Product | Design implication |
|---|---|---|
| **1 — The Record** (now) | Semantic search, transcripts, MP profiles, cited AI summaries | Museum collection: objects, provenance, browsing |
| **2 — The Annotated Record** | Genius-style annotations on transcript sentences: context, data, **said vs. voted** (speech ↔ roll-call votes from psp.cz) | Annotation layer on top of the same objects. No new visual language needed |

Rule: **never label the product "fact-check" in UI copy until Phase 2 ships.** Phase 1 tagline is about the record, not about verdicts.

---

## 2. Design principles

1. **Provenance over decoration.** Every quote shows where it came from: date, schůze, page, authorization status, link to psp.cz original. If space is tight, cut decoration, never provenance.
2. **Neutral by construction.** Every party, MP and quote gets identical visual treatment. No element may imply a judgment unless it is an explicit, sourced annotation (Phase 2).
3. **The quote is the object.** Quotes are the hero of every page, set in the reading serif and treated like museum pieces with catalog labels.
4. **Calm system, one loud signature.** The base is quiet (ink, paper, rules). The dot-matrix data layer is the only "loud" element. Don't add a second one.
5. **Human vs. machine is always visible.** AI-generated text looks different from verbatim transcript text, always (§7.8).
6. **Readable for citizens, fast for power users.** The visible search box is the primary entry. ⌘K is the shortcut layer on top, never a replacement.
7. **Czech first.** All type must render Czech diacritics perfectly (ě š č ř ž ý á í é ú ů ď ť ň, uppercase included). Dates, numbers and quotes follow Czech typographic conventions (§4.6).

---

## 3. Color

### 3.1 Core tokens — light (default)

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#F6F5F0` | Page background (archival paper) |
| `--paper-2` | `#ECEAE2` | Sunken surfaces: AI summary block, stat tiles, code/meta wells |
| `--paper-3` | `#E2DFD5` | Hover on sunken surfaces, active filter background |
| `--ink` | `#111111` | Primary text, rules, primary buttons, dot-matrix "on" dots |
| `--ink-2` | `#3D3C38` | Secondary text, body UI text |
| `--ink-3` | `#6B6A64` | Meta text (dates, page numbers, counts). AA on `--paper` |
| `--ink-4` | `#A3A198` | Disabled text, placeholder, dot-matrix "off" dots |
| `--rule` | `#D3D0C6` | Hairline dividers |
| `--rule-strong` | `#111111` | Catalog label top rules, section dividers |
| `--highlight` | `#FFE45E` | Search-term highlighting, annotated spans, selection |
| `--highlight-strong` | `#E8C400` | Underline of annotated spans, active citation |
| `--focus` | `#111111` | Focus ring (2px solid + 2px offset in `--paper`) |
| `--danger` | `#B3261E` | Errors only (form/system errors). Never for content |

### 3.2 Core tokens — dark

| Token | Hex |
|---|---|
| `--paper` | `#0F0F0E` |
| `--paper-2` | `#1A1A18` |
| `--paper-3` | `#24241F` |
| `--ink` | `#EDEBE4` |
| `--ink-2` | `#C4C2BA` |
| `--ink-3` | `#8E8C84` |
| `--ink-4` | `#56554F` |
| `--rule` | `#2E2D29` |
| `--rule-strong` | `#EDEBE4` |
| `--highlight` | `#FFE45E` (text inside highlight is always `#111111`) |
| `--highlight-strong` | `#E8C400` |
| `--focus` | `#EDEBE4` |
| `--danger` | `#F2B8B5` |

Dark mode follows `prefers-color-scheme`, with a manual toggle stored in a cookie (`theme=light|dark|system`).

### 3.3 Color rules

- **No brand accent color.** The current teal is removed. Primary buttons are `--ink` background with `--paper` text.
- **Yellow means only "this matches / this is annotated."** It is never decoration, never a button, never a badge background.
- **No red, blue, green, orange or purple in brand UI.** These are party colors in Czech politics and would read as partisan.
- Links: `--ink` text, 1px underline in `--ink-3`, `text-underline-offset: 3px`. On hover the underline becomes `--ink` 2px.

### 3.4 Party identity swatches

Parties are identified by **abbreviation text + a small swatch**, never by colored backgrounds or colored text.

- Swatch: **8×8 px square**, inline before the party abbreviation, `margin-right: 6px`.
- Colors live in `lib/parties.ts`, sourced from each party's official brand manual (**TODO: verify each hex against official sources before launch**; do not guess).
- **Normalization (mandatory):** convert each official color to OKLCH, then force **L = 0.62, C = 0.12** and keep only the hue. Every party then has the same visual weight; no party "shouts" louder.
- Achromatic parties (e.g. black branding): use `oklch(0.35 0 0)` solid.
- **Hue collision rule:** if two parties' hues are within 20°, the later one (alphabetical by abbreviation) gets a **diagonal-hatched swatch** (45°, 2px stripes, same color + `--paper`).
- Party pill: abbreviation in mono, uppercase, `--ink-2`, 1px `--rule` border, no fill, padding `2px 6px`, radius 0.
- Independent MPs: swatch is a 1px `--ink-3` outlined empty square, label `NEZ.`

```ts
// lib/parties.ts — shape (values TODO: verify)
export type Party = {
  id: string;            // "ods"
  abbr: string;          // "ODS"
  name: string;          // "Občanská demokratická strana"
  officialHex: string;   // from brand manual — TODO verify
  hue: number;           // derived: oklch hue of officialHex
  hatched?: boolean;     // derived by collision rule
};
export const swatchColor = (p: Party) =>
  p.hue === null ? "oklch(0.35 0 0)" : `oklch(0.62 0.12 ${p.hue})`;
```

---

## 4. Typography

### 4.1 Families

| Role | Family | Fallback | Notes |
|---|---|---|---|
| **Sans (UI, display)** | **Cooper Hewitt** (SIL OFL) | `Schibsted Grotesk`, `system-ui` | **Must pass the diacritics test (§4.5) before adopting.** If it fails, use Schibsted Grotesk as primary |
| **Serif (quotes, transcripts)** | **Source Serif 4** (variable, opsz) | `Georgia`, serif | Use optical size axis: `opsz` 20+ for quotes, auto for body |
| **Mono (meta, catalog numbers, labels)** | **IBM Plex Mono** | `ui-monospace` | Weights 400, 500 |
| **Dot-matrix (numbers only)** | **Custom SVG 5×7 glyphs** (§8) | n/a | Never a webfont. Digits, space, `.`, `,`, `%`, `–` only |

Load via `next/font/local` (Cooper Hewitt) and `next/font/google` (Source Serif 4, IBM Plex Mono, Schibsted Grotesk) with `subsets: ["latin", "latin-ext"]`. **`latin-ext` is mandatory.**

### 4.2 Type scale

Base 16px. Values: `font-size / line-height / letter-spacing / weight`.

| Token | Family | Size | LH | Tracking | Weight | Use |
|---|---|---|---|---|---|---|
| `display-xl` | Sans | 80px (5rem) | 0.92 | -0.035em | 600 | Home hero only |
| `display-l` | Sans | 56px | 0.95 | -0.03em | 600 | MP name, bill title on transcript |
| `h1` | Sans | 40px | 1.05 | -0.02em | 600 | Page titles |
| `h2` | Sans | 28px | 1.15 | -0.015em | 600 | Section titles |
| `h3` | Sans | 20px | 1.25 | -0.01em | 600 | Card titles, speaker names in transcript |
| `quote-l` | Serif | 26px | 1.45 | -0.005em | 400 | Featured quote, quote card |
| `quote` | Serif | 21px | 1.55 | 0 | 400 | Quotes in result lists |
| `body-read` | Serif | 19px | 1.7 | 0 | 400 | Transcript running text |
| `body` | Sans | 16px | 1.5 | 0 | 400 | UI prose, AI summary |
| `ui` | Sans | 15px | 1.35 | 0 | 500 | Buttons, chips, nav |
| `meta` | Mono | 13px | 1.4 | 0.01em | 400 | Dates, pages, counts |
| `label` | Mono | 11px | 1.3 | 0.08em | 500, UPPERCASE | Catalog label keys, section eyebrows |

Mobile (<640px): `display-xl` → 48px, `display-l` → 40px, `h1` → 32px, `quote-l` → 22px, `quote` → 19px, `body-read` → 18px. Everything else unchanged.

### 4.3 Measure

- Transcript and quote text: **max 68ch** (`max-width: 68ch`).
- AI summary: max 72ch.
- UI prose: max 60ch.

### 4.4 Rules

- Never set running text in mono or sans when it is verbatim speech. **Verbatim = serif, always.**
- Never use italic for emphasis in UI. Italic is reserved for `[poznámka stenografa]` style transcript annotations (e.g. *(Potlesk.)*, *(Hluk v sále.)*).
- Never use the `label` style for anything longer than 4 words.
- Headlines: sentence case, no trailing period.

### 4.5 Diacritics test (must pass for every family, regular + bold + uppercase)

```
Příliš žluťoučký kůň úpěl ďábelské ódy.
PŘÍLIŠ ŽLUŤOUČKÝ KŮŇ ÚPĚL ĎÁBELSKÉ ÓDY.
Sněmovně · přepisu · schůze · neautorizováno · Jiří Havránek · Činčila
„Doslovná citace“ – 6. 11. 2026 – 43 897 slov
```

Check: carons on ď/ť render as apostrophe-style on lowercase; kroužek on ů not clipped at `line-height: 0.92`; uppercase accents not clipped by `overflow: hidden` in display sizes (add `padding-top: 0.08em` on display headings).

### 4.6 Czech typographic conventions

- Quotes: **„…“** (low-99 open, high-66 close). Never `"…"`.
- Dash: en dash with spaces ` – `. Ranges: `2021–2026` (en dash, no spaces).
- Thousands separator: **thin non-breaking space** ` ` (`43 897`). Use `Intl.NumberFormat("cs-CZ")` (it outputs ` `; replace with ` `).
- Decimal: comma (`3,5 %`), space before `%`.
- Dates: `6. 11. 2026` (spaces, non-breaking ` ` after dots). Long form: `pátek 6. listopadu 2026`.
- Time: `12:50`.
- Non-breaking space after single-letter prepositions and conjunctions (`v`, `k`, `s`, `z`, `o`, `u`, `a`, `i`). Implement a `nbsp()` utility applied to all quote and summary text: `text.replace(/(\s|^)([vkszouaiVKSZOUAI])\s/g, "$1$2 ")`.

---

## 5. Layout, spacing, shape

### 5.1 Spacing scale (4px base)

`0, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128` px → tokens `space-0 … space-11`.

- Component internal padding: 16 / 24.
- Between list items: 0 (separated by rules, not gaps).
- Between page sections: 96 desktop, 64 mobile.

### 5.2 Grid

- 12 columns, gutter 24px, outer margin 32px desktop / 16px mobile.
- Max container width: **1312px** (1280 + margins).
- Standard page split: **main 8 cols / aside 4 cols** (aside is facets, "on this page", related).
- Reading pages (transcript): main column 7 cols, offset 0; aside 4 cols, offset 1.

### 5.3 Breakpoints

| Name | Min width |
|---|---|
| `sm` | 640px |
| `md` | 768px |
| `lg` | 1024px |
| `xl` | 1280px |

Aside collapses below `lg` into a "Filtry" drawer (search) or into a section below content (profile, transcript).

### 5.4 Shape

- **Border radius: 0** on everything: buttons, inputs, chips, cards, avatars, tooltips, modals, images.
- **No shadows** except: ⌘K palette and popovers get `0 0 0 1px var(--ink), 8px 8px 0 0 var(--ink)` (a hard offset shadow like a printed label). Nothing else gets a shadow.
- **No boxed cards** in lists. Objects are separated by a **1px `--rule-strong` top rule** (catalog-label style). Sunken surfaces (`--paper-2`) are used only for AI summary, stat tiles and the quote card preview.

### 5.5 Borders

- Hairline: `1px solid var(--rule)`.
- Strong: `1px solid var(--rule-strong)`.
- Inputs: `1px solid var(--ink)`; focus adds 2px ring.

---

## 6. Iconography & imagery

- Icons: **Lucide**, `stroke-width: 1.5`, sizes 16px (inline) and 20px (buttons). Color `currentColor`.
- **No photos of MPs in Phase 1.** Use square monogram tiles (`--paper-2` background, initials in Sans 600, `--ink`). Sizes: 32, 48, 96px. (Photos introduce bias via photo quality/choice; revisit later with official psp.cz portraits only, all treated identically: grayscale, same crop.)
- No illustrations. No emoji in UI.
- Arrows in links: `→` / `←` / `↗` (external) as text glyphs in the same font.

---

## 7. Components

### 7.1 Site header

- Height 64px, `--paper` background, bottom `1px var(--rule)`. Sticky on scroll; when scrolled > 8px it stays sticky with no shadow.
- Left: wordmark **"Rozprava"** in Sans 600 22px, tracking -0.02em, followed by a **single 6×6px square in `--highlight`** aligned to the baseline (replaces the current teal dot).
- Center-left (all pages except Home): compact search trigger, 360px wide, 40px tall, 1px `--ink` border, placeholder `Hledat v projevech`, right side shows key hint `⌘K` (Mac) / `Ctrl K` (others) in `label` style inside a 1px `--rule` box. Clicking opens the ⌘K palette (§7.4).
- Right: nav `Hledat · Poslanci · Schůze · Jak to funguje` in `ui`, `--ink-2`. Active item: `--ink` + 2px `--ink` underline 18px below baseline (aligns to header bottom).
- Mobile: wordmark + search icon + menu icon; menu opens a full-screen sheet with the nav as `h2` links.

### 7.2 Search bar (primary, Home + Search page)

- Height 64px, full main-column width, `1px var(--ink)` border, `--paper` background.
- Left: Lucide `Search` 20px in `--ink-3`, 20px from edge.
- Input text: Sans 20px `--ink`; placeholder `--ink-4`, e.g. `Co zaznělo k automatické účasti v penzijním spoření?`
- Right: submit button inside the bar, 48px tall, `--ink` bg, `--paper` text, label `Hledat`, 4px inset from the bar edges.
- Focus: border stays `--ink`, add 2px focus ring outside.
- Below bar (Home only): `Zkuste:` + 3 example queries as links (§3.3 link style), wrapping.

### 7.3 Filter chips

- Height 32px, 1px `--ink` border, `--paper` background, `ui` text, padding `0 12px`, chevron 14px.
- Active filter: `--ink` background, `--paper` text, value shown inline (`Volební období: 10. (2025–)`), trailing `×` button (24px hit area).
- Order: `Volební období · Poslanec · Strana · Bod/tisk · Datum`.
- Dropdowns: popover with hard offset shadow (§5.4), list items 36px, checkbox squares 14px, search field at top for Poslanec/Strana lists.

### 7.4 ⌘K command palette

**Trigger:** `⌘K` / `Ctrl+K` anywhere; `/` when focus is not in an input; click on header search.
**Library:** `cmdk` (pacocoursey/cmdk), styled per this spec.

- Modal, width 640px (mobile: full width, top-anchored), max-height 480px, top offset 15vh.
- Backdrop: `--ink` at 40% opacity (light), `#000` at 60% (dark).
- Container: `--paper`, `1px var(--ink)`, hard offset shadow `8px 8px 0 var(--ink)`.
- Input row: 56px, Sans 18px, Lucide `Search` left, `Esc` key hint right.
- Groups (in this order, each with a `label`-style header):
  1. **Poslanci** — monogram 24px + name + party pill + region in `meta`
  2. **Body a tisky** — `tisk 285` in mono + short title (§10.3)
  3. **Schůze** — `34. schůze` + date range
  4. **Hledat v projevech** — always present last item: `Hledat „{query}“ v projevech →` (Enter submits full semantic search)
  5. **Akce** (no query typed): `Přepnout motiv`, `Jak to funguje`, `Nejnovější schůze`
  6. **Nedávné** (no query typed): last 5 searches/visits from `localStorage` (wrapped in try/catch)
- Items: 44px, padding 0 16px. Selected item: `--paper-3` background + 2px `--ink` left bar. Matched characters in item text: `--highlight` background.
- Matching: diacritics-insensitive and case-insensitive (`str.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase()`), so `jurecka` finds `Jurečka`.
- Footer row (32px, `--paper-2`): key hints `↑↓ vybrat · ↵ otevřít · esc zavřít` in `label` style.
- Max 6 items per group; "Zobrazit vše (n)" item at group end if more.

### 7.5 Catalog number

Every speech/quote object has a catalog number shown in `meta` style, like a museum accession number:

```
{volební období}/{schůze, 3 digits}/{strana, 4 digits}/{pořadí projevu na straně}
10/034/0644/2
```

- Shown top-left of every result object and quote card.
- Clicking copies a permalink to that exact speech paragraph (toast: `Odkaz zkopírován`).
- Used in URLs: `/projev/10-034-0644-2`.

### 7.6 Result object (quote in search results / profile lists)

Structure (top to bottom):

```
─────────────────────────────────────────────── 1px --rule-strong
10/034/0644/2                         [1]         ← meta | citation index (if in summary)
■ STAN  Jan Papajanovský                          ← swatch+party pill, name h3 (link to profile)

„No a třetí návrh, to je návrh, který je zdaleka   ← quote style, serif
nejambicióznější… zavádí ▓automatickou účast▓ …“   ← matches in --highlight

BOD 17 · Novela zákona o doplňkovém penzijním spoření   ← label key + body text --ink-2
6. 11. 2026 · 34. schůze · s. 644 · NEAUTORIZOVÁNO     ← meta --ink-3
                                      Otevřít v přepisu →
```

- Padding: 24px top, 32px bottom. No side padding, no background.
- Hover: background `--paper-2` across the full row, 150ms.
- Excerpt: max 4 lines (`line-clamp: 4`) in lists; ellipsis rendered as `…` inside the quotes.
- Status `NEAUTORIZOVÁNO`: `label` style, 1px dotted `--ink-3` underline, tooltip: `Stenografický záznam zatím neprošel autorizací řečníkem. Znění se může drobně změnit.` Authorized speeches show nothing (absence = default/normal).

### 7.7 Citation chip

- Inline in AI summary: `[3]` in mono 12px, `--ink-2`, 1px `--rule` border, padding `0 4px`, vertical-align baseline.
- Hover/focus (desktop): popover 360px wide showing speaker, party pill, the cited sentence(s) in `quote` serif 17px with the relevant span highlighted, catalog number, and `Otevřít v přepisu →`. Delay 150ms in, 100ms out.
- Click: scrolls to result `[3]` in the list and flashes its top rule `--highlight-strong` 3px for 1.2s.
- Mobile: tap opens the same content as a bottom sheet.

### 7.8 AI summary block

Must look clearly machine-made and distinct from verbatim text:

- Surface: `--paper-2`, **left border 4px `--ink`**, padding 24px 32px.
- Header row: `label` style `SHRNUTÍ · JAZYKOVÝ MODEL` left; right: `Podle 6 projevů · každá věta cituje zdroj` in `meta`.
- Body: **Sans** `body` 17px/1.6, `--ink` (never serif; serif is reserved for verbatim speech).
- Footer: hairline rule, then `Rozhodující je vždy znění přepisu.` + link `Jak shrnutí vznikají`.
- Loading state: 3 lines of dot-matrix shimmer (dots pulsing left to right, 1.2s loop; static under reduced motion) + `label` text `GENERUJI SHRNUTÍ`.
- If a sentence has no citation, it must not be rendered (enforced in code; the UI never shows uncited AI sentences).

### 7.9 Facet list (search aside)

- Section header: `label` style (`ŘAZENÍ`, `STRANA`, `ŘEČNÍK`, `DATUM`).
- Sort options: radio-style list, active item `--ink` text + 2px left bar; inactive `--ink-2`.
- Facet row: 32px tall; name left (party rows include swatch), count right in `meta`, and a **horizontal bar** behind/below the name: 2px tall, `--ink` at width = count / max count in that facet. Selected facet: name `--ink` 600 + bar 4px.
- Show top 8, then `Zobrazit další (n)`.
- Date facet: mini histogram of results by month, 48px tall, bars 1px gap, `--ink-4`, selected range `--ink`; drag to select range.

### 7.10 Stat tile (dot-matrix)

- Surface `--paper-2`, no border, padding 24px, min-height 152px.
- Value: dot-matrix digits (§8), dot size 4px, gap 2px → digit height 7×6−2 = 40px.
- Unit (optional): Sans `ui` `--ink-3`, baseline-aligned after the number (`slov`).
- Label below: `label` style, `--ink-3`.
- Comparison line (required for profile tiles): `meta` style, e.g. `medián poslanců: 31` — gives context so numbers aren't vanity metrics.
- Tile set on MP profile (replaces current vanity set):
  1. `PROJEVY` — count, comparison to median
  2. `JEDNACÍ DNY S PROJEVEM` — `26 / 48` (spoke / sitting days in term)
  3. `ÚČAST NA HLASOVÁNÍ` — `%` (derived from roll-call data)
  4. `NEJČASTĚJŠÍ TÉMA` — this one is text, not dot-matrix: topic name in `h3`

### 7.11 Session-day activity graph (GitHub-style)

The signature visualization. Rendered as **SVG**, dot-matrix style.

**Data unit:** one cell = one **calendar day**; only **jednací dny** (days the plenary sat) are visible as full dots.

**Layout (desktop, "calendar" mode):**
- Columns = ISO weeks of the selected term/year, left → right.
- Rows = Mon–Fri (5 rows). A 6th row (So/Ne) appears **only** if the period contains a weekend sitting.
- Cell pitch 12px (dot 8px + 4px gap). Dots are circles (the only round element in the system, intentional: dot-matrix).
- Month labels above in `label` style, aligned to the first week of each month. Weekday labels left: `Po`, `St`, `Pá` only.

**Cell states:**

| State | Rendering |
|---|---|
| No sitting that day | 2px dot, `--ink-4` at 40% opacity (keeps the grid visible, doesn't read as "absent") |
| Sitting, MP absent (didn't vote at all that day) | 8px **ring**, 1px `--ink-3` stroke, no fill |
| Sitting, present, didn't speak | 8px dot, `--ink-4` |
| Spoke — level 1 | 8px dot, `--ink` at 35% |
| Spoke — level 2 | 8px dot, `--ink` at 60% |
| Spoke — level 3 | 8px dot, `--ink` at 80% |
| Spoke — level 4 | 8px dot, `--ink` 100% |

- Levels use **global quartiles** of words-spoken-per-MP-per-sitting-day across all MPs in the term (q25/q50/q75), so every profile is on the same scale and comparable. Thresholds recomputed nightly.
- Attendance derivation: MP is "present" on a day if they cast any vote (incl. "zdržel se") that day in psp.cz roll-call data; "absent" if they are recorded as absent/omluven for all votes that day.
- Legend below right: `Méně` ○ · · · ● `Více` + separate legend items `○ nepřítomen` and `· nejednalo se`.
- Hover tooltip (hard-offset shadow style): `pátek 6. 11. 2026 · 34. schůze` / `3 projevy · 1 204 slov` / `Hlasoval(a): 41 z 44` / link `Projevy toho dne →`.
- Click: filters the profile's speech list to that day.
- Period selector above the graph: segmented control `10. období · 2026 · 2025` (square, 1px `--ink`, active `--ink` bg).

**Compact mode (< 768px):** only sitting days, in chronological order, wrapping rows of 20 cells, grouped by month with a `label` above each group. Same states.

**Accessibility:** the SVG has `role="img"` with an `aria-label` summary (`Vystoupil(a) ve 26 ze 48 jednacích dnů 10. volebního období.`), and a visually hidden `<table>` listing every sitting day with state and word count. Cells are not individually focusable; a "Zobrazit jako tabulku" toggle reveals the table.

### 7.12 MP profile header

- Back link `← Všichni poslanci` (link style).
- Row: monogram tile 96px · name in `display-l` · below: party pill + `Poslanec za Ústecký kraj` (`ui`, `--ink-2`) + `10. volební období, od 2025` (`meta`).
- Right side (desktop): `Originál na psp.cz ↗` link and `Sdílet` button (secondary).
- Below: stat tiles row (4 tiles, 24px gap) → activity graph (full width) → two-column: `Projevy` list (8 cols) + aside `Nejčastější témata` / `Nejčastější body` (4 cols).
- Aside list items: `tisk 285` in mono + short title (§10.3) + `6 projevů` in `meta`. Never show raw 200-character bill names.
- Phase 2 adds a `Řekl(a) vs. hlasoval(a)` section between graph and speeches.

### 7.13 Transcript page

- Sub-header bar (below site header, 48px, bottom hairline): `34. schůze · 6. 11. 2026 · od 12:50 · s. 644 · NEAUTORIZOVÁNO` in `meta` left; `Originál na psp.cz ↗` right.
- Eyebrow: `10. VOLEBNÍ OBDOBÍ · 34. SCHŮZE · BOD 17` in `label`.
- Title: bill short title in `display-l`; full official title below in `body` `--ink-3`, max 72ch, collapsed to 2 lines with `Celý název` toggle.
- Page pager: `← s. 643` · `pátek 6. listopadu 2026` · `s. 645 →`, between hairlines. Keyboard: `[` / `]` previous/next page.
- **Speech block:**
  - Speaker row: name `h3` (link) + party pill + role in `--ink-3` (e.g. `místopředseda PSP`, `řídí schůzi`).
  - Continuation note if applicable: `Pokračování projevu ze s. 642` in `meta`.
  - Text: `body-read` serif. Paragraphs 16px apart.
  - **Speaker rail:** 2px vertical line at the left edge of the speech block (−16px offset) in the speaker's normalized party color; presiding officer (`řídí schůzi`) gets `--rule` gray. This is the only place party color appears as a line.
  - Paragraph permalinks: on hover, a `#` link appears in the left margin (−40px), `--ink-3`. Click copies URL with `#p-{catalog}-{n}`; targeted paragraph gets `--highlight` background that fades to transparent over 2s.
  - Selecting text shows a mini toolbar (hard offset shadow): `Citovat` (copies „…“ + provenance line) · `Vytvořit kartu` (opens quote card composer) · Phase 2: `Anotace`.
  - Stenographer notes `(Potlesk.)` in italic `--ink-3`.
  - Separation between speeches: 1px `--rule`, 48px vertical spacing.
- **Aside (sticky, top 80px):** `← Zpět na výsledky` (only if referred from search, preserves query) · `NA TÉTO STRANĚ` list of speakers (name + party/role) · **Day minimap**: vertical strip 8px wide, height 320px, one segment per speech of the whole day, segment height ∝ word count, colored by speaker's party swatch; current page range outlined 1px `--ink`; click jumps.

### 7.14 Quote card (share/export)

The shareable object. Generated server-side with `@vercel/og` (Satori) at `/api/card/[catalog]`.

- Sizes: **1200×630** (OG/X/Facebook), **1080×1350** (Instagram), **1080×1920** (stories).
- Composition (1200×630):
  - Background `#F6F5F0`, outer padding 64px.
  - Top-left: catalog number `10/034/0644/2` in Plex Mono 22px `#6B6A64`.
  - Top-right: wordmark `Rozprava` + yellow square.
  - Center-left: quote in Source Serif 4, 44px/1.3, max 4 lines; if longer, the user must select a shorter span (composer enforces max 280 chars).
  - Highlighted span (if user chose one): `#FFE45E` background.
  - Bottom: 1px `#111` rule, then name (Sans 600 28px) + party swatch + abbr, and provenance line in mono 20px: `6. 11. 2026 · 34. schůze · s. 644 · neautorizováno`.
  - Bottom-right: short URL `rozprava.cz/p/10-034-0644-2` in mono 18px.
- Never crop a quote mid-sentence without `…`. Never allow editing the quote text in the composer (verbatim only, user can only choose the span).

### 7.15 Buttons

| Variant | Spec |
|---|---|
| Primary | `--ink` bg, `--paper` text, `ui`, height 40 (48 in search bar), padding `0 20px`, radius 0. Hover: bg `#2B2B28` (dark: `#FFFFFF`) |
| Secondary | transparent bg, 1px `--ink` border, `--ink` text. Hover: `--paper-2` bg |
| Ghost | no border, `--ink-2` text, underline on hover |
| Icon | 40×40, ghost style, Lucide 20px, `aria-label` required |

Disabled: `--ink-4` text, `--rule` border, `cursor: not-allowed`. Pressed: translate 1px 1px.

### 7.16 Tooltip & popover

- `--paper` bg, 1px `--ink`, hard offset shadow `4px 4px 0 var(--ink)` (tooltips) / `8px 8px 0` (popovers).
- Text `body` 14px, max-width 320px, padding 8px 12px.
- Open delay 300ms (tooltips), 150ms (citation popovers).

### 7.17 Toast

- Bottom-center, 40px tall, `--ink` bg, `--paper` text, `ui`, radius 0, auto-dismiss 2.5s. One at a time.

### 7.18 Pagination / load more

- Search results: "Načíst dalších 20" secondary button, full main width. No infinite scroll (keeps results citable and footer reachable).
- Result count line above list: **`6 projevů`** (Sans 600) + ` v 10. volebním období, seřazeno podle relevance` (`--ink-2`).

### 7.19 Empty, loading, error states

| State | Spec |
|---|---|
| No results | `h2` `Nic jsme nenašli.` + body `Zkuste obecnější dotaz nebo odeberte filtr.` + active filters listed as removable chips + 3 example queries |
| Loading results | 3 skeleton objects: top rule + gray bars (`--paper-3`) at quote line heights, no shimmer under reduced motion |
| Search error | `--danger` 1px left bar block: `Hledání se nepodařilo. Zkuste to znovu.` + retry button |
| Data gap (e.g. `Bod pořadu není v datech Sněmovny uveden`) | Show `BOD NEUVEDEN` in `label` style `--ink-3`. Never show a full apologetic sentence in place of a title |
| 404 | Dot-matrix `404` at dot size 8px, `h2` `Tahle strana v záznamu není.`, link home + search bar |

---

## 8. Dot-matrix system

### 8.1 Usage rules

- **Allowed:** stat tile values, the activity graph, live session board (Phase 2), 404, loading shimmer.
- **Forbidden:** body text, headings, buttons, anything with letters (diacritics would break). Digits and `space . , % –` only.
- Max one dot-matrix number cluster per viewport row.

### 8.2 Glyph grid

5 columns × 7 rows. Each glyph rendered as SVG circles. Glyph advance = 5 cells + 1 cell gap. Thousands separator = 2-cell blank (renders `43 897` correctly).

`1` = dot on, `0` = dot off (off dots are rendered in `--ink-4` at 25% opacity to show the matrix, like an LED panel).

```
0: 01110 10001 10011 10101 11001 10001 01110
1: 00100 01100 00100 00100 00100 00100 01110
2: 01110 10001 00001 00010 00100 01000 11111
3: 11111 00010 00100 00010 00001 10001 01110
4: 00010 00110 01010 10010 11111 00010 00010
5: 11111 10000 11110 00001 00001 10001 01110
6: 00110 01000 10000 11110 10001 10001 01110
7: 11111 00001 00010 00100 01000 01000 01000
8: 01110 10001 10001 01110 10001 10001 01110
9: 01110 10001 10001 01111 00001 00010 01100
,: 00000 00000 00000 00000 00110 00100 01000
.: 00000 00000 00000 00000 00000 01100 01100
%: 11000 11001 00010 00100 01000 10011 00011
–: 00000 00000 00000 11111 00000 00000 00000
```

Sizes:

| Token | Dot Ø | Gap | Digit height |
|---|---|---|---|
| `dm-s` | 3px | 1px | 27px |
| `dm-m` | 4px | 2px | 40px |
| `dm-l` | 6px | 2px | 54px |
| `dm-xl` | 8px | 3px | 74px |

### 8.3 Component API

```tsx
<DotNumber value={43897} size="m" locale="cs-CZ" ariaLabel="43 897 slov" animate />
```

- Renders `<svg role="img" aria-label=…>`; real number also in a visually hidden `<span>` for copy/paste and screen readers.
- `animate`: on first viewport entry, dots switch on column by column, left → right, 400ms total, `steps()` easing. Disabled under `prefers-reduced-motion`.

---

## 9. Motion

- Durations: 100ms (hover color), 150ms (popover in), 200ms (drawer/palette in), 400ms (dot-matrix reveal).
- Easing: `cubic-bezier(0.2, 0, 0, 1)` for entrances; `linear` for color.
- ⌘K palette: fade + 4px upward translate, 200ms. Exit 120ms fade.
- No parallax, no scroll-jacking, no bouncy springs.
- `prefers-reduced-motion: reduce` disables all transforms and the dot reveal; keeps instant color changes.

---

## 10. Content & data presentation

### 10.1 Voice

- Neutral, exact, short. Verbs over adjectives. No exclamation marks. No "skvělé", "bohužel", "šokující".
- Address the user with formal plural imperative: `Hledejte`, `Zkuste`.
- Never characterize a speech (no "ostrý", "kontroverzní") outside of a sourced Phase 2 annotation.

### 10.2 Glossary (use these terms exactly)

| Term | Meaning | Don't use |
|---|---|---|
| projev | one speaker's continuous contribution | příspěvek, výstup |
| schůze | numbered plenary meeting | zasedání (except in official titles) |
| jednací den | a day the plenary sat | den jednání |
| bod | agenda item | položka |
| tisk / sněmovní tisk | numbered bill document | dokument |
| přepis / stenozáznam | transcript | záznam (ambiguous) |
| neautorizováno | not yet authorized by speaker | neověřeno |
| shrnutí | AI summary | AI odpověď |

### 10.3 Bill short titles

Raw psp.cz titles are too long. Generate a short title (max 60 chars) by:
1. Manual override table `lib/billTitles.ts` keyed by tisk number (wins if present).
2. Otherwise strip patterns: `^Vládní návrh zákona, kterým se mění zákon č\. \d+/\d+ Sb\., o ` → `Novela zákona o `; `^Návrh poslanců .+? na vydání zákona, kterým se mění ` → `Poslanecký návrh: změna `; remove `, ve znění pozdějších předpisů` and trailing `/sněmovní tisk \d+/ - (prvé|druhé|třetí) čtení`.
3. Reading stage as separate chip: `1. čtení`, `2. čtení`, `3. čtení` in `label` style.
4. Full official title always available on hover/expand.

### 10.4 Neutrality rules (enforced in code review)

1. Homepage "Z posledního jednání" featured quote is chosen **randomly** among speeches of the last sitting day with ≥ 60 words, re-rolled every hour, with visible label `NÁHODNÝ VÝBĚR Z POSLEDNÍHO JEDNACÍHO DNE`.
2. Party lists and facets sort by **count**, ties alphabetical. Never by party size or seat count.
3. All parties use normalized swatches (§3.4).
4. MP lists default sort: alphabetical by surname.
5. AI summary prompt instructs: attribute every claim, no evaluative words. UI drops uncited sentences.

---

## 11. Pages

### 11.1 Home `/`

1. Header (no compact search; the hero has the full one).
2. Hero (12 cols): eyebrow `STENOZÁZNAMY POSLANECKÉ SNĚMOVNY · 2021–2026` (label) → `display-xl` headline `Co ve Sněmovně opravdu zaznělo` (max 2 lines) → lede `body` 20px `--ink-2`, max 56ch → search bar (8 cols) → filter chips → `Zkuste:` examples.
   - **Right 4 cols (desktop):** live-ish panel "Poslední jednací den": date in `label`, dot-matrix count of speeches that day (`dm-l`) + label `PROJEVŮ`, dot-matrix word count (`dm-m`), and a mini 1-row strip of the last 20 sitting days (activity graph compact style, aggregate for the whole chamber). This fills the empty right half.
3. Section `Z posledního jednání` (rule-strong on top): left 4 cols = date, schůze, bod, short title, `Celý den v přepisu →`; right 8 cols = one featured result object (§7.6) with `quote-l` text and the random-pick label (§10.4).
4. Section `Procházet`: Cooper Hewitt-style browse entry points, 4 columns of large text links with counts in `meta`: `Podle poslance (200)` · `Podle strany (7)` · `Podle tisku (…)` · `Podle schůze (34)`.
5. Footer.

### 11.2 Search `/hledat?q=…`

Header with compact search → search bar (8 cols) + chips → count line → AI summary (§7.8) → result objects → load more. Aside (4 cols, sticky): Řazení, Strana, Řečník, Datum histogram. URL holds all state (`q`, `obdobi`, `strana`, `poslanec`, `od`, `do`, `razeni`) so results are shareable.

### 11.3 Transcript `/schuze/[obdobi]/[schuze]/[strana]`

As §7.13.

### 11.4 MP profile `/poslanec/[slug]`

As §7.12. In-profile search field (`Hledat v projevech poslance`), full width of main column, 48px, same style as search bar without the button.

### 11.5 MP index `/poslanci`

- Filter row: party chips (multi-select), region select, search field.
- Grid of MP rows (not cards): monogram 32 · name · party pill · region · mini activity strip (last 20 sitting days, `dm-s` dots) · `projevy` count right-aligned in mono. Rows 56px, hairline separated. Sortable columns: Jméno, Strana, Kraj, Projevy, Účast.

### 11.6 Session index `/schuze` (new)

Table-like list of schůze: number (mono, large), date range, number of sitting days, top 3 bodies by speech count, total words. Each row expands to show sitting days as dot strip.

### 11.7 How it works `/jak-to-funguje`

Long-form page, `body-read` serif on 68ch column. Sections: Zdroje dat (psp.cz, update cadence), Jak funguje vyhledávání, Jak vznikají shrnutí, Co znamená „neautorizováno“, Jak počítáme aktivitu a účast (exact formulas incl. quartile thresholds), Kontakt a opravy. Each section anchor-linked; left sticky TOC in `label` style.

### 11.8 Footer

Top rule-strong, 3 columns: wordmark + one-line description · links (Hledat, Poslanci, Schůze, Jak to funguje, API/Data) · `Data: Poslanecká sněmovna PČR (psp.cz). Aktualizováno {datum, čas}.` in `meta`. Bottom row: theme toggle (segmented `Světlý · Tmavý · Systém`).

---

## 12. Phase 2 (designed now, built later)

### 12.1 Annotations (Genius model)

- Annotated span in transcript: `--highlight` background at 45% opacity + 2px `--highlight-strong` underline.
- Click opens annotation in the aside (desktop) / bottom sheet (mobile): `label` type (`KONTEXT`, `DATA`, `HLASOVÁNÍ`), annotation body in Sans `body`, sources as numbered list with links, author/editor + date in `meta`, `Navrhnout opravu` link.
- Annotations never contain verdict words in the span highlight itself; the type label carries meaning.

### 12.2 Said vs. voted

On profile and annotations: two-column block. Left `ŘEKL(A)`: quote object (serif). Right `HLASOVAL(A)`: vote record (`tisk 285 · 3. čtení · PRO / PROTI / ZDRŽEL SE / NEPŘÍTOMEN` as square badge with 1px `--ink` border; text only, no colors) + link to psp.cz vote. A neutral connector line between them, no judgment label.

### 12.3 Live session board

When the Sněmovna is sitting: Home right panel turns into a departure-board style "Právě mluví" panel: speaker name, party pill, bod, elapsed time in dot-matrix (`dm-m`), updating every 60s from transcript feed (or psp.cz live data if available).

---

## 13. Accessibility

- WCAG 2.2 AA minimum. All text tokens checked against `--paper` and `--paper-2`.
- Focus: visible 2px `--focus` ring + 2px offset on every interactive element; never `outline: none` without replacement.
- All keyboard shortcuts (`⌘K`, `/`, `[`, `]`, `Esc`) listed in `Jak to funguje` and in the palette footer; none hijack typing inside inputs.
- `lang="cs"` on `<html>`.
- Party swatches are never the only carrier of meaning (abbreviation always shown).
- Activity graph has table alternative (§7.11). Dot numbers have hidden text (§8.3).
- Hit targets ≥ 40×40 px (24px minimum for inline `×` with surrounding padding).
- Highlight color only as background with `#111` text (contrast > 15:1).

---

## 14. Implementation tokens

### 14.1 CSS variables (globals.css)

```css
:root {
  --paper: #F6F5F0;
  --paper-2: #ECEAE2;
  --paper-3: #E2DFD5;
  --ink: #111111;
  --ink-2: #3D3C38;
  --ink-3: #6B6A64;
  --ink-4: #A3A198;
  --rule: #D3D0C6;
  --rule-strong: #111111;
  --highlight: #FFE45E;
  --highlight-strong: #E8C400;
  --focus: #111111;
  --danger: #B3261E;

  --shadow-pop: 8px 8px 0 0 var(--ink);
  --shadow-tip: 4px 4px 0 0 var(--ink);
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
  --measure-read: 68ch;
  --header-h: 64px;
}

[data-theme="dark"] {
  --paper: #0F0F0E;
  --paper-2: #1A1A18;
  --paper-3: #24241F;
  --ink: #EDEBE4;
  --ink-2: #C4C2BA;
  --ink-3: #8E8C84;
  --ink-4: #56554F;
  --rule: #2E2D29;
  --rule-strong: #EDEBE4;
  --focus: #EDEBE4;
  --danger: #F2B8B5;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #0F0F0E; --paper-2: #1A1A18; --paper-3: #24241F;
    --ink: #EDEBE4; --ink-2: #C4C2BA; --ink-3: #8E8C84; --ink-4: #56554F;
    --rule: #2E2D29; --rule-strong: #EDEBE4; --focus: #EDEBE4; --danger: #F2B8B5;
  }
}

* { border-radius: 0 !important; }
mark { background: var(--highlight); color: #111111; padding: 0 1px; }
::selection { background: var(--highlight); color: #111111; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
```

> Exception to `border-radius: 0`: dot-matrix circles are SVG `<circle>` elements and are unaffected.

### 14.2 Tailwind v4 theme

```css
@theme inline {
  --color-paper: var(--paper);
  --color-paper-2: var(--paper-2);
  --color-paper-3: var(--paper-3);
  --color-ink: var(--ink);
  --color-ink-2: var(--ink-2);
  --color-ink-3: var(--ink-3);
  --color-ink-4: var(--ink-4);
  --color-rule: var(--rule);
  --color-rule-strong: var(--rule-strong);
  --color-highlight: var(--highlight);
  --color-highlight-strong: var(--highlight-strong);
  --color-danger: var(--danger);

  --font-sans: var(--font-cooper), "Schibsted Grotesk", system-ui, sans-serif;
  --font-serif: var(--font-source-serif), Georgia, serif;
  --font-mono: var(--font-plex-mono), ui-monospace, monospace;

  --radius: 0px;
  --shadow-pop: 8px 8px 0 0 var(--ink);
  --shadow-tip: 4px 4px 0 0 var(--ink);

  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
}
```

### 14.3 Component inventory (build order)

1. Tokens + fonts + diacritics test page (`/_design`)
2. `PartyPill`, `Swatch`, `CatalogNumber`, `AuthStatus`
3. `SearchBar`, `FilterChip`, `CommandPalette` (cmdk)
4. `ResultObject`, `CitationChip`, `AISummary`, `FacetList`, `DateHistogram`
5. `DotNumber`, `StatTile`, `ActivityGraph` (+ compact mode, table fallback)
6. `TranscriptSpeech`, `SpeakerRail`, `DayMinimap`, `SelectionToolbar`
7. `QuoteCard` OG route + composer
8. Pages: Search → Transcript → MP profile → Home → MP index → Session index → Jak to funguje
9. Phase 2: `Annotation`, `SaidVsVoted`, `LiveBoard`

A `/_design` route (dev-only) renders every component in every state, light and dark, for review.

---

## 15. Open decisions / TODO

- [ ] **Positioning:** confirm Phase 1 copy avoids "fact-check" wording (§1).
- [ ] **Cooper Hewitt font:** run diacritics test (§4.5); if any glyph fails, switch primary sans to Schibsted Grotesk.
- [ ] **Party colors:** collect official hexes from brand manuals, apply normalization (§3.4), check collisions.
- [ ] **Attendance data:** confirm psp.cz roll-call export gives per-MP absent/omluven per vote; otherwise drop the "absent" ring state and the `ÚČAST` tile.
- [ ] **Topic tagging** for `NEJČASTĚJŠÍ TÉMA`: define taxonomy (≈ 15 topics) and method.
- [ ] **Domain** for short URLs on quote cards.
- [ ] **Bill title overrides** table: seed with the 30 most-discussed tisky of the 10th term.

---

## 16. What changed vs. current build (migration checklist)

- [ ] Remove teal accent everywhere → ink primary buttons, yellow highlight for matches
- [ ] Rounded pills/cards → radius 0, rule-separated objects
- [ ] Inter/serif/mono default trio → Cooper Hewitt (or Schibsted) / Source Serif 4 / IBM Plex Mono
- [ ] Gray identical party badges → swatch + mono pill
- [ ] Empty hero right half → "Poslední jednací den" dot-matrix panel
- [ ] Vanity stat tiles → dot-matrix tiles with median comparison + attendance
- [ ] Add activity graph to MP profile
- [ ] Truncated raw bill names → tisk number + short title
- [ ] AI summary: serif-free, left ink bar, explicit "jazykový model" label, hover-preview citations
- [ ] Facet counts → counts + bars
- [ ] Featured quote → random pick with visible label
- [ ] Add ⌘K palette, catalog numbers, paragraph permalinks, quote cards
- [ ] Transcript: speaker rail, day minimap, selection toolbar
- [ ] Replace `Bod pořadu není v datech Sněmovny uveden` sentence with `BOD NEUVEDEN` label


## 17. Implementation decisions — static preview (2026-11-17)

The existing FastAPI/Jinja project remains the implementation target. The Next.js,
cmdk and Satori examples above specify behavior and composition; they do not require
a React migration. The preview uses local fonts, Jinja macros, plain CSS and vanilla
JavaScript. The app routes map to generated HTML files; `/_design/` is also available
as a local development review route.

- **Preview search:** six stored source speeches, filtered locally by text, party,
  speaker, term, bill and dates. State is stored in query parameters. Live semantic
  retrieval and generated summaries await the backend. Summary sentences without
  valid source references are removed before rendering.
- **Quote export:** the preview exports PNG through Canvas using the same local
  fonts and all three dimensions. Only an immutable stored source and numeric span
  offsets are accepted; no editable quotation field. Both the 280-character maximum
  and line capacity are checked. Until the public domain is chosen, attribution uses
  `psp.cz` and the catalogue number; copying uses the real source URL.
- **Activity:** cached roll-call data supports attendance. Word counts are incomplete
  across the archive, so the preview uses global speech-count quartiles (1/2/3),
  explicitly labeled in methodology. Production should switch to the word-count
  definition in §7.11 when full ingestion is available. `Nejčastější bod` is shown
  until the topic taxonomy is defined.
- **Identity colours:** all party swatches remain neutral until official colour
  sources have been verified; normalization and collision hatching are implemented
  and demonstrated on non-party sample colours in `/_design/`.
- **Static sampling:** the home quote is sampled from the latest cached day's
  eligible speeches when the fixture is rebuilt, with an hourly seed. The preview
  labels it as a saved sample; hourly live rotation needs the production job.
- **Responsive excerpts:** a four-line quote is cut at a word boundary with an
  explicit `…` before the closing quote. The stored source and citation never change.
  Without JavaScript, the complete server-rendered excerpt remains readable.
- **Fonts:** bundled regular and bold font coverage passes the Czech glyph fixture
  in §4.5. Cooper Hewitt remains primary, with Schibsted Grotesk as fallback.
