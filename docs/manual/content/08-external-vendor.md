# External Vendor guide

{EV} The External Vendor role is for outside testers who work on part of an engagement. You upload and manage **your own** findings. You do not see other testers' findings, internal notes, the audit log or user lists.

## What you can and cannot do

| You can | You cannot |
|---|---|
| See the organisations, assets and engagements you are added to, and the shared notes and documents of those engagements. | See findings of other testers, team-only notes, users, roles or the audit log. |
| Create, edit, duplicate and **publish** your own findings. | Verify fixes, close, reopen, accept risk, assign people, delete or bulk update findings. |
| Upload evidence, delete your own evidence, write technical notes on your findings. | Generate PDF reports. |
| Import findings from CSV and export your own findings. | See other people's import files. |
| Use finding templates and the calendar. | Change engagements, scope or the team. |

> **Note:** If you are added to more than one engagement, your list shows your own findings from all of them together. You never see another vendor's findings, even on the same engagement.

## Your dashboard

![The External testing dashboard](27-vendor-dashboard.png)

The **External testing** dashboard shows your open findings, drafts, overdue items, how many findings you uploaded and any retest rounds that involve your findings.

## Report a finding

1. Open **Findings** and select **New finding**.
2. Choose the engagement (only engagements you belong to appear), then fill in the same fields as a Pentester: title, weakness, asset, CVSS or severity, description, recommendation, technical details, proof of concept and references (see Chapter 6).
3. Save. The finding is a **Draft** that only you and the testing team can see.
4. Attach **evidence** and add a **technical note** if needed.
5. Select **Publish** when it is ready. It becomes **Open** and the fix date starts.

![Your findings list shows only your own work](28-vendor-findings.png)

> **Tip:** Publish only findings that are complete. A recommendation is required. After publishing a finding can still be edited while it is Open, In progress or Reopened, but not after it is submitted for verification or closed.

## Import findings from CSV

1. Open **Imports** and select **New import**.
2. Choose the engagement and your CSV file, map the columns, and read the **Check** result.
3. Fix problems in your file using the problem report, or import only the valid rows.
4. The imported findings are **drafts reported by you**. Review them in **Findings** and publish them.

Other vendors cannot see your import files or rows, and the duplicate check does not reveal their findings. Details of the import steps are in Chapter 6.

## What happens after you publish

- The Pentester lead assigns a remediation owner and tracks the fix.
- When the owner submits a fix, a Pentester or Admin verifies it. If the findings you reported are part of a retest round, you can see the round and its result.
- You can follow the **Timeline** of each of your findings.

## Leaving the engagement

When the engagement ends, an administrator removes you from the team or archives the engagement. You lose access immediately and your history stays in the audit log.
