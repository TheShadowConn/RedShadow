# OWASP ASVS L2 pass (Phase 12, 2026-11-13)

Self-assessment by chapter against what is built and tested. "Evidence" names a test file, a script or a document. Pass means a control exists and is tested or demonstrated; Partial means a control exists with a stated gap; Gap means not built (reason given).

| Chapter | Result | Evidence and notes |
|---|---|---|
| V1 Architecture, threat model | Pass | `BLUEPRINT.md` section 6, ADRs 0001 to 0017, `SECURITY.md` |
| V2 Authentication | Partial | Argon2id, 12-character minimum, common-password list, lockout, constant-style errors, TOTP MFA with replay protection and encrypted secret (`tests/test_auth.py`). Gaps: no breached-password online check; no self-service password reset by email (admin reset only, by design); no self-service MFA disable |
| V3 Session | Pass | Server-side sessions, key rotation on sign-in, idle 30 min, absolute 12 h, instant revoke by `session_version`, HttpOnly, SameSite=Lax, Secure with TLS. Gap: a user cannot list or end their own other sessions |
| V4 Access control | Pass | RBAC plus object scoping, default deny, anti-escalation, role matrix and route-coverage tests (`tests/test_rbac.py`), isolation tests per module, dashboards and reports reuse the scoped selectors |
| V5 Validation, encoding | Pass | Strict serializers (unknown fields rejected), CSV and upload validation, markdown through an allow-list, autoescaped templates, formula-safe CSV, PDF fetcher allows only `data:` and bundled fonts (`tests/test_reports.py`) |
| V6 Cryptography | Partial | Fernet for MFA secrets, Argon2id, TLS 1.2 and 1.3, SHA-256 hash chain for audit, SHA-256 for files and reports. Gap: key rotation (`mfa_key`, `secret_key`) is a manual procedure (`RUNBOOKS.md`) |
| V7 Errors, logging | Pass | Hash-chained append-only audit with verification task and banner, request ids, log redaction, generic error pages |
| V8 Data protection | Partial | `no-store` and `nosniff` on downloads, soft delete and purge, report expiry. Gap: backups contain secrets (documented, protect them); no per-engagement storage quota |
| V9 Communications | Pass | TLS 1.2+ with HSTS, internal-only service network, TLS modes documented. Note: the default certificate is self-signed |
| V10 Malicious code | Gap (accepted) | ClamAV was declined in Phase 3. Files are never executed or rendered by the server; images are re-encoded; archives are inspected not extracted |
| V11 Business logic | Pass | Finding state machine with locks and version checks (`tests/test_lifecycle.py`), one import and one report build at a time per engagement, caps on rows, findings and images |
| V12 Files | Pass | Content-sniffed allow-list, re-encoding, size limits, random storage keys, authorised downloads through `X-Accel-Redirect` (`tests/test_files.py`) |
| V13 API | Pass | JSON only, CSRF on every unsafe request, per-action permissions, pagination caps, nginx and Django throttles on sign-in endpoints |
| V14 Configuration | Partial | Images pinned by digest, all capabilities dropped (database keeps only the five it needs), read-only root filesystems, memory and process limits, secrets in a volume, security headers (CSP without inline code, COOP, CORP, frame deny). Scans: `bandit` (0 high, medium findings reviewed and annotated), `pip-audit` (Pillow and WeasyPrint updated, 0 known vulnerabilities), `npm audit` (0). Gap: the OWASP ZAP baseline scan was not run (large image not downloaded); see `PROJECT_STATUS.md` |

Re-run before a release: `make lint`, `make test`, `make smoke`, `make drill`, `pip-audit -r backend/requirements.txt`, `npm audit` in `frontend/`, `bandit -r backend/apps`.
