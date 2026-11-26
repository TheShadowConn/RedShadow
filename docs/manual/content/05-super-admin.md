# Super Admin guide

{SA} The Super Admin sets up the platform and the engagements, keeps access tidy and is the final authority on the audit log. This chapter covers users, roles, organisations, engagements, the calendar and the dashboard.

## Users

Open **Users** to see everyone who can sign in, with role, status, two-step verification and last sign-in.

![The Users page](07-users.png)

### Create a user

1. Select **New user**.
2. Enter the name, the email address and choose a **role**.
3. Select **Create**. A **temporary password is shown once**. Copy it and give it to the person through a secure channel.
4. The person must change the password at first sign-in.

### Manage a user

Select a user to open the detail panel.

- **Change role**: takes effect at once and signs the person out.
- **Deactivate** and **Reactivate**: accounts are never deleted, so history stays attributed to a name.
- **Reset password**: shows a new temporary password once.
- **Reset two-step verification**: use when a person lost their device and recovery codes.
- Tick **Active users without two-step verification** above the list to find accounts that have not set it up.
- **Revoke sessions**: signs the person out of every device.

> **Note:** Safety rules protect the platform. Nobody can change their own role or deactivate themselves. A role can only be granted by someone who holds every permission in it. The last active Super Admin cannot be removed.

## Roles

Open **Roles** to see the four system roles and any custom roles you made.

![The role editor showing the External Vendor role](08-roles.png)

- **Finding access**: **All findings**, **Assigned findings only** or **Own findings only (reported or assigned)**.
- **Reaches every engagement**: when ticked, the role sees all engagements without being on a team. Only Super Admin has this by default.
- **Require two-step verification**: forces members to enrol.
- **Permissions**: grouped by module. You can only grant permissions that you hold yourself. Platform permissions apply everywhere; engagement permissions apply on the engagements a person can reach.
- System roles cannot be deleted or renamed. A role that still has users cannot be deleted. Changing a role signs out everyone who holds it.

> **Tip:** To create a limited internal role, select **New role**, name it, choose the finding access and tick only the permissions you need. Appendix A lists what every permission allows.

## Organisations and assets

Open **Organisations** and select **New organisation**. Add the name and industry, then use the tabs on the organisation page.

![The organisation list](14-organisations.png)

- **Assets**: add each system you may test, with type, identifier (URL, IP, range), environment, criticality 1 to 5 and tags. An identifier must be unique within an organisation and type.
- **Contacts**: the client people you work with. Mark one as primary.
- **Engagements**: all tests for this organisation.
- **Logo**: upload an image shown on the organisation and usable on reports.
- **Archive** an organisation you no longer test. It becomes read-only and can be unarchived.

## Engagements

![The engagements list](03-engagements.png)

### Create an engagement

1. Open **Engagements** and select **New engagement**.
2. Choose the **organisation**, the **type** (web, API, mobile, internal network, external network, cloud, red team, social engineering, code review, wireless or other), the **start** and **end dates** and the **lead**.
3. Fill in **scope**, **out of scope**, **objectives**, **methodology** and **rules of engagement**. Each of these five boxes takes Markdown: use the toolbar buttons for bold, italic, bulleted lists, numbered lists, links and code, or type the syntax yourself (`- item`, `1. item`, `[text](https://example.com)`). **Preview** shows how it will look. Raw HTML and images are not shown, and only `http`, `https` and `mailto` links work, so a pasted `javascript:` link is shown as plain text. The same rules apply in the PDF report.
4. Select **Create**. The reference, for example `RS-E-2026-0001`, is assigned for you.

The **lead is required**. The lead is added to the team and notified.

![The Edit engagement dialog: each text section has a toolbar, Write and Preview](31-engagement-edit-markdown.png)

![The Overview tab shows the same sections as formatted bullets, numbers and links](35-engagement-sections-markdown.png)

### Change the lead, archive or delete

- **Change lead** (Super Admin): choose another active user at any time while the engagement is not archived. The new lead joins the team and both people are notified. The previous lead stays on the team until you remove them.
- **Add myself** on the Team tab adds the signed-in user to the team.
- **Archive** makes a completed or cancelled engagement read-only. **Unarchive** undoes it.
- **Deleting a finding** (Super Admin, or a role with `findings.delete`) asks you to confirm and names the finding. Straight after you delete it, a bar at the bottom shows **Undo** for about 12 seconds; select it to bring the finding back, with its notes and history. The same bar appears after deleting several findings at once from the list. The audit log records both the delete and the restore.

![The Undo bar appears for a few seconds after a finding is deleted](40-undo-after-delete.png)

