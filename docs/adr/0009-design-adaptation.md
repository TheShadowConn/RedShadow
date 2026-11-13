# ADR-0009 design-taste-frontend adapted for an application

Status: accepted (2026-11-12)

**Decision:** Applied from the skill: dealt palette (cool-white-slate) and pairing (Geist), sharp radius, one accent, 16px text, 44px controls, motion timings, focus ring, sentence case, no violet. Not applied: marketing page rules (one section per screen, hero deals, photographs, consistency.mjs).

**Why:** The skill targets marketing sites. Its system tokens fit an authenticated app; its page-layout checks do not.

**Consequences:** Tokens live in frontend/src/design/tokens.css. Fonts are self-hosted (fontsource) because CSP allows no external origins. The wordmark is custom (Geist outlines): Red casts a crimson shadow.
