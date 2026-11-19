---
type: implementation
updated: 2026-11-18
status: current
---

# Live archive views

Related: [[functional-app-design]], [[functional-app-plan]], [[transcript-import]], [[dev-environment]]

## Implemented

Step 6 connects the existing home, MP directory/profiles, sittings and methodology
templates to PostgreSQL. Directory filters (name, club, region), sorting, term
selection and speech pagination are normal GET navigation. Profile calendar days
search all stored speeches for that person/date/term. Fixture-only filtering stays
confined to the static preview. Both desktop and mobile calendar views retain
unknown attendance and incomplete-transcript states.

Home shows the latest **imported** day, or an explicit empty state, and a speech
sample selected deterministically by hour from non-chair speeches of at least 60
words. Shared coverage includes terms without pages and reports pending, failed
and unavailable pages; none of those count as a complete corpus. Metadata-only
sittings remain addressable before their day/page metadata arrives.

## Statistical rules

- Activity counts current assembled speeches once, excludes known chair roles and
  speeches outside an MP's mandate dates, and uses positive MP-day word quartiles
  within one term. Fewer than four positive observations use level 1. Profile
  speech lists include and label chair contributions; statistics exclude them.
- A complete transcript day needs source pages with current revisions assembled;
  no page metadata or outstanding assembly is incomplete. Incomplete statistics
  remain explicitly provisional. Saturday and Sunday have distinct calendar rows
  when both occur in one week.
- Voting participation uses A/B/N/C/F/K registration and @/M absence. Exclude W
  before oath, invalidated votes, manual R and technical E votes, and votes outside
  mandate timestamps. Missing/unrecognized records remain unknown, suppress the
  percentage, and stay out of percentage medians. A day without eligible votes
  is unknown. Apologies are imported separately and do not invent participation.
- Club labels use the last sitting date, capped at mandate end; the profile shows
  that reference date. Unknown club membership remains distinct from independent.

Source schema checked against [PSP voting data](https://public.psp.cz/sqw/hp.sqw?k=1302).

`python -m rozprava.ingest votes` imports both terms atomically and can run
alongside transcript backfill under a separate advisory lock. `update` also
acquires the votes lock. Reimports replace removed/changed votes and apologies;
missing tables are rejected and failed replacements roll back.

## Verification and remaining work

143 tests pass, including codes/eligibility/unknown attendance, rollback and
replacement, quartiles, missing pages, empty archives, real-person routes,
term-qualified bill links and pagination. Ruff, formatting, Pyright, token
freshness, JS syntax checks and static preview rendering pass.

T3 browser DOM checks covered desktop and 390px mobile pages, directory filtering,
profile term/date links, year filtering and the table toggle. Fixed mobile overflow
in the previous term's six-option year selector. T3 snapshots fail at the client;
DOM inspection and computed dimensions were used instead of screenshots.
Representative local HTTP requests took about 0.1–2.4 seconds (profile/directory
queries include voting aggregates); no page cache is required for this local phase.

At 11:06 CET on 18 Nov, the backfill was still running (PID 26259): term 9 had
6,340 / 13,926 imported pages, 7,580 pending and 6 failed; term 10 had 25 / 4,574
imported and 4,549 pending. These are a snapshot, not completion counts. Both
terms' voting import had completed at 09:19 CET. Web requests never fetch PSP.

Next is step 7: server palette queries and revision-pinned quotation export.
The live home/methodology now describe keyword/phrase search and manual imports;
there are no AI summaries or automatic nightly updates in this version.
