import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";

import { api } from "../../api/client";
import type { FindingRow, Page, TransitionRule } from "../../api/types";
import { Badge, ErrorNote, Field, fieldError, Modal, Button, Select, Textarea, TextInput } from "../../design/ui";
import { isConflict, noFieldErrors } from "../findings/shared";

/** Whole days from today to an ISO date (yyyy-mm-dd), in the viewer's calendar. Negative when past. */
export function daysUntil(iso: string): number {
  const today = new Date();
  const a = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const [y, m, d] = iso.split("-").map(Number);
  return Math.round((Date.UTC(y, m - 1, d) - a) / 86_400_000);
}

const CLOCK_RUNNING = new Set(["open", "in_progress", "reopened"]);

/** Deadline badge. Only findings still being fixed carry one: the clock stops at submission. */
export function SlaBadge({ due, status, overdue }: { due: string | null; status: string; overdue: boolean }) {
  if (!CLOCK_RUNNING.has(status)) return null;
  if (!due) return <span className="text-[14px] text-muted">No SLA</span>;
  const n = daysUntil(due);
  if (overdue || n < 0) return <Badge tone="fail">Overdue {Math.abs(n)}d</Badge>;
  if (n === 0) return <Badge tone="warn">Due today</Badge>;
  return (
    <span className="inline-flex items-center gap-1.5 text-[14px] text-muted">
      <CalendarClock size={15} aria-hidden />
      Due in {n}d
    </span>
  );
}

export type Move = Pick<TransitionRule, "to" | "name" | "note_required" | "needs">;

/** Button and dialog wording per move. The server decides what is allowed; this is wording only. */
export const MOVES: Record<string, { label: string; tone: "primary" | "secondary" | "danger"; title: string; noteLabel?: string; intro?: string; confirm?: string }> = {
  published: { label: "Publish", tone: "primary", title: "Publish finding" },
  started: { label: "Start work", tone: "primary", title: "Start work" },
  paused: { label: "Pause work", tone: "secondary", title: "Pause work" },
  submitted_for_verification: { label: "Submit for verification", tone: "primary", title: "Submit for verification", noteLabel: "What was fixed?", intro: "The testing team retests the fix. Say what changed and where, so they can check it.", confirm: "Submit" },
  verified: { label: "Verify and close", tone: "primary", title: "Verify and close", noteLabel: "How did you verify?", intro: "The fix held. The finding is closed and your name is recorded as the verifier.", confirm: "Verify and close" },
  verification_failed: { label: "Fail verification", tone: "danger", title: "Fail verification", noteLabel: "What still fails?", intro: "The finding is reopened and goes back to the remediation team with your note.", confirm: "Fail and reopen" },
  closed: { label: "Close", tone: "secondary", title: "Close finding", noteLabel: "Why close it now?", intro: "Closes the finding without a retest. The note is recorded.", confirm: "Close finding" },
  risk_accepted: { label: "Accept risk", tone: "secondary", title: "Accept risk", noteLabel: "Business reason", intro: "The finding stays visible but stops counting against the deadline. It reopens by itself on the date below.", confirm: "Accept risk" },
  reopened: { label: "Reopen", tone: "secondary", title: "Reopen finding", noteLabel: "Why reopen?", intro: "The finding goes back to remediation with the original due date.", confirm: "Reopen" },
  false_positive: { label: "False positive", tone: "danger", title: "Mark as false positive", noteLabel: "Why is it not real?", intro: "The finding becomes read-only. It can be reopened later with a reason.", confirm: "Mark false positive" },
  duplicate: { label: "Duplicate of…", tone: "danger", title: "Mark as duplicate", intro: "Choose the original finding in this engagement. This finding becomes read-only. It can be reopened later with a reason.", confirm: "Mark duplicate" },
};

/** Preferred order for the one primary action. Everything else lives behind "More". */
export const MOVE_PRIORITY = ["published", "started", "submitted_for_verification", "verified", "reopened", "verification_failed", "closed", "paused", "risk_accepted", "false_positive", "duplicate"];

export const needsDialog = (m: Move) => m.note_required || m.needs.length > 0;

export type MoveTarget = Pick<FindingRow, "id" | "version" | "ref" | "title"> & { engagement: { id: string } };

