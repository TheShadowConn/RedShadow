import { useEffect, useRef, useState } from "react";
import { TriangleAlert } from "lucide-react";

import type { CalendarEvent } from "../../api/types";
import { cx } from "../../design/ui";
import { add, diff, today as todayIso, weekdayShort } from "./dates";
import { lookFor, movable, statusText } from "./shared";

type Mode = "move" | "start" | "end";
type Drag = { id: string; mode: Mode; origin: string; orig: { start: string; end: string }; start: string; end: string; moved: boolean };
type Segment = { ev: CalendarEvent; from: number; to: number; left: boolean; right: boolean; lane: number };

const LANE_PX = 30;

/** Pack the events of one week into lanes so bars never overlap. */
function pack(weekDays: string[], events: CalendarEvent[]): { segments: Segment[]; lanes: number } {
  const raw = events
    .filter((e) => e.start_date <= weekDays[6] && e.end_date >= weekDays[0])
    .map((ev) => ({
      ev,
      from: Math.max(0, diff(ev.start_date, weekDays[0])),
      to: Math.min(6, diff(ev.end_date, weekDays[0])),
      left: ev.start_date < weekDays[0],
      right: ev.end_date > weekDays[6],
    }))
    .sort((a, b) => a.from - b.from || b.to - b.from - (a.to - a.from) || a.ev.ref.localeCompare(b.ev.ref));
  const laneEnds: number[] = [];
  const segments = raw.map((s) => {
    let lane = laneEnds.findIndex((end) => end < s.from);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = s.to;
    return { ...s, lane };
  });
  return { segments, lanes: laneEnds.length };
}

type Props = {
  /** Monday of the first visible week, and how many weeks to show (1 = the week view). */
  first: string;
  weeks: number;
  /** Month the grid belongs to, to fade the days outside it. */
  month?: string;
  events: CalendarEvent[];
  detailed?: boolean;
  canDrag: boolean;
  onOpen: (e: CalendarEvent) => void;
  onMove: (e: CalendarEvent, start: string, end: string) => void;
};

/** Month and week view: one row per week, engagements as bars that span their days.
 *  Super Admin can drag a bar to move it or an end to resize it (mouse and pen). "Change dates" is the keyboard route. */
