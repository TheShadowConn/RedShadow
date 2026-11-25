# Security (implemented controls)

Baseline: OWASP ASVS L2. Full threat model: BLUEPRINT.md section 6. This file lists what exists now.

## Authentication and sessions (Phase 2)

- Passwords: Argon2id; minimum 12 characters; Django common-password list, numeric and similarity checks.
- Login: identical error and comparable timing for unknown, inactive, locked and wrong-password cases. Lock for 15 minutes after 5 consecutive failures (sign-in or MFA). Per-IP throttle 20/min on login and MFA (Redis).
- Sessions: server-side, HttpOnly, SameSite=Lax, Secure when TLS is on; key rotated on sign-in; idle 30 min; absolute 12 h; revoked instantly by `session_version` (role change, password change or reset, deactivation, MFA reset, explicit revoke).
- CSRF: required on every unsafe request, including login (double-submit token in `X-CSRFToken`).
- MFA: TOTP with replay protection, encrypted secret at rest (Fernet), hashed single-use recovery codes. Required per role (Super Admin by default); voluntary otherwise. Admin reset is audited.
- Restricted sessions: after password sign-in the session can only reach the endpoints needed to finish MFA verify, password change or MFA setup.
- Bootstrap: first Super Admin is created once, with a generated password printed once in the `migrate` logs, `must_change_password` set. Not repeated if a Super Admin exists.

## Authorisation

- Default deny: viewsets refuse any action without a `permission_map` entry; a test fails if a ModelViewSet does not derive from `ScopedModelViewSet`, if an action has no permission, if a public view is added, or if a route lacks matrix coverage.
- Anti-escalation (apps/rbac/guards.py, tested): nobody changes their own role or account state; a role can only be granted if its permissions are a subset of the grantor's; a user can only manage users whose role permissions are a subset of theirs; last active Super Admin is protected; Super Admin role is immutable; custom roles cannot grant permissions the editor lacks.
- Mass assignment: request serializers reject unknown and read-only fields with 400.
- Frontend permission hints are UX only; the backend decides.

## Files and uploads (Phase 3B)

- Type comes from the file's bytes, never from the name or the browser's Content-Type. Allow-list: png, jpg, gif, webp, pdf, txt, log, csv, json, xml, zip, pcap, pcapng, docx, xlsx. The claimed extension must match the detected type. HTML and SVG files are refused. Text files that start with HTML or SVG markup are refused (logs that merely contain markup are fine and are served as `text/plain`).
- Images are re-encoded with Pillow: EXIF and any trailing polyglot payload are dropped. Pixel limit 50 million.
- Archives (zip, docx, xlsx) are inspected, not extracted: at most 2000 entries, 500 MB expanded, compression ratio under 200 per large entry, no `..` or absolute paths.
- Size limit 25 MB, enforced by nginx (26 MB body, then 413 from nginx) and Django (exact, JSON 413).
- Files are stored as `yyyy/mm/<uuid>` on the media volume; the user-supplied name is cleaned and kept only as display text. Storage keys are validated against a strict pattern and resolved under the media root.
- Download: Django authorises (scoped queryset and `documents.view` on the engagement), records an audit event, then answers with `X-Accel-Redirect`. nginx serves from an `internal` location (the media volume is mounted read-only there), with `Content-Disposition: attachment`, `nosniff`, a `sandbox` CSP and `Cache-Control: private, no-store`. `/protected/...` requested directly is 404.
- Deletion is soft; a daily Celery task (`files.purge_deleted`, queue `maintenance`) removes the blob after `ATTACHMENT_RETENTION_DAYS` (default 30). No malware scanning (ClamAV was declined): files are never executed or rendered by the server, and are downloaded as attachments only.

## Reports and dashboards (Phases 9 and 10)

