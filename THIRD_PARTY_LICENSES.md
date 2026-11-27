# Third-party licenses

RedShadow depends on the open-source components below. They are installed from their package registries at build time and keep their own licenses. License names are listed for orientation; check each package's own license text before redistributing builds. Versions are in `backend/requirements.txt` and `frontend/package-lock.json`.

## Backend (Python)

| Package | License |
|---|---|
| Django | BSD-3-Clause |
| Django REST framework | BSD-3-Clause |
| psycopg | LGPL-3.0 (used unmodified as a dependency) |
| Celery | BSD-3-Clause |
| redis-py | MIT |
| gunicorn | MIT |
| argon2-cffi | MIT |
| pyotp | MIT |
| segno | BSD-3-Clause |
| cryptography | Apache-2.0 or BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| cvss | LGPL-3.0 (used unmodified as a dependency) |
| defusedxml | PSF-2.0 |
| nh3 | MIT |
| Markdown | BSD-3-Clause |
| WeasyPrint | BSD-3-Clause |
| pytest, pytest-django, ruff, pypdf (development) | MIT, BSD-3-Clause, MIT, BSD-3-Clause |

## Frontend (npm)

| Package | License |
|---|---|
| React, React DOM | MIT |
| React Router | MIT |
| TanStack Query | MIT |
| react-markdown | MIT |
| lucide-react | ISC |
| Tailwind CSS | MIT |
| Vite, @vitejs/plugin-react | MIT |
| TypeScript | Apache-2.0 |
| @fontsource-variable/geist, geist-mono | OFL-1.1 (font), MIT (package) |

## Fonts, data and images

- **Geist and Geist Mono**: SIL Open Font License 1.1, copy in `backend/apps/reports/assets/fonts/OFL.txt`.
- **CWE list** (`backend/apps/findings/data/cwe.json`): names from the Common Weakness Enumeration, (c) The MITRE Corporation, used under the CWE Terms of Use (https://cwe.mitre.org/about/termsofuse.html).
- **Brand assets** (logos, wordmarks, favicons): **not** open source. See `TRADEMARKS.md`.

## Container images

PostgreSQL, Redis, Nginx, Python and Node base images keep their own licenses (PostgreSQL License, BSD-3-Clause, BSD-2-Clause, PSF License, MIT).

> This list is a good-faith summary, not legal advice. If you find an error, please open an issue.
