import { useState } from "react";

import { useAuth } from "../../api/auth";
import type { QueueRow } from "../../api/types";
import { Button, ErrorNote } from "../../design/ui";
import { QueueView, type StripItem } from "./QueueView";
import { MoveDialog, RULE, useQuickMove } from "./shared";

const STRIP: StripItem[] = [
  { key: "open", label: "Open", count: (c) => c.open ?? 0 },
  { key: "in_progress", label: "In progress", count: (c) => c.in_progress ?? 0 },
  { key: "reopened", label: "Reopened", count: (c) => c.reopened ?? 0 },
  { key: "overdue", label: "Overdue", count: (c) => c.overdue ?? 0 },
];

/** What a remediation user works from: overdue first, then nearest deadline, then severity. */
export function RemediationQueue() {
  const { can } = useAuth();
  const [submitting, setSubmitting] = useState<QueueRow | null>(null);
  const start = useQuickMove();
  const canStart = can("remediation.update_status");
  const canSubmit = can("remediation.submit_verification");

  return (
    <>
      <ErrorNote error={start.error} />
      <QueueView
        title="Remediation"
        lead="Findings waiting for a fix, overdue ones first."
        endpoint="/queues/remediation"
        strip={STRIP}
        emptyTitle="Nothing to fix"
        emptyBody="Published findings assigned to you appear here until they are submitted for verification."
        actions={(r) => (
          <>
            {canStart && r.status !== "in_progress" && <Button size="sm" variant="primary" loading={start.isPending && start.variables?.f.id === r.id} onClick={() => start.mutate({ f: r, move: RULE.started })}>Start work</Button>}
            {canSubmit && r.status === "in_progress" && <Button size="sm" variant="primary" onClick={() => setSubmitting(r)}>Submit for verification</Button>}
          </>
        )}
      />
      {submitting && <MoveDialog f={submitting} move={RULE.submit} onClose={() => setSubmitting(null)} />}
    </>
  );
}
