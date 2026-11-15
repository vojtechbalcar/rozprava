---
type: decision
updated: 2026-11-12
status: current
---

# Design direction

Related: [[project-choice]], [[stack-decision]]

The user chose anthropic.com as the visual reference. Also offered: Stripe Press and the Financial Times (warm editorial); Linear, Exa and Vercel (precise and minimal); The Pudding and Our World in Data (data journalism). The warm editorial direction was recommended because a serif, paper-toned look makes a civic tool read like a source rather than a chatbot, and it contrasts with Watchlist's Mobbin-style sans.

The base tokens come from getdesign's `claude` spec (`npx getdesign@latest add claude`), the same tool Watchlist used for Mobbin. `DESIGN.md` is our adapted version, not the raw download.

## Adaptations

- **Fonts.** Copernicus and StyreneB are licensed, so Newsreader (serif, optical sizes) and Inter replace them. Both cover Czech diacritics. Cormorant Garamond, the spec's suggested substitute, was passed over: it's too high-contrast for 19px quote text.
- **Colours.** Our own "archive" palette replaces Anthropic's cream and coral: grey-green paper `#f6f7f4`, green-black ink `#121a18`, petrol accent `#1d6b65`, dark surface `#0f1b19`. Petrol passes AA as text on the canvas (5.8:1) and behind white text (6.3:1), so one accent does every job. See the correction below.
- **Serif means quoted speech.** Verbatim quotes are set in the serif and AI summaries in the sans, so evidence and commentary never look alike.
- **No party colours.** Petrol is the brand only, and full-bleed accent callouts were dropped so nothing reads as a party colour. Petrol was picked partly because it sits away from the primary colours Czech parties campaign in.
- **No Anthropic marks.** Own wordmark with a petrol full stop, echoing Watchlist's maroon full stop.

## Correction: the colours are not Anthropic's

The first version of `DESIGN.md` kept Anthropic's cream canvas and coral accent (as "clay", with a darker clay-deep `#a9583e` for buttons and links). The user corrected this: they want anthropic.com's layout, fonts and structure, but not its colours. Copying the palette as well made the app look like an Anthropic clone.

**How to apply:** take structure, type scale, spacing, radii and the colour-block depth from anthropic.com; never its cream, coral or warm greys. Keep the archive palette above unless the user changes it.

**Rejected palettes:** cream and coral (Anthropic's own); ink blue, oxblood and other reds, orange, yellow and purple accents, because they are close to Czech party colours.
