---
type: research
updated: 2026-11-17
status: current
---

# Feasibility research

Related: [[project-choice]], [[stack-decision]], [[design-direction]]

Research done on 12 November 2026, before any app code. Everything below comes from pages and files opened that day. Throwaway scripts and downloaded samples are in `scratch/` (gitignored, so they exist only on the machine that ran this). Anything I couldn't confirm is marked **unverified**.

## Verdict: build, with a reduced scope

**Build it, but start with the 2021– transcripts (9th and 10th terms) loaded straight from psp.cz.** Don't start with the whole archive or with ParlaMint.

Why:

- **The data is better than expected.** psp.cz publishes every plenary transcript as HTML. Each speech has an anchor (`id="rN"`), and a daily open-data table (`rec`) maps every anchor to a stable person ID (`id_osoba`). That includes ministers, senators and other non-MPs, and the same ID is used in the MP, party and term tables. Transcripts appear the same day. Republishing is legally low-risk: Chamber publications are official works with no copyright.
- **The gap is real but smaller than it looks.** [Hlídač státu](https://www.hlidacstatu.cz/data/Index/stenozaznamy-psp) already offers speech-level keyword search across 480 659 speeches, with person filters, daily updates and email alerts. Rozprava's case rests on three things: search by meaning, summaries where every claim is cited, and an MP-centred reading interface. Those things don't exist for the Czech parliament today. Against Hlídač státu, though, Rozprava has to be clearly better at "what did X say about Y", not just prettier.
- **A full archive is affordable but not worth it on day one.** Embedding everything since 1993 costs about $4–37 one-off, depending on the model. The reasons to wait are elsewhere: older terms use different markup, 1996–98 has no speaker table, and checking retrieval quality on a small set first is cheaper.

## 1. Data availability

### Where transcripts live

| What | Where | Notes |
|---|---|---|
| Per-term index | `https://www.psp.cz/eknih/{YYYY}ps/stenprot/index.htm` (e.g. [2025ps](https://www.psp.cz/eknih/2025ps/stenprot/index.htm)) | Lists sittings and sitting days |
| Day index | `…/{NNN}schuz/{N}-{day}.html` (e.g. [34-12](https://www.psp.cz/eknih/2025ps/stenprot/034schuz/34-12.html)) | Lists every speaker with a link to `sNNNTTT.htm#rN` and the agenda items |
| Transcript page ("turn") | `…/{NNN}schuz/s{NNN}{TTT}.htm` (e.g. [s034650](https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034650.htm)) | About 10 minutes of debate per page ([open-data docs](https://www.psp.cz/sqw/hp.sqw?k=1310)) |
| Per-sitting ZIP | `…/stenprot/zip/{NNN}schuz.zip` ([index](https://www.psp.cz/eknih/2025ps/stenprot/zip/index.htm)) | Patchy, see below |
| Open data (metadata only) | [psp.cz open data page](https://www.psp.cz/sqw/hp.sqw?k=1300): `steno.zip`, `poslanci.zip`, `schuze.zip`, … | Pipe-separated UNL in windows-1250, full dump rebuilt daily (`Last-Modified: Thu, 12 Nov 2026 00:54:41 GMT`) |

There is **no bulk export of the transcript text** in the open data. `steno.zip` (2.4 MB) holds only the indexes: `steno` (one row per page: term, sitting, turn, date, start/end minute), `steno_bod` (agenda item per page) and `rec` (one row per speech: page, `id_osoba`, anchor number, agenda item, and role: chair or speaker). The text has to come from the HTML pages.

**ZIPs aren't reliable.** In a polite HEAD sweep, all sampled ZIPs existed for 2006, 2013 and 2021. For 2025ps only sittings 1–23 existed; 24–35 returned 404 even though they're linked. For 2002ps and older, every sampled ZIP returned 404. ZIP markup also differs from the live pages: the 2025ps ZIP has no `rN` anchors at all, so it can't be joined to `rec` (checked in `scratch/dl/steno-html/unz-2025ps_stenprot_zip_005schuz/`). **Crawl the live HTML pages.**

### Coverage by term

From `steno.unl` and `rec.unl` (12 Nov 2026 dump), computed by `scratch/scripts/steno_stats.py`:

| Term | Years | Sittings | Pages | Speech rows in `rec` | Distinct speakers | Non-MP speakers |
|---|---|---|---|---|---|---|
| PSP1 | 1993–96 | 43 | 1 149 | 23 542 | 211 | 13 |
| PSP2 | 1996–98 | 26 | 3 421 | **0** | – | – |
| PSP3 | 1998–2002 | 51 | 10 021 | 68 956 | 243 | 38 |
| PSP4 | 2002–06 | 56 | 10 139 | 66 634 | 321 | 91 |
| PSP5 | 2006–10 | 79 | 7 546 | 44 299 | 294 | 80 |
| PSP6 | 2010–13 | 59 | 6 508 | 38 885 | 287 | 78 |
| PSP7 | 2013–17 | 61 | 10 461 | 77 304 | 290 | 80 |
| PSP8 | 2017–21 | 119 | 11 961 | 83 110 | 308 | 89 |
| PSP9 | 2021–25 | 147 | 13 926 | 72 057 | 242 | 31 |
| PSP10 | 2025– | 35 | 4 548 | 20 710 | 212 | 15 |

- Every term since the Chamber was created (1993) has digital HTML transcripts. Pages from 1993, 1996 and 2002 all loaded and use the same `id="rN"` anchors ([1993 sample](https://www.psp.cz/eknih/1993ps/stenprot/010schuz/s010005.htm), [1996 sample](https://www.psp.cz/eknih/1996ps/stenprot/010schuz/s010005.htm), [2002 sample](https://www.psp.cz/eknih/2002ps/stenprot/006schuz/s006010.htm)).
- **1996–98 has no `rec` rows**, so speakers there must be matched by name. The 1993 and 1996 pages also don't link speakers to a person ID.
- The chair-vs-speaker role (`rec.druh`) is filled in only from 2013. Before that, every row is "unknown". Since 2013 roughly half the rows are the chair (e.g. PSP9: 35 585 speaker rows, 36 472 chair rows).

### Format and encoding

- HTML, `charset=windows-1250` on every term (checked response headers and the `<meta>` tag).
- A speech starts with `<b><a href="/sqw/detail.sqw?id={id_osoba}" id="rN">{role} {name}</a></b>: text`, followed by plain `<p>` paragraphs. Markup varies by era: uppercase tags and a different `<b>` nesting in 2002, and no `href` in 1993/1996.
- **Ministers who aren't MPs link to `vlada.gov.cz`, not a psp.cz ID.** Example: Schillerová on [s034648](https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034648.htm). `rec` still resolves them: `aname=2 → id_osoba 6545`.
- A speech that runs past a 10-minute page continues at the top of the next page with no header. The parser has to stitch pages. 15–20% of speeches span pages in the samples.
- Every page carries a revision status line. See "Publication and revisions" below.

### Parse test

`scratch/scripts/parse_sitting.py` splits pages into speeches, stitches continuations, and joins each `(page, rN)` to `rec`. It also checks that the surname in the HTML label matches the surname of the `rec` person.

| Sample | Pages | Speeches | Joined to `rec` | Wrong person in `rec` |
|---|---|---|---|---|
| 2021ps sitting 50 (ZIP) | 161 | 971 | 971 (100 %) | **27 (2.8 %)** |
| 2025ps sitting 35 (live, 14 Oct 2026) | 31 | 95 | 95 (100 %) | 0 |
| 2025ps sitting 34, pages 600–651 (live, 5–6 Nov 2026) | 52 | 266 | 249 (93.6 %) | 0 |

- **`rec` can be stale.** In 2021/50, `rec` still listed a speech by Pavel Blažek that editors later removed from the text, so every later anchor on that page was shifted by one. The live page agrees with the edited text ([s050072](https://www.psp.cz/eknih/2021ps/stenprot/050schuz/s050072.htm)). Ingest has to treat the HTML label as the source of truth, take `id_osoba` from `rec` only when the surname matches, and otherwise resolve by name, role and date against `osoby`/`zarazeni`.
- **`rec` lags the newest pages, sometimes by days.** On 12 Nov, page 651 (the last page from 6 Nov) wasn't in `rec` yet. On 15 Nov, the 36th sitting's day of 13 Nov had all 26 pages in `steno` and online, but **no `rec` rows at all** (dump `Last-Modified: Sun, 15 Nov 2026 00:54:41 GMT`, checked in `scratch/dl/recheck-1115/`). New sittings therefore have to be attributed from the page labels first and linked to `rec` IDs when they arrive.
- Non-MP speakers do have IDs. Since 2013, 170 non-MP speakers appear in `rec`. 108 of them never held a government post: mostly senators (Vystrčil, Goláň, Seitlová), the ČNB governor (Singer) and the ombudsman (Šabatová).
- **A page can open with the tail of a speech that began several pages earlier.** [s034644](https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034644.htm) opens with the end of Olga Richterová's speech, which began on s034642; s034643 has no speaker label at all. Stitching has to walk back over unlabelled pages. Found on 17 Nov while building the [[design-preview]].
- **`rec.id_bod` can be 0 inside a debate.** Two of Jan Papajanovský's speeches have `id_bod` 0 and no `steno_bod` rows: page 16 of 13 Oct (a proposal to change the agenda) and page 243 of 21 Oct (during the budget debate). The UI says the agenda item is missing rather than guessing one.
- **`osoby.pohlavi` is inconsistent.** Men are `M` (5 851 rows). Women are `Ž` in most rows (1 105) but `Z` in newer ones (83, e.g. Ester Weimerová, id 7061), and 7 rows hold a mis-encoded byte. Treat anything but `M` as female; Czech titles depend on it (poslanec/poslankyně).
- Every person ID matches the psp.cz people tables in `poslanci.zip` ([schema](https://www.psp.cz/sqw/hp.sqw?k=1301)), which link people to parties, clubs and terms through `zarazeni` and `organy`.

### Publication and revisions

- **Same day.** A [Wayback Machine snapshot](https://web.archive.org/web/20261022154306/https://www.psp.cz/eknih/2025ps/stenprot/index.htm) taken on 22 Oct 2026 at 15:43 UTC already lists the 22 Oct sitting day. Rechecked on 15 Nov: the 36th sitting's day of 13 Nov (closed at 13.18) was complete on the [index](https://www.psp.cz/eknih/2025ps/stenprot/index.htm) and [day page](https://www.psp.cz/eknih/2025ps/stenprot/036schuz/36-1.html), still as a raw draft. So a full day is online within two days at most; the exact lag in hours is **unverified** (the Wayback Machine was offline on 15 Nov, so I couldn't see when it first appeared).
- **Three stages**, shown in a `<p class="status …">` line:
  1. `Neprošlo jazykovou korekturou, neautorizováno!`: raw first version. The 6 Nov pages contain errors such as "chcisi chci" and "plus(?)".
  2. `Neautorizováno!`: language-edited but not yet authorised by the speakers. 13 Oct pages were still at this stage 30 days later.
  3. No status line: final. Sitting 35 (14 Oct) was already final.
- psp.cz itself says the authorised version follows "cca za 2–3 týdny" and that transcripts are edited into standard Czech: grammar fixed, hesitations removed, factual errors left alone ([O stenoprotokolech](https://www.psp.cz/sqw/hp.sqw?k=1352)). **So "verbatim" means verbatim to the transcript, not to what was literally said.** The UI should say so.
- Since September 2024 the first draft is made with the Beey speech-to-text tool and then corrected by stenographers ([psp.cz press release, 15 Oct 2024](https://www.psp.cz/zprava/19978)).
- **How to detect new transcripts:** diff the daily `steno.zip` against stored page IDs, or watch the per-term `stenprot/index.htm`. Then re-fetch pages with a non-final status until the status line disappears, and store each revision. `Last-Modified` on pages is just the regeneration time (every page said 10:21 GMT on 12 Nov), so it's useless for change detection.

### Robots and terms of use

- [robots.txt](https://www.psp.cz/robots.txt) (last modified 2022) disallows `/sqw/hlasovani.sqw`, `/sqw/hl.sqw`, `/doc/`, `/*.mp3$` and a few others. **`/eknih/` (transcripts) and `/eknih/cdrom/opendata/` aren't disallowed.** There's no crawl-delay.
- The open-data licence is one line on the [open data page](https://www.psp.cz/sqw/hp.sqw?k=1300): "Data jsou poskytována bezplatně, využití dat je podmíněno uvedením zdroje dat a případně datem zpracování dat." (Free to use, with the source and processing date credited.)
- I found **no site-wide terms of use** on psp.cz. The footer has only GDPR and accessibility pages. Whether the open-data licence also covers the HTML pages is **unverified**, but in practice credit "Poslanecká sněmovna PČR, psp.cz" everywhere.
- Crawl budget: about 80 000 pages since 1993, or about 18 500 since 2021. At 1 request/s that's about 22 h or 5 h, one-off. Identify the crawler in the User-Agent with a contact address.

### Alternatives to scraping

| Source | Coverage | Licence | Format | Verdict |
|---|---|---|---|---|
| **ParlaMint-CZ 5.0** ([CLARIN.SI 11356/2004](https://www.clarin.si/repository/xmlui/handle/11356/2004)) | **25 Nov 2013 – 26 Jul 2023** (checked in the downloaded tarball and its `README-CZ.md`). 196 185 speeches, 30 774 250 words | CC BY 4.0 | TEI XML + TXT + TSV metadata, 183 MB `.tgz` | Clean and well linked: each `<u>` has `source="…s071321.htm#r2"` and each person a psp.cz `detail.sqw?id=` URL plus a `ForenameSurname.birthyear` ID. But **released 2025-07-08 with data ending July 2023**, so the update lag is about 2 years and there's nothing from the current term. Use it to validate the parser on the 2021–23 overlap, not as the main source. |
| ParlaMint 4.0 ([11356/1860](https://www.clarin.si/repository/xmlui/handle/11356/1860)) | Same end date (last file `2023-07-26`) | CC BY 4.0 | | Superseded by 5.0 |
| ParCzech 4.0 ([LINDAT](https://lindat.mff.cuni.cz/services/catalog/view/http:__hdl_handle_net_11234_1-5360)) | 2013–Jul 2023 with audio alignment | CC0 according to [B2FIND](https://b2find.eudat.eu/dataset/d28258db-f962-5db5-8d76-99eb92ac7ecc) (**unverified** on LINDAT itself) | TEI | The upstream of ParlaMint-CZ, with the same lag |
| ParlCorp (ČNK) ([wiki](https://wiki.korpus.cz/doku.php/en:cnk:parlcorp)) | 1993–2021, 166 754 speeches, 38.6 M tokens | **unverified** (ČNK corpora usually need registration) | Concordancer | For linguistics, not a data feed |
| Hlídač státu dataset | 1998 at least – 6 Nov 2026 | **unverified** | Web/API | A competitor, not a source |

## 2. Legal and licensing

*Not legal advice; these are the texts as written.*

- **Copyright.** The Copyright Act 121/2000 Sb., [§ 3 písm. a)](https://www.zakonyprolidi.cz/cs/2000-121), excludes official works from protection, explicitly naming "sněmovní a senátní publikace" (Chamber and Senate publications). Stenographic transcripts published by the Chamber fit that wording. **No court ruling on this was checked (unverified).** Separately, [§ 34 písm. d)](https://www.zakonyprolidi.cz/cs/2000-121) lets anyone use "politický projev … v rozsahu odpovídajícím informativnímu účelu" (political speeches, to an extent fitting an informative purpose). Quoting and republishing speeches is therefore on firm ground.
- **Database right.** §§ 88a and 90 of the same act give the maker of a database a separate 15-year right against extracting substantial parts. psp.cz's open-data licence permits use with attribution. For the HTML pages, attribution, polite crawling and linking back to every source page keep the risk low (**unverified** whether the Chamber claims this right).
- **GDPR.** Speeches are personal data, and they reveal *political opinions*, a special category under [Art. 9(1)](https://gdpr-info.eu/art-9-gdpr/). Two bases fit:
  - Art. 9(2)(e): data "manifestly made public by the data subject". Plenary speeches are given in public and published by the Chamber.
  - [Art. 85](https://gdpr-info.eu/art-85-gdpr/) with the Czech [Act 110/2019 Sb. § 17](https://www.zakonyprolidi.cz/cs/2019-110): processing for journalistic, academic or literary purposes is lawful "přiměřeným způsobem" (to a proportionate extent). §§ 18–21 relax the duties to inform data subjects and to grant access and rectification.

  Everyday processing would rest on legitimate interest (Art. 6(1)(f)). **Non-MP speakers** (ministers, senators, the ombudsman, the ČNB governor) speak in an official capacity, so the same reasoning applies. The weaker spot is **private individuals whom MPs name in speeches**. Don't build person pages or filters for anyone who isn't a speaker. Publish a privacy notice and give people a way to object.
- **Accuracy.** AI summaries that misattribute a claim to a named politician create defamation risk and GDPR accuracy risk (Art. 5(1)(d)). The "no uncited claims" rule in CLAUDE.md is the main mitigation.
- **Attribution to show in the footer and on the methodology page:**
  - psp.cz: source credit, plus the processing date (per the [licence line](https://www.psp.cz/sqw/hp.sqw?k=1300)).
  - ParlaMint, if used: CC BY 4.0, cite the [handle](http://hdl.handle.net/11356/2004).
  - Embedding models: bge-m3, multilingual-e5-large and -instruct are MIT; Qwen3-Embedding-0.6B is Apache-2.0 (Hugging Face API tags).
  - The [kokes/od](https://github.com/kokes/od) parser of psp.cz open data is MPL-2.0, if we borrow from it.

## 3. Existing products

| Product | What it does well | What it lacks for this use |
|---|---|---|
| [Hlídač státu: Stenozáznamy PSP](https://www.hlidacstatu.cz/data/Index/stenozaznamy-psp) | Speech-level keyword search (613 hits for "důchodová reforma"), sort by date, person or length, politicians mentioned in each speech, email alerts for a query, updated within days (latest 6 Nov 2026), running since about March 2021. Built on psp.cz open data via [kokes/od](https://github.com/kokes/od). | Keyword only. No semantic search or summaries seen. Generic data-table interface. |
| [psp.cz full-text search](https://fulltext.psp.cz/stenozaznamy) | Official, covers all terms 1993–2029 | Keyword only. Hits are 10-minute pages, not speeches or MPs. |
| psp.cz name index ([jmenný rejstřík](https://www.psp.cz/eknih/2025ps/rejstrik/jmenny/index.htm)) | Every page where an MP spoke, per term | No search, no text |
| [Demagog.cz](https://demagog.cz/vyroky?page=1076) | Expert fact-checks with verdicts. About 7 500 statements in its first five years ([Novinky](https://www.novinky.cz/domaci/430978-demagog-cz-cesti-politici-mluvi-pravdu-vetsinou.html)), mostly from TV and interviews. Feeds [Naši politici](https://www.lupa.cz/clanky/neziskovky-se-spojily-a-spustily-web-nasipolitici-cz-ktery-chce-nabizet-informace-o-vsech-politicich/). | A curated sample, not an archive of everything said in the Chamber |
| [ZamysleteSe.org](https://www.zamysletese.org/) | A one-person project "s AI nástroji": vote and debate dashboards for current sittings, plans to fact-check statements against transcripts | Analyses of individual sittings, not search |
| ParlaMint / ParCzech concordancers ([noSketch/KonText](https://www.clarin.si/repository/xmlui/handle/11356/1860)) | Linguistic queries, lemmas, named entities | Researcher tools; data ends July 2023 |
| [TheyWorkForYou](https://www.mysociety.org/category/democracy/theyworkforyou/) (UK) | The model to follow: MP pages, searchable speeches, keyword and MP email alerts (2.2 M sent in 2026), voting summaries | No semantic or AI search found on mySociety's blog (**unverified** absence) |

**The gap, honestly:** "find a keyword in what MPs said" is already solved, by Hlídač státu best of all. What nobody offers for the Czech Chamber is (a) search by meaning ("what did ANO say about pension age" without guessing the exact wording) and (b) short answers where every sentence links to the speech it came from, (c) wrapped in a reading interface built around MPs. That gap is **moderate**: compelling for journalists, students and curious citizens, marginal for power users who already use Hlídač. For a portfolio project, the gap and the craft both justify building it. For an actual civic product, Rozprava would need to prove its retrieval and its citation discipline in a way Hlídač doesn't. Linking each speech to Hlídač and psp.cz rather than competing on alerts is the sensible stance.

## 4. Technical feasibility

### Data size

- **Measured ratios.** 281 188 words from three parsed samples (`scratch/scripts/tokcount.py`): 6.34 chars/word, and tokens per word of 1.72 (bge-m3/XLM-R), 2.09 (o200k), 2.83 (cl100k, which `text-embedding-3-*` uses according to tiktoken's model map) and 2.83 (Qwen3). The Claude tokenizer ratio is **unverified** (no API credentials on this machine).
- **Words per page**, from 4 random pages per term (`scratch/scripts/sample_pages.py`): about 3 500 in 1993 (longer pages), unstable in 1996–98, and 960–1 230 from 1998 on. The estimate is scaled by 0.9 because the raw per-page figure gives 34.0 M words for Nov 2013–Jul 2023, while ParlaMint counts 30.8 M for the same span.

`scratch/scripts/estimate.py`, assuming 300-word chunks with 15 % overlap:

| Scope | Words | Speech rows (`rec`) | Chunks | Tokens (bge-m3 / cl100k) | Vectors 1024-d fp32 |
|---|---|---|---|---|---|
| Current term (Nov 2025–) | ≈ 4.7 M | 20 710 | ≈ 18 k | 9 M / 15 M | 0.07 GB |
| 2021– (terms 9 + 10) | ≈ 20 M | 92 767 | ≈ 77 k | 40 M / 65 M | 0.31 GB |
| 2013– | ≈ 44 M | 253 181 | ≈ 168 k | 87 M / 143 M | 0.69 GB |
| Full 1993– | ≈ 87 M | 495 497 + 1996–98 | ≈ 332 k | 171 M / 282 M | 1.36 GB |

About half the speech rows are the chair, and chair text is roughly 10–20 % of the words in the samples. Skipping procedural chair remarks when embedding cuts tokens accordingly. Raw text for the full archive is about 0.6 GB.

### Embedding models

**Czech quality evidence.** These are nDCG@10 scores on the Czech subsets of public MTEB tasks, pulled from [embeddings-benchmark/results](https://github.com/embeddings-benchmark/results) by `scratch/scripts/mteb_cz.py`:

| Model | Belebele (ces) | WikipediaRetrieval (cs) | WebFAQ (ces) | Hosting | Price / 1 M tokens |
|---|---|---|---|---|---|
| multilingual-e5-large | **0.952** | – | **0.828** | local, MIT, 560 M params | free |
| bge-m3 | 0.940 | 0.902 | – | local, MIT, ~568 M params, 8 k context, dense + sparse | free |
| multilingual-e5-large-instruct | 0.939 | **0.928** | 0.822 | local, MIT | free |
| text-embedding-3-large | 0.930 | 0.915 | – | hosted | $0.13 ([OpenAI pricing](https://platform.openai.com/docs/pricing)) |
| multilingual-e5-small | 0.904 | – | 0.744 | local, MIT, small | free |
| Qwen3-Embedding-0.6B | 0.894 | 0.878 | – | local, Apache-2.0 | free |
| text-embedding-3-small | 0.881 | – | – | hosted | $0.02 |
| voyage-4 / voyage-4-lite | **unverified** (no Czech results) | | | hosted | $0.06 / $0.02, first 200 M tokens free ([Voyage pricing](https://docs.voyageai.com/docs/pricing)) |
| gemini-embedding-001 / -2 | **unverified** | | | hosted | $0.15 / $0.20 ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) |
| Cohere Embed | **unverified** | | | hosted | price didn't render on [cohere.com/pricing](https://cohere.com/pricing) |

The top four are within about 0.03 of each other. These tasks are short Wikipedia and QA passages, not long rhetorical speeches, so **retrieval quality on parliamentary speech is unverified.** I found no Czech-specific benchmark of embeddings on parliamentary or long-form text. The Seznam paper ["Some Like It Small"](https://arxiv.org/abs/2311.13921) covers small Czech models for web search, not this.

**One-off cost to embed** (token counts from the table above; Voyage and Gemini assume the o200k ratio, **unverified**):

| Scope | text-embedding-3-small | text-embedding-3-large | voyage-4-lite | voyage-4 | gemini-embedding-001 |
|---|---|---|---|---|---|
| Current term | $0.30 | $1.97 | $0.22 (free tier) | $0.67 (free tier) | $1.68 |
| 2021– | $1.30 | $8.48 | $0.96 (free tier) | $2.89 (free tier) | $7.22 |
| Full 1993– | $5.64 | $36.66 | $4.17 | $12.50 | $31.24 |

**Self-hosting.** bge-m3 and e5-large are about 560 M-parameter XLM-R-large models (1.1 GB fp16 / 2.2 GB fp32 weights). Embedding queries at search time means keeping the model loaded on the server. That rules out the smallest VPS tiers, or needs a separate inference host. Throughput for a one-off local ingest on this machine (Apple M2, 8 GB RAM) is **unverified**: I didn't install torch and bge-m3, because the disk has 10 GB free (95 % full). A rough FLOP estimate puts 40 M tokens (the 2021– scope) at several hours on the M2 GPU and the full archive at roughly a day or two (**unverified**).

**Postgres keyword search has no Czech stemmer.** PostgreSQL's Snowball stemmers don't include Czech ([`src/backend/snowball/Makefile`](https://github.com/postgres/postgres/blob/master/src/backend/snowball/Makefile)), and it ships no Ispell files ([docs](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)). Hybrid keyword + vector search needs a Czech hunspell dictionary or the `simple` configuration plus `unaccent`. The bge-m3 sparse output is an alternative.

### LLM summaries with citations

- **The Claude [Citations](https://platform.claude.com/docs/en/build-with-claude/citations) feature fits the "no uncited claims" rule.** You pass each speech as a `document` with citations enabled, and the answer comes back as text blocks with a `citations` array. Each citation has `cited_text` plus character offsets (plain-text documents) or block indices ("custom content" documents, which aren't re-chunked, so one block per stored paragraph maps straight back to our database). The docs say citations "are guaranteed to contain valid pointers to the provided documents", and `cited_text` doesn't count as output tokens. Any text block without a citation can be dropped mechanically.
- **Two limits.** Citations can't be combined with structured outputs (400 error). And a valid pointer doesn't guarantee the cited passage actually *supports* the claim: that needs a check of our own or human review of samples.
- **Known weaknesses for this corpus:**
  1. Misattribution when several speeches are in context. Put one speech per document, with the speaker and date in the title.
  2. MPs quoting or paraphrasing opponents ("pan ministr tady říkal, že…") can be summarised as the speaker's own view.
  3. Irony and heckling notes in parentheses.
  4. Procedural chair text drowning out the substance.
  5. Unauthorised first drafts with transcription errors.
  6. Czech inflection of names ("Babišovi", "Babiše") for filters and keyword search.

  I found no Czech summary-faithfulness benchmark. [BenCzechMark](https://aclanthology.org/2025.tacl-1.50.pdf) covers general Czech LLM ability, and summarisation scores were **unverified** in what I read.
- **Price** ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), per million tokens, input / output): Claude Haiku 5.5 $0.10 / $0.50 (prompts up to 100 k tokens); Claude Sonnet 5.5 $2 / $10, with cache reads at $0.10; Claude Opus 5.5 $4 / $20. Batch is 50 % off. For an answer built from about 10 speech excerpts (≈10 k input tokens, 500 output; Claude's Czech token ratio **unverified**), that's about $0.001 per answer on Haiku 5.5 and about $0.025 on Sonnet 5.5. Cache answers by query and filters.

### Hosting (portfolio budget)

- **Storage need for the 2021– scope:** under 2 GB in total (text plus vectors plus an HNSW index), assuming pgvector's HNSW index is about the size of the vectors (**unverified**).
- **Cheapest workable setup:** one VPS running FastAPI and Postgres with pgvector. [Hetzner Cloud](https://www.hetzner.com/cloud/) shared "Regular Performance" plans start at **€5.49/month excl. VAT** (the cheaper Cost-Optimized line shows "Currently not available"). RAM and disk for that tier are **unverified**. Hetzner raised prices twice in 2026 ([Northflank summary](https://northflank.com/blog/hetzner-cloud-server-price-increases), secondary source).
- **Managed Postgres:**
  - [Supabase](https://supabase.com/pricing): Free is 500 MB and pauses after a week of inactivity, which is too small for 2021– and too flaky for a demo. Pro is $25/month with 8 GB disk.
  - [Neon](https://neon.com/pricing): Free has 1 GB storage per project and scales to zero. That fits the current term and possibly 2021– with `halfvec`. The app would still need a host (**unverified** prices for Fly/Render/Railway).
- **Estimate:** about €6–10/month for hosting, plus LLM spend under a hard cap (for example $5/month). Hosted query embeddings cost a fraction of a cent per thousand searches.

## Recommended first scope

1. **Terms to load:** 2025– (current) **plus 2021–25**, so search spans a change of government (who said what in opposition vs. in power). Next steps: 2013–21, where `rec` has chair/speaker roles; then 1998–2013; and 1993–98 last, since 1996–98 needs name matching and pages from 1996 and earlier have no person links.
2. **Data source:** psp.cz directly. Speakers, parties and agenda items come from the daily open-data dumps (`steno.zip`, `poslanci.zip`, `schuze.zip`), and text from the live HTML pages crawled at about 1 request/s. Store the revision status with each speech and re-fetch until final. Use **ParlaMint-CZ 5.0 as a test oracle**: compare parsed speeches and speaker IDs for Nov 2021–Jul 2023 against its TEI files.
3. **Speaker attribution:** use the HTML label as the source of truth and take `id_osoba` from `rec` only when the surname matches. Otherwise resolve by name, role and date. Log mismatches.
4. **Embedding approach:** start with a **hosted** model behind the single LLM/embedding module, so the server doesn't hold a 2 GB model in RAM. `text-embedding-3-large` is the evidenced default: 0.930/0.915 on Czech retrieval and about $8.50 one-off for 2021–. Before freezing the choice, run a one-day bake-off on about 50 hand-written Czech questions over the 2025– term against **bge-m3** (local or via a hosted endpoint) and **multilingual-e5-large-instruct**, which scored as well or better on the Czech tasks. Embed chunks of substantive speeches only, not procedural chair remarks. Add Czech keyword search through a hunspell dictionary or `simple` + `unaccent` for exact-phrase queries.
5. **Summaries:** Claude with Citations on custom-content documents (one block per paragraph). Drop any uncited sentence. Start on Haiku 5.5 and compare against Sonnet 5.5 on the same 50-question set before choosing.

## Risks and unknowns, ranked

1. **Small differentiation from Hlídač státu.** If semantic search isn't clearly better than keyword search on real questions, there's little reason to use Rozprava. *Test it first with the bake-off.*
2. **Wrong or unsupported AI claims about named politicians** (reputational, defamation, GDPR accuracy). Citations guarantee valid pointers, not support. *Mitigate with a support check, sampling and an "AI summary" label.*
3. **Speaker attribution drift.** 2.8 % of speeches in one sitting were attributed to the wrong person by `rec`, and `rec` can be missing for days after a sitting. *Mitigate with the label cross-check, label-first attribution for new pages, and logging.*
4. **Transcripts change after publication** (raw → edited → authorised), so stored quotes can go stale. *Store a revision status per speech, re-fetch until final, and show "neautorizováno" on quotes.*
5. **Scraper fragility.** There's no API for the text, markup differs by era, ZIPs are inconsistent, and psp.cz can change pages without notice. *Mitigate with per-era parser tests and ParlaMint as an oracle.*
6. **Czech retrieval on long political speech is untested.** The MTEB evidence comes from short passages.
7. **Legal edges, unverified:** no court ruling on transcripts as official works, possible database right over the HTML, private people named in speeches.
8. **No Czech stemming in Postgres** for the keyword half of hybrid search.
9. **Price drift.** Hetzner rose twice in 2026, and model prices change.
10. **Local environment.** Homebrew's Python 3.14 is broken here: pip fails with a `pyexpat` / `libexpat` symbol error. `uv` isn't installed. The disk is 95 % full. Fix these before scaffolding.

## Answers to the open decisions in CLAUDE.md

- **Interface language:** *partly settled.* Every transcript, name and party is Czech, and the likely users are Czech, so the UI should be Czech-first. ParlaMint's English machine translation carries a warning about factual errors, so don't translate quotes. Whether to add an English UI for the portfolio audience is the user's call.
- **Embedding model:** *narrowed, not settled.* Hosted vs. local is a hosting question, not a quality one: Czech scores are within 0.03 across text-embedding-3-large, bge-m3 and the e5 models. Recommendation: hosted `text-embedding-3-large` for v1 behind a swappable module, with the bge-m3 bake-off as the deciding test.
- **How far back:** *settled for v1.* Load 2021– first. Every term since 1993 is available, but 1996–98 has no speaker table and the older markup needs extra parser work.
- **Hosting:** *narrowed.* One small VPS with Postgres + pgvector + the app (about €6–10/month) fits the 2021– scope. Supabase Pro ($25) is the managed alternative. Neon Free could work for the current term only.
