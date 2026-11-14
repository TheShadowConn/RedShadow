# Roadmap

RedShadow 1.0 covers the full engagement lifecycle. This is what comes next. Items are ideas, not promises. Open a discussion to vote or to propose something.

## Next

- **Demo mode**: a one-command seeded installation with fictional data so you can try every role in minutes.
- **End-to-end tests**: browser tests (Playwright) for the main workflows, run in CI.
- **OWASP ZAP baseline scan** and a published result.
- **CI and dependencies**: scheduled dependency updates and a coverage report.

## Later

- Notifications (email and in-app) for assignments, verification and due dates.
- Comments with mentions and saved filters.
- DOCX report export.
- Engagement templates and checklists (for example OWASP WSTG).
- Single sign-on (OIDC, SAML).
- Metrics endpoint and an admin health view.
- Per-engagement control over what vendors can see (documents, shared notes).
- Automated, off-machine backups.

## Good first issues

- Add a screenshot or translation to the user manual.
- Improve an empty state or an error message.
- Add a missing test for a service in `backend/apps`.
- Add a keyboard shortcut hint to a screen.
- Fix a typo or unclear sentence in `docs/`.

## Out of scope for now

Hosted SaaS, scanning tools, and exploit features. RedShadow manages pentests, it does not perform them.
