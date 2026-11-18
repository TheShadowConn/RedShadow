# ADR-0021 User deletion removes the account or anonymises it

Status: accepted (2026-11-18)

**Decision:** `DELETE /users/{id}` (permission `users.delete`, Super Admin by default) deletes a deactivated account. The caller must type the account's email. The service refuses to act on the caller's own account, on a user with more access than the caller, on the last active Super Admin, on an account that is still active, and while the user has an active retest round or a running import. It removes engagement memberships, saved import mappings and recovery codes, and unassigns the user from engagements they lead and from open findings (pentester and remediation owner). Then:

- if nothing else refers to the user, the row is deleted;
- otherwise the row stays as a tombstone: email `deleted-<id>@deleted.invalid`, name "Deleted user", unusable password, MFA cleared, `deleted_at` set. Findings, notes, evidence and reports keep their foreign keys, so history keeps its shape. Tombstones are hidden from the user list and cannot be managed or signed in to, and the original email is free for reuse.

`GET /users/{id}/deletion-impact` returns the blockers, what will be removed or cleared, which kinds of records refer to the user, and which of the two modes will apply. The audit event `user.deleted` keeps the original email (audit rows hold labels, not foreign keys) and the counts.

**Why:** Most records that point at a user (finding author, note author, evidence uploader, retest tester) are append-only or protected by foreign keys on purpose, so reassigning or nulling them would rewrite history. Anonymising keeps the record, removes the personal data, and still lets an unused account be removed completely.

**Consequences:** `User.deleted_at` is new. A person who is deleted and later hired again gets a fresh account. Closed findings keep pointing at the tombstone.
