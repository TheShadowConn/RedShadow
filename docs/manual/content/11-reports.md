# Reports and exports

RedShadow builds **PDF reports** for clients and **CSV exports** for analysis. Both are created in the background from the findings the requester is allowed to see, so a report can never contain more than its author may read.

## Create a report

![The New report dialog](13-new-report.png)

1. Open **Reports** (or an engagement's **Reports** tab) and select **New report**.
2. Choose the **engagement**.
3. Choose the **format**: **PDF report** (a designed document to hand to the client) or **CSV export** (one row per finding, for spreadsheets).
4. Choose the **audience**:
   - **Client-facing**: no proof of concept, technical details or technical notes.
   - **Internal**: adds technical details, proof of concept and technical notes. Do not send this version to the client.
5. Choose a **template**, an optional **title**, a **version** label (for example `1.0`) and a **classification** such as Confidential.
6. Optionally limit the **severities** and **statuses** included. Drafts are never included.
7. Select **Create report**. The report is built in the background and appears in the list when ready.

Download it from the list. Files are kept for a limited time (90 days by default), and every download is audited.

> **Note:** Who may create which report depends on the role. {SA} and {PT} can create PDF and CSV reports. {RO} can export CSV of their findings. {EV} can export CSV of their own findings but cannot create PDF reports by default.

## What the PDF contains

A report is assembled from sections. The default template includes all of them, in this order:

| Section | Content |
|---|---|
| Cover | Client, engagement, testing period, version, classification, overall risk posture. |
| Document control | Version, date, distribution, classification. |
| Executive summary | Plain-language result and the number of findings by severity. |
| Engagement overview | Dates, team, type, objectives. |
| Scope | In-scope and out-of-scope assets and statements. |
| Methodology and rating scale | How the test was done and how severity is rated. |
| Findings at a glance | One table of all findings with severity and status. |
| Severity and status distribution | Charts. |
| Detailed findings | One block per finding: description, recommendation, references and, in the internal edition, proof of concept. |
| Remediation roadmap | What to fix first, with due dates. |
| Retest results | Outcome of retest rounds. |
| Appendix | Supporting material. |

Reports use only fonts and images built into RedShadow. A finding cannot make the report fetch anything from the internet or read files from the server.

## Report styles

{SA} Open **Report styles** to manage templates.

- **Name**: shown in the picker.
- **Accent colour**: used for the cover bar, numbers and rules.
- **Font**: Geist (sans-serif) or DejaVu Serif.
- **Footer text**: printed bottom left on every page. Empty prints the engagement reference.
- **Sections**: tick which sections to include and use the arrows to reorder them. **Detailed findings** is always included.
- **Logo**: upload a PNG or JPEG for the cover. It is re-encoded for safety.
- A built-in default template cannot be deleted.

## CSV exports

- **From the Findings page**: **Export CSV** exports what you see with your filters.
- **From Reports**: create a CSV report for an engagement.
- The file lists reference, engagement, title, severity, CVSS, status, asset, endpoint, CWE, people, dates and text fields (Appendix C).
- Values that begin with `=`, `+`, `-` or `@` are prefixed so a spreadsheet will not run them as formulas.

## Choosing the right output

| Need | Choose |
|---|---|
| A document for the client | PDF, client-facing, with your classification and version. |
| A technical handover to the remediation team | PDF, internal, or CSV with technical details. |
| Analysis in a spreadsheet | CSV export. |
| Evidence of review for an auditor | Audit explorer export (Chapter 10). |
