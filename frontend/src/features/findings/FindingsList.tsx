import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileUp, Plus, Search } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, downloadFile } from "../../api/client";
import { FINDING_STATUSES, SEVERITIES, type BulkResult, type Engagement, type EngagementRow, type FindingRow, type Page, type User } from "../../api/types";
import {
  Alert, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, formatDay, LoadingRows, Modal, Pager, Select, TextInput,
} from "../../design/ui";
import { announceUndo } from "../../design/undo";
import { TagList } from "../assets/Tags";
import { FindingStatus, SeverityBadge, userName } from "./shared";

const PAGE_SIZE = 25;
type Filters = { search: string; severity: string[]; status: string; engagement: string; mine: boolean; review: boolean; ordering: string; tag: string; untagged: boolean };
const EMPTY: Filters = { search: "", severity: [], status: "", engagement: "", mine: false, review: false, ordering: "-severity", tag: "", untagged: false };

/** Findings table with filters, paging and bulk actions. Pass `engagement` to lock it to one engagement. */
export function FindingsList({ engagement }: { engagement?: Engagement }) {
  const { can } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams(); // dashboard tiles link here with filters in the address
  const [f, setF] = useState<Filters>(() => ({
    ...EMPTY,
    severity: engagement ? [] : (params.get("severity")?.split(",").filter((x) => SEVERITIES.some(([k]) => k === x)) ?? []),
    status: engagement ? "" : (params.get("status") ?? ""),
    mine: !engagement && params.get("assigned") === "me",
    review: params.get("needs_review") === "true",
    tag: engagement ? "" : (params.get("tag") ?? ""),
    untagged: !engagement && params.get("untagged") === "true",
  }));
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<"publish" | "assign" | "delete" | null>(null);
  const [result, setResult] = useState<(BulkResult & { names: Map<string, string> }) | null>(null);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const update = (patch: Partial<Filters>) => { setF({ ...f, ...patch }); setPage(1); setPicked(new Set()); };

  const engagements = useQuery({
    queryKey: ["engagements-pick"],
    queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100&archived=all"),
    enabled: !engagement && can("engagements.view"),
  });

  const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE), ordering: f.ordering, search: f.search });
  const eng = engagement?.id ?? f.engagement;
  if (eng) qs.set("engagement", eng);
  if (f.severity.length) qs.set("severity", f.severity.join(","));
  if (f.status) qs.set("status", f.status);
  if (f.mine) qs.set("assigned", "me");
  if (f.review) qs.set("needs_review", "true");
  if (f.tag) qs.set("tag", f.tag);
  if (f.untagged) qs.set("untagged", "true");
  const list = useQuery({ queryKey: ["findings", qs.toString()], queryFn: () => api<Page<FindingRow>>("GET", `/findings?${qs}`), placeholderData: (p) => p });
  const filtered = !!(f.tag || f.untagged || f.search || f.severity.length || f.status || f.engagement || f.mine || f.review);
  const rows = list.data?.results ?? [];
  const canBulk = can("findings.bulk_update");
  const canCreate = engagement ? engagement.permissions.includes("findings.create") && !engagement.archived_at : can("findings.create");
  const allPicked = rows.length > 0 && rows.every((r) => picked.has(r.id));

  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const toggleAll = () => setPicked(allPicked ? new Set() : new Set(rows.map((r) => r.id)));

  const run = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<BulkResult>("POST", "/findings/bulk", { ids: [...picked], ...body }),
    onSuccess: (r, vars) => {
      setResult({ ...r, names: new Map(rows.map((x) => [x.id, `${x.ref} ${x.title}`])) });
      setBulk(null); setPicked(new Set()); void qc.invalidateQueries({ queryKey: ["findings"] });
      const gone = r.results.filter((x) => x.ok).map((x) => x.id);
      if (vars.action === "delete" && gone.length) announceUndo(`${gone.length} finding${gone.length === 1 ? "" : "s"} deleted.`, () => api("POST", "/findings/restore", { ids: gone }));
    },
  });
  async function exportCsv() {
    const x = new URLSearchParams({ ordering: f.ordering });
    if (f.search) x.set("search", f.search);
    if (eng) x.set("engagement", eng);
    if (f.severity.length) x.set("severity", f.severity.join(","));
    if (f.status) x.set("status", f.status);
    if (f.mine) x.set("assigned", "me");
    if (f.review) x.set("needs_review", "true");
    if (f.tag) x.set("tag", f.tag);
    if (f.untagged) x.set("untagged", "true");
    setExporting(true);
    setExportError(null);
    try { await downloadFile(`/findings/export.csv?${x}`, "redshadow-findings.csv"); } catch (e) { setExportError(e); } finally { setExporting(false); }
  }
  const newUrl = `/findings/new${engagement ? `?engagement=${engagement.id}` : ""}`;

  return (
    <>
      <div className="card overflow-hidden">
        <div className="space-y-3 border-b border-line p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(220px,1.5fr)_repeat(3,minmax(0,1fr))]">
            <div className="relative sm:col-span-2 lg:col-span-1">
              <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
              <TextInput aria-label="Search findings" placeholder="Search findings" className="pl-11" value={f.search} onChange={(e) => update({ search: e.target.value })} />
            </div>
            <Select aria-label="Status" value={f.status} onChange={(e) => update({ status: e.target.value })}>
              <option value="">All statuses</option>
              {f.status.includes(",") && <option value={f.status}>Open or in progress</option>}
              {FINDING_STATUSES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            {!engagement && can("engagements.view") && (
              <Select aria-label="Engagement" value={f.engagement} onChange={(e) => update({ engagement: e.target.value })}>
                <option value="">All engagements</option>
                {engagements.data?.results.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
              </Select>
            )}
            <Select aria-label="Sort by" value={f.ordering} onChange={(e) => update({ ordering: e.target.value })}>
              <option value="-severity">Most severe first</option>
              <option value="severity">Least severe first</option>
              <option value="-discovered_at">Newest discovered</option>
              <option value="discovered_at">Oldest discovered</option>
              <option value="-updated_at">Recently updated</option>
              <option value="title">Title A to Z</option>
            </Select>
          </div>
          {(f.tag || f.untagged) && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="label">Department</span>
              <TagList tags={[f.tag || "Untagged"]} onRemove={() => update({ tag: "", untagged: false })} />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <fieldset className="m-0 flex min-w-0 flex-wrap items-center gap-x-4 border-0 p-0">
              <legend className="sr-only">Severity</legend>
              {SEVERITIES.map(([k, v]) => (
                <label key={k} className="check">
                  <input type="checkbox" checked={f.severity.includes(k)} onChange={(e) => update({ severity: e.target.checked ? [...f.severity, k] : f.severity.filter((s) => s !== k) })} />
                  {v}
                </label>
              ))}
            </fieldset>
            <label className="check"><input type="checkbox" checked={f.mine} onChange={(e) => update({ mine: e.target.checked })} /> Assigned to me</label>
            <label className="check"><input type="checkbox" checked={f.review} onChange={(e) => update({ review: e.target.checked })} /> Needs review</label>
            <span className="ml-auto flex flex-wrap items-center gap-3">
              {can("exports.csv") && <Button loading={exporting} onClick={() => void exportCsv()}><Download size={18} aria-hidden /> Export CSV</Button>}
              {can("imports.create") && <Link to="/imports" className="btn btn-secondary"><FileUp size={18} aria-hidden /> Import CSV</Link>}
              {canCreate && <Button variant="primary" onClick={() => nav(newUrl)}><Plus size={18} aria-hidden /> New finding</Button>}
            </span>
          </div>
          {exportError ? <ErrorNote error={exportError} /> : null}
        </div>

        {canBulk && picked.size > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-raised px-4 py-3" role="region" aria-label="Bulk actions">
            <span className="font-medium">{picked.size} selected</span>
            {can("findings.publish") && <Button size="sm" onClick={() => { run.reset(); setBulk("publish"); }}>Publish</Button>}
            {can("findings.assign") && can("users.view") && <Button size="sm" onClick={() => { run.reset(); setBulk("assign"); }}>Assign</Button>}
            {can("findings.delete") && <Button size="sm" variant="danger" onClick={() => { run.reset(); setBulk("delete"); }}>Delete</Button>}
            <Button size="sm" onClick={() => setPicked(new Set())}>Clear selection</Button>
          </div>
        )}

        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && rows.length === 0 && (
          <EmptyState
            title={filtered ? "No findings match" : "No findings yet"}
            body={filtered ? "Clear a filter or try different words." : canCreate ? "Record the first finding for this scope." : "Findings you are allowed to see appear here."}
            action={filtered ? <Button onClick={() => { setF(EMPTY); setPage(1); }}>Clear filters</Button> : canCreate ? <Button variant="primary" onClick={() => nav(newUrl)}>New finding</Button> : undefined}
          />
        )}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead>
                <tr>
                  {canBulk && <th className="w-10"><input type="checkbox" aria-label="Select all on this page" checked={allPicked} onChange={toggleAll} /></th>}
                  <th>Severity</th><th>Finding</th>{!engagement && <th>Engagement</th>}<th>Status</th><th>Owner</th><th>Discovered</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => nav(`/findings/${r.id}`)}>
                    {canBulk && <td onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`Select ${r.ref}`} checked={picked.has(r.id)} onChange={() => toggle(r.id)} /></td>}
                    <td><SeverityBadge severity={r.severity} score={r.cvss_score} /></td>
                    <td><button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); nav(`/findings/${r.id}`); }}><span className="block font-medium">{r.title}</span><span className="mono block text-[14px] text-muted">{r.ref}{r.asset ? ` · ${r.asset.name}` : ""}</span></button></td>
                    {!engagement && <td>{r.engagement.name}</td>}
                    <td><FindingStatus status={r.status} needsReview={r.needs_review} /></td>
                    <td>{userName(r.remediation_owner)}</td>
                    <td className="whitespace-nowrap text-muted">{formatDay(r.discovered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((r) => (
                <li key={r.id} className="flex items-start gap-3 px-4 py-3">
                  {canBulk && <input type="checkbox" className="mt-1.5" aria-label={`Select ${r.ref}`} checked={picked.has(r.id)} onChange={() => toggle(r.id)} />}
                  <button type="button" onClick={() => nav(`/findings/${r.id}`)} className="block min-w-0 flex-1 space-y-1.5 text-left">
                    <span className="flex flex-wrap items-center gap-2"><SeverityBadge severity={r.severity} score={r.cvss_score} /><FindingStatus status={r.status} needsReview={r.needs_review} /></span>
                    <span className="block font-medium">{r.title}</span>
                    <span className="block text-[14px] text-muted"><span className="mono">{r.ref}</span>{!engagement && ` · ${r.engagement.name}`}</span>
                  </button>
                </li>
              ))}
            </ul>
            <Pager page={page} count={list.data!.count} size={PAGE_SIZE} onPage={(p) => { setPage(p); setPicked(new Set()); }} />
          </>
        )}
      </div>

      <ConfirmDialog
        open={bulk === "publish" || bulk === "delete"}
        title={bulk === "delete" ? "Delete findings" : "Publish findings"}
        body={bulk === "delete" ? `${picked.size} selected finding${picked.size === 1 ? " is" : "s are"} removed from every list. Findings other findings point to as the original are skipped. You get a few seconds to press Undo straight after.` : `${picked.size} selected drafts become open and visible to the people assigned. Findings that are not drafts or are incomplete are skipped.`}
        confirmLabel={bulk === "delete" ? "Delete" : "Publish"}
        danger={bulk === "delete"}
        busy={run.isPending}
        error={run.error}
        onConfirm={() => run.mutate({ action: bulk })}
        onClose={() => setBulk(null)}
      />
      {bulk === "assign" && <AssignDialog busy={run.isPending} error={run.error} onClose={() => setBulk(null)} onAssign={(b) => run.mutate({ action: "assign", ...b })} />}
      <Modal open={!!result} onClose={() => setResult(null)} title="Bulk result">
        {result && (
          <div className="space-y-4 p-6">
            <Alert tone={result.failed ? "warn" : "ok"}>{result.succeeded} succeeded, {result.failed} skipped or failed.</Alert>
            {result.failed > 0 && (
              <ul className="m-0 max-h-72 list-none space-y-2 overflow-y-auto p-0">
                {result.results.filter((r) => !r.ok).map((r) => (
                  <li key={r.id} className="rounded-md border border-line p-3 text-[15px]"><span className="block font-medium">{result.names.get(r.id) ?? "Unknown finding"}</span>{r.error?.message}</li>
                ))}
              </ul>
            )}
            <div className="flex justify-end"><Button variant="primary" onClick={() => setResult(null)}>Done</Button></div>
          </div>
        )}
      </Modal>
    </>
  );
}

