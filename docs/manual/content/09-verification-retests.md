# Verification, retests and validation

This chapter explains how a fix becomes a **verified** fix, and the different kinds of checking RedShadow performs. Four ideas are easy to confuse:

| Term | What is checked | Where |
|---|---|---|
| **Validation** | That data is well-formed and allowed: required fields, CVSS vectors, file types, CSV rows. | Forms, imports, uploads |
| **Verification** | That a fix really works. A person confirms it and writes down how. | Finding page, Verification queue |
| **Retest** | A formal round in which an assessor tests a batch of fixes and records a result for each. | Retests |
| **Integrity check** | That the audit log has not been altered. | Audit |

## The verification workflow

```
Open -> In progress -> Pending verification -> (retest) -> Closed
                                      |                      
                                      +-> Reopened (failed) -> In progress ...
```

1. The {RO} submits the fix with a written note. The finding becomes **Pending verification** and appears in the **Verification** queue.
2. A {PT} or {SA} decides, either directly or through a retest round.
3. **Pass**: the finding is **Closed** and the verifier is recorded with their note.
4. **Fail**: the finding is **Reopened** with the reason and returns to the remediation owner.

> **Warning:** A note is always required to pass, fail, close or reopen a finding. It cannot be edited later. Write what you tested and what you saw, for example "Replayed the payload against /search on staging. The server now returns a 400."

## Verify one finding directly

![A finding waiting for verification](17-finding-detail.png)

1. Open the finding in **Pending verification**.
2. Select **Verify and close** or **Fail verification**.
3. Enter the note and confirm.

The same two buttons exist on each row of the **Verification** queue.

## Retest rounds

Use a retest round when several fixes must be tested together, or when someone other than you will test them. Each round has a reference such as `RS-E-2026-0001-R1`, one **assessor**, a list of findings and a note.

### Request a round

![The verification queue with checkboxes](18-verification.png)

1. Open **Verification**.
2. Tick the findings to include (all from one engagement).
3. Select **Request retest**.
4. Choose the **assessor**. Only people who may record results are offered.
5. Add a note, for example "Retest after release 4.18", and confirm.

The findings stay **Pending verification** and show a banner such as "In retest RS-E-2026-0001-R1, assigned to Priya Pentester".

### Record the results

Only the assigned assessor can record results.

![A retest round with two findings waiting](20-retest-pass.png)

1. Open **Retests** and select the round. Use **Assigned to me** to filter your rounds.
2. For each finding select **Pass** or **Fail**.
3. Explain **how you verified** (at least 5 characters). The note is stored on the finding.
4. Select **Pass and close** or **Fail and reopen**.

The round summary updates after each result, for example "1 passed, 1 failed, 0 pending". When no item is pending the round is complete.

### Other actions on a round

- **Reassign**: give the round to another eligible assessor.
- **Cancel round**: stops the round. The findings stay pending verification and can be verified directly.

![The list of retest rounds](19-retests.png)

## Closing without a retest

A finding that no longer applies can be **Closed** directly with a reason, by a person who may close findings. Use verification for fixes and closing for everything else.

## Risk acceptance

Sometimes the client decides to live with a risk. A {SA} (or a role granted the right) can set the finding to **Risk accepted** with a reason and an **expiry date**, at most 365 days away by default. When the date passes, RedShadow **reopens** the finding automatically and the fix clock continues.

## Reopening

A closed, risk-accepted, false-positive or duplicate finding can be **Reopened** with a reason when new facts appear. The original due date is kept.

## Validation in practice

| Where | What is validated |
|---|---|
| New finding | Title and severity (or CVSS vector) are required. The vector must be valid CVSS 3.1 or 4.0. The recommendation is required before publishing. Assignees must be engagement members. The asset must be in scope. |
| Edits | The version you loaded must still be current. If not, you get a conflict and reload. |
| Evidence | Real file type, allowed type list, 25 MB limit, images re-encoded. |
| CSV import | Per row: title, severity or CVSS, CWE, date, asset, endpoint length, duplicates. See Chapter 6. |
| Status changes | Only moves in the state table (Appendix B), by people allowed to make them, with the required note. |
| Passwords | At least 12 characters, no common passwords. |

Errors are shown next to the field and in plain language. The same rules are applied by the server, so nothing depends on the screen.
