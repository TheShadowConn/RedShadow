import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, FileText, Pencil, Trash2, UploadCloud } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, upload } from "../../api/client";
import { type Activity, type Evidence, type Finding, type FindingNote, type HistoryEvent, type Page, type RetestRound } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, fieldError, formatBytes, formatDate, formatDay,
  LoadingRows, NotFoundOrError, Pager, Select, Sheet, TabPanel, Tabs, Textarea,
} from "../../design/ui";
import { describe } from "../engagements/EngagementTabs";
import { MOVES, MOVE_PRIORITY, MoveDialog, SlaBadge, needsDialog, useQuickMove, type Move } from "../remediation/shared";
import { FindingStatus, Markdown, SeverityBadge, isConflict, userName } from "./shared";

type Tab = "details" | "timeline" | "notes" | "evidence" | "history";
const EDITABLE = new Set(["draft", "open", "in_progress", "reopened"]);
const MAX_BYTES = 25 * 1024 * 1024;

export function FindingPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("details");
  const [dialog, setDialog] = useState<"delete" | null>(null);
  const [move, setMove] = useState<Move | null>(null);
  const [more, setMore] = useState(false);

  const q = useQuery({ queryKey: ["finding", id], queryFn: () => api<Finding>("GET", `/findings/${id}`) });
  const quick = useQuickMove();
  const reviewed = useMutation({
    mutationFn: (v: number) => api("POST", `/findings/${id}/import-reviewed`, { version: v }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["finding", id] }); },
  });
  const remove = useMutation({
    mutationFn: () => api("DELETE", `/findings/${id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["findings"] }); nav(`/engagements/${q.data!.engagement.id}`); },
  });

  if (q.isPending) return <LoadingRows rows={4} />;
  if (q.isError) return <><Back /><div className="card"><NotFoundOrError error={q.error} what="Finding" onRetry={() => void q.refetch()} /></div></>;
  const f = q.data;
  const perms = new Set(f.permissions);
  const editable = EDITABLE.has(f.status);
  const moves = [...f.allowed_transitions].sort((a, b) => MOVE_PRIORITY.indexOf(a.name) - MOVE_PRIORITY.indexOf(b.name));
  const run = (m: Move) => { setMore(false); if (needsDialog(m)) setMove(m); else quick.mutate({ f, move: m }); };
  const canEdit = perms.has("findings.update") && editable;
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "details", label: "Details" },
    ...(f.status === "draft" ? [] : [{ id: "timeline" as const, label: "Timeline" }]),
    { id: "notes", label: "Notes" },
    ...(perms.has("evidence.view") ? [{ id: "evidence" as const, label: "Evidence" }] : []),
    ...(perms.has("audit.view_engagement") ? [{ id: "history" as const, label: "History" }] : []),
  ];
  const active = tabs.some((t) => t.id === tab) ? tab : "details";
  const lock = f.status === "draft" ? "Draft: visible to the testing team only until published." : null;

  return (
    <>
      <Back engagement={f.engagement} />
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mono m-0 text-[14px] text-muted">{f.ref}</p>
          <h1 className="mt-1 text-[32px] max-sm:text-[26px]">{f.title}</h1>
          <p className="mt-3 flex flex-wrap items-center gap-3"><SeverityBadge severity={f.severity} score={f.cvss_score} /><FindingStatus status={f.status} /><SlaBadge due={f.due_date} status={f.status} overdue={f.is_overdue} /></p>
        </div>
        <div className="flex flex-wrap gap-3 max-md:hidden">
          {moves.map((m, i) => <Button key={m.name} variant={i === 0 ? "primary" : MOVES[m.name].tone === "danger" ? "danger" : "secondary"} loading={quick.isPending && quick.variables?.move.name === m.name} onClick={() => run(m)}>{MOVES[m.name].label}</Button>)}
          {canEdit && <Button onClick={() => nav(`/findings/${f.id}/edit`)}><Pencil size={18} aria-hidden /> Edit</Button>}
          {perms.has("findings.delete") && <Button variant="danger" onClick={() => { remove.reset(); setDialog("delete"); }}>Delete</Button>}
        </div>
      </header>
      {f.import_issues?.length > 0 && (
        <div className="mb-4">
          <Alert tone="warn">
            <p className="m-0 font-medium">Imported with gaps: please review before publishing.</p>
            <ul className="m-0 mt-2 list-disc space-y-1 pl-5">
              {f.import_issues.map((i, n) => <li key={n}><span className="font-medium">{i.field.replace(/_/g, " ")}:</span> {i.message}</li>)}
            </ul>
            <p className="m-0 mt-2 text-[14px]">Use Edit to fill the values in; each gap clears when you change its field. If a value is meant to stay empty, mark the gaps as reviewed.</p>
            {canEdit && <div className="mt-3"><Button size="sm" loading={reviewed.isPending} onClick={() => reviewed.mutate(f.version)}>Mark import gaps as reviewed</Button></div>}
            {reviewed.error && <ErrorNote error={reviewed.error} />}
          </Alert>
        </div>
      )}
      {lock && <div className="mb-4"><Alert tone="warn">{lock}</Alert></div>}
      {quick.error && <div className="mb-4">{isConflict(quick.error) ? <Alert tone="error">Someone else changed this finding. It was reloaded, try again.</Alert> : <ErrorNote error={quick.error} />}</div>}
      <RetestNotice f={f} />
      {f.status === "risk_accepted" && f.risk_accepted_until && <div className="mb-4"><Alert tone="warn">Risk accepted until {formatDay(f.risk_accepted_until)}. It reopens automatically after that date.{f.risk_acceptance_reason ? ` Reason: ${f.risk_acceptance_reason}` : ""}</Alert></div>}
      {f.possible_duplicates.length > 0 && (
        <div className="mb-4"><Alert tone="warn">
          Looks like {f.possible_duplicates.map((d, i) => <span key={d.id}>{i > 0 && ", "}<Link className="underline" to={`/findings/${d.id}`}>{d.ref}</Link></span>)} in this engagement. Mark this one as a duplicate if it is the same issue.
        </Alert></div>
      )}
      {f.duplicate_of && <div className="mb-4"><Alert tone="warn">Duplicate of {f.duplicate_of.id ? <Link className="underline" to={`/findings/${f.duplicate_of.id}`}>{f.duplicate_of.ref} {f.duplicate_of.title}</Link> : f.duplicate_of.ref}.</Alert></div>}

      <div className="grid gap-6 pb-20 md:pb-0 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 lg:order-1">
          <Tabs label="Finding sections" value={active} onChange={setTab} tabs={tabs} />
          <TabPanel id={active}>
            {active === "details" && <Details f={f} />}
            {active === "timeline" && <Timeline f={f} />}
            {active === "notes" && <Notes f={f} />}
            {active === "evidence" && <EvidencePanel f={f} />}
            {active === "history" && <History f={f} />}
          </TabPanel>
        </div>
        <aside aria-label="Finding metadata" className="lg:order-2"><Meta f={f} /></aside>
      </div>

      {move && <MoveDialog f={f} move={move} onClose={() => setMove(null)} />}
      <div className="fixed inset-x-0 bottom-16 z-10 flex gap-3 border-t border-line bg-surface p-3 md:hidden" role="region" aria-label="Finding actions">
        {moves[0] ? <Button variant="primary" block loading={quick.isPending && quick.variables?.move.name === moves[0].name} onClick={() => run(moves[0])}>{MOVES[moves[0].name].label}</Button> : canEdit ? <Button block onClick={() => nav(`/findings/${f.id}/edit`)}><Pencil size={18} aria-hidden /> Edit</Button> : null}
        {(moves.length > 1 || canEdit || perms.has("findings.delete")) && <Button block aria-haspopup="dialog" onClick={() => setMore(true)}>More actions</Button>}
      </div>
      <Sheet open={more} onClose={() => setMore(false)} title="Actions">
        <div className="space-y-3 p-4">
          {moves.slice(1).map((m) => <Button key={m.name} block variant={MOVES[m.name].tone === "danger" ? "danger" : "secondary"} onClick={() => run(m)}>{MOVES[m.name].label}</Button>)}
          {canEdit && <Button block onClick={() => nav(`/findings/${f.id}/edit`)}><Pencil size={18} aria-hidden /> Edit</Button>}
          {perms.has("findings.delete") && <Button block variant="danger" onClick={() => { setMore(false); remove.reset(); setDialog("delete"); }}>Delete</Button>}
        </div>
      </Sheet>
      <ConfirmDialog open={dialog === "delete"} title="Delete finding" body="The finding disappears from every list. Its audit history is kept." confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => remove.mutate()} onClose={() => setDialog(null)} />
    </>
  );
}

function Back({ engagement }: { engagement?: { id: string; name: string } }) {
  return (
    <Link to={engagement ? `/engagements/${engagement.id}` : "/findings"} className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink">
      <ArrowLeft size={18} aria-hidden /> {engagement ? engagement.name : "Findings"}
    </Link>
  );
}

function Meta({ f }: { f: Finding }) {
  const rows: Array<[string, React.ReactNode]> = [
    ["Engagement", <Link key="e" className="text-accent hover:underline" to={`/engagements/${f.engagement.id}`}>{f.engagement.ref} {f.engagement.name}</Link>],
    ["Asset", f.asset?.name ?? "None"],
    ["Endpoint", f.endpoint ? <span className="mono break-all">{f.endpoint}</span> : "None"],
    ["CVSS", f.cvss_vector ? <span className="mono break-all text-[13px]">{f.cvss_vector}</span> : "Not scored"],
    ["Weakness", f.cwe ? <span key="c"><span className="mono">CWE-{f.cwe.id}</span> {f.cwe.name}</span> : "None"],
    ["Assigned pentester", userName(f.assigned_pentester)],
    ["Remediation owner", userName(f.remediation_owner)],
    ["Reported by", userName(f.reported_by)],
    ["Discovered", formatDay(f.discovered_at)],
    ...(f.due_date ? [["Due", formatDay(f.due_date)] as [string, React.ReactNode]] : []),
    ...(f.resolved_at && f.status === "pending_verification" ? [["Fix submitted", formatDate(f.resolved_at)] as [string, React.ReactNode]] : []),
    ...(f.verified_at ? [["Verified", `${formatDate(f.verified_at)}${f.verified_by ? ` by ${f.verified_by.display_name}` : ""}`] as [string, React.ReactNode]] : []),
    ...(f.closed_at ? [["Closed", formatDate(f.closed_at)] as [string, React.ReactNode]] : []),
    ["Updated", formatDate(f.updated_at)],
  ];
  return (
    <dl className="card card-pad m-0 space-y-4">
      {rows.map(([k, v]) => <div key={k}><dt className="label">{k}</dt><dd className="m-0 mt-0.5 break-words">{v}</dd></div>)}
    </dl>
  );
}

function Details({ f }: { f: Finding }) {
  const hasTech = f.technical_details || f.poc;
  const block = (title: string, body: string, empty?: string) => (
    <section className="card card-pad"><h2 className="mb-3 text-lg">{title}</h2><Markdown text={body} empty={empty} /></section>
  );
  return (
    <div className="space-y-6">
      {block("Description", f.description, "No description yet.")}
      {block("Recommendation", f.recommendation, "No recommendation yet.")}
      {hasTech ? block("Technical details", f.technical_details, "None.") : null}
      {f.poc ? block("Proof of concept", f.poc) : null}
      {f.references.length > 0 && (
        <section className="card card-pad"><h2 className="mb-3 text-lg">References</h2>
          <ul className="m-0 list-disc space-y-1 pl-5">{f.references.map((r, i) => <li key={i}><a className="text-accent underline-offset-2 hover:underline" href={r.url} target="_blank" rel="noopener noreferrer nofollow">{r.label}</a></li>)}</ul>
        </section>
      )}
    </div>
  );
}

function Notes({ f }: { f: Finding }) {
  const qc = useQueryClient();
  const perms = new Set(f.permissions);
  const kinds = [...(perms.has("finding_notes.technical") ? ["technical" as const] : []), ...(perms.has("finding_notes.remediation") && f.status !== "draft" ? ["remediation" as const] : [])];
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState<"technical" | "remediation">(kinds[0] ?? "remediation");
  const [body, setBody] = useState("");
  const q = useQuery({ queryKey: ["finding-notes", f.id, page], queryFn: () => api<Page<FindingNote>>("GET", `/findings/${f.id}/notes?page=${page}`), placeholderData: (p) => p });
  const add = useMutation({
    mutationFn: () => api("POST", `/findings/${f.id}/notes`, { kind, body }),
    onSuccess: () => { setBody(""); setPage(1); void qc.invalidateQueries({ queryKey: ["finding-notes", f.id] }); void qc.invalidateQueries({ queryKey: ["finding-history", f.id] }); },
  });
  return (
    <div className="space-y-4">
      {kinds.length > 0 && (
        <form className="card card-pad space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }}>
          <ErrorNote error={add.error} />
          <Field label="Add a note" hint="Notes cannot be edited or removed afterwards." error={fieldError(add.error, "body")}>{(p) => <Textarea {...p} rows={3} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} />}</Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            {kinds.length > 1 ? (
              <Select aria-label="Kind of note" className="max-w-xs" value={kind} onChange={(e) => setKind(e.target.value as "technical" | "remediation")}>
                <option value="technical">Technical: testing team only</option>
                <option value="remediation">Remediation: everyone on this finding</option>
              </Select>
            ) : <span className="text-[14px] text-muted">{kinds[0] === "technical" ? "Visible to the testing team only." : "Visible to everyone who can see this finding."}</span>}
            <Button type="submit" variant="primary" loading={add.isPending} disabled={!body.trim()}>Add note</Button>
          </div>
        </form>
      )}
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title="No notes yet" body="Notes record decisions, fixes and observations on this finding." />}
        {q.data && q.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((n) => (
              <li key={n.id} className="space-y-2 p-4">
                <p className="m-0 flex flex-wrap items-center gap-2 text-[14px] text-muted"><span className="font-medium text-ink">{n.author.display_name}</span>{formatDate(n.created_at)}<Badge tone={n.kind === "technical" ? "warn" : "info"}>{NOTE_KIND[n.kind]}</Badge></p>
                <Markdown text={n.body} />
              </li>
            ))}
          </ul>
        )}
        {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
      </div>
    </div>
  );
}

function EvidencePanel({ f }: { f: Finding }) {
  const qc = useQueryClient();
  const perms = new Set(f.permissions);
  const [page, setPage] = useState(1);
  const [progress, setProgress] = useState<number | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Evidence | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ["finding-evidence", f.id, page], queryFn: () => api<Page<Evidence>>("GET", `/findings/${f.id}/evidence?page=${page}`), placeholderData: (p) => p });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["finding-evidence", f.id] }); void qc.invalidateQueries({ queryKey: ["finding-history", f.id] }); };
  const send = useMutation({ mutationFn: (file: File) => upload("POST", `/findings/${f.id}/evidence`, file, setProgress), onSuccess: () => { setPage(1); refresh(); }, onSettled: () => setProgress(null) });
  const remove = useMutation({ mutationFn: (e: Evidence) => api("DELETE", `/findings/${f.id}/evidence/${e.id}`), onSuccess: () => { refresh(); setRemoving(null); } });
  const { me } = useAuth();
  const canUpload = perms.has("evidence.upload");
  const canRemove = (e: Evidence) => (e.uploaded_by.id === me?.id && perms.has("evidence.delete_own")) || perms.has("findings.delete");

  function pick(file: File | undefined) {
    if (!file) return;
    send.reset();
    if (file.size === 0) return setClientError("That file is empty.");
    if (file.size > MAX_BYTES) return setClientError(`${file.name} is ${formatBytes(file.size)}. The limit is 25 MB.`);
    setClientError(null);
    send.mutate(file);
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); if (canUpload && progress === null) pick(e.dataTransfer.files[0]); };

  return (
    <div className="space-y-4">
      {canUpload && (
        <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop} className={`card card-pad flex flex-col items-center gap-3 border-dashed text-center ${over ? "bg-raised" : ""}`}>
          <UploadCloud size={28} className="text-muted" aria-hidden />
          <p className="m-0">Drop a screenshot or file here, or choose one.</p>
          <input ref={input} type="file" className="sr-only" aria-label="Choose evidence file" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          <Button variant="primary" loading={progress !== null} onClick={() => input.current?.click()}>Choose file</Button>
          <p className="m-0 text-[13px] text-muted">Images, PDF, text, log, CSV, JSON, XML, ZIP, PCAP, DOCX or XLSX up to 25 MB. HTML and SVG are refused. Images are re-encoded.</p>
          {progress !== null && (
            <div className="w-full max-w-sm" role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
              <div className="h-2 overflow-hidden rounded-full bg-raised"><div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} /></div>
              <p className="m-0 mt-1 text-[13px] text-muted">{progress >= 1 ? "Checking the file…" : `Uploading ${Math.round(progress * 100)}%`}</p>
            </div>
          )}
          {clientError && <Alert tone="error">{clientError}</Alert>}
          <ErrorNote error={send.error} />
        </div>
      )}
      {q.isPending && <div className="card"><LoadingRows rows={2} /></div>}
      {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
      {q.data && q.data.results.length === 0 && <div className="card"><EmptyState title="No evidence" body="Attach screenshots, request logs or captures that prove the finding." /></div>}
      {q.data && q.data.results.length > 0 && (
        <ul className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 xl:grid-cols-3">
          {q.data.results.map((e) => (
            <li key={e.id} className="card overflow-hidden">
              {e.is_image ? (
                <a href={e.download_url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${e.original_name}`}>
                  <img src={e.download_url} alt={e.original_name} loading="lazy" className="h-44 w-full bg-raised object-contain" />
                </a>
              ) : (
                <div className="grid h-44 place-items-center bg-raised text-muted"><FileText size={40} aria-hidden /></div>
              )}
              <div className="space-y-2 p-3">
                <p className="m-0 break-all font-medium">{e.original_name}</p>
                <p className="m-0 text-[13px] text-muted">{formatBytes(e.size)} · {e.uploaded_by.display_name} · {formatDate(e.created_at)}</p>
                <div className="flex gap-2">
                  <a href={e.download_url} download={e.original_name} className="btn btn-secondary btn-sm"><Download size={16} aria-hidden /> Download</a>
                  {canRemove(e) && <Button size="sm" variant="danger" aria-label={`Delete ${e.original_name}`} onClick={() => { remove.reset(); setRemoving(e); }}><Trash2 size={16} aria-hidden /></Button>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {q.data && <div className="card"><Pager page={page} count={q.data.count} size={50} onPage={setPage} /></div>}
      <ConfirmDialog open={!!removing} title="Delete evidence" body={`${removing?.original_name} is removed now and permanently purged after 30 days.`} confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </div>
  );
}

