# Troubleshooting and FAQ

## Signing in

**I cannot sign in and the message is generic.**
The message is the same for a wrong password, an unknown email and a locked account. Wait 15 minutes if you failed five times, or ask an administrator to check that your account is active.

**I lost my two-step device and my recovery codes.**
Ask a Super Admin to **Reset two-step verification**. You will enrol again at the next sign-in.

**I was signed out suddenly.**
Sessions end after 30 minutes without activity and after 12 hours in total. They also end when an administrator changes your role or engagement access, so the new access applies at once.

## What I can and cannot see

**I cannot find an engagement or a finding.**
You may not be on the engagement's team, or the finding is not assigned to you, or you are an External Vendor and it was reported by someone else. The application hides what is out of scope. Ask the engagement lead to check the **Team** tab.

**A button is missing.**
Buttons appear only when your role and the finding's status allow the action. Appendix B lists who can make each status move.

**I see a "forbidden" message.**
You can see the item but not do that action. Ask someone with the right role.

## Findings

**I cannot publish my draft.**
A recommendation is required before publishing. Check the form for a message next to the field.

**I cannot edit a finding.**
Findings are editable in Draft, Open, In progress and Reopened. After **Pending verification**, **Closed**, **Risk accepted**, **False positive** or **Duplicate** the text is locked. Reopen it first if you have the right.

**I get a conflict message when saving.**
Someone else saved first. Reload the page and apply your change again.

**The severity will not change.**
When a CVSS vector is set, the severity follows it. Clear the vector first to set a severity by hand.

**The asset is not offered.**
Only assets linked to the engagement as **in scope** can be chosen. Ask an administrator to link the asset on the **Scope and assets** tab.

## Evidence and files

**My upload was refused.**
Check the type (images, PDF, pcap, ZIP, DOCX, XLSX or text), the size (25 MB) and that the file is what its extension says. HTML and SVG files are never accepted.

## Imports

**The import says the file is not valid.**
Save it as CSV (UTF-8), keep it under 10 MB and 50,000 rows, and keep a header row. Split larger files.

**Rows are marked as errors.**
Select **Download problem report**, fix the lines named in the report and import again. Common causes: empty title, a severity that is not one of Critical, High, Medium, Low or Info, a date not written as `YYYY-MM-DD`, or an asset name that is not in scope.

**Duplicates were found.**
RedShadow compares title, asset, endpoint and weakness inside the engagement. Choose to skip them or import them anyway.

## Retests and verification

**I cannot record a retest result.**
Only the assigned assessor can record results. Ask the round's owner to **Reassign** it.

**Pass and close is greyed out.**
Write at least 5 characters explaining how you verified.

## Reports

**My report is still building.**
Reports are built in the background. Refresh the list after a moment. If it fails, create it again and check the filters.

**The report is missing technical details.**
Client-facing reports leave them out on purpose. Choose the **Internal** audience if you may see them.

## Audit

**The chain shows as broken.**
Do not delete anything. Follow `docs/RUNBOOKS.md` and compare with a backup from before the incident.

## Getting help

Open **About** and note the version and build. Give your administrator the time of the problem, the page and the message you saw.
