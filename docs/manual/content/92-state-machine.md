# Finding status moves {: .appendix }

The table lists every allowed status change. It is generated from the same rules the server enforces. "Allowed by default for" shows the roles whose default permissions include at least one permission that allows the move; administrators may change role permissions, and the person must also be on the engagement.

[[TRANSITIONS]]

- **Needs** shows whether a written reason (at least 5 characters) is required and any extra input.
- Moves not listed are refused. Examples: Draft cannot go straight to Closed, and a finding in Pending verification cannot be edited.
- Retest results use these same moves: a pass runs **Verified**, a fail runs **Verification failed**.
- The hourly job reopens risk-accepted findings whose expiry has passed and flags findings past their due date.

## Editable statuses

Draft, Open, In progress and Reopened can be edited. All other statuses are read-only until reopened.