function AssignDialog({ busy, error, onClose, onAssign }: { busy: boolean; error: unknown; onClose: () => void; onAssign: (b: Record<string, string | null>) => void }) {
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => api<Page<User>>("GET", "/users?page_size=100&search=") });
  const [pentester, setPentester] = useState("");
  const [owner, setOwner] = useState("");
  const options = users.data?.results.filter((u) => u.is_active) ?? [];
  const body: Record<string, string | null> = {};
  if (pentester) body.assigned_pentester = pentester === "none" ? null : pentester;
  if (owner) body.remediation_owner = owner === "none" ? null : owner;
  return (
    <Modal open onClose={onClose} title="Assign selected findings">
      <form className="space-y-5 p-6" onSubmit={(e) => { e.preventDefault(); onAssign(body); }}>
        <ErrorNote error={error} />
        <p className="m-0 text-muted">People must already be on each engagement. Findings where they are not are reported as skipped.</p>
        <div className="field"><label htmlFor="bulk-pen">Assigned pentester</label>
          <Select id="bulk-pen" value={pentester} onChange={(e) => setPentester(e.target.value)}><option value="">Leave unchanged</option><option value="none">Unassign</option>{options.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</Select></div>
        <div className="field"><label htmlFor="bulk-own">Remediation owner</label>
          <Select id="bulk-own" value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">Leave unchanged</option><option value="none">Unassign</option>{options.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</Select></div>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={busy} disabled={!pentester && !owner}>Assign</Button></div>
      </form>
    </Modal>
  );
}
