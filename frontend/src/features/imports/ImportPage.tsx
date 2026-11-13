import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Loader2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api, downloadFile } from "../../api/client";
import { IMPORT_FIELDS, type ImportJob, type ImportRow, type Page, type SavedMapping } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, formatBytes, formatDate, LoadingRows, NotFoundOrError, Pager, Select, TextInput,
} from "../../design/ui";
import { isConflict } from "../findings/shared";
import { ImportStatus } from "./ImportsPage";

const STEPS = ["File", "Columns", "Check", "Import", "Done"];
const WORKING = ["uploaded", "parsing", "validating", "importing"];

function stepOf(status: ImportJob["status"]): number {
  return { uploaded: 0, parsing: 0, parsed: 1, validating: 2, previewed: 2, importing: 3, completed: 4, failed: 4, cancelled: 4 }[status];
}

export function ImportPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["import", id],
    queryFn: () => api<ImportJob>("GET", `/imports/${id}`),
    refetchInterval: (query) => (query.state.data && WORKING.includes(query.state.data.status) ? 1500 : false),
  });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["import", id] }); void qc.invalidateQueries({ queryKey: ["imports"] }); void qc.invalidateQueries({ queryKey: ["import-rows", id] }); };
  const [remap, setRemap] = useState(false);
  const cancel = useMutation({ mutationFn: () => api("POST", `/imports/${id}/cancel`, {}), onSuccess: refresh, onError: (e) => { if (isConflict(e)) refresh(); } });

  const back = <Link to="/imports" className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink"><ArrowLeft size={18} aria-hidden /> Imports</Link>;
  if (q.isPending) return <>{back}<LoadingRows rows={4} /></>;
  if (q.isError) return <>{back}<div className="card"><NotFoundOrError error={q.error} what="Import" onRetry={() => void q.refetch()} /></div></>;
  const job = q.data;
  const step = stepOf(job.status);
  const cancellable = ["uploaded", "parsed", "previewed"].includes(job.status);

  return (
    <>
      {back}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mono m-0 text-[14px] text-muted">{job.engagement.ref}</p>
          <h1 className="mt-1 break-all text-[32px] max-sm:text-[26px]">{job.original_name}</h1>
          <p className="mt-3 flex flex-wrap items-center gap-3 text-muted"><ImportStatus status={job.status} /><span>{job.engagement.name}</span><span>{formatBytes(job.file_size)}</span><span>{formatDate(job.created_at)}</span></p>
        </div>
        {cancellable && <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel import</Button>}
      </header>
      <ol className="m-0 mb-6 flex list-none flex-wrap gap-2 p-0" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s} aria-current={i === step ? "step" : undefined} className={`rounded-md border px-3 py-1.5 text-[14px] ${i === step ? "border-accent bg-raised font-medium" : i < step ? "border-line text-ink" : "border-line text-muted"}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      <ErrorNote error={cancel.error && !isConflict(cancel.error) ? cancel.error : null} />

      {WORKING.includes(job.status) && <Working job={job} />}
      {job.status === "parsed" && <MapStep job={job} initial={job.suggested_mapping} onDone={refresh} />}
      {job.status === "previewed" && remap && <MapStep job={job} initial={job.mapping.column_map ?? {}} onDone={() => { setRemap(false); refresh(); }} onBack={() => setRemap(false)} />}
      {job.status === "previewed" && !remap && <PreviewStep job={job} onDone={refresh} onChangeColumns={() => setRemap(true)} />}
      {job.status === "completed" && <DoneStep job={job} />}
      {job.status === "failed" && (
        <div className="flex flex-col gap-4">
          <Alert tone="error"><p className="m-0 font-medium">This import did not finish.</p><p className="m-0 mt-1">{job.error || "Something went wrong."}</p></Alert>
          <div><Link to="/imports" className="btn btn-primary">Back to imports</Link></div>
        </div>
      )}
      {job.status === "cancelled" && <div className="card"><EmptyState title="Import cancelled" body="Nothing was imported and the uploaded file was deleted." action={<Link to="/imports" className="btn btn-primary">Back to imports</Link>} /></div>}
    </>
  );
}

function Working({ job }: { job: ImportJob }) {
  const text = { uploaded: "Waiting for the worker…", parsing: "Reading the file…", validating: "Checking every row…", importing: "Creating the draft findings in one step. Nothing is kept if it fails…" }[job.status as "uploaded"];
  return (
    <div className="card card-pad flex items-center gap-4" role="status">
      <Loader2 className="flex-none animate-spin text-accent" aria-hidden />
      <div><p className="m-0 font-medium">{text}</p><p className="m-0 text-[14px] text-muted">{job.counts.total ? `${job.counts.total.toLocaleString()} rows. ` : ""}Large files take a minute. You can leave this page; the import carries on.</p></div>
    </div>
  );
}

// step 2: columns

function MapStep({ job, initial, onDone, onBack }: { job: ImportJob; initial: Record<string, string>; onDone: () => void; onBack?: () => void }) {
  const saved = useQuery({ queryKey: ["import-mappings"], queryFn: () => api<SavedMapping[]>("GET", "/import-mappings") });
  const [map, setMap] = useState<Record<string, string>>(initial);
  const [saveAs, setSaveAs] = useState("");
  const send = useMutation({
    mutationFn: () => api("POST", `/imports/${job.id}/mapping`, { column_map: map, value_map: job.mapping.value_map ?? {}, save_as: saveAs }),
    onSuccess: onDone,
    onError: (e) => { if (isConflict(e)) onDone(); },
  });
  const fields = (send.error as { fields?: Record<string, string[]> } | null)?.fields ?? {};
  const set = (field: string, header: string) => setMap((m) => { const n = { ...m }; if (header) n[field] = header; else delete n[field]; return n; });
  const apply = (m: SavedMapping) => setMap(Object.fromEntries(Object.entries(m.column_map).filter(([, h]) => job.headers.includes(h))));
  const ready = !!map.title && (!!map.severity || !!map.cvss_vector);

  return (
    <div className="flex flex-col gap-6">
      <section className="card card-pad flex flex-col gap-4">
        <h2 className="text-xl">Step 2: match the columns</h2>
        <p className="m-0 text-muted">{job.counts.total?.toLocaleString()} rows found ({job.encoding}, {job.delimiter === "\t" ? "tab" : job.delimiter === ";" ? "semicolon" : "comma"} separated). Choose which column fills each finding field. Title is required, and so is either a severity or a CVSS vector.</p>
        {saved.data && saved.data.length > 0 && (
          <label className="flex flex-wrap items-center gap-3"><span className="label">Use a saved mapping</span>
            <Select aria-label="Saved mapping" className="max-w-xs" value="" onChange={(e) => { const m = saved.data!.find((s) => s.id === e.target.value); if (m) apply(m); }}>
              <option value="">Choose one…</option>{saved.data.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </Select>
          </label>
        )}
        <ErrorNote error={Object.keys(fields).length === 0 && !isConflict(send.error) ? send.error : null} />
        {isConflict(send.error) && <ErrorNote error={send.error} />}
        <div className="grid gap-4 md:grid-cols-2">
          {IMPORT_FIELDS.map(([key, name]) => (
            <div key={key} className="field">
              <label htmlFor={`map-${key}`}>{name}{key === "title" ? " (required)" : ""}</label>
              <Select id={`map-${key}`} value={map[key] ?? ""} aria-invalid={fields[key] ? true : undefined} onChange={(e) => set(key, e.target.value)}>
                <option value="">Not in the file</option>
                {job.headers.map((h) => <option key={h} value={h}>{h}</option>)}
              </Select>
              {fields[key] && <span className="field-error" role="alert">{fields[key][0]}</span>}
            </div>
          ))}
        </div>
        <label className="flex flex-col gap-1.5"><span className="label">Save this mapping as (optional)</span><TextInput className="max-w-xs" maxLength={120} value={saveAs} onChange={(e) => setSaveAs(e.target.value)} placeholder="For example: Burp export" /></label>
        <div className="flex flex-wrap justify-end gap-3">{onBack && <Button onClick={onBack}>Back</Button>}<Button variant="primary" loading={send.isPending} disabled={!ready} onClick={() => send.mutate()}>Check the rows</Button></div>
      </section>
      <section className="card overflow-hidden">
        <h3 className="m-0 border-b border-line p-4 text-lg">First rows of the file</h3>
        <div className="overflow-x-auto">
          <table className="data-table min-w-[640px]">
            <thead><tr>{job.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>{job.sample.map((r, i) => <tr key={i}>{job.headers.map((h, j) => <td key={h} className="max-w-64 truncate">{r[j]}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// step 3 and 4: check and import

const FILTERS = [["problems", "Problems"], ["invalid", "Errors"], ["duplicate", "Duplicates"], ["valid", "Valid"], ["", "All"]] as const;

function PreviewStep({ job, onDone, onChangeColumns }: { job: ImportJob; onDone: () => void; onChangeColumns: () => void }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("problems");
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState(job.counts.invalid ? "valid_rows_only" : "all_or_nothing");
  const [dups, setDups] = useState("skip");
  const [confirm, setConfirm] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  const c = job.counts;
  const status = filter === "problems" ? "invalid,duplicate" : filter;
  const rowsQ = useQuery({
    queryKey: ["import-rows", job.id, filter, page],
    queryFn: () => api<Page<ImportRow>>("GET", `/imports/${job.id}/rows?page=${page}&page_size=25${status ? `&status=${status}` : ""}`),
    placeholderData: (p) => p,
  });
  const shown = rowsQ.data?.results ?? [];
  const importable = (c.valid ?? 0) + (dups === "import" ? (c.duplicate ?? 0) : 0);
  const send = useMutation({
    mutationFn: () => api("POST", `/imports/${job.id}/commit`, { mode, duplicates: dups }),
    onSuccess: () => { setConfirm(false); onDone(); },
    onError: (e) => { if (isConflict(e)) onDone(); },
  });

  return (
    <div className="flex flex-col gap-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Result of the check">
        {[["Rows", c.total ?? 0, ""], ["Valid", c.valid ?? 0, "text-ok"], ["With errors", c.invalid ?? 0, (c.invalid ?? 0) > 0 ? "text-fail" : ""], ["Duplicates", c.duplicate ?? 0, ""]].map(([name, n, cls]) => (
          <div key={name as string} className="card px-4 py-3"><p className={`m-0 text-[28px] font-semibold leading-none ${cls}`}>{(n as number).toLocaleString()}</p><p className="m-0 mt-1 text-[14px] text-muted">{name}</p></div>
        ))}
      </section>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <div role="group" aria-label="Show rows" className="flex flex-wrap gap-2">
            {FILTERS.map(([k, name]) => <Button key={k} size="sm" aria-pressed={filter === k} variant={filter === k ? "primary" : "secondary"} onClick={() => { setFilter(k); setPage(1); }}>{name}</Button>)}
          </div>
          <span className="flex flex-wrap gap-2">
            <Button size="sm" onClick={onChangeColumns}>Change columns</Button>
            {((c.invalid ?? 0) > 0 || (c.duplicate ?? 0) > 0) && <Button size="sm" onClick={() => downloadFile(`/imports/${job.id}/errors.csv`).catch(setDlError)}><Download size={16} aria-hidden /> Download problem report</Button>}
          </span>
        </div>
        <ErrorNote error={dlError} />
        {rowsQ.isPending && <LoadingRows rows={3} />}
        {rowsQ.isError && <ErrorState error={rowsQ.error} onRetry={() => void rowsQ.refetch()} />}
        {rowsQ.data && shown.length === 0 && <EmptyState title={filter === "problems" ? "No problems found" : "Nothing here"} body={filter === "problems" ? "Every row can be imported." : "No rows have this status."} />}
        {shown.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {shown.map((r) => (
              <li key={r.id} className="flex flex-col gap-1.5 p-4">
                <p className="m-0 flex flex-wrap items-center gap-2"><span className="mono text-[14px] text-muted">Line {r.row_number}</span><RowBadge status={r.status} /><span className="font-medium break-words">{r.title || r.cells[job.mapping.column_map?.title ?? ""] || "(no title)"}</span></p>
                {r.errors.map((e, i) => <p key={i} className="m-0 text-[15px] text-fail"><span className="font-medium">{e.field}:</span> {e.message}</p>)}
                {r.duplicate_of && <p className="m-0 text-[15px] text-muted">{r.duplicate_of.finding ? <>Same as <Link to={`/findings/${r.duplicate_of.finding.id}`} className="text-accent hover:underline">{r.duplicate_of.finding.ref}</Link> {r.duplicate_of.finding.title}</> : r.duplicate_of.hidden ? "Same as an existing finding you cannot see." : `Same as line ${r.duplicate_of.line} of this file.`}</p>}
              </li>
            ))}
          </ul>
        )}
        {rowsQ.data && <Pager page={page} count={rowsQ.data.count} size={25} onPage={setPage} />}
      </section>

      {(c.invalid ?? 0) > 0 && job.mapping.column_map?.severity && <SeverityWords job={job} onDone={onDone} />}

      <section className="card card-pad flex flex-col gap-5">
        <h2 className="text-xl">Step 4: import</h2>
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="label mb-1">If a row has errors</legend>
          <label className="check"><input type="radio" name="mode" checked={mode === "all_or_nothing"} disabled={(c.invalid ?? 0) > 0} onChange={() => setMode("all_or_nothing")} /> All or nothing: import only if every row is valid{(c.invalid ?? 0) > 0 ? " (not available: some rows have errors)" : ""}</label>
          <label className="check"><input type="radio" name="mode" checked={mode === "valid_rows_only"} onChange={() => setMode("valid_rows_only")} /> Import the valid rows and leave the rest</label>
        </fieldset>
        {(c.duplicate ?? 0) > 0 && (
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="label mb-1">Duplicates ({c.duplicate})</legend>
            <label className="check"><input type="radio" name="dups" checked={dups === "skip"} onChange={() => setDups("skip")} /> Skip them</label>
            <label className="check"><input type="radio" name="dups" checked={dups === "import"} onChange={() => setDups("import")} /> Import them anyway</label>
          </fieldset>
        )}
        <p className="m-0 text-muted">Findings are created as drafts in {job.engagement.name}. Nobody outside the testing team sees them until they are published.</p>
        <ErrorNote error={send.error && !isConflict(send.error) ? send.error : null} />
        {isConflict(send.error) && <Alert tone="error">{(send.error as Error).message}</Alert>}
        <div className="flex flex-wrap justify-end gap-3">
          <Button variant="primary" disabled={importable === 0} onClick={() => { send.reset(); setConfirm(true); }}>Import {importable.toLocaleString()} finding{importable === 1 ? "" : "s"}</Button>
        </div>
      </section>
      <ConfirmDialog open={confirm} title="Import findings" body={`${importable.toLocaleString()} draft finding${importable === 1 ? "" : "s"} will be created in ${job.engagement.name}${mode === "all_or_nothing" ? ". If anything fails, none are created" : ""}. This cannot be undone in one step, but drafts can be deleted.`} confirmLabel="Import" busy={send.isPending} error={isConflict(send.error) ? null : send.error} onConfirm={() => send.mutate()} onClose={() => setConfirm(false)} />
    </div>
  );
}

const SEVERITY_CHOICES = [["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"], ["info", "Info"]] as const;

/** Severity wording the importer does not know (for example "Sehr hoch"): map each word, then re-check. */
function SeverityWords({ job, onDone }: { job: ImportJob; onDone: () => void }) {
  const header = job.mapping.column_map!.severity;
  const [choice, setChoice] = useState<Record<string, string>>({});
  const q = useQuery({ queryKey: ["import-rows", job.id, "invalid-all"], queryFn: () => api<Page<ImportRow>>("GET", `/imports/${job.id}/rows?status=invalid&page_size=200`) });
  const words = [...new Set((q.data?.results ?? []).filter((r) => r.errors.some((e) => e.code === "invalid_severity")).map((r) => r.cells[header] ?? "").filter(Boolean))];
  const send = useMutation({
    mutationFn: () => api("POST", `/imports/${job.id}/mapping`, { column_map: job.mapping.column_map, value_map: { severity: { ...(job.mapping.value_map?.severity ?? {}), ...choice } } }),
    onSuccess: onDone,
    onError: (e) => { if (isConflict(e)) onDone(); },
  });
  const chosen = Object.keys(choice).filter((k) => choice[k]);
  if (words.length === 0) return null;
  return (
    <section className="card card-pad flex flex-col gap-4">
      <h2 className="text-xl">Severity words not recognised</h2>
      <p className="m-0 text-muted">Say what each word means, then check the rows again. Informational, Moderate and Crit are understood already.</p>
      <ErrorNote error={send.error && !isConflict(send.error) ? send.error : null} />
      <div className="grid gap-3 md:grid-cols-2">
        {words.map((w) => (
          <label key={w} className="flex items-center gap-3"><span className="min-w-0 flex-1 break-words font-medium">{w}</span>
            <Select aria-label={`Severity for ${w}`} className="max-w-40" value={choice[w] ?? ""} onChange={(e) => setChoice({ ...choice, [w]: e.target.value })}>
              <option value="">Choose…</option>{SEVERITY_CHOICES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </label>
        ))}
      </div>
      <div className="flex justify-end"><Button variant="primary" loading={send.isPending} disabled={chosen.length === 0} onClick={() => send.mutate()}>Apply and check again</Button></div>
    </section>
  );
}

function RowBadge({ status }: { status: ImportRow["status"] }) {
  const tone = { invalid: "fail", duplicate: "warn", valid: "ok", imported: "ok", skipped: "info", pending: "info" }[status] as "ok" | "warn" | "fail" | "info";
  const name = { invalid: "Error", duplicate: "Duplicate", valid: "Valid", imported: "Imported", skipped: "Skipped", pending: "Pending" }[status];
  return <Badge tone={tone}>{name}</Badge>;
}

// step 5: done

function DoneStep({ job }: { job: ImportJob }) {
  const c = job.counts;
  const [dlError, setDlError] = useState<unknown>(null);
  return (
    <div className="flex flex-col gap-5">
      <Alert tone="ok"><p className="m-0 font-medium">{(c.imported ?? 0).toLocaleString()} draft finding{c.imported === 1 ? "" : "s"} imported.</p><p className="m-0 mt-1">{(c.skipped ?? 0).toLocaleString()} duplicate{c.skipped === 1 ? "" : "s"} skipped, {(c.invalid ?? 0).toLocaleString()} row{c.invalid === 1 ? "" : "s"} with errors left out. Review the drafts, then publish them from the findings list.</p></Alert>
      <ErrorNote error={dlError} />
      <div className="flex flex-wrap gap-3">
        <Link to={`/engagements/${job.engagement.id}`} className="btn btn-primary">Review findings in {job.engagement.ref}</Link>
        {((c.invalid ?? 0) > 0 || (c.skipped ?? 0) > 0) && job.file_available !== undefined && <Button onClick={() => downloadFile(`/imports/${job.id}/errors.csv`).catch(setDlError)}><Download size={16} aria-hidden /> Download problem report</Button>}
        <Link to="/imports" className="btn btn-secondary">All imports</Link>
      </div>
      <p className="m-0 text-[14px] text-muted">Started by {job.uploaded_by.display_name}{job.finished_at ? `, finished ${formatDate(job.finished_at)}` : ""}. File checksum <span className="mono break-all">{job.file_sha256}</span>.</p>
    </div>
  );
}
