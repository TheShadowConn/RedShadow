import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { SEVERITIES, type EngagementRow, type Page, type QueuePage, type QueueRow } from "../../api/types";
import { Button, EmptyState, ErrorState, LoadingRows, PageHeader, Pager, Select, Sheet, cx, formatDay } from "../../design/ui";
import { FindingStatus, SeverityBadge, userName } from "../findings/shared";
import { SlaBadge, daysUntil } from "./shared";

const PAGE_SIZE = 25;
export type QueueFilters = { status: string; severity: string[]; engagement: string; mine: boolean };
const EMPTY: QueueFilters = { status: "", severity: [], engagement: "", mine: false };

export type StripItem = { key: string; label: string; count: (c: Record<string, number>) => number };

type Props = {
  title: string;
  lead: string;
  endpoint: "/queues/remediation" | "/queues/verification";
  strip: StripItem[];
  /** Per-row action buttons (kept short: they sit in the row on desktop and under the title on mobile). */
  actions?: (row: QueueRow) => ReactNode;
  /** Selection support (verification queue): which rows may be ticked, and the bar shown when some are. */
  selectable?: (row: QueueRow) => boolean;
  bulkBar?: (picked: QueueRow[], clear: () => void) => ReactNode;
  emptyTitle: string;
  emptyBody: string;
  waitingColumn?: boolean;
};

/** Work queue: status strip, filters (a bottom sheet on phones), rows as a table or cards. */
export function QueueView(p: Props) {
  const { can } = useAuth();
  const [f, setF] = useState<QueueFilters>(EMPTY);
  const [page, setPage] = useState(1);
  const [sheet, setSheet] = useState(false);
  const [picked, setPicked] = useState<Map<string, QueueRow>>(new Map());
  const set = (patch: Partial<QueueFilters>) => { setF({ ...f, ...patch }); setPage(1); setPicked(new Map()); };

  const engagements = useQuery({ queryKey: ["engagements-pick"], queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100&archived=all"), enabled: can("engagements.view") });
  const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (f.status === "overdue") qs.set("overdue", "true");
  else if (f.status) qs.set("status", f.status);
  if (f.severity.length) qs.set("severity", f.severity.join(","));
  if (f.engagement) qs.set("engagement", f.engagement);
  if (f.mine) qs.set("assigned", "me");
  const q = useQuery({ queryKey: ["queue", p.endpoint, qs.toString()], queryFn: () => api<QueuePage>("GET", `${p.endpoint}?${qs}`), placeholderData: (x) => x });
  const rows = q.data?.results ?? [];
  const counts = q.data?.counts ?? {};
  const filtered = !!(f.status || f.severity.length || f.engagement || f.mine);
  const ticked = rows.filter((r) => picked.has(r.id));
  const tickable = rows.filter((r) => p.selectable?.(r));
  const allTicked = tickable.length > 0 && tickable.every((r) => picked.has(r.id));
  const toggle = (r: QueueRow) => setPicked((m) => { const n = new Map(m); if (n.has(r.id)) n.delete(r.id); else n.set(r.id, r); return n; });
  const toggleAll = () => setPicked(allTicked ? new Map() : new Map(tickable.map((r) => [r.id, r])));

  const filterControls = (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <Select aria-label="Engagement" className="sm:max-w-64" value={f.engagement} onChange={(e) => set({ engagement: e.target.value })}>
        <option value="">All engagements</option>
        {engagements.data?.results.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
      </Select>
      <fieldset className="m-0 flex min-w-0 flex-wrap gap-x-4 border-0 p-0">
        <legend className="label mb-1">Severity</legend>
        {SEVERITIES.map(([k, v]) => (
          <label key={k} className="check">
            <input type="checkbox" checked={f.severity.includes(k)} onChange={(e) => set({ severity: e.target.checked ? [...f.severity, k] : f.severity.filter((s) => s !== k) })} />
            {v}
          </label>
        ))}
      </fieldset>
      <label className="check"><input type="checkbox" checked={f.mine} onChange={(e) => set({ mine: e.target.checked })} /> Assigned to me</label>
    </div>
  );
  const activeFilters = f.severity.length + (f.engagement ? 1 : 0) + (f.mine ? 1 : 0);

  return (
    <>
      <PageHeader title={p.title} lead={p.lead} />
      <div role="group" aria-label="Filter by status" className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {p.strip.length > 1 && <StripButton label="All" count={p.strip.filter((s) => s.key !== "overdue").reduce((n, s) => n + s.count(counts), 0)} active={f.status === ""} onClick={() => set({ status: "" })} />}
        {p.strip.map((s) => <StripButton key={s.key} label={s.label} count={s.count(counts)} active={f.status === s.key} danger={s.key === "overdue"} onClick={() => set({ status: f.status === s.key ? "" : s.key })} />)}
      </div>

      <div className="card overflow-hidden">
        <div className="hidden flex-wrap items-center justify-between gap-4 border-b border-line p-4 md:flex">{filterControls}{filtered && <Button size="sm" onClick={() => { setF(EMPTY); setPage(1); }}>Clear filters</Button>}</div>
        <div className="flex items-center justify-between gap-3 border-b border-line p-3 md:hidden">
          <Button onClick={() => setSheet(true)}><SlidersHorizontal size={18} aria-hidden /> Filters{activeFilters ? ` (${activeFilters})` : ""}</Button>
          {filtered && <Button size="sm" onClick={() => { setF(EMPTY); setPage(1); }}>Clear</Button>}
        </div>

        {p.bulkBar && ticked.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-raised px-4 py-3" role="region" aria-label="Selected findings">
            <span className="font-medium">{ticked.length} selected</span>
            {p.bulkBar(ticked, () => setPicked(new Map()))}
          </div>
        )}

        {q.isPending && <LoadingRows />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && rows.length === 0 && <EmptyState title={filtered ? "Nothing matches" : p.emptyTitle} body={filtered ? "Clear a filter to see more." : p.emptyBody} action={filtered ? <Button onClick={() => { setF(EMPTY); setPage(1); }}>Clear filters</Button> : undefined} />}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden lg:table">
              <thead><tr>
                {p.selectable && <th className="w-10"><input type="checkbox" aria-label="Select all selectable on this page" checked={allTicked} disabled={tickable.length === 0} onChange={toggleAll} /></th>}
                <th>Severity</th><th>Finding</th><th>Engagement</th><th>{p.waitingColumn ? "Waiting" : "Deadline"}</th><th>Owner</th><th><span className="sr-only">Actions</span></th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    {p.selectable && <td>{p.selectable(r) && <input type="checkbox" aria-label={`Select ${r.ref}`} checked={picked.has(r.id)} onChange={() => toggle(r)} />}</td>}
                    <td><SeverityBadge severity={r.severity} score={r.cvss_score} /></td>
                    <td><Link to={`/findings/${r.id}`} className="block hover:underline"><span className="block font-medium">{r.title}</span><span className="mono block text-[14px] text-muted">{r.ref}{r.asset ? ` · ${r.asset.name}` : ""}</span></Link>{r.retest && <RetestChip row={r} />}</td>
                    <td>{r.engagement.name}</td>
                    <td className="whitespace-nowrap">{p.waitingColumn ? <Waiting row={r} /> : <Deadline row={r} />}</td>
                    <td>{userName(p.waitingColumn ? r.assigned_pentester : r.remediation_owner)}</td>
                    <td><div className="flex flex-wrap justify-end gap-2">{p.actions?.(r)}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 lg:hidden">
              {rows.map((r) => (
                <li key={r.id} className="space-y-3 px-4 py-4">
                  <div className="flex items-start gap-3">
                    {p.selectable?.(r) && <input type="checkbox" className="mt-1.5" aria-label={`Select ${r.ref}`} checked={picked.has(r.id)} onChange={() => toggle(r)} />}
                    <Link to={`/findings/${r.id}`} className="block min-w-0 flex-1 space-y-1.5">
                      <span className="flex flex-wrap items-center gap-2"><SeverityBadge severity={r.severity} score={r.cvss_score} /><FindingStatus status={r.status} /></span>
                      <span className="block font-medium">{r.title}</span>
                      <span className="block text-[14px] text-muted"><span className="mono">{r.ref}</span> · {r.engagement.name}</span>
                      <span className="block">{p.waitingColumn ? <Waiting row={r} /> : <Deadline row={r} />}</span>
                      {r.retest && <RetestChip row={r} />}
                    </Link>
                  </div>
                  <div className={cx("flex flex-wrap gap-2", p.selectable?.(r) && "pl-8")}>{p.actions?.(r)}</div>
                </li>
              ))}
            </ul>
            <Pager page={page} count={q.data!.count} size={PAGE_SIZE} onPage={(n) => { setPage(n); setPicked(new Map()); }} />
          </>
        )}
      </div>
      <Sheet open={sheet} onClose={() => setSheet(false)} title="Filters">
        <div className="flex flex-col gap-5 p-5">
          {filterControls}
          <Button variant="primary" block onClick={() => setSheet(false)}>Show {q.data?.count ?? ""} findings</Button>
        </div>
      </Sheet>
    </>
  );
}

