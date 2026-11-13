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
3. Fill in **scope**, **out of scope**, **objectives**, **methodology** and **rules of engagement**.
4. Select **Create**. The reference, for example `RS-E-2026-0001`, is assigned for you.

### Run an engagement

The buttons at the top of the engagement page follow the status rules in Chapter 3: **Move to reporting**, **Cancel engagement**, **Edit**, **Archive**, **Open in calendar**.

- **Overview**: dates, lead, type, scope, out of scope, objectives, methodology.
- **Scope and assets**: link organisation assets as **in scope** or **out of scope** with a note, and unlink them. Findings can only point at in-scope assets.
- **Findings**: all findings of the engagement with the same filters as the Findings page.
- **Reports**: reports built for this engagement.
- **Team**: members and roles.
- **Notes and documents**: team or shared notes, and documents such as the statement of work (drag and drop, 25 MB each).
- **History**: every change to this engagement.

> **Warning:** Editing an engagement uses a version check. If someone else saved first, you see a conflict message. Reload and apply your change again so that you never overwrite another person's work.

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

## Dashboard

The **Administration** dashboard shows open, overdue and due-soon findings, items waiting for verification, running engagements, severity and status charts, a twelve-week trend, fix-deadline compliance, upcoming engagements and the latest activity. Each number equals the same filter on the matching list page.

## Other Super Admin duties

- **Audit explorer** and integrity checks: Chapter 10.
- **Reports and report styles**: Chapter 11.
- **Finding templates**: reusable starting texts for common findings (Chapter 6).
- **Risk acceptance**: only Super Admins can accept risk (Chapter 9).
- **Backups, secrets and upgrades**: Chapter 12.
