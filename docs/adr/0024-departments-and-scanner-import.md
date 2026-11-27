# ADR-0024: departments from tags, and scanner file import

Status: accepted (release 1.5.0, 2026-11-27)

## Departments

A department is an asset tag. No department table was added, because an asset may belong to more than one team. The Departments page (`GET /assets/departments`) counts the caller's visible assets and findings per tag. An asset with two tags counts in both rows; the total counts it once.

## Scanner files

Nessus, Burp and Nmap XML is converted in the worker to the same table a CSV upload gives (`apps/imports/scans.py`). Mapping, checking, preview, duplicate detection, history and the import itself are therefore shared, and no migration was needed.

- XML is read with `defusedxml`: entity expansion and external references are refused.
- Scanner files may be 50 MB; CSV stays at 10 MB. Nginx now accepts 52 MB request bodies; attachments are still limited by the application.
- Findings arrive as drafts. A host must be an in-scope asset; otherwise the row is flagged. The same file can be imported as assets first (not onboarded).
- Nmap is accepted only as an asset import. Open ports are shown in the preview and are not stored.
- Informational results are left out unless asked for.