export function useInvalidateWork() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["finding", "findings", "finding-history", "finding-activity", "finding-notes", "queue", "retests", "retest"]) void qc.invalidateQueries({ queryKey: [key] });
  };
}

/** One-tap moves that need no note (publish, start, pause). */
export function useQuickMove(onDone?: () => void) {
  const refresh = useInvalidateWork();
  return useMutation({
    mutationFn: ({ f, move }: { f: MoveTarget; move: Move }) => api("POST", `/findings/${f.id}/transition`, { to: move.to, version: f.version }),
    onSuccess: () => { refresh(); onDone?.(); },
    onError: (e) => { if (isConflict(e)) refresh(); },
  });
}

/** The single dialog behind every move that needs a note, an expiry or an original finding. */
export function MoveDialog({ f, move, onClose, onDone }: { f: MoveTarget; move: Move; onClose: () => void; onDone?: () => void }) {
  const text = MOVES[move.name];
  const refresh = useInvalidateWork();
  const [note, setNote] = useState("");
  const [until, setUntil] = useState("");
  const [target, setTarget] = useState("");
  const wantsDuplicate = move.needs.includes("duplicate_of");
  const wantsExpiry = move.needs.includes("expiry");
  const list = useQuery({
    queryKey: ["findings", "dup-pick", f.engagement.id],
    queryFn: () => api<Page<FindingRow>>("GET", `/findings?engagement=${f.engagement.id}&page_size=100&ordering=ref`),
    enabled: wantsDuplicate,
  });
  const options = list.data?.results.filter((r) => r.id !== f.id && r.status !== "duplicate") ?? [];
  const save = useMutation({
    mutationFn: () => api("POST", `/findings/${f.id}/transition`, {
      to: move.to, version: f.version,
      ...(move.note_required ? { note } : {}),
      ...(wantsExpiry ? { risk_accepted_until: until } : {}),
      ...(wantsDuplicate ? { duplicate_of: target } : {}),
    }),
    onSuccess: () => { refresh(); onDone?.(); onClose(); },
    onError: (e) => { if (isConflict(e)) refresh(); },
  });
  const today = new Date();
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const min = iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1));
  const max = iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 365));
  const ready = (!move.note_required || note.trim().length >= 5) && (!wantsExpiry || !!until) && (!wantsDuplicate || !!target);

  return (
    <Modal open onClose={onClose} title={text.title}>
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (ready) save.mutate(); }}>
        <p className="m-0 text-[15px] text-muted"><span className="mono">{f.ref}</span> {f.title}</p>
        {text.intro && <p className="m-0 text-muted">{text.intro}</p>}
        {isConflict(save.error) ? <ErrorNote error={save.error} /> : <ErrorNote error={noFieldErrors(save.error)} />}
        {move.note_required && (
          <Field label={text.noteLabel ?? "Note"} hint="At least 5 characters. Recorded on the finding and cannot be edited." error={fieldError(save.error, "note")}>
            {(p) => <Textarea {...p} rows={4} required maxLength={20000} value={note} onChange={(e) => setNote(e.target.value)} />}
          </Field>
        )}
        {wantsExpiry && (
          <Field label="Accepted until" hint="Up to 365 days from today." error={fieldError(save.error, "risk_accepted_until")}>
            {(p) => <TextInput {...p} type="date" required min={min} max={max} value={until} onChange={(e) => setUntil(e.target.value)} />}
          </Field>
        )}
        {wantsDuplicate && (
          <Field label="Original finding" error={fieldError(save.error, "duplicate_of")}>
            {(p) => (
              <Select {...p} required value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="" disabled>{list.isPending ? "Loading…" : "Choose the original"}</option>
                {options.map((r) => <option key={r.id} value={r.id}>{r.ref} {r.title}</option>)}
              </Select>
            )}
          </Field>
        )}
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={text.tone === "danger" ? "danger" : "primary"} loading={save.isPending} disabled={!ready}>{text.confirm ?? text.label}</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Fixed rule objects for queue rows, which only know the finding's status. */
export const RULE = {
  started: { to: "in_progress", name: "started", note_required: false, needs: [] },
  submit: { to: "pending_verification", name: "submitted_for_verification", note_required: true, needs: [] },
  verified: { to: "closed", name: "verified", note_required: true, needs: [] },
  failed: { to: "reopened", name: "verification_failed", note_required: true, needs: [] },
} satisfies Record<string, Move>;
