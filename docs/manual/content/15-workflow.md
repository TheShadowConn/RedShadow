# The workflow from start to finish

This chapter follows one piece of work from an empty platform to a closed engagement. Each step says who does it, where, and what the status becomes. The steps run in this order. Later chapters give the click-by-click detail.

```
Organisation -> Assets -> Engagement -> Findings (draft) -> Publish
   -> Review and comment -> Fix -> Verification and retest
   -> Review -> Verification -> Close finding -> Close engagement
```

| Step | Who | Where | Result |
|---|---|---|---|
| 1. Organisation | {SA} | Organisations | The client exists, with contacts and an optional logo. |
| 2. Assets | {SA} | Assets, Imports | Assets and their identifiers exist and are **onboarded**. |
| 3. Engagement | {SA} | Engagements | A `Planned` engagement with a **lead**, a team and in-scope assets. |
| 4. Findings | {PT}, {EV} | The engagement, Findings | `Draft` findings with evidence. Only the testing team sees drafts. |
| 5. Publish | {PT}, {EV} | The finding | `Open`. The due date is set from the severity. The assignee is notified. |
| 6. Review and comment | {RO}, {PT} | The finding timeline | Questions and answers recorded as timeline entries. Everyone involved is notified. |
| 7. Fix | {RO} | Remediation queue | `In progress`, then **Submit for verification** with a written note: `Pending verification`. |
| 8. Retest | {PT}, {SA} | Verification, Retests | A retest round with an assessor. Each finding gets **Pass** or **Fail**. |
| 9. Review | {PT}, {SA} | The finding, Retests | The result and the assessor's note are read. A fail returns to step 6 as `Reopened`. |
| 10. Verification | {PT}, {SA} | Verification | **Verify and close** with a written note. |
| 11. Close finding | The same action | The finding | `Closed`. The verifier and note are recorded. |
| 12. Close engagement | {SA} | The engagement | `Reporting`, then `Completed`. Reports are generated. Optionally **Archive**. Untested scenarios need a confirmation. |

## 1. Organisation

A Super Admin creates the organisation (name, industry, contacts, logo). Everything else hangs from it. Organisations are archived, never deleted.

## 2. Assets

Add assets one by one or import a CSV (Chapter 14). An asset has one or more identifiers (URL, IP address, hostname and so on). Imported assets are **not onboarded** until a Super Admin onboards them. Only onboarded assets can join an engagement.

Tag each asset with the department that owns it (Chapter 14). The Departments page then shows who has open findings.

```
Organisation -> Assets (tagged by department) -> Engagement -> Findings
```

A department is not a separate level inside the organisation. It is a tag on the asset, so one asset can belong to two departments. An engagement belongs to the organisation and can include assets of any department.

## 3. Engagement

Create the engagement under the organisation. Choose a **lead**: this is required, and the lead joins the team automatically. A Super Admin can change the lead later at any time with **Change lead** (the previous lead stays on the team until removed). Then:

1. Add the **team** on the Team tab. **Add myself** adds you if you are not on it yet.
2. Link the **in-scope assets** on the Scope and assets tab.
3. Move the status forward: Planned, Scheduled, In progress.

Two different actions end an engagement's life, and they are not the same. **Archive** keeps everything and makes it read-only, and can be undone with **Unarchive**. **Delete** (Super Admin only) removes the engagement and its findings from every screen. You must type the engagement reference to confirm, and the audit log records who deleted it and why. Use Archive unless you really want it gone.

## 4. Findings

While the engagement is **In progress**, testers create findings: title, weakness, asset, CVSS vector or severity, description, recommendation, evidence. A finding starts as a **Draft**. Drafts can be edited freely and are invisible to the remediation team. The severity follows the scale in Chapter 3 (Critical 9.0 and above, High 7.0 to 8.9, Medium 4.0 to 6.9, Low 0.1 to 3.9, Info 0.0).

## 5. Publish

**Publish** makes the finding **Open**. The fix date is set from its severity. From now on the text is part of the record, and the remediation owner (if assigned) is notified.

## 6. Review and comment

The remediation owner reads the finding and asks questions on the timeline. The tester answers. Every entry is kept and cannot be edited. The bell in the header tells each person when something new arrives on a finding they report or own, and again when a finding is due within 3 days or becomes overdue.

## 7. Fix and submit

The remediation owner selects **Start work** (`In progress`), fixes the problem, and selects **Submit for verification** with a written note describing the fix. The finding becomes **Pending verification** and joins the Verification queue.

## 8. Retest

A tester or Super Admin selects the findings in the Verification queue and chooses **Request retest**, naming an **assessor**. The assessor opens the round and records **Pass** or **Fail** for each finding, with a note and optional evidence (Chapter 9).

## 9. Review the result

The tester reads the assessor's notes and evidence. If a finding **failed**, it becomes **Reopened** with the reason and returns to the remediation owner: go back to step 6. This loop can repeat as often as needed. Every pass and fail is kept in the history.

## 10. Verification and close

When the retest passes, a tester or Super Admin confirms with **Verify and close** and a note (a pass recorded in a retest runs this same move). Findings can also be verified directly without a round (Chapter 9).

## 11. Close the finding

The finding is **Closed**. The person who verified it and their note are recorded. A Super Admin can still reopen it later, with a reason. Other final states exist for special cases: **Risk accepted** (Super Admin, with an expiry date), **False positive** and **Duplicate**.

## 12. Close the engagement

When every finding is closed or otherwise settled:

1. Move the engagement to **Reporting**.
2. Generate the **reports** (PDF and CSV) from the Reports tab.
3. Move it to **Completed**.
4. Optionally **Archive** it so it becomes read-only.

At every step the action is written to the audit log with who, what and when.
