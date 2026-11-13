import { Badge } from "../../design/ui";
import { REPORT_STATUSES } from "../../api/types";
import { label } from "../../design/ui";

const TONE: Record<string, "ok" | "warn" | "fail" | "info"> = { queued: "info", rendering: "warn", done: "ok", failed: "fail" };

export function ReportStatus({ status }: { status: string }) {
  return <Badge tone={TONE[status] ?? "info"}>{label(REPORT_STATUSES, status)}</Badge>;
}

export const WORKING = ["queued", "rendering"];
