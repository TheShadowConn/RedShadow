# ADR-0003 RBAC model

Status: accepted (2026-11-12)

**Decision:** A user has one platform role. A role is a set of catalogue permissions plus flags (reaches every engagement, finding scope, MFA required). Engagement-level access comes from the role (all-engagement roles) or, from Phase 3, from engagement membership. One resolver (apps/rbac/authz.py) answers every question; viewsets deny by default.

**Why:** Permissions must be configurable but auditable. Per-object grants explode and are hard to review. Deriving scope from membership keeps one source of truth.

**Consequences:** Anti-escalation rules live in apps/rbac/guards.py. Any role or permission change bumps session_version so affected users sign in again. Organisation-level membership can be added later without a schema break.
