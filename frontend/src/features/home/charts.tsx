import { useState } from "react";
import { Link } from "react-router-dom";

import { FINDING_STATUSES, SEVERITIES } from "../../api/types";
import { SeverityBadge } from "../findings/shared";

const ACTIVE = "open,in_progress,pending_verification,reopened";

/** One bar per severity. The badge (shape, colour, word) and the number carry the meaning, not the colour alone. */
export function SeverityBars({ counts, status = ACTIVE, mine = false }: { counts: Record<string, number>; status?: string; mine?: boolean }) {
  const peak = Math.max(1, ...SEVERITIES.map(([k]) => counts[k] ?? 0));
  return (
    <ul className="m-0 list-none space-y-1 p-0">
      {SEVERITIES.map(([k]) => {
        const n = counts[k] ?? 0;
        return (
          <li key={k}>
            <Link to={`/findings?severity=${k}&status=${status}${mine ? "&assigned=me" : ""}`} className="grid min-h-11 grid-cols-[6.5rem_1fr_2.5rem] items-center gap-3 rounded-md px-1 hover:bg-raised">
              <SeverityBadge severity={k} />
              <span className="h-2.5 overflow-hidden rounded-full bg-raised" aria-hidden>
                <span className="block h-full rounded-full" style={{ width: `${(n / peak) * 100}%`, minWidth: n ? 6 : 0, background: `var(--color-sev-${k})` }} />
              </span>
              <span className="text-right text-[17px] font-semibold tabular-nums">{n}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

const STATUS_COLOUR: Record<string, string> = {
  open: "var(--color-sev-high)", reopened: "var(--color-fail)", in_progress: "var(--color-accent)", pending_verification: "var(--color-info)",
  closed: "var(--color-ok)", risk_accepted: "var(--color-sev-medium)", draft: "var(--color-muted)", false_positive: "var(--color-line-strong)", duplicate: "var(--color-line-strong)",
};

/** A single stacked bar (2px gaps) plus a legend that lists every status with its number. */
export function StatusStrip({ counts }: { counts: Record<string, number> }) {
  const rows = FINDING_STATUSES.map(([k, l]) => ({ k, l, n: counts[k] ?? 0 })).filter((r) => r.n > 0);
  const total = rows.reduce((a, r) => a + r.n, 0);
  if (!total) return <p className="m-0 text-muted">No findings yet.</p>;
  return (
    <div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" role="img" aria-label={`Findings by status: ${rows.map((r) => `${r.l} ${r.n}`).join(", ")}`}>
        {rows.map((r) => <span key={r.k} className="h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(r.n / total) * 100}%`, background: STATUS_COLOUR[r.k] }} />)}
      </div>
      <ul className="m-0 mt-4 grid list-none grid-cols-2 gap-x-6 gap-y-1 p-0 max-sm:grid-cols-1">
        {rows.map((r) => (
          <li key={r.k}>
            <Link to={`/findings?status=${r.k}`} className="flex min-h-11 items-center gap-3 rounded-md px-1 hover:bg-raised">
              <span className="size-3 shrink-0 rounded-sm" style={{ background: STATUS_COLOUR[r.k] }} aria-hidden />
              <span className="flex-1">{r.l}</span>
              <span className="font-semibold tabular-nums">{r.n}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Point = { week_start: string; opened: number; closed: number };
const W = 640, H = 230, L = 36, R = 14, T = 16, B = 30;
const fmtWeek = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** Opened vs closed per week. One axis, two lines, hover or focus a week to read both numbers; a table view sits below. */
export function TrendChart({ data }: { data: Point[] }) {
  const [active, setActive] = useState<number | null>(null);
  const peak = Math.max(4, ...data.flatMap((d) => [d.opened, d.closed]));
  const top = Math.ceil(peak / 4) * 4;
  const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, data.length - 1);
  const y = (v: number) => T + (1 - v / top) * (H - T - B);
  const line = (key: "opened" | "closed") => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d[key]).toFixed(1)}`).join(" ");
  const series = [
    { key: "opened" as const, name: "Opened", colour: "var(--color-sev-high)" },
    { key: "closed" as const, name: "Closed", colour: "var(--color-ok)" },
  ];
  const last = data[data.length - 1];
  const shown = active === null ? last : data[active];
  return (
    <figure className="m-0">
      <figcaption className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <ul className="m-0 flex list-none flex-wrap gap-x-5 p-0">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-2 text-[15px]"><span className="h-0.5 w-5 rounded" style={{ background: s.colour }} aria-hidden />{s.name} <strong className="tabular-nums">{shown?.[s.key] ?? 0}</strong></li>
          ))}
        </ul>
        <span className="text-[14px] text-muted" aria-live="polite">Week of {shown ? fmtWeek(shown.week_start) : ""}</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="group" aria-label="Findings opened and closed per week">
        {[0, 1, 2, 3, 4].map((t) => {
          const v = (top / 4) * t;
          return <g key={t}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} style={{ stroke: "var(--color-line)" }} strokeWidth={1} /><text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={11} style={{ fill: "var(--color-muted)" }}>{v}</text></g>;
        })}
        {data.map((d, i) => (i % 2 === (data.length - 1) % 2 ? <text key={d.week_start} x={x(i)} y={H - 8} textAnchor="middle" fontSize={11} style={{ fill: "var(--color-muted)" }}>{fmtWeek(d.week_start)}</text> : null))}
        {active !== null && <line x1={x(active)} x2={x(active)} y1={T} y2={H - B} style={{ stroke: "var(--color-line-strong)" }} strokeWidth={1} />}
        {series.map((s) => (
          <g key={s.key}>
            <path d={line(s.key)} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" style={{ stroke: s.colour }} />
            {data.map((d, i) => (active === i || i === data.length - 1) && <circle key={d.week_start} cx={x(i)} cy={y(d[s.key])} r={4.5} strokeWidth={2} style={{ fill: s.colour, stroke: "var(--color-surface)" }} />)}
          </g>
        ))}
        {data.map((d, i) => (
          <rect key={d.week_start} x={x(i) - (W - L - R) / (2 * Math.max(1, data.length - 1))} y={T} width={(W - L - R) / Math.max(1, data.length - 1)} height={H - T - B} fill="transparent" tabIndex={0}
            role="img" aria-label={`Week of ${fmtWeek(d.week_start)}: ${d.opened} opened, ${d.closed} closed`}
            onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} className="outline-none focus-visible:outline-2 focus-visible:outline-accent" />
        ))}
      </svg>
      <details className="mt-3">
        <summary className="min-h-11 cursor-pointer py-2 text-accent">View as table</summary>
        <div className="overflow-x-auto">
          <table className="data-table"><thead><tr><th>Week of</th><th className="text-right">Opened</th><th className="text-right">Closed</th></tr></thead>
            <tbody>{data.map((d) => <tr key={d.week_start}><td>{fmtWeek(d.week_start)}</td><td className="text-right tabular-nums">{d.opened}</td><td className="text-right tabular-nums">{d.closed}</td></tr>)}</tbody></table>
        </div>
      </details>
    </figure>
  );
}
