# ADR-0008 Frontend served by an Nginx build stage

Status: accepted (2026-11-12)

**Decision:** Vite output is built in a Node stage and copied into the Nginx image; no frontend runtime container.

**Why:** Fewer moving parts, one origin, strict CSP, no Node in production.

**Consequences:** Frontend changes need an nginx image rebuild (docker compose up --build).
