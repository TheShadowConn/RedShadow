import { AlertCircle, AlertTriangle, CalendarCheck, CheckCircle2, CircleDashed, Hourglass, type LucideIcon } from "lucide-react";

import type { CalendarEvent } from "../../api/types";
import { STATUSES } from "../../api/types";
import { label } from "../../design/ui";

/** Status look for bars. Colour is never the only signal: every bar also carries the icon and the status text. */
export const LOOK: Record<string, { cls: string; icon: LucideIcon }> = {
  planned: { cls: "bg-info-bg text-info border-info", icon: CircleDashed },
  scheduled: { cls: "bg-raised text-ink border-accent", icon: CalendarCheck },
  in_progress: { cls: "bg-warn-bg text-warn border-warn", icon: Hourglass },
  reporting: { cls: "bg-warn-bg text-warn border-warn", icon: Hourglass },
  completed: { cls: "bg-ok-bg text-ok border-ok", icon: CheckCircle2 },
  cancelled: { cls: "bg-raised text-muted border-line-strong line-through", icon: AlertCircle },
};
export const OVERDUE_LOOK = { cls: "bg-fail-bg text-fail border-fail", icon: AlertCircle };

export const lookFor = (e: Pick<CalendarEvent, "status" | "overdue">) => (e.overdue ? OVERDUE_LOOK : (LOOK[e.status] ?? LOOK.planned));
export const statusText = (e: Pick<CalendarEvent, "status" | "overdue">) => `${label(STATUSES, e.status)}${e.overdue ? ", overdue" : ""}`;

/** Engagements that are finished cannot be moved: the API refuses it, so the UI does not offer it. */
export const movable = (e: Pick<CalendarEvent, "status">) => e.status !== "completed" && e.status !== "cancelled";

export function ConflictNote({ conflicts }: { conflicts: CalendarEvent["conflicts"] }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="alert alert-warn" role="status">
      <AlertTriangle size={20} className="mt-0.5 flex-none" aria-hidden />
      <ul className="m-0 list-none space-y-1 p-0">
        {conflicts.map((c, i) => (
          <li key={i}>{c.user.display_name} is also on <span className="mono">{c.with.ref}</span> {c.with.name} in these dates.</li>
        ))}
      </ul>
    </div>
  );
}