- **Delete** (Super Admin only) is separate from archive. The engagement and its findings disappear from every screen for all users. You type the engagement reference to confirm and may add a reason. The audit log records the deletion. Use Archive when in doubt. To undo a delete open **Engagements**, choose **Show: Deleted** and select **Restore**: the engagement returns with its findings, team and history.
- **Clone** (anyone who can create engagements) opens a dialog for a name, dates and a lead. The new Planned engagement copies the organisation, type, scope text, team and in-scope assets. Findings, notes, documents and costs are not copied.

### Run an engagement

The buttons at the top of the engagement page follow the status rules in Chapter 3: **Move to reporting**, **Cancel engagement**, **Edit**, **Archive**, **Open in calendar**.

- **Overview**: dates, lead, type, and the five text sections (scope, out of scope, objectives, methodology, rules of engagement) with their Markdown formatting, bullets and links.
- **Scope and assets**: link organisation assets as **in scope** or **out of scope** with a note, and unlink them. Findings can only point at in-scope assets.
- **Findings**: all findings of the engagement with the same filters as the Findings page.
- **Reports**: reports built for this engagement.
- **Team**: members and roles.
- **Cost**: cost lines of the engagement, each in its own currency. Shown only to people who hold the cost permissions (see Engagement cost below).
- **Notes and documents**: team or shared notes, and documents such as the statement of work (drag and drop, 25 MB each).
- **History**: every change to this engagement.

> **Warning:** Editing an engagement uses a version check. If someone else saved first, you see a conflict message. Reload and apply your change again so that you never overwrite another person's work.

### Engagement cost

The **Cost** tab records what an engagement costs. It is visible only to roles that hold `engagement_costs.view`; by default that is Super Admin alone. Pentesters, Remediation Owners and External Vendors do not see the tab, the totals or the dashboard panel.

1. Open the engagement and select the **Cost** tab, then **Add cost**.
2. Enter the **amount**, choose the **currency** (44 ISO 4217 codes, for example USD, EUR, GBP, INR, AED), the **category** (labour, tools and licences, travel, subcontractor or other), the **date** and an optional description.
3. Select **Add cost**. Use the pencil to edit a line or the bin to delete one. Both are recorded in the history.

An engagement can hold lines in several currencies. The **Total cost** card adds each currency separately. RedShadow never converts between currencies, so no exchange rate is applied. Archived engagements are read-only. Adding, editing and deleting needs `engagement_costs.manage`; a custom role can be given either permission in **Roles**.

### Manage the team

![The Team tab](05-team.png)

1. Open the **Team** tab and select **Add member**.
2. Choose the person. Optionally pick a **role for this engagement only** and a **finding access** override.
3. Select **Add member**. The person is signed out once so the new access applies.

The lead is added automatically and cannot be removed while they lead. You can only grant a role that is no broader than your own.

![The engagement history](06-history.png)

## Calendar

Open **Calendar** to see scheduled, in-progress, reporting and completed engagements as bars in **Month**, **Week** and **List** views. Filter by client, person, engagement and status.

![The calendar](12-calendar.png)

- **Drag a bar** to move an engagement, or drag an end to change the length. Open the engagement and choose **Change dates** to do the same with the keyboard.
- A hint warns when a pentester would be double-booked.
- Only people with scheduling rights can move bars. Everyone else sees them read-only.

## The Costs page

Select the **Total engagement cost** card on the dashboard, or **Costs** in the menu, to open the **Costs** page. It lists every cost line across your engagements with the engagement name and reference, the date, the category, the description and the amount.

![The Costs page: filters, totals per currency and cost over time](36-costs-page.png)

- **Filters:** year, month, engagement, category and currency. **Clear filters** shows everything again.
- **Totals** are shown per currency. Currencies are never converted into each other.
- **Cost over time** draws one bar per month for each currency, so peaks are easy to spot.
- **By engagement** adds up each engagement, and the engagement names open its Cost tab.
- The list shows the 1,000 most recent matching lines; the totals always include every matching line.

The page needs the `engagement_costs.view` permission, which only Super Admin holds by default.

## Dashboard

The **Administration** dashboard shows open, overdue and due-soon findings, items waiting for verification, running engagements (the card names the engagement, and a **Running now** panel lists each running engagement with the scenarios running inside it), severity and status charts, a twelve-week trend, fix-deadline compliance, upcoming engagements and the latest activity. Each number equals the same filter on the matching list page. The cards across the top are the same size and line up on desktop, laptop and phone.

The **Engagement cost** panel shows the total cost for every engagement you can see, one line per currency, and the highest-cost engagements. It appears only for roles that hold `engagement_costs.view`.

## Other Super Admin duties

- **Audit explorer** and integrity checks: Chapter 10.
- **Reports and report styles**: Chapter 11.
- **Finding templates**: reusable starting texts for common findings (Chapter 6).
- **Risk acceptance**: only Super Admins can accept risk (Chapter 9).
- **Backups, secrets and upgrades**: Chapter 12.
