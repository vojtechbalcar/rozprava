---
type: decision
updated: 2026-11-12
status: current
---

# Project choice

Related: [[design-direction]], [[stack-decision]]

On 12 November 2026 the user picked the next portfolio project after Watchlist from ten ideas. They liked two most: this one (search over Czech parliament transcripts) and a browser extension that tracks where time goes online. They plan to build both.

This one goes first because:
- Its biggest risk is the data: whether psp.cz transcripts are easy to download and parse. Checking that early is cheap; finding out late is not.
- It contrasts most with Watchlist (Python, embeddings, AI search) while Postgres stays familiar.
- The extension's first version is smaller and suits a second project; store review can run while its dashboard is built.

Rejected as the next project: the Prague transit delay tracker, the fake-discount detector, a real-time multiplayer app, an offline-first workout logger, an uptime monitor, "is this weather normal?", a booking system with payments, and a git bus-factor CLI.
