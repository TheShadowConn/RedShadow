# Assets, imports and account deletion

{SA} This chapter covers the Assets page, asset identifiers, importing assets, managing failed imports and deleting users. Pentesters and remediation users see assets of their own engagements only and cannot change them. Imports of findings are described in the pentester chapter; the tools for correcting and repeating an import apply to both kinds.

An **Importing assets** or **Importing findings** label (with a short pop-up when you switch) tells you which kind of import you are in.

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

## Tags and departments

A tag groups assets. Use one tag per department or team, such as `IT Help Desk` or `Network Engineering`. An asset can carry several tags. Capital and small letters count as the same tag, and the spelling already in use is kept. A tag exists as long as one asset carries it.

Wherever you add a tag, RedShadow asks **Add to an existing tag?** Answer *Yes* to pick from the tags in use, or *No* to type a new one.

| To do this | Steps |
|---|---|
| Tag a new asset | **New asset**, then the *Tags* part of the form. |
| Tag one asset | Open the asset and choose **Add tag**. Remove a tag with the cross beside it. **Edit details** works too. |
| Tag many assets | Tick them, choose **Tag selected**, pick or create tags, **Save tags**. |
| Tag by import | Fill the *Tags* column of the asset file, several tags separated by semicolons. |
| Find a department's assets | Click its tag above the list. *Untagged* shows assets with no tag. |
| Rename or merge everywhere | **Manage tags**, then **Rename**. Typing the name of another tag merges the two. |
| Delete everywhere | **Manage tags**, then **Delete**. The assets stay. |

Tags are shown in the asset list, the asset panel, the engagement's *Scope and assets* tab and the import preview. Archived assets are never changed and are reported as skipped. An asset holds up to 20 tags of 40 characters. Tag changes need the *Edit assets* permission and are written to the audit log.

## The Departments page

**Departments** in the menu shows one row per tag: assets, open findings by severity, overdue, due in 7 days and risk accepted. An asset with two tags counts in both rows; the *Total* row counts it once. Each person sees only the assets and findings they are already allowed to see. While *All organisations* is selected, the numbers for open and risk accepted findings link to the findings list, filtered to that department.

## Importing assets

Choose **Imports**, then **Import assets**, pick the organisation and the CSV file. A template is available for download. It has six plain columns: **Name**, **Asset type**, **Environment**, **Criticality**, **Identifiers** and **Tags**. Put every address of an asset in the Identifiers cell, separated by semicolons (for example `10.0.0.5; web01.acme.test`); RedShadow works out what each one is.

1. **Match the columns.** Map at least one identifier column. A cell can hold several values separated by semicolons. Name and type are optional.
2. **Check.** Each row is matched against the organisation's assets by identifier, never by name: *New asset* (will be created, not onboarded), *Add identifiers* (an existing asset gains identifiers it lacks; nothing else about it changes), *Already known* (skipped) or *Error* (invalid value, archived asset, or identifiers of two different assets). Rows of one file that share an identifier join the same asset.
3. **Import.** *All or nothing*, or *import the valid rows and leave the rest*.

Imported assets are **not onboarded**: they cannot join an engagement and pentesters cannot see them until a Super Admin opens the asset, checks the details and chooses **Onboard asset** (or ticks several on the *Not onboarded* tab and chooses **Onboard selected**).

## Scanner files

**Imports** also reads scanner results up to 50 MB: Nessus (`.nessus`), Burp (*XML issues* export) and Nmap (`-oX`). The same matching, check, preview and duplicate rules apply as for a CSV.

1. If the hosts are not assets yet, choose **Import assets** and upload the scan. Then onboard the new assets and add them to the engagement's scope.
2. Choose **Import findings**, pick the engagement and upload the Nessus or Burp file. Confirm the suggested columns, check the preview and import.

Findings arrive as **drafts** for review. Informational results are left out unless you tick *Include informational results*. A host that is not an in-scope asset is reported on its row. Nmap files list hosts and ports only, so they can be imported as assets but not as findings. Open ports appear in the preview and are not saved.

## When an import has problems

- **Problem report** lists the rows that were left out and why. *Row details* shows what the file said.
- **Upload a corrected file** puts a fixed file into the same import as a new attempt. Your column choices are kept and the file is checked at once. Rows that already went in are recognised and skipped, so nothing is created twice. Uploading the same file again is refused.
- **Retry** runs a failed import again with the same file.
- **Delete import** removes a failed or cancelled import with its rows, history and file. For most people an import that created records stays as history.
- **Super Admin only:** a Super Admin can delete any finished import from the history (completed, failed or cancelled), one at a time with the bin button, or all at once with **Clear history** at the top of the Imports page. The findings and assets those imports created are **kept**; they only lose the link back to the import. Imports that are still waiting or running are never touched. Each deletion is written to the audit log with the number of findings kept. The permission is `imports.delete_history`.
- **History of this import** lists every attempt with its file, counts and outcome.

## Deleting a user

Deactivate the account first, then choose **Delete account** and type the account's email. Memberships and saved mappings are removed and open work is unassigned. If nothing else refers to the account it is removed; if findings, notes or evidence still do, the account stays as an anonymous *Deleted user* so history keeps its shape, and the email can be used again. You cannot delete yourself, a user with more access than you, or an account with an active retest round or a running import. The audit log keeps the original email.