- A report is built by a worker from the requester's own scoped finding selector and their rights are checked again at run time; drafts are never included; internal editions (technical details, proof of concept, technical notes) need `finding_notes.technical` on the engagement.
- The PDF engine can fetch only `data:` URIs and the bundled `.woff` fonts. Local files and network addresses are refused (tested with hostile markdown, raw HTML, CSS `@import` and `file:` URLs). All user text passes the markdown allow-list; evidence images and logos are re-encoded; SVG logos are refused.
- Report generation and download are audit events (`report.requested`, `report.generated` with SHA-256, `report.downloaded`, `report.failed`, denied requests). Files expire after `REPORT_RETENTION_DAYS` (default 90); downloads answer 410 afterwards. Responses are `no-store` attachments with `nosniff`.
- Rendering runs in its own container with a memory limit, one build at a time per engagement, at most 500 findings per PDF.
- Dashboards are read-only aggregates over `scope_findings`, `scope_engagements` and `scope_audit`; a test asserts that each count equals the matching list for Super Admin, Pentester and Remediation users and that other organisations never appear.

## Audit

- Append-only (DB triggers + revoked UPDATE/DELETE/TRUNCATE for `redshadow_app`), SHA-256 hash chain, redaction of secrets, denied actions recorded. Verify with `docker compose exec backend python manage.py verify_audit`.
- Not yet: scheduled verification and off-host anchoring of the chain head (Phase 6), audit explorer UI.

## Infrastructure

See DOCKER_SETUP.md: only nginx published, internal network, non-root, read-only root fs, dropped capabilities, DB roles split (owner for DDL, app for DML), generated secrets, TLS (self-signed by default), CSP and security headers.

## Hardening (Phase 12)

- Base images are pinned by digest (python, node, nginx-unprivileged, alpine, postgres, redis). Backend and worker run as uid 10001, read-only root filesystem, all capabilities dropped. Redis runs as the redis user, read-only, all capabilities dropped. Postgres is read-only with only CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID. Memory and process limits on every service (reports worker 1 GB).
- nginx: `limit_req` 30 requests a minute (burst 15) per address on sign-in, MFA and password endpoints, in front of Django's own throttles (checked: the 17th rapid attempt answers 429); headers include CSP without inline code, HSTS (TLS modes), COOP, CORP, frame deny, nosniff.
- Scans on 2026-11-13: `pip-audit` found 44 advisories in Pillow 12.3 and WeasyPrint 69; both were raised (Pillow 13, WeasyPrint 70) and the suite passes; now 0. `npm audit` 0. `bandit`: no high findings; the medium ones (`mark_safe` of server-built SVG, directory mode 0755 for nginx) are reviewed and annotated. OWASP ZAP baseline: see the 2026-11-25 entry below. Checklist: `ASVS_L2_CHECKLIST.md`. Operations: `RUNBOOKS.md`.
- Clean start verified: a brand-new project with empty volumes built and became healthy with `docker compose up --build`; the backup drill restores into a separate project.

- OWASP ZAP 2.17.0 on 2026-11-25 against a clean stack with a self-signed certificate: baseline (passive) scan, 64 rules passed, 0 failures. One real warning, a missing `Cross-Origin-Embedder-Policy` header, is fixed (`require-corp`, added to `nginx/security-headers.inc`). The inline boot splash style was blocked by the CSP (`style-src 'self'`), so it moved to `/boot.css`; the CSP was not loosened. Remaining notes are informational and accepted: the CSRF cookie is readable by the SPA by design (double submit), hashed assets are cacheable (public files), and "suspicious comment" is the word "bug" in an icon name. An unauthenticated API scan of all 174 documented endpoints found nothing beyond the CSRF-cookie note. An authenticated active API scan was not completed (the scanner's auth header was rejected by the proxy); authenticated access control is covered by the test suite.

## Known gaps

- Timing parity for login is best effort (a dummy Argon2 verification), not measured.
- Throttle is per IP; behind a single NAT all users share a bucket.
- Images are tagged, not digest-pinned (Phase 12).
- No ClamAV, uploads and CSV import arrive in later phases.
