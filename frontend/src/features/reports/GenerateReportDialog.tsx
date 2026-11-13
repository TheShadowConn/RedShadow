import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { FINDING_STATUSES, SEVERITIES, type EngagementRow, type Page, type ReportJob, type ReportTemplate } from "../../api/types";
import { Button, ErrorNote, Field, Modal, Select, TextInput, fieldError } from "../../design/ui";

const DEFAULT_STATUSES = ["open", "in_progress", "pending_verification", "reopened", "closed", "risk_accepted"];
const SELECTABLE = FINDING_STATUSES.filter(([k]) => k !== "draft");

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line px-3.5 py-2 has-[:checked]:border-accent has-[:checked]:bg-raised">
      <input type="checkbox" className="size-4 accent-[var(--color-accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="text-[15px]">{children}</span>
    </label>
  );
}

function Choice({ name, value, current, onPick, title, body }: { name: string; value: string; current: string; onPick: (v: string) => void; title: string; body: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line p-3.5 has-[:checked]:border-accent has-[:checked]:bg-raised has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent">
      <input type="radio" name={name} className="mt-1 size-4 accent-[var(--color-accent)]" checked={current === value} onChange={() => onPick(value)} />
      <span className="min-w-0"><span className="block font-medium">{title}</span><span className="block text-[14px] text-muted">{body}</span></span>
    </label>
  );
}

/** Ask for a report. The file is built in the background; the list shows progress. */
export function GenerateReportDialog({ engagement, open, onClose, onCreated }: { engagement?: { id: string; permissions: string[] }; open: boolean; onClose: () => void; onCreated?: (job: ReportJob) => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [eng, setEng] = useState(engagement?.id ?? "");
  const [format, setFormat] = useState<"pdf" | "csv">("pdf");
  const [audience, setAudience] = useState<"client" | "internal">("client");
  const [template, setTemplate] = useState("");
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("1.0");
  const [classification, setClassification] = useState("Confidential");
  const [severities, setSeverities] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>(DEFAULT_STATUSES);

  const engagements = useQuery({ queryKey: ["engagements-pick"], queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100&archived=all"), enabled: open && !engagement });
  const templates = useQuery({ queryKey: ["report-templates"], queryFn: () => api<Page<ReportTemplate>>("GET", "/report-templates?page_size=100"), enabled: open });
  const options = engagements.data?.results.filter((e) => !e.archived_at) ?? [];
  const canInternal = engagement ? engagement.permissions.includes("finding_notes.technical") : can("finding_notes.technical");
  const toggle = (list: string[], set: (v: string[]) => void, key: string, on: boolean) => set(on ? [...list, key] : list.filter((k) => k !== key));

  const create = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { engagement: eng, format, audience, title, version_label: version, classification, filters: { severities, statuses } };
      if (format === "pdf" && template) body.template = template;
      return api<ReportJob>("POST", "/reports", body);
    },
    onSuccess: (job) => { void qc.invalidateQueries({ queryKey: ["reports"] }); onCreated?.(job); onClose(); },
  });

  return (
    <Modal open={open} onClose={onClose} title="New report">
      <form className="flex flex-col gap-5 p-6" onSubmit={(e) => { e.preventDefault(); if (eng && statuses.length) create.mutate(); }}>
        <ErrorNote error={create.error} />
        {!engagement && (
          <Field label="Engagement" error={fieldError(create.error, "engagement")}>
            {(p) => (
              <Select {...p} required value={eng} onChange={(e) => setEng(e.target.value)}>
                <option value="" disabled>{engagements.isPending ? "Loading…" : "Choose an engagement"}</option>
                {options.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}
              </Select>
            )}
          </Field>
        )}
        <fieldset className="m-0 grid gap-3 border-0 p-0 sm:grid-cols-2">
          <legend className="label mb-2 p-0">Format</legend>
          <Choice name="format" value="pdf" current={format} onPick={(v) => setFormat(v as "pdf")} title="PDF report" body="A designed document to hand to the client." />
          <Choice name="format" value="csv" current={format} onPick={(v) => setFormat(v as "csv")} title="CSV export" body="One row per finding, for spreadsheets." />
        </fieldset>
        <fieldset className="m-0 grid gap-3 border-0 p-0 sm:grid-cols-2">
          <legend className="label mb-2 p-0">Audience</legend>
          <Choice name="audience" value="client" current={audience} onPick={(v) => setAudience(v as "client")} title="Client-facing" body="No proof of concept, technical details or technical notes." />
          {canInternal && <Choice name="audience" value="internal" current={audience} onPick={(v) => setAudience(v as "internal")} title="Internal" body="Adds technical details, proof of concept and technical notes. Do not send to the client." />}
        </fieldset>
        {format === "pdf" && (
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Template" hint="Sets the look, sections and footer.">
              {(p) => (
                <Select {...p} value={template} onChange={(e) => setTemplate(e.target.value)}>
                  <option value="">Default template</option>
                  {templates.data?.results.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Title" hint="Leave empty to use the engagement type.">{(p) => <TextInput {...p} maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
            <Field label="Version">{(p) => <TextInput {...p} maxLength={20} value={version} onChange={(e) => setVersion(e.target.value)} />}</Field>
            <Field label="Classification">{(p) => <TextInput {...p} maxLength={40} value={classification} onChange={(e) => setClassification(e.target.value)} />}</Field>
          </div>
        )}
        <fieldset className="m-0 border-0 p-0">
          <legend className="label mb-2 p-0">Severities <span className="font-normal text-muted">(none ticked means all)</span></legend>
          <div className="flex flex-wrap gap-2">{SEVERITIES.map(([k, l]) => <Check key={k} checked={severities.includes(k)} onChange={(on) => toggle(severities, setSeverities, k, on)}>{l}</Check>)}</div>
        </fieldset>
        <fieldset className="m-0 border-0 p-0">
          <legend className="label mb-2 p-0">Statuses <span className="font-normal text-muted">(drafts are never included)</span></legend>
          <div className="flex flex-wrap gap-2">{SELECTABLE.map(([k, l]) => <Check key={k} checked={statuses.includes(k)} onChange={(on) => toggle(statuses, setStatuses, k, on)}>{l}</Check>)}</div>
          {statuses.length === 0 && <p className="field-error mt-2" role="alert">Choose at least one status.</p>}
        </fieldset>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={create.isPending} disabled={!eng || statuses.length === 0}>Create report</Button>
        </div>
      </form>
    </Modal>
  );
}
