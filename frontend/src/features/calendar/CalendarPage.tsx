import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, SlidersHorizontal, TriangleAlert } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { STATUSES, type CalendarEvent } from "../../api/types";
import { Button, EmptyState, EngagementStatus, ErrorState, LoadingRows, PageHeader, Select, Sheet, cx, label } from "../../design/ui";
import { CalendarGrid } from "./CalendarGrid";
import { add, addMonths, dayShort, monthRange, monthStart, monthTitle, rangeTitle, today, weekRange, weekStart } from "./dates";
import { EventCard } from "./EventCard";
import { RescheduleDialog } from "./RescheduleDialog";
import { lookFor, statusText } from "./shared";

type View = "month" | "week" | "list";
const VIEWS: Array<[View, string]> = [["month", "Month"], ["week", "Week"], ["list", "List"]];
const DEFAULT_STATUSES = STATUSES.map(([k]) => k).filter((k) => k !== "cancelled");

/** Engagement calendar: month, week and list. Super Admin can move engagements; everyone sees only what they may see. */
export function CalendarPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [sheet, setSheet] = useState(false);
  const [open, setOpen] = useState<CalendarEvent | null>(null);
  const [edit, setEdit] = useState<{ event: CalendarEvent; start: string; end: string } | null>(null);
  const canMove = can("engagements.schedule");

  const phone = typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
  const view = (VIEWS.some(([v]) => v === params.get("view")) ? params.get("view") : phone ? "list" : "month") as View;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") ?? "") ? params.get("date")! : today();
  const statuses = params.get("status") ? params.get("status")!.split(",") : DEFAULT_STATUSES;
  const f = { engagement: params.get("engagement") ?? "", client: params.get("client") ?? "", pentester: params.get("pentester") ?? "", mine: params.get("mine") === "true" };
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) (v ? next.set(k, v) : next.delete(k));
    setParams(next, { replace: true });
  };

  const range = view === "week" ? weekRange(date) : monthRange(date);
  const qs = new URLSearchParams({ start: range.start, end: range.end });
  if (params.get("status")) qs.set("status", params.get("status")!);
  for (const [k, v] of Object.entries(f)) if (v) qs.set(k, String(v));
  const q = useQuery({ queryKey: ["calendar", qs.toString()], queryFn: () => api<{ results: CalendarEvent[] }>("GET", `/calendar/events?${qs}`), placeholderData: (p) => p });
  const events = q.data?.results ?? [];

  // Filter options come from what has been loaded, so a filter never hides its own choices.
  const seen = useRef({ clients: new Map<string, string>(), people: new Map<string, string>(), engagements: new Map<string, string>() });
  for (const e of events) {
    seen.current.clients.set(e.client.id, e.client.name);
    seen.current.engagements.set(e.id, `${e.ref} ${e.name}`);
    for (const u of e.team) seen.current.people.set(u.id, u.display_name);
  }
  const options = useMemo(() => ({
    clients: [...seen.current.clients].sort((a, b) => a[1].localeCompare(b[1])),
    people: [...seen.current.people].sort((a, b) => a[1].localeCompare(b[1])),
    engagements: [...seen.current.engagements].sort((a, b) => a[1].localeCompare(b[1])),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [q.data]);

  const step = (dir: -1 | 1) => set({ date: view === "week" ? add(date, 7 * dir) : addMonths(monthStart(date), dir) });
  const title = view === "week" ? rangeTitle(range.start, range.end) : monthTitle(date);
  const activeFilters = (f.engagement ? 1 : 0) + (f.client ? 1 : 0) + (f.pentester ? 1 : 0) + (f.mine ? 1 : 0) + (params.get("status") ? 1 : 0);
  const gridFirst = view === "week" ? weekStart(date) : range.start;
  const weeks = view === "week" ? 1 : Math.round((Date.parse(range.end) - Date.parse(range.start)) / 86_400_000 / 7 + 1 / 7);

  const controls = (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <Select aria-label="Client" className="sm:max-w-56" value={f.client} onChange={(e) => set({ client: e.target.value })}>
        <option value="">All clients</option>
        {options.clients.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </Select>
      <Select aria-label="Pentester" className="sm:max-w-56" value={f.pentester} onChange={(e) => set({ pentester: e.target.value })}>
        <option value="">Everyone</option>
        {options.people.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </Select>
      <Select aria-label="Engagement" className="sm:max-w-64" value={f.engagement} onChange={(e) => set({ engagement: e.target.value })}>
        <option value="">All engagements</option>
        {options.engagements.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </Select>
      <fieldset className="m-0 flex min-w-0 flex-wrap gap-x-4 border-0 p-0">
        <legend className="label mb-1">Status</legend>
        {STATUSES.map(([k, v]) => (
          <label key={k} className="check">
            <input type="checkbox" checked={statuses.includes(k)} onChange={(e) => set({ status: (e.target.checked ? [...statuses, k] : statuses.filter((s) => s !== k)).join(",") })} />
            {v}
          </label>
        ))}
      </fieldset>
      <label className="check"><input type="checkbox" checked={f.mine} onChange={(e) => set({ mine: e.target.checked ? "true" : "" })} /> My engagements</label>
    </div>
  );

  return (
    <>
      <PageHeader title="Calendar" lead="Scheduled, running and finished engagements you can see." />
      {canMove && view !== "list" && <p className="-mt-4 mb-4 hidden text-[15px] text-muted md:block">Drag a bar to move it, or drag an end to resize it. Open an engagement and choose Change dates to use the keyboard.</p>}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button aria-label={view === "week" ? "Previous week" : "Previous month"} onClick={() => step(-1)}><ChevronLeft size={18} aria-hidden /></Button>
          <Button aria-label={view === "week" ? "Next week" : "Next month"} onClick={() => step(1)}><ChevronRight size={18} aria-hidden /></Button>
          <Button onClick={() => set({ date: "" })}>Today</Button>
          <h2 className="ml-2 text-xl" aria-live="polite">{title}</h2>
        </div>
        <div role="group" aria-label="View" className="flex gap-1">
          {VIEWS.map(([v, name]) => <Button key={v} aria-pressed={view === v} variant={view === v ? "primary" : "secondary"} onClick={() => set({ view: v })}>{name}</Button>)}
        </div>
      </div>

      <div className="card mb-4 p-4">
        <div className="hidden md:block">{controls}</div>
        <div className="flex items-center justify-between gap-3 md:hidden">
          <Button onClick={() => setSheet(true)}><SlidersHorizontal size={18} aria-hidden /> Filters{activeFilters ? ` (${activeFilters})` : ""}</Button>
          {activeFilters > 0 && <Button size="sm" onClick={() => setParams({ view, date }, { replace: true })}>Clear</Button>}
        </div>
        {activeFilters > 0 && <div className="mt-4 hidden md:block"><Button size="sm" onClick={() => setParams({ view, date }, { replace: true })}>Clear filters</Button></div>}
      </div>

      {q.isPending && <div className="card"><LoadingRows /></div>}
      {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
      {q.data && view !== "list" && (
        <>
          <CalendarGrid first={gridFirst} weeks={weeks} month={view === "month" ? date : undefined} events={events} detailed={view === "week"} canDrag={canMove}
            onOpen={setOpen} onMove={(event, start, end) => setEdit({ event, start, end })} />
          {events.length === 0 && <p className="mt-4 text-center text-muted">No engagements in this {view}.</p>}
        </>
      )}
      {q.data && view === "list" && <ListView events={events} onOpen={setOpen} />}

      <Legend />
      <Sheet open={sheet} onClose={() => setSheet(false)} title="Filters">
        <div className="flex flex-col gap-5 p-5">{controls}<Button variant="primary" block onClick={() => setSheet(false)}>Show {events.length} engagements</Button></div>
      </Sheet>
      {open && <EventCard event={open} canMove={canMove} onClose={() => setOpen(null)} onEdit={() => { setEdit({ event: open, start: open.start_date, end: open.end_date }); setOpen(null); }} />}
      {edit && <RescheduleDialog event={edit.event} start={edit.start} end={edit.end} onClose={() => setEdit(null)} />}
    </>
  );
}

function ListView({ events, onOpen }: { events: CalendarEvent[]; onOpen: (e: CalendarEvent) => void }) {
  if (events.length === 0) return <div className="card"><EmptyState title="No engagements here" body="Nothing is scheduled in this month for the current filters." /></div>;
  return (
    <ul className="card m-0 list-none divide-y divide-line p-0">
      {events.map((e) => {
        const look = lookFor(e);
        const Icon = look.icon;
        return (
          <li key={e.id}>
            <button type="button" onClick={() => onOpen(e)} className="block w-full space-y-1.5 px-4 py-4 text-left hover:bg-raised">
              <span className="flex flex-wrap items-center gap-2"><span className="mono text-[14px] text-muted">{e.ref}</span><EngagementStatus status={e.status} overdue={e.overdue} />{e.conflicts.length > 0 && <span className="inline-flex items-center gap-1 text-[14px] text-warn"><TriangleAlert size={14} aria-hidden /> Double-booked</span>}</span>
              <span className="flex items-center gap-2 font-medium"><span className={cx("inline-flex h-6 w-6 flex-none items-center justify-center rounded-md border", look.cls)}><Icon size={14} aria-hidden /></span><span className="min-w-0">{e.name}</span><span className="sr-only">{statusText(e)}</span></span>
              <span className="block text-[15px]">{e.client.name}</span>
              <span className="block text-[14px] text-muted">{dayShort(e.start_date)} to {dayShort(e.end_date)} · {e.lead ? `Lead ${e.lead.display_name}` : "No lead"} · {e.team.length} on the team</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Legend() {
  return (
    <ul className="m-0 mt-4 flex list-none flex-wrap gap-x-5 gap-y-2 p-0 text-[14px] text-muted" aria-label="Legend">
      {[...STATUSES, ["overdue", "Overdue"] as const].map(([k, v]) => {
        const look = k === "overdue" ? lookFor({ status: "planned", overdue: true }) : lookFor({ status: k, overdue: false });
        const Icon = look.icon;
        return <li key={k} className="flex items-center gap-2"><span className={cx("inline-flex h-5 w-5 items-center justify-center rounded border", look.cls)}><Icon size={12} aria-hidden /></span>{k === "overdue" ? v : label(STATUSES, k)}</li>;
      })}
    </ul>
  );
}
