import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import type { QueueRow, RetestRound, UserRef } from "../../api/types";
import { Button, ErrorNote, Field, fieldError, Modal, Select, Textarea } from "../../design/ui";
import { noFieldErrors } from "../findings/shared";
import { useInvalidateWork } from "../remediation/shared";

/** Ask an assessor to retest findings of one engagement. Only people who can record results are offered. */
export function RequestRetestDialog({ rows, onClose, onDone }: { rows: QueueRow[]; onClose: () => void; onDone: () => void }) {
  const nav = useNavigate();
  const refresh = useInvalidateWork();
  const engagement = rows[0].engagement;
  const [assessor, setAssessor] = useState("");
  const [note, setNote] = useState("");
  const people = useQuery({ queryKey: ["assessors", engagement.id], queryFn: () => api<UserRef[]>("GET", `/retest-rounds/assessors?engagement=${engagement.id}`) });
  const save = useMutation({
    mutationFn: () => api<RetestRound>("POST", "/retest-rounds", { engagement: engagement.id, assessor, findings: rows.map((r) => r.id), note }),
    onSuccess: (round) => { refresh(); onDone(); onClose(); nav(`/retests/${round.id}`); },
  });
  return (
    <Modal open onClose={onClose} title="Request retest">
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (assessor) save.mutate(); }}>
        <p className="m-0 text-muted">{rows.length} finding{rows.length === 1 ? "" : "s"} in {engagement.name}. Only the assessor you choose can record the results.</p>
        <ul className="m-0 max-h-32 list-none space-y-1 overflow-y-auto p-0 text-[15px]">
          {rows.map((r) => <li key={r.id}><span className="mono text-muted">{r.ref}</span> {r.title}</li>)}
        </ul>
        <ErrorNote error={noFieldErrors(save.error)} />
        <ErrorNote error={people.error} />
        <Field label="Assessor" error={fieldError(save.error, "assessor") ?? fieldError(save.error, "findings")}>
          {(p) => (
            <Select {...p} required value={assessor} onChange={(e) => setAssessor(e.target.value)}>
              <option value="" disabled>{people.isPending ? "Loading…" : "Choose the assessor"}</option>
              {people.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Note for the assessor (optional)">{(p) => <Textarea {...p} rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!assessor}>Request retest</Button>
        </div>
      </form>
    </Modal>
  );
}
