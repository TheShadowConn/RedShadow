import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { CalendarEvent, RescheduleResult } from "../../api/types";
import { Button, ErrorNote, Field, fieldError, Modal, TextInput } from "../../design/ui";
import { isConflict, noFieldErrors } from "../findings/shared";
import { dayLong } from "./dates";
import { ConflictNote } from "./shared";

/** Change an engagement's dates. Used after a drag and from "Edit dates" (the keyboard route).
 *  A dry run shows double-booking before saving. Warnings never block the save. */
export function RescheduleDialog({ event, start: s0, end: e0, onClose }: { event: CalendarEvent; start: string; end: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [start, setStart] = useState(s0);
  const [end, setEnd] = useState(e0);
  const valid = !!start && !!end && end >= start;
  const changed = start !== event.start_date || end !== event.end_date;
  const body = { start_date: start, end_date: end, version: event.version };

  const check = useQuery({
    queryKey: ["calendar-check", event.id, start, end, event.version],
    queryFn: () => api<RescheduleResult>("POST", `/calendar/events/${event.id}/reschedule`, { ...body, dry_run: true }),
    enabled: valid && changed,
    retry: false,
  });
  const save = useMutation({
    mutationFn: () => api<RescheduleResult>("POST", `/calendar/events/${event.id}/reschedule`, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["calendar"] }); void qc.invalidateQueries({ queryKey: ["engagement"] }); onClose(); },
    onError: (e) => { if (isConflict(e)) void qc.invalidateQueries({ queryKey: ["calendar"] }); },
  });

  return (
    <Modal open onClose={onClose} title="Change dates">
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (valid && changed) save.mutate(); }}>
        <p className="m-0 text-[15px] text-muted"><span className="mono">{event.ref}</span> {event.name}<br />Now {dayLong(event.start_date)} to {dayLong(event.end_date)}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Start" error={fieldError(save.error, "start_date")}>{(p) => <TextInput {...p} type="date" required value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} />}</Field>
          <Field label="End" error={fieldError(save.error, "end_date") ?? (start && end && end < start ? "End must be on or after the start." : undefined)}>{(p) => <TextInput {...p} type="date" required value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />}</Field>
        </div>
        {isConflict(save.error) ? <ErrorNote error={save.error} /> : <ErrorNote error={noFieldErrors(save.error) ?? noFieldErrors(check.error)} />}
        {check.data && <ConflictNote conflicts={check.data.conflicts} />}
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!valid || !changed || check.isPending || check.isError}>Save dates</Button>
        </div>
      </form>
    </Modal>
  );
}
