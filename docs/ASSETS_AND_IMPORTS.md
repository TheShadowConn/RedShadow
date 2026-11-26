# Assets, identifiers, imports and deleting users: user guide

## Assets

Open **Assets** in the left menu. The list shows every asset you can see, with search (name, any identifier, tag), filters (organisation, type, environment, criticality) and four tabs: All, Onboarded, Not onboarded, Archived. Click a row for the detail panel.

- **New asset** (Super Admin): choose the organisation, name, type, environment, criticality, tags and one or more identifiers.
- On the list, tick assets (desktop) and use **Archive selected**, **Unarchive selected** or **Onboard selected**.
- **Edit details**, **Archive** and **Delete** are in the detail panel. A deleted asset is gone for good, so deleting is refused while an engagement or a finding uses it: archive it, or merge it into another asset.
- Pentesters and remediation users see only assets of engagements they work on, and cannot change assets.

### Tags

Tags group assets, for example by department (`service-delivery`, `netops`). Tags are compared without regard to case. A tag exists while at least one asset has it; there is no separate tag list to fill in first.

- **Add:** tick assets, choose **Tag selected**, type one or more tags (comma separated). Also possible in the asset's **Edit details** form and in the `Tags` column of an asset CSV (semicolons).
- **Count:** pick a tag in the **Any tag** filter. The numbers on All, Onboarded, Not onboarded and Archived then count that tag only (within the chosen organisation).
- **Remove from some assets:** tick them, choose **Tag selected**, tick the tags under *Remove tags*.
- **Rename or delete everywhere:** **Manage tags**. It applies to the organisation chosen in the filter, or to all organisations. Renaming onto an existing tag merges the two. Deleting a tag keeps the assets.

Archived assets are never changed; they are listed as skipped, so a tag can stay on them until they are unarchived. Adding, renaming and deleting tags needs `assets.update` (Super Admin by default) and is written to the audit log.

### Identifiers

One asset can have many identifiers: an IP address, a hostname, a domain, a URL, a MAC address, a cloud resource ID, a repository. Leave the type on **Detect type** and RedShadow works it out. Every identifier is tidied before it is saved (case, trailing slashes, default ports, IPv6 spelling), so `HTTPS://Shop.Acme.test:443/` and `https://shop.acme.test` are the same identifier.

An identifier can belong to **one asset in an organisation**. While you type, the form tells you when another asset already owns it and names that asset. To fix a real duplicate, open the asset you want to keep and use **Merge a duplicate into this**: identifiers, engagement links and findings move across and the duplicate is deleted. One identifier is the **primary** one (the star); it is the one shown first in lists and reports.

### Not onboarded assets

Assets that arrive through an import are **not onboarded**: they have not been checked yet. They show a "Not onboarded" badge, cannot be added to an engagement and are invisible to pentesters. Open the asset, check or complete its details and identifiers, then **Onboard asset**. To onboard many at once, open the Not onboarded tab, tick the assets and choose **Onboard selected**.

## Importing assets

Imports, then **Import assets** (or Assets, then **Import assets**). Choose the organisation and a CSV file; **Download a template** shows the layout.

1. **Columns.** Match your columns to asset fields. At least one identifier column is required (IP address, hostname, domain, URL, MAC, cloud ID, repository, or the mixed "Other identifiers"). A cell may hold several values separated by semicolons. Name and type are optional: the first identifier becomes the name and the type is guessed.
2. **Check.** Every row is compared with the organisation's assets by identifier, never by name:
   - **New asset**: no identifier is known. It will be created, not onboarded.
   - **Add identifiers**: the row belongs to an existing asset and brings identifiers it lacks. Only the identifiers are added; the asset's other details are never overwritten.
   - **Already known**: nothing new. Skipped.
   - **Error**: an invalid value, an identifier that belongs to an archived asset, or identifiers that belong to two different assets. Nothing is guessed: fix the file, or merge the assets first.
   Rows of the same file that share an identifier are folded into one asset.
3. **Import.** Choose *All or nothing* or *Import the valid rows and leave the rest*.

### When something goes wrong

- **Problem report**: download the rows that were left out, with the reason for each, in the shape of your file. *Row details* shows what the file said.
- **Upload a corrected file**: fix the spreadsheet and upload the whole file again into the same import. It starts attempt 2, keeps your column choices and is checked at once. Rows that already went in are recognised and skipped, so nothing is created twice. This works while the import is failed, waiting, or finished with rows left out. Uploading the same file again is refused.
- **Retry**: for a failed import, run it again with the same file.
- **Delete import**: removes a failed or cancelled import with its rows, history and file. An import that created assets or findings is kept as history.
- **History of this import**: every attempt with its file, counts and outcome.

The same corrected-file, retry, delete and history tools apply to findings imports.

## Deleting users

Super Admin only. Open the user, **Deactivate** the account first, then **Delete account**. The dialog lists what will happen and asks you to type the account's email.

- Memberships and saved import mappings are removed, and the user is unassigned from engagements they lead and from open findings.
- If nothing else refers to the account, it is removed. If findings, notes, evidence or reports still refer to it, the account stays as an anonymous "Deleted user" (no name, email or sign-in) so the history keeps its shape. The email can be used again.
- You cannot delete yourself, a user with more access than you, or an account that has an active retest round or a running import. The audit log keeps the original email.
