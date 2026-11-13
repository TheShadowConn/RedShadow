# ADR-0002 Session cookies over JWT

Status: accepted (2026-11-12)

**Decision:** Browser auth uses HttpOnly, Secure, SameSite=Lax session cookies on the same origin via Nginx, with CSRF tokens.

**Why:** JWT in browser storage is XSS-stealable and hard to revoke. Server-side sessions allow instant revocation (session_version).

**Consequences:** API is browser-bound; machine clients need hashed API tokens later (deferred). Implemented in Phase 2.