function StripButton({ label, count, active, danger, onClick }: { label: string; count: number; active: boolean; danger?: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cx("card flex min-h-16 flex-col items-start justify-center px-4 py-2 text-left transition-colors", active ? "border-accent bg-raised" : "hover:bg-raised")}>
      <span className={cx("text-[26px] font-semibold leading-none", danger && count > 0 && "text-fail")}>{count}</span>
      <span className="mt-1 text-[14px] text-muted">{label}</span>
    </button>
  );
}

function Deadline({ row }: { row: QueueRow }) {
  return (
    <span className="inline-flex flex-col gap-0.5">
      <SlaBadge due={row.due_date} status={row.status} overdue={row.is_overdue} />
      {row.due_date && <span className="text-[13px] text-muted">{formatDay(row.due_date)}</span>}
    </span>
  );
}

function Waiting({ row }: { row: QueueRow }) {
  if (!row.resolved_at) return <span className="text-muted">Unknown</span>;
  const days = Math.max(0, -daysUntil(row.resolved_at.slice(0, 10)));
  return <span className="inline-flex flex-col"><span>{days === 0 ? "Since today" : `${days} day${days === 1 ? "" : "s"}`}</span><span className="text-[13px] text-muted">since {formatDay(row.resolved_at.slice(0, 10))}</span></span>;
}

function RetestChip({ row }: { row: QueueRow }) {
  return <Link to={`/retests/${row.retest!.round_id}`} className="mt-1 inline-flex min-h-8 items-center text-[14px] text-accent hover:underline">Retest {row.retest!.ref} · {row.retest!.assessor.display_name}</Link>;
}
