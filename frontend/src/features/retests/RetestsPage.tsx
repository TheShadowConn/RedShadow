import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import type { Page, RetestRound } from "../../api/types";
import { Badge, EmptyState, ErrorState, formatDate, LoadingRows, PageHeader, Pager, Select } from "../../design/ui";

const PAGE_SIZE = 25;
const STATUS: Record<string, { label: string; tone: "ok" | "warn" | "fail" | "info" }> = {
  queued: { label: "Queued", tone: "info" }, in_progress: { label: "In progress", tone: "warn" },
  completed: { label: "Completed", tone: "ok" }, cancelled: { label: "Cancelled", tone: "fail" },
};

export function RoundStatus({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: "info" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function RoundCounts({ r }: { r: RetestRound }) {
  const c = r.counts;
  return <span className="text-[15px]">{c.passed} passed · {c.failed} failed · {c.pending} pending{c.not_tested ? ` · ${c.not_tested} not tested` : ""}</span>;
}

/** Retest rounds the caller can see. Assessors usually want "Assigned to me". */
export function RetestsPage() {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (status) qs.set("status", status);
  if (mine) qs.set("assessor", "me");
  const q = useQuery({ queryKey: ["retests", qs.toString()], queryFn: () => api<Page<RetestRound>>("GET", `/retest-rounds?${qs}`), placeholderData: (p) => p });
  const rows = q.data?.results ?? [];
  const filtered = !!(status || mine);

  return (
    <>
      <PageHeader title="Retests" lead="Rounds of findings sent back to an assessor to confirm the fix." />
      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line p-4">
          <Select aria-label="Status" className="max-w-56" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </Select>
          <label className="check"><input type="checkbox" checked={mine} onChange={(e) => { setMine(e.target.checked); setPage(1); }} /> Assigned to me</label>
        </div>
        {q.isPending && <LoadingRows />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && rows.length === 0 && <EmptyState title={filtered ? "No rounds match" : "No retest rounds"} body={filtered ? "Clear a filter to see more." : "Request a retest from the Verification queue."} />}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead><tr><th>Round</th><th>Engagement</th><th>Status</th><th>Results</th><th>Assessor</th><th>Requested</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => nav(`/retests/${r.id}`)}>
                    <td><Link className="mono font-medium hover:underline" to={`/retests/${r.id}`} onClick={(e) => e.stopPropagation()}>{r.ref}</Link></td>
                    <td>{r.engagement.name}</td><td><RoundStatus status={r.status} /></td><td><RoundCounts r={r} /></td>
                    <td>{r.assessor.display_name}</td><td className="whitespace-nowrap text-muted">{formatDate(r.requested_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((r) => (
                <li key={r.id}>
                  <Link to={`/retests/${r.id}`} className="block space-y-1.5 px-4 py-4">
                    <span className="flex flex-wrap items-center gap-2"><span className="mono font-medium">{r.ref}</span><RoundStatus status={r.status} /></span>
                    <span className="block text-[15px]">{r.engagement.name}</span>
                    <span className="block"><RoundCounts r={r} /></span>
                    <span className="block text-[14px] text-muted">Assessor {r.assessor.display_name} · {formatDate(r.requested_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <Pager page={page} count={q.data!.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>
    </>
  );
}
