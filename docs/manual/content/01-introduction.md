# Introduction and roles

RedShadow is a self-hosted platform for managing penetration tests from the first scoping call to the verified fix. It keeps organisations, assets, engagements, findings, evidence, retests, reports and an append-only audit trail in one place, and it shows every person only the work they are meant to see.

<p class="lead">This manual explains how to use RedShadow day to day. It follows one fictional engagement, <strong>Acme web test Q4</strong>, through all four roles so that each workflow is shown with real screens and real results.</p>

## What you can do with RedShadow

- **Plan**: record clients, their assets and each engagement with scope, rules of engagement, team and dates. Follow engagements on a calendar.
- **Test**: create findings with CVSS scoring and CWE weaknesses, attach evidence, write technical notes and import findings from CSV.
- **Fix**: assign findings to a remediation owner, track due dates against SLA targets and keep a timeline of every step.
- **Verify**: request retest rounds, record pass or fail with a written reason and close findings only after verification.
- **Prove**: every change and every refusal is written to a hash-chained audit log that can be verified at any time.
- **Report**: produce client-ready PDF reports and CSV exports that contain only what the requester may see.

## The four roles

RedShadow ships with four system roles. Administrators can change what a role holds or create custom roles, but the defaults below are what this manual describes.

{SA} runs the platform. Creates users, roles, organisations and engagements, sees every engagement, reads the whole audit log and accepts risk.

{PT} works on engagements they are a member of. Creates and publishes findings, uploads evidence, imports CSV, verifies fixes and runs retests.

{RO} receives findings assigned to them. Starts work, adds remediation notes and evidence, and submits the fix for verification.

{EV} is an outside tester. Creates, imports and publishes their own findings on engagements they are added to. They never see other people's findings.

[[CAPABILITIES]]

> **Note:** "Yes" means the role holds the permission by default. Access also depends on **scope**: a Pentester or Remediation Owner sees an engagement only after being added to its team. Chapter 3 explains scope, and Appendix A lists every permission.

## How access is enforced

Every screen hides what you cannot use, but hiding is only a convenience. The server checks your role and your engagement membership on every request. If something is outside your scope the application answers as if it does not exist, so you cannot discover the existence of other teams' work by guessing links.

## Conventions used in this manual

- Buttons and menu names appear in **bold**. File and field values appear in `code`.
- Coloured role badges mark who a step applies to: {SA} {PT} {RO} {EV}.
- Callouts marked **Tip**, **Note** and **Warning** highlight shortcuts, background and risks.
- All screenshots come from a demonstration installation. Names, organisations and findings are fictional.
