import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Evidence, Page, RetestItem, RetestRound, UserRef } from "../../api/types";
import { Alert, Badge, Button, ConfirmDialog, ErrorNote, Field, fieldError, formatDate, LoadingRows, Modal, NotFoundOrError, Select, Textarea } from "../../design/ui";
import { isConflict, noFieldErrors, SeverityBadge, userName } from "../findings/shared";
import { useInvalidateWork } from "../remediation/shared";
import { RoundCounts, RoundStatus } from "./RetestsPage";

const RESULT: Record<string, { label: string; tone: "ok" | "warn" | "fail" | "info" }> = {
  pending: { label: "Pending", tone: "warn" }, passed: { label: "Passed", tone: "ok" },
  failed: { label: "Failed", tone: "fail" }, not_tested: { label: "Not tested", tone: "info" },
};

export function RetestPage() {
  const { id } = useParams();
  const refresh = useInvalidateWork();
  const [dialog, setDialog] = useState<"assign" | "cancel" | null>(null);
  const [recording, setRecording] = useState<{ item: RetestItem; result: "passed" | "failed" } | null>(null);
  const q = useQuery({ queryKey: ["retest", id], queryFn: () => api<RetestRound>("GET", `/retest-rounds/${id}`) });
  const cancel = useMutation({
    mutationFn: () => api("POST", `/retest-rounds/${id}/cancel`, { version: q.data!.version }),
    onSuccess: () => { refresh(); setDialog(null); },
    onError: (e) => { if (isConflict(e)) refresh(); },
  });

  const back = <Link to="/retests" className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink"><ArrowLeft size={18} aria-hidden /> Retests</Link>;
  if (q.isPending) return <>{back}<LoadingRows rows={4} /></>;
  if (q.isError) return <>{back}<div className="card"><NotFoundOrError error={q.error} what="Retest round" onRetry={() => void q.refetch()} /></div></>;
  const r = q.data;
  const open = r.status === "queued" || r.status === "in_progress";

  return (
    <>
      {back}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mono m-0 text-[14px] text-muted">{r.engagement.ref}</p>
          <h1 className="mt-1 text-[32px] max-sm:text-[26px]">Retest {r.ref}</h1>
          <p className="mt-3 flex flex-wrap items-center gap-3"><RoundStatus status={r.status} /><RoundCounts r={r} /></p>
        </div>
        {r.can_manage && open && (
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => setDialog("assign")}>Reassign</Button>
            <Button variant="danger" onClick={() => { cancel.reset(); setDialog("cancel"); }}>Cancel round</Button>
          </div>
        )}
      </header>

      {r.can_record && <div className="mb-4"><Alert tone="warn">You are the assessor. Record a result for each finding; a pass closes it and a fail reopens it.</Alert></div>}
      {open && !r.can_record && <div className="mb-4"><Alert tone="warn">Only {r.assessor.display_name} can record results for this round.</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <ul className="card m-0 list-none divide-y divide-line p-0">
          {r.items.map((it) => (
            <li key={it.id} className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={it.finding.severity} />
                <Badge tone={RESULT[it.result].tone}>{RESULT[it.result].label}</Badge>
              </div>
              <Link to={`/findings/${it.finding.id}`} className="block hover:underline"><span className="block font-medium">{it.finding.title}</span><span className="mono block text-[14px] text-muted">{it.finding.ref}</span></Link>
              {it.note && <p className="m-0 whitespace-pre-wrap break-words text-[15px]">{it.note}</p>}
              {it.tested_at && <p className="m-0 text-[14px] text-muted">{userName(it.tested_by, "Someone")} · {formatDate(it.tested_at)}</p>}
              {r.can_record && it.result === "pending" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="primary" onClick={() => setRecording({ item: it, result: "passed" })}>Pass</Button>
                  <Button size="sm" variant="danger" onClick={() => setRecording({ item: it, result: "failed" })}>Fail</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
        <aside aria-label="Round details">
          <dl className="card card-pad m-0 space-y-4">
            {([
              ["Engagement", <Link key="e" className="text-accent hover:underline" to={`/engagements/${r.engagement.id}`}>{r.engagement.name}</Link>],
              ["Assessor", r.assessor.display_name], ["Requested by", r.requested_by.display_name],
              ["Requested", formatDate(r.requested_at)], ["Finished", r.completed_at ? formatDate(r.completed_at) : "Not yet"],
              ...(r.note ? [["Note", r.note] as [string, string]] : []),
            ] as Array<[string, React.ReactNode]>).map(([k, v]) => <div key={k}><dt className="label">{k}</dt><dd className="m-0 mt-0.5 break-words">{v}</dd></div>)}
          </dl>
        </aside>
      </div>

      {dialog === "assign" && <AssignDialog round={r} onClose={() => setDialog(null)} onDone={refresh} />}
      <ConfirmDialog open={dialog === "cancel"} title="Cancel retest round" body="Pending findings stay in pending verification and are marked not tested. You can request a new round for them." confirmLabel="Cancel round" danger busy={cancel.isPending} error={cancel.error} onConfirm={() => cancel.mutate()} onClose={() => setDialog(null)} />
      {recording && <ResultDialog round={r} item={recording.item} result={recording.result} onClose={() => setRecording(null)} onDone={refresh} />}
    </>
  );
}

function AssignDialog({ round, onClose, onDone }: { round: RetestRound; onClose: () => void; onDone: () => void }) {
  const [assessor, setAssessor] = useState("");
  const people = useQuery({ queryKey: ["assessors", round.engagement.id], queryFn: () => api<UserRef[]>("GET", `/retest-rounds/assessors?engagement=${round.engagement.id}`) });
  const save = useMutation({
    mutationFn: () => api("POST", `/retest-rounds/${round.id}/assign`, { assessor, version: round.version }),
    onSuccess: () => { onDone(); onClose(); },
    onError: (e) => { if (isConflict(e)) onDone(); },
  });
  return (
    <Modal open onClose={onClose} title="Reassign retest">
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (assessor) save.mutate(); }}>
        <p className="m-0 text-muted">The current assessor, {round.assessor.display_name}, can no longer record results.</p>
        <ErrorNote error={noFieldErrors(save.error)} />
        <Field label="New assessor" error={fieldError(save.error, "assessor")}>
          {(p) => (
            <Select {...p} required value={assessor} onChange={(e) => setAssessor(e.target.value)}>
              <option value="" disabled>{people.isPending ? "Loading…" : "Choose the assessor"}</option>
              {people.data?.filter((u) => u.id !== round.assessor.id).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </Select>
          )}
        </Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!assessor}>Reassign</Button></div>
      </form>
    </Modal>
  );
}

function ResultDialog({ round, item, result, onClose, onDone }: { round: RetestRound; item: RetestItem; result: "passed" | "failed"; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<string[]>([]);
  const files = useQuery({ queryKey: ["finding-evidence", item.finding.id, 1], queryFn: () => api<Page<Evidence>>("GET", `/findings/${item.finding.id}/evidence?page=1`) });
  const save = useMutation({
    mutationFn: () => api("POST", `/retest-rounds/${round.id}/items/${item.id}/result`, { result, note, version: item.finding.version, ...(evidence.length ? { evidence_ids: evidence } : {}) }),
    onSuccess: () => { onDone(); onClose(); },
    onError: (e) => { if (isConflict(e)) onDone(); },
  });
  const pass = result === "passed";
  return (
    <Modal open onClose={onClose} title={pass ? "Record pass" : "Record fail"}>
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (note.trim().length >= 5) save.mutate(); }}>
        <p className="m-0 text-[15px] text-muted"><span className="mono">{item.finding.ref}</span> {item.finding.title}</p>
        <p className="m-0 text-muted">{pass ? "The fix held. The finding is closed and you are recorded as the verifier." : "The fix did not hold. The finding is reopened and goes back to the remediation team with your note."}</p>
        {isConflict(save.error) ? <ErrorNote error={save.error} /> : <ErrorNote error={noFieldErrors(save.error)} />}
        <Field label={pass ? "How did you verify?" : "What still fails?"} hint="At least 5 characters. Recorded on the finding and cannot be edited." error={fieldError(save.error, "note")}>
          {(p) => <Textarea {...p} rows={4} required maxLength={20000} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        {files.data && files.data.results.length > 0 && (
          <fieldset className="m-0 min-w-0 space-y-1 border-0 p-0">
            <legend className="label mb-1">Attach evidence (optional)</legend>
            {files.data.results.map((f) => (
              <label key={f.id} className="check">
                <input type="checkbox" checked={evidence.includes(f.id)} onChange={(e) => setEvidence(e.target.checked ? [...evidence, f.id] : evidence.filter((x) => x !== f.id))} />
                <span className="break-all">{f.original_name}</span>
              </label>
            ))}
            {fieldError(save.error, "evidence_ids") && <span className="field-error" role="alert">{fieldError(save.error, "evidence_ids")}</span>}
          </fieldset>
        )}
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={pass ? "primary" : "danger"} loading={save.isPending} disabled={note.trim().length < 5}>{pass ? "Pass and close" : "Fail and reopen"}</Button>
        </div>
      </form>
    </Modal>
  );
}
