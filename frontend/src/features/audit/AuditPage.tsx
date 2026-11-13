import { useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ShieldAlert, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, downloadFile } from "../../api/client";
import type { AuditEvent, AuditFacets, AuditPage as AuditPageData, IntegrityState } from "../../api/types";
import {
  Alert, Badge, Button, EmptyState, ErrorNote, ErrorState, Field, formatDate, LoadingRows, Modal, PageHeader, Select, Sheet, TextInput,
} from "../../design/ui";

const FILTER_KEYS = ["engagement", "actor", "entity_type", "entity_id", "action", "outcome", "from", "to", "request_id"] as const;
type Filters = Record<(typeof FILTER_KEYS)[number], string>;

/** "finding.false_positive" becomes "Finding: false positive". The raw code stays in the drawer. */
export function humanAction(code: string): string {
  const [head, ...rest] = code.split(".");
  const tail = rest.join(" ").replace(/_/g, " ");
  const text = tail ? `${head}: ${tail}` : head;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const OUTCOME_TONE = { success: "ok", denied: "fail", failure: "fail" } as const;

function OutcomeBadge({ outcome }: { outcome: AuditEvent["outcome"] }) {
  if (outcome === "success") return null;
  return <Badge tone={OUTCOME_TONE[outcome]}>{outcome === "denied" ? "Denied" : "Failed"}</Badge>;
}

export function AuditPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [sheet, setSheet] = useState(false);
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const [exporting, setExporting] = useState(false);
  const isAdmin = can("audit.view_all");
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])) as Filters;
  const active = FILTER_KEYS.filter((k) => filters[k]);
  const setFilters = (patch: Partial<Filters>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) (v ? next.set(k, v) : next.delete(k));
    setParams(next, { replace: true });
  };
  const query = new URLSearchParams(active.map((k) => [k, filters[k]]));

  const facets = useQuery({ queryKey: ["audit-facets"], queryFn: () => api<AuditFacets>("GET", "/audit/facets"), staleTime: 60_000 });
  const list = useInfiniteQuery({
    queryKey: ["audit-events", query.toString()],
    initialPageParam: "",
    queryFn: ({ pageParam }) => api<AuditPageData>("GET", `/audit/events?${query}${pageParam ? `&before=${pageParam}` : ""}`),
    getNextPageParam: (last) => (last.has_more && last.next_before ? String(last.next_before) : undefined),
  });
  const events = list.data?.pages.flatMap((p) => p.results) ?? [];

  const controls = (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Select aria-label="Engagement" value={filters.engagement} onChange={(e) => setFilters({ engagement: e.target.value })}>
          <option value="">All engagements</option>
          {facets.data?.engagements.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
        </Select>
        <Select aria-label="Person" value={filters.actor} onChange={(e) => setFilters({ actor: e.target.value })}>
          <option value="">Anyone</option>
          {facets.data?.actors.map((a) => <option key={a.id} value={a.id}>{a.label || a.id}</option>)}
        </Select>
        <Select aria-label="Action" value={filters.action} onChange={(e) => setFilters({ action: e.target.value })}>
          <option value="">All actions</option>
          {filters.action && !facets.data?.actions.includes(filters.action) && <option value={filters.action}>{filters.action}</option>}
          {facets.data?.actions.map((a) => <option key={a} value={a}>{humanAction(a)}</option>)}
        </Select>
        <Select aria-label="Kind of record" value={filters.entity_type} onChange={(e) => setFilters({ entity_type: e.target.value, entity_id: "" })}>
          <option value="">All records</option>
          {facets.data?.entity_types.map((t) => <option key={t} value={t}>{t}</option>)}
        </Select>
        <Select aria-label="Outcome" value={filters.outcome} onChange={(e) => setFilters({ outcome: e.target.value })}>
          <option value="">Any outcome</option>
          <option value="success">Succeeded</option>
          <option value="denied">Denied</option>
          <option value="failure">Failed</option>
        </Select>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="From">{(p) => <TextInput {...p} type="date" value={filters.from} max={filters.to || undefined} onChange={(e) => setFilters({ from: e.target.value })} />}</Field>
        <Field label="To">{(p) => <TextInput {...p} type="date" value={filters.to} min={filters.from || undefined} onChange={(e) => setFilters({ to: e.target.value })} />}</Field>
      </div>
      {(filters.entity_id || filters.request_id) && (
        <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] text-muted">
          {filters.entity_id && <Badge tone="info">Record {filters.entity_id.slice(0, 8)}…</Badge>}
          {filters.request_id && <Badge tone="info">Request {filters.request_id.slice(0, 8)}…</Badge>}
        </p>
      )}
    </div>
  );

  return (
    <>
      <PageHeader
        title="Audit"
        lead={isAdmin ? "Every change and refusal on the platform, newest first." : "Changes and refusals on your engagements, newest first."}
        actions={isAdmin ? <Button onClick={() => setExporting(true)}><Download size={18} aria-hidden /> Export CSV</Button> : undefined}
      />
      {isAdmin && <IntegrityPanel />}

      <div className="card overflow-hidden">
        <div className="hidden border-b border-line p-4 md:block">
          {controls}
          {active.length > 0 && <div className="mt-4"><Button size="sm" onClick={() => setParams({}, { replace: true })}>Clear filters</Button></div>}
        </div>
        <div className="flex items-center justify-between gap-3 border-b border-line p-3 md:hidden">
          <Button onClick={() => setSheet(true)}><SlidersHorizontal size={18} aria-hidden /> Filters{active.length ? ` (${active.length})` : ""}</Button>
          {active.length > 0 && <Button size="sm" onClick={() => setParams({}, { replace: true })}>Clear</Button>}
        </div>

        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && events.length === 0 && <EmptyState title={active.length ? "Nothing matches" : "No events yet"} body={active.length ? "Clear a filter or widen the dates." : "Events appear here as people use the platform."} action={active.length ? <Button onClick={() => setParams({}, { replace: true })}>Clear filters</Button> : undefined} />}
        {events.length > 0 && (
          <>
            <table className="data-table hidden lg:table">
              <thead><tr><th>When</th><th>Who</th><th>What</th><th>Record</th><th>Engagement</th></tr></thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} onClick={() => setOpen(e)}>
                    <td className="whitespace-nowrap text-muted">{formatDate(e.occurred_at)}</td>
                    <td>{e.actor_label || "System"}</td>
                    <td><button type="button" className="text-left font-medium hover:underline" onClick={(ev) => { ev.stopPropagation(); setOpen(e); }}>{humanAction(e.action)}</button> <OutcomeBadge outcome={e.outcome} /></td>
                    <td className="max-w-xs truncate">{e.entity_label || e.entity_type}</td>
                    <td className="mono text-[14px]">{e.engagement?.ref ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 lg:hidden">
              {events.map((e) => (
                <li key={e.id}>
                  <button type="button" onClick={() => setOpen(e)} className="block w-full space-y-1 px-4 py-3 text-left">
                    <span className="flex flex-wrap items-center gap-2"><span className="font-medium">{humanAction(e.action)}</span><OutcomeBadge outcome={e.outcome} /></span>
                    <span className="block text-[15px]">{e.entity_label || e.entity_type}</span>
                    <span className="block text-[14px] text-muted">{e.actor_label || "System"} · {formatDate(e.occurred_at)}{e.engagement ? ` · ${e.engagement.ref}` : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex justify-center border-t border-line p-4">
              {list.hasNextPage
                ? <Button loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>Load older events</Button>
                : <span className="text-[14px] text-muted">That is everything: {events.length} event{events.length === 1 ? "" : "s"}.</span>}
            </div>
          </>
        )}
      </div>

      <Sheet open={sheet} onClose={() => setSheet(false)} title="Filters">
        <div className="flex flex-col gap-5 p-5">{controls}<Button variant="primary" block onClick={() => setSheet(false)}>Show events</Button></div>
      </Sheet>
      <EventDrawer event={open} onClose={() => setOpen(null)} onFilter={(patch) => { setFilters(patch); setOpen(null); }} />
      {exporting && <ExportDialog query={query} onClose={() => setExporting(false)} />}
    </>
  );
}

// event drawer

const LIMIT = 280;

function Value({ v }: { v: unknown }) {
  const [full, setFull] = useState(false);
  if (v === null || v === undefined || v === "") return <span className="text-muted">empty</span>;
  if (v === "[REDACTED]") return <Badge tone="info">Hidden</Badge>;
  const text = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  const long = text.length > LIMIT;
  return (
    <span className="break-words whitespace-pre-wrap">
      {long && !full ? `${text.slice(0, LIMIT)}…` : text}
      {long && <button type="button" className="ml-2 text-accent hover:underline" onClick={() => setFull(!full)}>{full ? "Show less" : "Show more"}</button>}
    </span>
  );
}

function ChangeRows({ changes }: { changes: Record<string, unknown> }) {
  const entries = Object.entries(changes);
  if (entries.length === 0) return <p className="m-0 text-muted">No field changes were recorded.</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {entries.map(([field, v]) => {
        const pair = Array.isArray(v) && v.length === 2 ? v : null;
        return (
          <li key={field} className="rounded-md border border-line p-3">
            <p className="label m-0 mb-2">{field.replace(/_/g, " ")}</p>
            {pair ? (
              <div className="grid gap-2 sm:grid-cols-2">
                <div><p className="m-0 text-[13px] text-muted">Before</p><p className="m-0 text-[15px]"><Value v={pair[0]} /></p></div>
                <div><p className="m-0 text-[13px] text-muted">After</p><p className="m-0 text-[15px]"><Value v={pair[1]} /></p></div>
              </div>
            ) : <p className="m-0 text-[15px]"><Value v={v} /></p>}
          </li>
        );
      })}
    </ul>
  );
}

function EventDrawer({ event, onClose, onFilter }: { event: AuditEvent | null; onClose: () => void; onFilter: (patch: Partial<Filters>) => void }) {
  const e = event;
  const meta = e ? Object.entries(e.metadata) : [];
  const rows: Array<[string, React.ReactNode]> = e ? [
    ["When", formatDate(e.occurred_at)],
    ["Who", e.actor_label || "System"],
    ["Record", `${e.entity_type}${e.entity_label ? ` · ${e.entity_label}` : ""}`],
    ...(e.engagement ? [["Engagement", e.engagement.ref] as [string, React.ReactNode]] : []),
    ["Action code", <span key="a" className="mono break-all">{e.action}</span>],
    ...(e.actor_ip ? [["IP address", <span key="i" className="mono">{e.actor_ip}</span>] as [string, React.ReactNode]] : []),
    ...(e.request_id ? [["Request", <span key="r" className="mono break-all">{e.request_id}</span>] as [string, React.ReactNode]] : []),
    ...(e.hash ? [["Hash", <span key="h" className="mono break-all text-[13px]">{e.hash}</span>] as [string, React.ReactNode]] : []),
  ] : [];
  return (
    <Sheet open={!!e} onClose={onClose} title={e ? humanAction(e.action) : "Event"}>
      {e && (
        <div className="flex flex-col gap-5 p-5">
          <p className="m-0 flex flex-wrap items-center gap-2"><Badge tone={e.outcome === "success" ? "ok" : "fail"}>{e.outcome === "success" ? "Succeeded" : e.outcome === "denied" ? "Denied" : "Failed"}</Badge><span className="text-muted">#{e.id}</span></p>
          <dl className="m-0 grid gap-3">
            {rows.map(([k, v]) => <div key={k}><dt className="label">{k}</dt><dd className="m-0 mt-0.5 break-words">{v}</dd></div>)}
          </dl>
          <section><h3 className="mb-3 text-lg">Changes</h3><ChangeRows changes={e.changes} /></section>
          {meta.length > 0 && <section><h3 className="mb-3 text-lg">Details</h3><ChangeRows changes={Object.fromEntries(meta)} /></section>}
          <div className="flex flex-wrap gap-3">
            {e.entity_id && <Button size="sm" onClick={() => onFilter({ entity_type: e.entity_type, entity_id: e.entity_id })}>Show this record's history</Button>}
            {e.request_id && <Button size="sm" onClick={() => onFilter({ request_id: e.request_id })}>Show this request</Button>}
          </div>
        </div>
      )}
    </Sheet>
  );
}

// integrity (Super Admin)

function IntegrityPanel() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["audit-integrity"],
    queryFn: () => api<IntegrityState>("GET", "/audit/integrity"),
    refetchInterval: (query) => (query.state.data?.latest?.status === "running" ? 2000 : false),
  });
  const run = useMutation({ mutationFn: () => api("POST", "/audit/verify", {}), onSuccess: () => void qc.invalidateQueries({ queryKey: ["audit-integrity"] }) });
  const d = q.data;
  const last = d?.last_finished;
  const running = d?.latest?.status === "running";
  return (
    <section className="mb-6" aria-label="Log integrity">
      {q.isError && <ErrorNote error={q.error} />}
      {d?.broken && last ? (
        <Alert tone="error">
          <p className="m-0 font-medium">The audit log failed its integrity check.</p>
          <p className="m-0 mt-1">{(last.reason || "An event no longer matches its hash").replace(/\.?$/, ".")} First bad event: #{last.first_bad_id}. Checked {last.checked.toLocaleString()} events before the break, on {formatDate(last.finished_at)}. Treat the log after that point as untrustworthy and investigate.</p>
        </Alert>
      ) : (
        <div className="card card-pad flex flex-wrap items-center justify-between gap-4">
          <p className="m-0 flex items-center gap-3">
            {last?.status === "ok" ? <ShieldCheck size={22} className="flex-none text-ok" aria-hidden /> : <ShieldAlert size={22} className="flex-none text-muted" aria-hidden />}
            <span>
              {last?.status === "ok" ? <><span className="font-medium">Chain intact.</span> {last.checked.toLocaleString()} events verified {formatDate(last.finished_at)}.</>
                : last?.status === "error" ? <><span className="font-medium">The last check could not run.</span> {last.reason}</>
                : <span className="text-muted">The log has not been verified yet.</span>}
            </span>
          </p>
          <Button loading={running || run.isPending} onClick={() => run.mutate()}>{running ? "Verifying…" : "Verify now"}</Button>
        </div>
      )}
      {d?.broken && <div className="mt-3"><Button loading={running || run.isPending} onClick={() => run.mutate()}>{running ? "Verifying…" : "Verify again"}</Button></div>}
      <ErrorNote error={run.error} />
    </section>
  );
}

// export (Super Admin)

function ExportDialog({ query, onClose }: { query: URLSearchParams; onClose: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const filters = [...query.entries()];
  async function download() {
    setBusy(true);
    setError(null);
    try {
      await downloadFile(`/audit/export?${query}`, "redshadow-audit.csv");
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} title="Export audit events">
      <div className="flex flex-col gap-5 p-6">
        <p className="m-0 text-muted">Downloads the events that match the filters below as a CSV, up to 50,000. The export itself is recorded in the audit log with the file's checksum.</p>
        {filters.length === 0 ? <p className="m-0">No filters: every event.</p> : (
          <ul className="m-0 list-none space-y-1 p-0 text-[15px]">{filters.map(([k, v]) => <li key={k}><span className="text-muted">{k.replace(/_/g, " ")}:</span> <span className="break-all">{v}</span></li>)}</ul>
        )}
        <ErrorNote error={error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => void download()}>Download CSV</Button>
        </div>
      </div>
    </Modal>
  );
}
