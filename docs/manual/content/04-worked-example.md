# Worked example: Acme web test Q4

This chapter follows one engagement from setup to closure. The same data appears in the role chapters that follow, so you can match each screen to the step that created it.

> **Example:** **Acme Corp** is a retailer. Its holiday peak starts in two weeks, so it asked for a web test of the customer shop and the order API. Priya Pentester leads the test. Sam Tester helps. Vera Vendor, an outside tester, tests the order API. Ravi Remediation fixes what is found.

| Person | Role | Part in the story |
|---|---|---|
| Admin | {SA} | Sets up Acme, the engagement and the team. Reads the audit log. |
| Priya Pentester | {PT} | Lead tester. Finds the critical and high issues, verifies fixes. |
| Sam Tester | {PT} | Second tester on the team. |
| Ravi Remediation | {RO} | Owns the fixes for the shop. |
| Vera Vendor | {EV} | Tests the order API, imports a CSV, publishes her findings. |

## Timeline

| Step | Who | What happens | Where |
|---|---|---|---|
| 1 | {SA} | Creates organisation **Acme Corp**, a contact, three assets (Acme Shop, Orders API, Build server). | Organisations |
| 2 | {SA} | Creates engagement `RS-E-2026-0001`, links the assets (the build server is out of scope), sets the dates and lead. | Engagements |
| 3 | {SA} | Adds Priya (lead), Sam, Ravi and Vera to the team, moves the engagement to **In progress**. | Engagement, Team |
| 4 | {PT} | Records SQL injection `RS-F-000001` (Critical) and stored XSS `RS-F-000002` (High) and publishes them. Assigns Ravi as remediation owner. | Findings |
| 5 | {PT} | Marks a scanner result as a **false positive** with a reason. | Finding page |
| 6 | {EV} | Reports an IDOR in the order API (`RS-F-000008`) and publishes it, then imports a CSV of more findings. | Findings, Imports |
| 7 | {RO} | Starts work on `RS-F-000001`, adds a remediation note, submits the fix for verification. Does the same for the XSS. | Remediation |
| 8 | {PT} | Requests a **retest round** `RS-E-2026-0001-R1` for the two submitted fixes. | Verification |
| 9 | {PT} | As assessor, records **Pass** or **Fail** for each finding with a reason. A pass closes the finding. | Retests |
| 10 | {SA} | Verifies the audit chain, generates the client report. | Audit, Reports |

![The Acme engagement, overview tab](04-engagement-overview.png)

The following chapters show each of these steps for the role that performs it. Read your own chapter first, then Chapter 9 (verification and retests) and Chapter 10 (audit) to see how the pieces fit together.
