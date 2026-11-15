# CSV import and export columns {: .appendix }

## Import fields

| Field | Required | Accepted column names (examples) | Notes |
|---|---|---|---|
| Title | Yes | title, name, finding, issue, vulnerability, summary | Up to 200 characters. |
| Severity | Unless a CVSS vector is mapped | severity, risk, priority, rating | Critical, High, Medium, Low or Info. |
| CVSS vector | No | cvss, cvss vector, vector | Valid 3.1 or 4.0 vector. Sets score and severity. |
| Description | No | description, details, synopsis | Markdown. |
| Recommendation | No | recommendation, solution, remediation, fix | Needed before publishing. |
| Technical details | No | technical details, technical | Testing team only. |
| Proof of concept | No | poc, proof of concept, steps to reproduce | |
| Endpoint | No | endpoint, url, path, location | Up to 500 characters. |
| Asset | No | asset, asset name, host, target, hostname, ip, ip address, affected asset, affected host | Asset name, IP address or URL, matched against the in-scope assets. |
| CWE | No | cwe, cwe id | A number or `CWE-79` style. |
| Discovered date | No | discovered, date, found | `YYYY-MM-DD`. |
| References | No | references, links, urls | Links, optionally `Label|URL`, separated by semicolons or new lines. |

The downloadable template has three example rows: an asset by name (`Acme shop`), by IP address (`10.0.0.5`) and by URL (`https://shop.acme.test`).

**Limits:** CSV, TSV or TXT; UTF-8 or Windows-1252; 10 MB; 50,000 rows; 60 columns; 100,000 characters per cell.

## Export columns

`reference`, `engagement`, `engagement_name`, `title`, `severity`, `cvss_score`, `cvss_vector`, `status`, `asset`, `endpoint`, `cwe`, `assigned_pentester`, `remediation_owner`, `discovered_at`, `due_date`, `created_at`, `description`, `recommendation`, `technical_details`, `poc`, `references`.

Exports contain only the findings the requester can see, with at most 50,000 rows.
