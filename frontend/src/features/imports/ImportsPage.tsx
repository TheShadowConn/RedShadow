import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, downloadFile, upload } from "../../api/client";
import { IMPORT_STATUSES, type EngagementRow, type ImportJob, type Page } from "../../api/types";
import {
  Alert, Badge, Button, EmptyState, ErrorNote, ErrorState, Field, formatBytes, formatDate, label, LoadingRows, PageHeader, Pager, Select,
} from "../../design/ui";

const PAGE_SIZE = 25;
const MAX_BYTES = 10 * 1024 * 1024;
const TONE: Record<string, "ok" | "warn" | "fail" | "info"> = {
  uploaded: "info", parsing: "warn", parsed: "info", validating: "warn", previewed: "info", importing: "warn", completed: "ok", failed: "fail", cancelled: "info",
};

export function ImportStatus({ status }: { status: string }) {
  return <Badge tone={TONE[status] ?? "info"}>{label(IMPORT_STATUSES, status)}</Badge>;
}

/** Import history, and the first step of the wizard (choose engagement and file). */
export function ImportsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [page, setPage] = useState(1);
  const [starting, setStarting] = useState(false);
  const list = useQuery({ queryKey: ["imports", page], queryFn: () => api<Page<ImportJob>>("GET", `/imports?page=${page}&page_size=${PAGE_SIZE}`), placeholderData: (p) => p, refetchInterval: (q) => (q.state.data?.results.some((j) => ["parsing", "validating", "importing"].includes(j.status)) ? 3000 : false) });
  const rows = list.data?.results ?? [];
  const canCreate = can("imports.create");

  return (
    <>
      <PageHeader
        title="Imports"
        lead="Bring findings in from a CSV file. Imported findings arrive as drafts for a pentester to review and publish."
        actions={canCreate ? <Button variant="primary" onClick={() => setStarting(!starting)}><Upload size={18} aria-hidden /> New import</Button> : undefined}
      />
      {starting && canCreate && <NewImport onDone={(id) => nav(`/imports/${id}`)} onCancel={() => setStarting(false)} />}
      <div className="card overflow-hidden">
        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && rows.length === 0 && <EmptyState title="No imports yet" body="Upload a CSV of findings to map its columns, check every row and import the valid ones." action={canCreate ? <Button variant="primary" onClick={() => setStarting(true)}>New import</Button> : undefined} />}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead><tr><th>File</th><th>Engagement</th><th>Status</th><th>Rows</th><th>Imported</th><th>By</th><th>When</th></tr></thead>
              <tbody>
                {rows.map((j) => (
                  <tr key={j.id} onClick={() => nav(`/imports/${j.id}`)}>
                    <td><Link to={`/imports/${j.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{j.original_name}</Link></td>
                    <td>{j.engagement.name}</td><td><ImportStatus status={j.status} /></td>
                    <td>{j.counts.total ?? "…"}</td><td>{j.counts.imported ?? 0}</td><td>{j.uploaded_by.display_name}</td>
                    <td className="whitespace-nowrap text-muted">{formatDate(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((j) => (
                <li key={j.id}>
                  <Link to={`/imports/${j.id}`} className="block space-y-1.5 px-4 py-4">
                    <span className="flex flex-wrap items-center gap-2"><span className="font-medium break-all">{j.original_name}</span><ImportStatus status={j.status} /></span>
                    <span className="block text-[15px]">{j.engagement.name}</span>
                    <span className="block text-[14px] text-muted">{j.counts.total ?? "…"} rows · {j.counts.imported ?? 0} imported · {j.uploaded_by.display_name} · {formatDate(j.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <Pager page={page} count={list.data!.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>
    </>
  );
}

function NewImport({ onDone, onCancel }: { onDone: (id: string) => void; onCancel: () => void }) {
  const [engagement, setEngagement] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dlError, setDlError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);
  const engagements = useQuery({ queryKey: ["engagements-pick"], queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100&archived=all") });
  const options = engagements.data?.results.filter((e) => !e.archived_at && e.status !== "cancelled") ?? [];
  const send = useMutation({
    mutationFn: () => upload<ImportJob>("POST", "/imports", file!, setProgress, { engagement }),
    onSuccess: (job) => onDone(job.id),
    onSettled: () => setProgress(null),
  });

  function pick(f: File | undefined) {
    send.reset();
    if (!f) return setFile(null);
    if (f.size === 0) return (setFile(null), setProblem("That file is empty."));
    if (f.size > MAX_BYTES) return (setFile(null), setProblem(`${f.name} is ${formatBytes(f.size)}. The limit is 10 MB.`));
    if (!/\.(csv|tsv|txt)$/i.test(f.name)) return (setFile(null), setProblem("Choose a .csv file."));
    setProblem(null);
    setFile(f);
  }

  return (
    <form className="card card-pad mb-6 flex flex-col gap-5" onSubmit={(e) => { e.preventDefault(); if (file && engagement) send.mutate(); }}>
      <h2 className="text-xl">Step 1: choose the engagement and the file</h2>
      <ErrorNote error={send.error} />
      {problem && <Alert tone="error">{problem}</Alert>}
      <ErrorNote error={dlError} />
      <Field label="Engagement" hint="Findings are created in this engagement, as drafts.">
        {(p) => (
          <Select {...p} required value={engagement} onChange={(e) => setEngagement(e.target.value)}>
            <option value="" disabled>{engagements.isPending ? "Loading…" : "Choose an engagement"}</option>
            {options.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
          </Select>
        )}
      </Field>
      <div className="flex flex-col items-start gap-2">
        <span className="label">CSV file</span>
        <input ref={input} type="file" accept=".csv,.tsv,.txt,text/csv" className="sr-only" aria-label="Choose CSV file" onChange={(e) => pick(e.target.files?.[0])} />
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => input.current?.click()}>{file ? "Choose another file" : "Choose file"}</Button>
          {file && <span className="break-all">{file.name} <span className="text-muted">({formatBytes(file.size)})</span></span>}
        </div>
        <p className="m-0 text-[14px] text-muted">UTF-8 or Windows-1252, comma, semicolon or tab separated, first row holds the column names. Up to 10 MB and 50,000 rows.</p>
        <button type="button" className="inline-flex min-h-11 items-center gap-2 text-accent hover:underline" onClick={() => downloadFile("/imports/template.csv").catch(setDlError)}><Download size={16} aria-hidden /> Download a template</button>
      </div>
      {progress !== null && (
        <div role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
          <div className="h-2 overflow-hidden rounded-full bg-raised"><div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} /></div>
        </div>
      )}
      <div className="flex flex-wrap justify-end gap-3">
        <Button onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={send.isPending} disabled={!file || !engagement}>Upload and read file</Button>
      </div>
    </form>
  );
}
