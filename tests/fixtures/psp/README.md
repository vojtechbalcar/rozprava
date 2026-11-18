# psp.cz source fixtures

Small, real samples of the Chamber of Deputies' transcript pages and open-data
tables, used by the offline parser and import tests. Tests never fetch from psp.cz.
Source: Poslanecká sněmovna Parlamentu ČR, www.psp.cz (official works; the
open-data licence asks for the source and processing date to be credited).

## Transcript pages (`pages/`)

Fetched on 18 November 2026 through `rozprava.ingest.fetch` (one request per
second, identified User-Agent). Each file keeps the original Windows-1250 bytes
of the transcript body, from `<!-- sx -->` to `<!-- sy -->` inclusive, inside a
minimal HTML shell with the original charset declaration. The rest of the page
(site header, menus, scripts) is dropped. SHA-256 is of the full original response.

| File | Source | Retrieved | SHA-256 of original |
| --- | --- | --- | --- |
| `2025ps-s034642.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034642.htm> | 2026-11-18 07:31 UTC | `1281f89b3ade2be3…` |
| `2025ps-s034643.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034643.htm> | 2026-11-18 07:31 UTC | `1c2886b3b1ad04bd…` |
| `2025ps-s034644.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034644.htm> | 2026-11-18 07:31 UTC | `b474f3dbbec12f77…` |
| `2025ps-s034648.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034648.htm> | 2026-11-18 07:31 UTC | `64937411580b6b2f…` |
| `2025ps-s001002.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/001schuz/s001002.htm> | 2026-11-18 07:31 UTC | `161217bfe2f0ec3d…` |
| `2025ps-s001003.htm` | <https://www.psp.cz/eknih/2025ps/stenprot/001schuz/s001003.htm> | 2026-11-18 07:31 UTC | `d3a2582dfcc88d31…` |
| `2021ps-s050071.htm` | <https://www.psp.cz/eknih/2021ps/stenprot/050schuz/s050071.htm> | 2026-11-18 07:31 UTC | `1082d732674bb0aa…` |
| `2021ps-s050072.htm` | <https://www.psp.cz/eknih/2021ps/stenprot/050schuz/s050072.htm> | 2026-11-18 07:31 UTC | `702884cd1819f613…` |
| `2021ps-s112001.htm` | <https://www.psp.cz/eknih/2021ps/stenprot/112schuz/s112001.htm> | 2026-11-18 07:31 UTC | `217144f55072f22a…` |

What each sample covers:

- `2025ps-s034642` … `s034644`: Olga Richterová's speech starts on 642, fills all
  of 643 (no speech label at all) and ends on 644. Draft status line
  ("Neprošlo jazykovou korekturou, neautorizováno!"). 644 has the Papajanovský
  speech used in the design preview.
- `2025ps-s034648`: a minister (Alena Schillerová) whose label links to
  vlada.gov.cz, not a psp.cz person ID.
- `2025ps-s001002`, `s001003`: the constituent sitting; an agenda heading in the
  middle of the chair's speech, the oath list continuing across pages, and a
  page (003) with no rows in psp.cz's speech index (`rec`).
- `2021ps-s050071`, `s050072`: stale index attribution. Minister Pavel Blažek's
  speech starts on 071 with an unanchored label (no `id="rN"`) after an agenda
  heading, continues on 072, and he replies again on 072 without an anchor.
  `rec` counts those speeches, so its anchor numbers on 072 are shifted by one
  against the page (rec r2 = Blažek, page r2 = Skopeček).
- `2021ps-s112001`: first page of a sitting, "Neautorizováno!" status, opening
  note "(Schůze zahájena v 14.00 hodin.)".

## Open-data rows (`opendata/`)

Rows copied byte for byte (Windows-1250, pipe-separated UNL) from the official
dumps downloaded on 18 November 2026 from
<https://www.psp.cz/eknih/cdrom/opendata/> (`poslanci.zip`, `schuze.zip`,
`steno.zip`, `tisky.zip`; all built `2026-11-18 01:54`). `extract_opendata.py`
selected them: `steno`/`rec`/`steno_bod` rows for pages around the samples, the
people they mention plus namesakes (four people named Jan Černý) and Pavel
Blažek, Ivo Vondrák (who left the ANO club for the non-attached on 21 February
2023, 14.00), their mandates and club memberships in terms 173 and 174, the terms,
clubs and regions, the four sittings, and their agenda items and bills.

Column layouts: <https://www.psp.cz/sqw/hp.sqw?k=1301> (people),
<https://www.psp.cz/sqw/hp.sqw?k=1308> (sittings),
<https://www.psp.cz/sqw/hp.sqw?k=1310> (transcripts).

To refresh, download the dumps, unzip each into its own folder and run:

```sh
uv run python tests/fixtures/psp/extract_opendata.py DUMPS_DIR tests/fixtures/psp/opendata tests/fixtures/psp/pages
```