function History({ f }: { f: Finding }) {
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["finding-history", f.id, page], queryFn: () => api<Page<HistoryEvent>>("GET", `/findings/${f.id}/history?page=${page}`), placeholderData: (p) => p });
  return (
    <div className="card overflow-hidden">
      {q.isPending && <LoadingRows />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.results.length === 0 && <EmptyState title="No history yet" body="Every change to this finding is recorded here." />}
      {q.data && q.data.results.length > 0 && (
        <ol className="m-0 list-none divide-y divide-line p-0">
          {q.data.results.map((ev) => (
            <li key={ev.id} className="space-y-1 p-4">
              <p className="m-0 flex flex-wrap items-center gap-2"><span className="mono text-[14px]">{ev.action}</span>{ev.outcome !== "success" && <Badge tone="fail">{ev.outcome}</Badge>}</p>
              <p className="m-0 text-[14px] text-muted">{ev.actor_label} · {formatDate(ev.occurred_at)}</p>
              {describe(ev.changes).map((line) => <p key={line} className="m-0 break-words text-[14px]">{line}</p>)}
            </li>
          ))}
        </ol>
      )}
      {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
    </div>
  );
}

const NOTE_KIND: Record<string, string> = { technical: "Team only", remediation: "Remediation", verification: "Verification", retest: "Retest" };

