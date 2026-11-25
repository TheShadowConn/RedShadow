# Remediation Owner guide

{RO} The Remediation Owner fixes what the testers find. You see only the findings assigned to you, on the engagements you belong to. You can read the technical details and proof of concept, because you need them to reproduce and fix the issue, but you cannot see testers' private technical notes.

## Your queue

After you sign in you land on the **Remediation** dashboard. Select **Open my queue** (or **Remediation** in the menu) for the findings waiting for a fix, overdue ones first.

![The remediation queue](24-remediation-queue.png)

- The top tiles count **All**, **Open**, **In progress**, **Reopened** and **Overdue**. Select a tile to filter.
- Filter by engagement, severity or **Assigned to me**.
- The **Deadline** column shows the due date and how many days remain. Overdue items are marked in red.
- The button on each row is the next step for that finding: **Start work** or **Submit for verification**.

## Work a finding

![A finding in progress](26-remediation-finding.png)

1. Open the finding. Read the description, recommendation, technical details and proof of concept.
2. Select **Start work**. The status becomes **In progress** and the timeline records who started and when.
3. Fix the issue in your environment. Use **Pause work** if you must put it back to **Open**.
4. Add a **remediation note** on the **Notes** tab to share progress: what you changed, which release, any question for the testers.
5. Upload **evidence** on the **Evidence** tab if useful, such as a screenshot of the new configuration.
6. Select **Submit for verification**.

### Submit for verification

![The submit for verification dialog](25-submit-verification.png)

- Write **what was fixed and where**, so the tester can check it. At least 5 characters are required.
- The text is saved on the finding and **cannot be edited** afterwards.
- The status becomes **Pending verification**. The finding is locked until the testers decide.

## After you submit

| Outcome | What you see | What to do |
|---|---|---|
| Verification **passed** | Status **Closed**. The verification note shows who checked it. | Nothing. |
| Verification **failed** | Status **Reopened** with the tester's reason. | Read the reason, fix again, submit again. |
| Finding **reopened** later | Status **Reopened**. | Treat as a new fix request. The original due date stays. |

Check your queue and the dashboard for these changes. The **Timeline** tab always shows the full history.

## Dashboard

The **Remediation** dashboard shows what is open for you, what is overdue, what is due in 7 days, what awaits verification and what you closed in the last 30 days.

## What you cannot do

You cannot create findings, publish, verify, close, reopen, accept risk, import CSV or see other people's findings. If something looks wrong, add a remediation note or contact the engagement lead.

> **Tip:** Bookmark the **Remediation** page. It is your daily starting point and works well on a phone.
