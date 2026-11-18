import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2, Upload } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, downloadFile, upload } from "../../api/client";
import { IMPORT_STATUSES, type EngagementRow, type ImportJob, type Organisation, type Page } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, formatBytes, formatDate, label, LoadingRows, PageHeader, Pager,
  Select, TextInput,
} from "../../design/ui";

const PAGE_SIZE = 25;
const MAX_BYTES = 10 * 1024 * 1024;
const TONE: Record<string, "ok" | "warn" | "fail" | "info"> = {
  uploaded: "info", parsing: "warn", parsed: "info", validating: "warn", previewed: "info", importing: "warn", completed: "ok", failed: "fail", cancelled: "info",
};
const WORKING = ["parsing", "validating", "importing"];

export function ImportStatus({ status }: { status: string }) {
  return <Badge tone={TONE[status] ?? "info"}>{label(IMPORT_STATUSES, status)}</Badge>;
}

export const targetName = (j: Pick<ImportJob, "engagement" | "organisation">) => j.engagement?.name ?? j.organisation?.name ?? "";
export const KindBadge = ({ kind }: { kind: ImportJob["kind"] }) => <Badge tone="info">{kind === "assets" ? "Assets" : "Findings"}</Badge>;

/** Import history, and the first step of the wizard (choose the target and the file). */
export function ImportsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [starting, setStarting] = useState<"findings" | "assets" | null>(params.get("new") === "assets" ? "assets" : null);
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [deleting, setDeleting] = useState<ImportJob | null>(null);
  const canFindings = can("imports.create");
  const canAssets = can("imports.create") && can("assets.import");

  useEffect(() => { const t = setTimeout(() => { setTerm(search.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (kind) query.set("kind", kind);
  if (status) query.set("status", status);
  if (term) query.set("search", term);
  const list = useQuery({
    queryKey: ["imports", query.toString()],
    queryFn: () => api<Page<ImportJob>>("GET", `/imports?${query}`),
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.results.some((j) => WORKING.includes(j.status)) ? 3000 : false),
  });
  const rows = list.data?.results ?? [];
  const remove = useMutation({
    mutationFn: (j: ImportJob) => api("DELETE", `/imports/${j.id}`),
    onSuccess: () => { setDeleting(null); void qc.invalidateQueries({ queryKey: ["imports"] }); },
  });
  const filtered = !!(kind || status || term);
  const start = (k: "findings" | "assets" | null) => { setStarting(k); if (params.get("new")) setParams({}, { replace: true }); };

  return (
    <>
      <PageHeader
        title="Imports"
        lead="Bring findings or assets in from a CSV file. Findings arrive as drafts for a pentester to review. Assets arrive not onboarded, matched by their identifiers so nothing is created twice."
        actions={
          <>
            {canAssets && <Button onClick={() => start("assets")}><Upload size={18} aria-hidden /> Import assets</Button>}
            {canFindings && <Button variant="primary" onClick={() => start("findings")}><Upload size={18} aria-hidden /> Import findings</Button>}
          </>
        }
      />
      {starting && <NewImport kind={starting} onDone={(id) => nav(`/imports/${id}`)} onCancel={() => start(null)} />}

      <div className="card overflow-hidden">
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-[minmax(200px,1fr)_160px_180px]">
          <TextInput aria-label="Search by file name" placeholder="Search by file name" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Select aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">All kinds</option><option value="findings">Findings</option><option value="assets">Assets</option></Select>
          <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">Any status</option>{IMPORT_STATUSES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        </div>
        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && rows.length === 0 && (
          <EmptyState
            title={filtered ? "No imports match" : "No imports yet"}
            body={filtered ? "Try a different search or clear a filter." : "Upload a CSV to map its columns, check every row and import the valid ones."}
            action={!filtered && canFindings ? <Button variant="primary" onClick={() => start("findings")}>Import findings</Button> : undefined}
          />
        )}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead><tr><th>File</th><th>Kind</th><th>Target</th><th>Status</th><th>Rows</th><th>Imported</th><th>By</th><th>When</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((j) => (
                  <tr key={j.id} onClick={() => nav(`/imports/${j.id}`)}>
                    <td><Link to={`/imports/${j.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{j.original_name}</Link>{j.attempt > 1 && <span className="ml-2 text-[13px] text-muted">attempt {j.attempt}</span>}</td>
                    <td><KindBadge kind={j.kind} /></td>
                    <td>{targetName(j)}</td><td><ImportStatus status={j.status} /></td>
                    <td>{j.counts.total ?? "…"}</td><td>{j.counts.imported ?? 0}</td><td>{j.uploaded_by.display_name}</td>
                    <td className="whitespace-nowrap text-muted">{formatDate(j.created_at)}</td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>{j.can_delete && <Button size="sm" aria-label={`Delete ${j.original_name}`} onClick={() => { remove.reset(); setDeleting(j); }}><Trash2 size={14} aria-hidden /></Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((j) => (
                <li key={j.id}>
                  <Link to={`/imports/${j.id}`} className="block space-y-1.5 px-4 py-4">
                    <span className="flex flex-wrap items-center gap-2"><span className="font-medium break-all">{j.original_name}</span><ImportStatus status={j.status} /><KindBadge kind={j.kind} /></span>
                    <span className="block text-[15px]">{targetName(j)}</span>
                    <span className="block text-[14px] text-muted">{j.counts.total ?? "…"} rows · {j.counts.imported ?? 0} imported · {j.uploaded_by.display_name} · {formatDate(j.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <Pager page={page} count={list.data!.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>
      <ConfirmDialog
        open={!!deleting}
        title="Delete import"
        body={`${deleting?.original_name} is deleted with its rows, its history and the uploaded file. Nothing it was meant to create exists, so no findings or assets are affected. This cannot be undone.`}
        confirmLabel="Delete import"
        danger
        busy={remove.isPending}
        error={remove.error}
        onConfirm={() => deleting && remove.mutate(deleting)}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}

export function useFilePicker() {
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  function pick(f: File | undefined) {
    if (!f) return setFile(null);
    if (f.size === 0) return (setFile(null), setProblem("That file is empty."));
    if (f.size > MAX_BYTES) return (setFile(null), setProblem(`${f.name} is ${formatBytes(f.size)}. The limit is 10 MB.`));
    if (!/\.(csv|tsv|txt)$/i.test(f.name)) return (setFile(null), setProblem("Choose a .csv file."));
    setProblem(null);
    setFile(f);
  }
  return { file, problem, pick, reset: () => { setFile(null); setProblem(null); } };
}

function UploadProgress({ progress }: { progress: number | null }) {
  if (progress === null) return null;
  return (
    <div role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
      <div className="h-2 overflow-hidden rounded-full bg-raised"><div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} /></div>
    </div>
  );
}

function NewImport({ kind, onDone, onCancel }: { kind: "findings" | "assets"; onDone: (id: string) => void; onCancel: () => void }) {
  const [target, setTarget] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [dlError, setDlError] = useState<unknown>(null);
  const picker = useFilePicker();
  const input = useRef<HTMLInputElement>(null);
  const isAssets = kind === "assets";
  const engagements = useQuery({ queryKey: ["engagements-pick"], queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100&archived=all"), enabled: !isAssets });
  const orgs = useQuery({ queryKey: ["organisations-pick"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100"), enabled: isAssets });
  const options = engagements.data?.results.filter((e) => !e.archived_at && e.status !== "cancelled") ?? [];
  const send = useMutation({
    mutationFn: () => upload<ImportJob>("POST", "/imports", picker.file!, setProgress, isAssets ? { kind: "assets", organisation: target } : { engagement: target }),
    onSuccess: (job) => onDone(job.id),
    onSettled: () => setProgress(null),
  });

  return (
    <form className="card card-pad mb-6 flex flex-col gap-5" onSubmit={(e) => { e.preventDefault(); if (picker.file && target) send.mutate(); }}>
      <h2 className="text-xl">{isAssets ? "Step 1: choose the organisation and the file" : "Step 1: choose the engagement and the file"}</h2>
      <ErrorNote error={send.error} />
      {picker.problem && <Alert tone="error">{picker.problem}</Alert>}
      <ErrorNote error={dlError} />
      {isAssets ? (
        <Field label="Organisation" hint="Assets are matched against this organisation's assets by their identifiers. Rows that match are not created again. New assets arrive not onboarded.">
          {(p) => (
            <Select {...p} required value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="" disabled>{orgs.isPending ? "Loading…" : "Choose an organisation"}</option>
              {orgs.data?.results.filter((o) => !o.archived).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          )}
        </Field>
      ) : (
        <Field label="Engagement" hint="Findings are created in this engagement, as drafts.">
          {(p) => (
            <Select {...p} required value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="" disabled>{engagements.isPending ? "Loading…" : "Choose an engagement"}</option>
              {options.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
            </Select>
          )}
        </Field>
      )}
      <div className="flex flex-col items-start gap-2">
        <span className="label">CSV file</span>
        <input ref={input} type="file" accept=".csv,.tsv,.txt,text/csv" className="sr-only" aria-label="Choose CSV file" onChange={(e) => { send.reset(); picker.pick(e.target.files?.[0]); }} />
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => input.current?.click()}>{picker.file ? "Choose another file" : "Choose file"}</Button>
          {picker.file && <span className="break-all">{picker.file.name} <span className="text-muted">({formatBytes(picker.file.size)})</span></span>}
        </div>
        <p className="m-0 text-[14px] text-muted">UTF-8 or Windows-1252, comma, semicolon or tab separated, first row holds the column names. Up to 10 MB and 50,000 rows.</p>
        <button type="button" className="inline-flex min-h-11 items-center gap-2 text-accent hover:underline" onClick={() => downloadFile(isAssets ? "/imports/asset-template.csv" : "/imports/template.csv").catch(setDlError)}><Download size={16} aria-hidden /> Download a template</button>
      </div>
      <UploadProgress progress={progress} />
      <div className="flex flex-wrap justify-end gap-3">
        <Button onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={send.isPending} disabled={!picker.file || !target}>Upload and read file</Button>
      </div>
    </form>
  );
}

/** Upload a corrected file into the same import. Shown wherever the import can take one. */
export function ReuploadPanel({ job, onDone }: { job: ImportJob; onDone: () => void }) {
  const [progress, setProgress] = useState<number | null>(null);
  const picker = useFilePicker();
  const input = useRef<HTMLInputElement>(null);
  const send = useMutation({
    mutationFn: () => upload<ImportJob>("POST", `/imports/${job.id}/reupload`, picker.file!, setProgress),
    onSuccess: () => { picker.reset(); onDone(); },
    onSettled: () => setProgress(null),
  });
  return (
    <section className="card card-pad flex flex-col gap-3" aria-labelledby="reupload-h">
      <h2 id="reupload-h" className="text-xl">Upload a corrected file</h2>
      <p className="m-0 text-muted">Fix the rows in your spreadsheet and upload the whole file again. It goes into this same import as attempt {job.attempt + 1}, with the same columns. Rows that were already imported are recognised and skipped, so nothing is created twice.</p>
      <ErrorNote error={send.error} />
      {picker.problem && <Alert tone="error">{picker.problem}</Alert>}
      <input ref={input} type="file" accept=".csv,.tsv,.txt,text/csv" className="sr-only" aria-label="Choose corrected CSV file" onChange={(e) => { send.reset(); picker.pick(e.target.files?.[0]); }} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => input.current?.click()}>{picker.file ? "Choose another file" : "Choose corrected file"}</Button>
        {picker.file && <span className="break-all">{picker.file.name} <span className="text-muted">({formatBytes(picker.file.size)})</span></span>}
        <Button variant="primary" loading={send.isPending} disabled={!picker.file} onClick={() => send.mutate()}><Upload size={16} aria-hidden /> Upload and check</Button>
      </div>
      <UploadProgress progress={progress} />
    </section>
  );
}
