# Core concepts

## The building blocks

| Concept | What it is | Notes |
|---|---|---|
| **Organisation** | A client or business unit you test. | Archived, never deleted, so history stays intact. Holds contacts, assets and an optional logo. |
| **Asset** | Something that can be tested: web app, API, host, network range, mobile app, cloud account, source repo, wireless, IoT, Active Directory, thick client, other. | Has an environment (production, staging, development), a criticality from 1 to 5 and tags, which mark the departments that own it. |
| **Engagement** | One penetration test for one organisation. | Reference such as `RS-E-2026-0001`. Has dates, a lead, scope, rules of engagement, team and a status. |
| **Finding** | One vulnerability inside an engagement. | Reference such as `RS-F-000001`. Has severity, status, owner, due date, evidence and notes. |
| **Evidence** | A file attached to a finding. | Screenshots, PDFs, packet captures and more. Checked and stored safely. |
| **Note** | Text added to an engagement or finding. | Never edited or deleted after posting. |
| **Retest round** | A batch of findings sent to an assessor to confirm the fix. | Reference such as `RS-E-2026-0001-R1`. |
| **Audit event** | A tamper-evident record of an action or a refusal. | Written automatically. |

## Engagement status

An engagement moves through a fixed set of statuses. The buttons on the engagement page offer only the moves that are allowed.

| From | Can move to |
|---|---|
| Planned | Scheduled, Cancelled |
| Scheduled | Planned, In progress, Cancelled |
| In progress | Reporting, Cancelled |
| Reporting | In progress, Completed |
| Completed | Reporting |
| Cancelled | Planned |

Only **Completed** or **Cancelled** engagements can be **archived**. Archived engagements and their findings are read-only. **Unarchive** restores the earlier status. An engagement is shown as **overdue** when its end date has passed and it is still planned, scheduled, in progress or in reporting.

## Who sees what: scope

RedShadow combines two ideas.

1. **Role permissions** say what a person may do: create findings, verify fixes, export CSV.
2. **Scope** says where: on which engagements, and which findings inside them.

- {SA} sees every engagement.
- {PT} {RO} {EV} see an engagement only when they are on its **team**.
- Inside an engagement the **finding access** setting narrows what a member sees.
  - **All findings**: everything the role may view (drafts only if the role may see drafts).
  - **Assigned findings only**: findings where the person is the remediation owner or assigned pentester. The default for {RO}.
  - **Own findings only**: findings the person reported or imported, plus findings assigned to them. The default for {EV}.
- A team membership can override the role's default for that one engagement.

> **Example:** Vera Vendor is an External Vendor on the Acme engagement. She reports finding RS-F-000008. Another vendor, Victor, cannot open RS-F-000008 even with the link. Priya, the lead Pentester, sees both. If Vera is also added to a second engagement, she sees her own findings on both engagements in one list.

## Findings

### Severity, CVSS and CWE

- Enter a **CVSS vector** (versions 3.1 and 4.0) and RedShadow calculates the base score and sets the severity. You cannot enter a score by hand, and you cannot set a severity that conflicts with the vector.
- The base score decides the severity like this. The scale is also shown on the finding form.

| Severity | CVSS base score |
|---|---|
| Critical | 9.0 to 10.0 |
| High | 7.0 to 8.9 |
| Medium | 4.0 to 6.9 |
| Low | 0.1 to 3.9 |
| Info | 0.0 |

- Without a vector, choose the severity yourself: **Critical, High, Medium, Low** or **Info**.
- Choose a **CWE** weakness from the built-in list of common weaknesses by typing a number or a name such as `89` or `injection`.

### Status lifecycle

```
Draft -> Open -> In progress -> Pending verification -> Closed
                      ^                   |
                      +----- Reopened <---+   (verification failed)
```

Other endings: **Risk accepted**, **False positive** and **Duplicate**. Appendix B lists every allowed move, who may make it and whether a written reason is required.

| Status | Meaning | Editable |
|---|---|---|
| Draft | Visible to the testing team only. | Yes |
| Open | Published. The clock for the fix date is running. | Yes |
| In progress | The owner is working on the fix. | Yes |
| Pending verification | The owner submitted a fix. Waiting for a retest. | No |
| Reopened | A fix failed verification, or a closed finding was reopened. | Yes |
| Closed | Verified fixed. | No |
| Risk accepted | The client accepts the risk until an expiry date. | No |
| False positive | Not a real issue. Reason recorded. | No |
| Duplicate | Same as another finding in the engagement. | No |

### Fix dates and SLA

When a finding is published it gets a **due date**: the publish date plus the target for its severity.

| Severity | Default fix target |
|---|---|
| Critical | 7 days |
| High | 30 days |
| Medium | 90 days |
| Low | 180 days |
| Info | No target |

Administrators can change these targets in the deployment settings. An hourly job flags findings that pass their due date. Risk acceptance has an expiry (at most 365 days by default); when it passes, the finding **reopens** by itself.

### Notes and the timeline

- **Technical notes**: testing team only.
- **Remediation notes**: visible to everyone who can see the finding.
- **Verification notes**: written automatically when a fix is verified, failed or a finding is closed or reopened. They cannot be posted by hand.
- The **Timeline** tab lists every step: published, started, submitted for verification, verified, reopened.

### Evidence

Evidence accepts PNG, JPEG, GIF, WebP, PDF, packet captures (pcap, pcapng), ZIP, DOCX, XLSX and plain text files (txt, log, csv, json, xml), up to **25 MB** each. RedShadow checks the real file type, re-encodes images to strip hidden data, refuses HTML and SVG, and records every download in the audit log.

## Audit

Every create, change, refusal, sign-in and download is written to the audit log with who, what, when and from which engagement. Entries are chained with hashes so any later change is detectable (Chapter 10).
