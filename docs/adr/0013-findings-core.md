# ADR-0013: Findings core (Phase 4A)

Status: accepted (Phase 4A). Date: 2026-11-13.

## Decisions

- **Ref**: `RS-F-000001`, one global counter row locked with `SELECT ... FOR UPDATE` (same pattern as engagements).
- **CVSS**: the client sends only a vector. The server parses it with the `cvss` library (3.1 and 4.0), stores version, base score and severity, and rejects a `cvss_score` field (unknown field). With a vector, severity is derived; a conflicting client severity is a 400. Without a vector severity is set by hand. Editing severity while a vector is set is refused until the vector is cleared.
- **CWE**: curated table (196 common weaknesses) seeded by migration from `apps/findings/data/cwe.json`. Extend the file and add a data migration to add more.
- **Statuses in 4A**: model carries all nine statuses so Phase 5 needs no data rewrite. Only `draft -> open` (publish), `draft/open -> false_positive` (reason required, kept in audit metadata) and `draft/open -> duplicate` (same engagement, original not itself a duplicate) are allowed. Draft and open findings are editable; every other status is read-only. There is no way back from false positive or duplicate until Phase 5 adds reopen.
- **Visibility** (`selectors.scope_findings`): `findings.view` on the engagement (role for all-engagement roles, membership role or override otherwise); drafts only with `findings.view_draft`; when the effective finding scope is `assigned` (membership override, else role default) only findings whose remediation owner or assigned pentester is the user. Out of scope answers 404.
- **Field permissions** (service layer, one code path for API and bulk): content fields need `findings.update` (`findings.create` on create); `assigned_pentester` and `remediation_owner` need `findings.assign`. A forbidden field is a 400 and an audited `finding.update_denied`. Assignees must hold `findings.view` on the engagement. The engagement is immutable after create. A linked asset must be in scope (`in_scope` link) for the engagement.
- **Technical fields**: `technical_details` and `poc` are returned to everyone who can see the finding, remediation users included (product owner decision, Phase 5A: they must reproduce a finding to fix and retest it). Technical *notes* stay testing-team only.
- **History**: `GET /findings/{id}/history` needs `audit.view_engagement`. Without `findings.view_draft` it starts at the publish event . Finding events are excluded from `GET /engagements/{id}/history` for users without `findings.view_draft`, so draft titles and text cannot leak through the engagement timeline.
- **Soft delete**: `DELETE /findings/{id}` (needs `findings.delete`, Super Admin only by default) sets `deleted_at`; the row disappears from every selector. Refused while other findings point at it as the original. No restore endpoint yet (DBA only).
- **Bulk** (`POST /findings/bulk`, max 100 ids, actions publish, assign, delete): each id is resolved through the scoped selector (unseen ids and nonexistent ids both answer `not_found`), authorised and committed on its own, and reported per item. The coarse gate needs `findings.bulk_update`.
- **Dedupe**: `sha256(engagement | normalised title | asset | normalised endpoint | cwe)` stored on every write. Detail responses list visible findings of the same engagement with the same hash (`possible_duplicates`). Nothing blocks creation.
- **Search**: Postgres full text over title and description (GIN index, `websearch` syntax) or a ref substring. Always applied on top of the scoped queryset.
- **Audit**: every write is tagged with the engagement; text changes are truncated to 500 characters per side to keep the chain small.

## Known limits

- No markdown sanitising yet (4B adds `nh3`); text is stored raw and must be rendered without raw HTML.
- Coarse-gate denials (role holds the code nowhere) are not audited, as for other modules.
- The "asset in scope" rule is enforced in the service, not by a database trigger.
- Real concurrent ref collisions are not tested, only the row lock.

## Phase 4B additions

- **Notes** are append-only (no routes, plus a `BEFORE UPDATE OR DELETE` trigger). Kind decides visibility: technical = testing team only (`finding_notes.technical`), remediation = everyone who sees the finding. Audit never stores note text.
- **Evidence** reuses `Attachment` (kind `evidence`, finding FK, owner check constraint). Visibility = finding in scope AND `evidence.view` on the engagement. Deleting needs `evidence.delete_own` for the uploader's own file or `findings.delete` for any.
- **Templates** are platform level; the finding create path merges template text under caller input and records `source=template`.
- **Markdown**: `render_markdown` (Python-Markdown + nh3) is the only way server code may turn user markdown into HTML.

## Phase 5A additions (state machine)

- **One table, one executor**: `findings/lifecycle.py` lists every allowed move with its permissions (any one suffices), required note and extra inputs; `services.transition` is the only code that changes `Finding.status`. Unknown moves are 409, missing permission 403 (audited), missing note or input 400, stale version 409.
- **Timeline vs audit**: `RemediationActivity` is the user-facing timeline (append-only by trigger); the hash-chained audit log stays the tamper-evident record. Both are written in the move's transaction.
- **Verification notes**: moves that need a written reason store it as a `verification` (or `remediation`) note visible to everyone who sees the finding. Those kinds cannot be posted by hand.
- **SLA**: `due_date` = publish date + `SLA_DAYS[severity]` (env configurable, info has none); severity edits recompute it; reopen keeps it. Risk acceptance expiry is capped by `RISK_ACCEPT_MAX_DAYS`; only `findings.risk_accept` (Super Admin by default) may accept risk.
- **Reopen**: closed, risk accepted, false positive and duplicate findings reopen with `findings.reopen` and a reason. Leaving `duplicate` clears `duplicate_of`.
- **Editing**: allowed in draft, open, in progress and reopened.

## Phase 5B additions (retests, queues, sweeps)

- **Retest rounds** reuse the state machine: `retests.record_result` calls `services.transition`, which settles the item inside its own transaction (`retests.settle`), so a round and its findings cannot disagree. Result rights are strict: only the assigned assessor, who must hold `retests.record` and `findings.verify`; the denial is audited.
- **Disclosure**: a round lists only items whose findings the caller can see (`scope_findings`).
- **System actor**: sweeps run `services._execute` with no actor; audit events carry the label "system" and timeline entries have no actor.
- **Queues** are read-only views over `scope_findings`; counts and rows come from the same scoped query.

## Phase 5C additions (screens)

- **One dialog for every move**: the finding page builds its buttons from `allowed_transitions` and opens `MoveDialog` only when a move needs a note, an expiry or an original finding. Wording lives in `features/remediation/shared.tsx`; the server remains the only judge of what is allowed.
- **Queues are cards below 1024 px**: the table keeps an actions column that does not fit beside the 72 px rail at tablet width.
- **Fixers land on the queue**: a role that can start work but cannot create findings is sent to `/remediation` after sign-in (a UX default, not a permission).