/** Shows the open retest round for this finding, if the caller may see rounds. */
function RetestNotice({ f }: { f: Finding }) {
  const enabled = f.permissions.includes("retests.view") && f.status === "pending_verification";
  const q = useQuery({ queryKey: ["retests", "finding", f.id], queryFn: () => api<Page<RetestRound>>("GET", `/retest-rounds?finding=${f.id}&status=queued,in_progress`), enabled });
  const round = q.data?.results[0];
  if (!round) return null;
  return <div className="mb-4"><Alert tone="warn">In retest <Link className="underline" to={`/retests/${round.id}`}>{round.ref}</Link>, assigned to {round.assessor.display_name}.</Alert></div>;
}

const ACTIVITY: Record<string, string> = {
  published: "Published", started: "Started work", paused: "Paused work", fix_deployed: "Fix deployed", mitigated: "Mitigated",
  submitted_for_verification: "Submitted for verification", verification_passed: "Verification passed", verification_failed: "Verification failed",
  closed: "Closed", reopened: "Reopened", risk_accepted: "Risk accepted", false_positive: "Marked false positive", duplicate: "Marked duplicate",
  comment: "Comment", retest_requested: "Retest requested", sla_breached: "Deadline missed",
};

function Timeline({ f }: { f: Finding }) {
  const qc = useQueryClient();
  const perms = new Set(f.permissions);
  const working = f.status === "open" || f.status === "in_progress" || f.status === "reopened";
  const kinds = [
    ...(perms.has("remediation.update_status") && working ? [["fix_deployed", "Fix deployed"], ["mitigated", "Mitigated"]] : []),
    ...(perms.has("finding_notes.remediation") ? [["comment", "Comment"]] : []),
  ] as Array<[string, string]>;
  const [page, setPage] = useState(1);
  const [action, setAction] = useState(kinds[0]?.[0] ?? "comment");
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<string[]>([]);
  const q = useQuery({ queryKey: ["finding-activity", f.id, page], queryFn: () => api<Page<Activity>>("GET", `/findings/${f.id}/activity?page=${page}`), placeholderData: (p) => p });
  const files = useQuery({ queryKey: ["finding-evidence", f.id, 1], queryFn: () => api<Page<Evidence>>("GET", `/findings/${f.id}/evidence?page=1`), enabled: perms.has("evidence.view") && kinds.length > 0 });
  const names = new Map(files.data?.results.map((e) => [e.id, e.original_name]));
  const add = useMutation({
    mutationFn: () => api("POST", `/findings/${f.id}/activity`, { action: kinds.some(([k]) => k === action) ? action : kinds[0][0], note, ...(evidence.length ? { evidence_ids: evidence } : {}) }),
    onSuccess: () => { setNote(""); setEvidence([]); setPage(1); void qc.invalidateQueries({ queryKey: ["finding-activity", f.id] }); void qc.invalidateQueries({ queryKey: ["finding-history", f.id] }); },
  });
  return (
    <div className="space-y-4">
      {kinds.length > 0 && (
        <form className="card card-pad space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }}>
          <ErrorNote error={add.error} />
          <Field label="Add to the timeline" hint="Entries cannot be edited or removed afterwards." error={fieldError(add.error, "note")}>{(p) => <Textarea {...p} rows={3} maxLength={20000} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          {files.data && files.data.results.length > 0 && (
            <fieldset className="m-0 min-w-0 space-y-1 border-0 p-0">
              <legend className="label mb-1">Link evidence (optional)</legend>
              {files.data.results.map((e) => <label key={e.id} className="check"><input type="checkbox" checked={evidence.includes(e.id)} onChange={(ev) => setEvidence(ev.target.checked ? [...evidence, e.id] : evidence.filter((x) => x !== e.id))} /><span className="break-all">{e.original_name}</span></label>)}
            </fieldset>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            {kinds.length > 1 ? <Select aria-label="Kind of entry" className="max-w-xs" value={action} onChange={(e) => setAction(e.target.value)}>{kinds.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select> : <span className="text-[14px] text-muted">Recorded as a comment.</span>}
            <Button type="submit" variant="primary" loading={add.isPending} disabled={!note.trim()}>Add entry</Button>
          </div>
        </form>
      )}
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title="Nothing yet" body="Status changes and progress updates appear here." />}
        {q.data && q.data.results.length > 0 && (
          <ol className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((a) => (
              <li key={a.id} className="space-y-2 p-4">
                <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1"><span className="font-medium">{ACTIVITY[a.action] ?? a.action}</span>{a.from_status && a.from_status !== a.to_status && <span className="text-[14px] text-muted">{a.from_status.replace(/_/g, " ")} to {a.to_status.replace(/_/g, " ")}</span>}</p>
                <p className="m-0 text-[14px] text-muted">{a.actor ? a.actor.display_name : "System"} · {formatDate(a.created_at)}</p>
                {a.note && <Markdown text={a.note} />}
                {a.evidence_ids.length > 0 && <p className="m-0 text-[14px] text-muted">Evidence: {a.evidence_ids.map((id) => names.get(id) ?? "file").join(", ")}</p>}
              </li>
            ))}
          </ol>
        )}
        {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
      </div>
    </div>
  );
}