export function CalendarGrid({ first, weeks, month, events, detailed, canDrag, onOpen, onMove }: Props) {
  const [drag, setDrag] = useState<Drag | null>(null);
  const dragRef = useRef<Drag | null>(null);
  const suppress = useRef(false);
  dragRef.current = drag;
  const today = todayIso();

  const shown = drag ? events.map((e) => (e.id === drag.id ? { ...e, start_date: drag.start, end_date: drag.end } : e)) : events;
  const rows = Array.from({ length: weeks }, (_, w) => Array.from({ length: 7 }, (_, d) => add(first, w * 7 + d)));

  const dayAt = (x: number, y: number): string | null => {
    for (const el of document.elementsFromPoint(x, y)) if (el instanceof HTMLElement && el.dataset.day) return el.dataset.day;
    return null;
  };

  useEffect(() => {
    if (!drag) return;
    const onMovePtr = (ev: PointerEvent) => {
      const cur = dragRef.current;
      const day = dayAt(ev.clientX, ev.clientY);
      if (!cur || !day) return;
      const delta = diff(day, cur.origin);
      let { start, end } = cur.orig;
      if (cur.mode === "move") { start = add(cur.orig.start, delta); end = add(cur.orig.end, delta); }
      else if (cur.mode === "start") start = add(cur.orig.start, delta) > cur.orig.end ? cur.orig.end : add(cur.orig.start, delta);
      else end = add(cur.orig.end, delta) < cur.orig.start ? cur.orig.start : add(cur.orig.end, delta);
      setDrag({ ...cur, start, end, moved: cur.moved || delta !== 0 });
    };
    const finish = (commit: boolean) => {
      const cur = dragRef.current;
      setDrag(null);
      if (!cur || !cur.moved) return;
      suppress.current = true;
      setTimeout(() => { suppress.current = false; }, 0);
      const ev = events.find((e) => e.id === cur.id);
      if (commit && ev && (cur.start !== cur.orig.start || cur.end !== cur.orig.end)) onMove(ev, cur.start, cur.end);
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    const onKey = (k: KeyboardEvent) => { if (k.key === "Escape") finish(false); };
    window.addEventListener("pointermove", onMovePtr);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointermove", onMovePtr);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      window.removeEventListener("keydown", onKey);
    };
  }, [drag?.id]);

  function begin(e: React.PointerEvent, ev: CalendarEvent, mode: Mode) {
    if (!canDrag || !movable(ev) || e.button !== 0 || e.pointerType === "touch") return;
    const day = dayAt(e.clientX, e.clientY);
    if (!day) return;
    e.stopPropagation();
    setDrag({ id: ev.id, mode, origin: day, orig: { start: ev.start_date, end: ev.end_date }, start: ev.start_date, end: ev.end_date, moved: false });
  }

  return (
    <div className="card overflow-hidden select-none" role="group" aria-label="Engagement calendar">
      <div className="grid grid-cols-7 border-b border-line bg-raised text-center text-[13px] font-medium text-muted">
        {rows[0].map((d) => <div key={d} className="py-2">{weekdayShort(d)}</div>)}
      </div>
      {rows.map((days) => {
        const { segments, lanes } = pack(days, shown);
        return (
          <div key={days[0]} className="grid grid-cols-7 border-b border-line last:border-b-0"
            style={{ gridTemplateRows: `32px repeat(${Math.max(lanes, 1)}, ${LANE_PX}px)`, minHeight: detailed ? 220 : 110 }}>
            {days.map((d, i) => {
              const faded = month ? d.slice(0, 7) !== month.slice(0, 7) : false;
              return (
                <div key={d} data-day={d} role="group" aria-label={d}
                  className={cx("border-l border-line first:border-l-0 px-2 pt-1 text-[13px]", faded && "bg-raised/50 text-muted")}
                  style={{ gridColumn: i + 1, gridRow: "1 / -1" }}>
                  <span className={cx("inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1", d === today && "bg-accent font-semibold text-on-accent")}>{Number(d.slice(8))}</span>
                </div>
              );
            })}
            {segments.map(({ ev, from, to, left, right, lane }) => {
              const look = lookFor(ev);
              const Icon = look.icon;
              const dragging = drag?.id === ev.id && drag.moved;
              const draggable = canDrag && movable(ev);
              return (
                <div key={ev.id} role="button" tabIndex={0}
                  aria-label={`${ev.ref} ${ev.name}, ${ev.client.name}, ${statusText(ev)}, ${ev.start_date} to ${ev.end_date}${ev.conflicts.length ? ", double-booked" : ""}`}
                  onClick={() => { if (!suppress.current) onOpen(ev); }}
                  onKeyDown={(k) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); onOpen(ev); } }}
                  onPointerDown={(e) => begin(e, ev, "move")}
                  className={cx("relative z-[1] mx-0.5 mt-0.5 flex min-w-0 items-center gap-1.5 border px-2 text-left text-[13px] font-medium outline-offset-2 focus-visible:outline-2 focus-visible:outline-accent",
                    look.cls, left ? "rounded-l-none border-l-0" : "rounded-l-md", right ? "rounded-r-none border-r-0" : "rounded-r-md",
                    draggable ? "cursor-grab" : "cursor-pointer", dragging && "cursor-grabbing opacity-80 shadow-md")}
                  style={{ gridColumn: `${from + 1} / ${to + 2}`, gridRow: lane + 2, height: LANE_PX - 4, touchAction: draggable ? "pan-y" : undefined }}>
                  {draggable && !left && <span aria-hidden className="absolute inset-y-0 left-0 w-2 cursor-ew-resize" onPointerDown={(e) => begin(e, ev, "start")} />}
                  <Icon size={14} className="flex-none" aria-hidden />
                  <span className="truncate">{ev.name}</span>
                  {detailed && <span className="hidden truncate font-normal opacity-80 md:inline">· {ev.client.name}</span>}
                  {ev.conflicts.length > 0 && <TriangleAlert size={14} className="ml-auto flex-none" aria-hidden />}
                  {draggable && !right && <span aria-hidden className="absolute inset-y-0 right-0 w-2 cursor-ew-resize" onPointerDown={(e) => begin(e, ev, "end")} />}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
