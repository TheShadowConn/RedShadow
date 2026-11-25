import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import type { QueueRow } from "../../api/types";
import { Alert, Button } from "../../design/ui";
import { RequestRetestDialog } from "../retests/RequestRetestDialog";
import { QueueView, type StripItem } from "./QueueView";
import { MoveDialog, RULE, type Move } from "./shared";

const STRIP: StripItem[] = [{ key: "pending_verification", label: "Waiting for retest", count: (c) => c.pending_verification ?? 0 }];

/** What the testing team works from: submitted fixes, longest waiting first. */
export function VerificationQueue() {
  const { can } = useAuth();
  const [action, setAction] = useState<{ row: QueueRow; move: Move } | null>(null);
  const [request, setRequest] = useState<{ rows: QueueRow[]; done: () => void } | null>(null);
  const scenario = useSearchParams()[0].get("scenario") ?? "";
  const canVerify = can("findings.verify");
  const canRequest = can("retests.create");

  return (
    <>
      {scenario && <div className="mb-4"><Alert tone="ok">Retest for scenario <strong>{scenario}</strong>. Select the findings it covers and choose Request retest. The scenario name is added to the note.</Alert></div>}
      <QueueView
        title="Verification"
        lead="Fixes submitted for retest, longest waiting first."
        endpoint="/queues/verification"
        strip={STRIP}
        waitingColumn
        emptyTitle="Nothing to verify"
        emptyBody="Findings appear here when the remediation team submits a fix."
        selectable={(r) => canRequest && !r.retest}
        bulkBar={(rows, clear) => {
          const one = new Set(rows.map((r) => r.engagement.id)).size === 1;
          return one ? (
            <Button size="sm" variant="primary" onClick={() => setRequest({ rows, done: clear })}>Request retest</Button>
          ) : (
            <Alert tone="warn">A retest round covers one engagement. Select findings from a single engagement.</Alert>
          );
        }}
        actions={(r) => canVerify && (
          <>
            <Button size="sm" variant="primary" onClick={() => setAction({ row: r, move: RULE.verified })}>Verify</Button>
            <Button size="sm" variant="danger" onClick={() => setAction({ row: r, move: RULE.failed })}>Fail</Button>
          </>
        )}
      />
      {action && <MoveDialog f={action.row} move={action.move} onClose={() => setAction(null)} />}
      {request && <RequestRetestDialog rows={request.rows} defaultNote={scenario ? `Retest of scenario: ${scenario}` : ""} onClose={() => setRequest(null)} onDone={request.done} />}
    </>
  );
}
