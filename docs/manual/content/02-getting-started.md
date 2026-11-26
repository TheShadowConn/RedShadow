# Getting started

## Signing in

Open the address your administrator gave you, for example `https://redshadow.example.lan`. Enter the email and password of the account an administrator created for you.

![The sign-in page](01-signin.png)

1. Enter your **Email** and **Password**. Use the eye icon to check what you typed.
2. Select **Sign in**.
3. If this is your first sign-in you are asked to **choose a new password**. Use at least 12 characters and avoid common words.
4. If your role requires two-step verification, scan the QR code with an authenticator app, enter the 6-digit code and **save the ten recovery codes** shown once.

> **Warning:** Recovery codes are shown only once. Each works one time. Store them in your password manager. If you lose both your device and your codes, an administrator must reset your two-step verification.

### Loading

While RedShadow loads a page, a list or a saved change, you see the eclipse "O" of the logo: a red arc circles the ring while the red cut pulses. A button that is saving shows a small white version and cannot be pressed twice. If your system is set to reduce motion, the animation stays still.

### Sessions and lockout

- A session ends after **30 minutes without activity**, or after **12 hours** in total, whichever comes first.
- After **5 failed attempts** in a row the account is locked for 15 minutes. The error message is the same for a wrong password and an unknown account, on purpose.
- An administrator can sign you out everywhere by revoking sessions, and changing your role or engagement access signs you out so the new access applies at once.

## Notifications

The **bell** beside the theme switch shows how many notifications are unread. Select it to read them, open the item they refer to, or **Mark all read**. You are told when you are added to or removed from an engagement, made or replaced as lead, when an engagement changes status, when a finding is assigned to you or changes status or gets a new timeline entry, and when a retest is assigned to you. You are never notified about your own actions. Findings that are due within 3 days, and findings that have become overdue, also notify the people on them (once each).

Select the **gear** in the bell panel to choose which groups you receive: engagement changes, assignments, finding updates, due dates and overdue, retests. If your administrator has set up email, you can also tick **Also email me assignments, due dates and retests**.

### Idle warning and signing out everywhere

Two minutes before an idle session ends, a box in the corner warns you. Select **Stay signed in** to keep working. On **Account**, **Sign out everywhere** ends every session of your account on every device, including the one you are using.

## Finding your way around

![The overview page of a Super Admin](02-admin-dashboard.png)

- **Sidebar** (wide screens): the pages your role can use. A page you cannot open does not appear.
- **Search** (top bar): finds findings, engagements, organisations and pages. Press `Ctrl K` or `Cmd K`, or `/` when you are not typing in a field.
- **Theme toggle**: the moon icon switches between light and dark. The choice is remembered on this device.
- **Overview**: the dashboard for your role. Each role sees only its own dashboard: Super Admins see the Administration dashboard, Pentesters the Testing one, Remediation Owners the Remediation one and External Vendors the External testing one. Only a custom role that was deliberately given several dashboards sees a tab for each.
- **About**: the last menu entry. It shows the version and build.
- **Footer**: "Built by Shadowconn" also links to the About page.

### On a phone or tablet

On narrow screens the sidebar becomes a bottom bar with **Overview**, **Tests**, **Findings** and **More**. Tables turn into cards and dialogs fill the screen. Everything in this manual works on a phone.

![The overview on a phone](30-mobile.jpg)

## Your account

Open **Account** to see your name, email and role, change your password, turn two-step verification on and read the keyboard shortcuts.

![The Account page](29-account.png)

> **Tip:** Turn on two-step verification even when your role does not require it. Super Admins must use it.

## About RedShadow

The **About** page (the **About** entry in the menu, and the footer) shows the version, build identifier, build date and runtime. Quote these when you report a problem.

![The About page: version, creator and, for Super Admins, the newest backup](15-about.png)
