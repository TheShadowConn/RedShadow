# Test scenarios

{PT} {SA} An engagement often lists several use cases. Some are tested now and others later, even next year, but they all belong to one engagement with one lead, one team and one set of findings. **Test scenarios** record what is tested and when. They do not split the engagement.

## What a scenario is

A scenario has a **name**, a **description**, optional **pictures**, optional **planned dates** and a **status**. It has no owner: the engagement lead owns the work. Findings are imported into and belong to the whole engagement, never to a scenario.

The name is kept exactly as you type it. It must be unique within the engagement, ignoring capitals.

| Status | Meaning |
|---|---|
| **Planned** | Listed, not started. It may have planned dates. |
| **In progress** | Testing has started. |
| **Tested** | Done. The date it was tested is recorded. |
| **Deferred** | Postponed. A reason is required. A new date is optional. |
| **Cancelled** | Not going ahead. A reason is required. It stays in the history. |

## Working with scenarios

Open an engagement and choose the **Scenarios** tab. Pentesters on the engagement and Super Admins can change scenarios. Remediation owners and external testers who can open the engagement can read them.

- **Add scenario** takes a name, a description, planned dates and pictures. **Add several** takes one name per line, up to 50, and adds none if any name is already used.
- **Edit** changes the name and description and adds or removes pictures (PNG, JPEG, GIF or WebP, up to 10 per scenario). Select a picture to see it larger.
- **Reschedule** sets new planned dates and an optional reason. A deferred scenario that gets dates becomes planned again.
- **Start testing**, **Mark tested**, **Defer**, **Cancel**, **Reopen**, **Plan again** and **Restore** move the scenario between statuses. A tested or cancelled scenario cannot be rescheduled until it is reopened or restored.
- **Reorder** with the arrow buttons, or drag the handle on a wide screen.
- The clock icon opens the **history** of that one scenario: who changed what, and why.

A bar on the engagement page, the engagement list and the dashboards shows progress, for example "3 of 5 tested". Cancelled scenarios are not counted.

## On the calendar

Scenarios with planned dates appear on the **Calendar** as dashed bars under their engagement, in the month, week and list views. Select one to open the engagement's Scenarios tab. Untick **Scenarios** in the **Show** group to hide them.

## Completing an engagement

When you move an engagement to **Reporting** or **Completed** while scenarios are still planned, in progress or deferred, RedShadow tells you how many and asks you to confirm with **Continue anyway**. The confirmation is written to the audit log. Nothing else stops the move.

## Reports, reminders and cloning

- The PDF report has a **Test scenarios** section with each scenario, its status and dates, and up to 3 pictures. While any scenario is untested the section says **Interim report** and lists those scenarios as not yet tested, with the planned date. Older report templates get the section automatically.
- Each hour RedShadow notifies the engagement team three days before a planned or deferred scenario starts, and when a planned or in-progress scenario passes its planned end. Each notification is sent once per scenario and date. They belong to the **Due dates and overdue** group, which you can mute.
- **Clone** copies the scenarios (name and description) into the new engagement as planned, without dates or pictures. Cancelled scenarios are skipped.

## Your dashboard

Every role opens on its own dashboard. The **Test scenarios** panel shows overdue scenarios and those starting within 7 days, and Super Admins also see deferred scenarios waiting for a date. Remediation owners reach their queue with **Open my queue**.
