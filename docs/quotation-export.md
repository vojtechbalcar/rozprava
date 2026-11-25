---
type: implementation
updated: 2026-11-19
status: current
---

# Live quick search and quotation export

Related: [[functional-app-plan]], [[archive-views]], [[functional-app-design]], [[design-preview]]

## Quick search

`/api/palette?q=…` performs bounded PostgreSQL queries for MPs, term-qualified
bills and sittings. Names and titles ignore accents; SQL wildcards remain literal.
An MP links to the latest term in which they have a mandate, including previous-only
members. The palette cancels superseded requests, ignores late responses, preserves
keyboard navigation/focus restoration and keeps a normal speech-search link on
errors. The bill filter uses the same API and retains the other search parameters.

## Quotation identity

`/karta?source=paragraph-{catalog}-{paragraph}&verze={speech revision}&start=…&end=…`
loads exactly one stored paragraph. Offsets count Unicode code points in both
Python and JavaScript; this also handles characters outside the BMP. The server
validates the catalogue/revision/paragraph relationship, both boundaries, nonempty
text, the 280-character maximum and one of the three supported image sizes.
Caller-supplied quotation or speaker text is never used.

Selections stay contiguous and trim surrounding whitespace. Ellipses mark omitted
text at either boundary, including earlier/later paragraphs and incomplete speech
starts. Highlighting can only match a substring of the selection. Copied card URLs
keep version, selection, format and highlighting; the source link pins its page
revision. Selecting another span updates the URL. The alternative of copying only
the changing PSP page was rejected because it loses the selection/version.

Result cards and transcript selections link into this workflow. The server
`/api/quote` revalidates a selection before copying or exporting. Canvas exports
1200×630, 1080×1350 and 1080×1920 PNGs using local fonts. Failed font loads block
export; oversized text, missing source validation, clipboard rejection and image
creation errors have visible messages. The static preview remains functional.

## Verification

173 Python tests and lint/format/type/token/JS syntax checks pass. Tests cover invalid
and mismatched identities, all boundary cases, forged text, markup escaping, Unicode,
empty states, formats and the same quote after its source speech is retired.

T3 initially verified live palette results. Its host then disconnected and
`preview_open` explicitly reported unavailable, so an isolated headless Chromium
checked the remaining interactions. Verified keyboard/focus behavior, delayed and
failed palette responses, bill lookup, result/reader quotation entry, reselection,
clipboard round-trip, mobile overflow and all PNG dimensions. Font/validation
failures were also exercised. Temporary artifacts: `/tmp/rozprava-browser-check/`.
