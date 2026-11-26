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

- **Add scenario** takes a name, a description, planned dates and pictures. The description takes Markdown, with the same toolbar and **Preview** as the engagement text boxes (bullets, numbers, links, bold, code); it is shown formatted on the tab and in the PDF report. **Add several** takes one name per line, up to 50, and adds none if any name is already used.
- **Edit** changes the name and description and adds or removes pictures (PNG, JPEG, GIF or WebP, up to 10 per scenario). Pictures are shown large on the Scenarios tab, each at its own proportions with no empty bars around it. Select one to open it in a wide viewer, then use the arrow buttons or the left and right arrow keys to move between pictures.
- **Reschedule** sets new planned dates and an optional reason. A deferred scenario that gets dates becomes planned again.
- **Start testing** also puts the engagement into testing: a scenario is part of its engagement, so starting one moves the engagement to **In progress** if it is Planned, Scheduled or in Reporting. The change is written to the audit log and the team is notified. A Completed or Cancelled engagement refuses with a message; reopen the engagement first.
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

Every role opens on its own dashboard. The **Test scenarios** panel shows overdue scenarios and those starting within 7 days, and Super Admins also see deferred scenarios waiting for a date. Remediation owners reach their queue with **Open my queue**. A **Running now** panel lists the engagements in testing, each with the scenarios that are in progress inside it, so you can see at a glance what is being tested.

## Starter templates

**From template** on the Scenarios tab adds a ready-made list in one step: OWASP Top 10 (2021) for web applications, OWASP API Security Top 10 (2023), OWASP Mobile Top 10 (2024), an internal network starter and a cloud configuration starter. Choose a template, untick anything you do not need and select **Add**. Every item arrives as a planned scenario with a description you can edit. Names already in the engagement are skipped, so applying a template twice does no harm.

## Deferred scenarios and reminders

When the new start date of a deferred scenario arrives, the engagement lead and the pentesters on the engagement get a notification (**Due dates and overdue** group). The scenario stays deferred until you plan it again or start it.

## Retesting after fixes

A tested scenario has a **Retest this scenario** button. It opens the **Verification** queue for that engagement with the scenario's name noted. Findings belong to the engagement, not to the scenario, so you choose which findings the retest covers. The scenario name is added to the note for the assessor.

## This week

The Pentester dashboard has a **Scenarios this week** panel listing the scenarios planned for the current week (Monday to Sunday), with a link to the week view of the calendar.
