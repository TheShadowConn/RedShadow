# Assets, imports and account deletion

{SA} This chapter covers the Assets page, asset identifiers, importing assets, managing failed imports and deleting users. Pentesters and remediation users see assets of their own engagements only and cannot change them. Imports of findings are described in the pentester chapter; the tools for correcting and repeating an import apply to both kinds.

## Assets and identifiers

Open **Assets** in the menu. Search covers the name, every identifier and the tags. Filters narrow by organisation, type, environment and criticality, and four tabs separate all, onboarded, not onboarded and archived assets.

One asset can have several **identifiers**: an IP address, a hostname, a domain, a URL, a MAC address, a cloud resource ID or a repository. Leave the type on *Detect type* and RedShadow works it out. Identifiers are tidied before they are saved, so spelling variants of one address count as one identifier.

| Rule | What it means |
|---|---|
| One owner | An identifier belongs to one asset in an organisation. The form warns while you type and names the asset that owns it. |
| Primary identifier | One identifier carries the star. It is shown first in lists. Removing it promotes another. |
| At least one | An onboarded asset keeps at least one identifier. |
| Merge | To resolve a real duplicate, open the asset to keep and choose **Merge a duplicate into this**. Identifiers, engagement links and findings move across and the duplicate is deleted. |
| Bulk | Tick assets in the list and choose *Archive selected*, *Unarchive selected* or *Onboard selected*. Assets that cannot be changed are reported. |
| Delete | Allowed only when no engagement and no finding uses the asset. Otherwise archive it or merge it. |

## Importing assets

Choose **Imports**, then **Import assets**, pick the organisation and the CSV file. A template is available for download.

1. **Match the columns.** Map at least one identifier column. A cell can hold several values separated by semicolons. Name and type are optional.
2. **Check.** Each row is matched against the organisation's assets by identifier, never by name: *New asset* (will be created, not onboarded), *Add identifiers* (an existing asset gains identifiers it lacks; nothing else about it changes), *Already known* (skipped) or *Error* (invalid value, archived asset, or identifiers of two different assets). Rows of one file that share an identifier join the same asset.
3. **Import.** *All or nothing*, or *import the valid rows and leave the rest*.

Imported assets are **not onboarded**: they cannot join an engagement and pentesters cannot see them until a Super Admin opens the asset, checks the details and chooses **Onboard asset** (or ticks several on the *Not onboarded* tab and chooses **Onboard selected**).

## When an import has problems

- **Problem report** lists the rows that were left out and why. *Row details* shows what the file said.
- **Upload a corrected file** puts a fixed file into the same import as a new attempt. Your column choices are kept and the file is checked at once. Rows that already went in are recognised and skipped, so nothing is created twice. Uploading the same file again is refused.
- **Retry** runs a failed import again with the same file.
- **Delete import** removes a failed or cancelled import with its rows, history and file. An import that created records stays as history.
- **History of this import** lists every attempt with its file, counts and outcome.

## Deleting a user

Deactivate the account first, then choose **Delete account** and type the account's email. Memberships and saved mappings are removed and open work is unassigned. If nothing else refers to the account it is removed; if findings, notes or evidence still do, the account stays as an anonymous *Deleted user* so history keeps its shape, and the email can be used again. You cannot delete yourself, a user with more access than you, or an account with an active retest round or a running import. The audit log keeps the original email.
