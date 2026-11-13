import { Link } from "react-router-dom";

import type { CalendarEvent } from "../../api/types";
import { ENGAGEMENT_TYPES } from "../../api/types";
import { Badge, Button, EngagementStatus, Modal, label } from "../../design/ui";
import { dayLong } from "./dates";
import { ConflictNote, movable } from "./shared";

/** Key facts for one engagement, with a way into it and (Super Admin) a keyboard route to change its dates. */
export function EventCard({ event, canMove, onClose, onEdit }: { event: CalendarEvent; canMove: boolean; onClose: () => void; onEdit: () => void }) {
  const rows: Array<[string, React.ReactNode]> = [
    ["Client", event.client.name],
    ["Type", label(ENGAGEMENT_TYPES, event.type)],
    ["Dates", `${dayLong(event.start_date)} to ${dayLong(event.end_date)}`],
    ["Lead", event.lead?.display_name ?? "None"],
    ["Team", event.team.length ? event.team.map((u) => u.display_name).join(", ") : "None"],
    ["Findings", `${event.findings.total} visible to you, ${event.findings.active} still to close`],
  ];
  return (
    <Modal open onClose={onClose} title={event.name}>
      <div className="flex flex-col gap-5 p-6">
        <p className="m-0 flex flex-wrap items-center gap-2"><span className="mono text-[14px] text-muted">{event.ref}</span><EngagementStatus status={event.status} overdue={event.overdue} />{event.conflicts.length > 0 && <Badge tone="warn">Double-booked</Badge>}</p>
        <dl className="m-0 grid gap-3">{rows.map(([k, v]) => <div key={k}><dt className="label">{k}</dt><dd className="m-0 mt-0.5 break-words">{v}</dd></div>)}</dl>
        <ConflictNote conflicts={event.conflicts} />
        <div className="flex flex-wrap justify-end gap-3">
          {canMove && movable(event) && <Button onClick={onEdit}>Change dates</Button>}
          <Link to={`/engagements/${event.id}`} className="btn btn-primary">Open engagement</Link>
        </div>
      </div>
    </Modal>
  );
}
