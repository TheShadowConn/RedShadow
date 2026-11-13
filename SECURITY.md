# Security policy

RedShadow stores sensitive penetration-test data, so security reports are taken seriously.

## Reporting a vulnerability

**Do not open a public issue for a vulnerability.**

Use GitHub private vulnerability reporting: open the **Security** tab of https://github.com/TheShadowConn/RedShadow and choose **Report a vulnerability**.

Please include the version (see the About page), steps to reproduce, the impact you expect and any proof of concept. You will get an acknowledgement within 7 days. Fixes are released as soon as they are verified, and you are credited unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes.

## Scope

In scope: authentication, sessions, access control, file uploads, import, reporting, the audit log, the Docker deployment.
Out of scope: attacks that need prior administrator access, denial of service by sheer volume, and findings about a deployment that ignores `docs/SECURITY.md` and `docs/RUNBOOKS.md`.

## Hardening and design notes

See [docs/SECURITY.md](docs/SECURITY.md), [docs/ASVS_L2_CHECKLIST.md](docs/ASVS_L2_CHECKLIST.md) and [docs/RUNBOOKS.md](docs/RUNBOOKS.md). An OWASP ZAP baseline scan has not been run yet. Contributions that add one are welcome.
