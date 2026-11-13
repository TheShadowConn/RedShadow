# ADR-0017 Dashboards: scoped selectors, no stored numbers, charts without a library

Status: accepted (2026-11-13, Phase 10)

**Decision:** `GET /dashboards/admin|pentester|remediation` compute every figure on request from `scope_findings`, `scope_engagements` and `scope_audit` with database aggregation. There are no dashboard tables and no caching. Each endpoint needs its own platform permission (`dashboards.*`). A test asserts, for each role, that every count equals the same filter on the matching list endpoint. The screens draw their charts as plain SVG and HTML (no Recharts); each chart has numbers on the marks, a legend, and a table view.

**Why:** Reusing the list selectors is the only way the numbers cannot disagree with the lists or leak a finding the user cannot open. At team scale the queries are cheap, so stored aggregates would only add staleness. The strict CSP (`style-src 'self'`) already led to an in-house calendar (ADR-0015); a chart library would add weight and the same inline-style risk for four simple charts.

**Consequences:** Dashboards cost a handful of queries per load (a test caps this); the screen refreshes once a minute. Very large installations would need materialised counts, which is out of scope.
