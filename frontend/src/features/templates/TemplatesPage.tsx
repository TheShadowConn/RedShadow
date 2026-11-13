import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { SEVERITIES, type Cwe, type Page, type Reference, type Template } from "../../api/types";
import { Alert, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, fieldError, LoadingRows, Modal, PageHeader, Select, Textarea, TextInput } from "../../design/ui";
import { CvssBuilder } from "../findings/CvssBuilder";
import { CwePicker } from "../findings/CwePicker";
import { SeverityBadge, isConflict, noFieldErrors } from "../findings/shared";

export function TemplatesPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Template | "new" | null>(null);
  const [removing, setRemoving] = useState<Template | null>(null);
  const q = useQuery({ queryKey: ["templates", search], queryFn: () => api<Page<Template>>("GET", `/finding-templates?page_size=100&search=${encodeURIComponent(search)}`) });
  const remove = useMutation({
    mutationFn: (t: Template) => api("DELETE", `/finding-templates/${t.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["templates"] }); setRemoving(null); },
  });
  const manage = can("templates.manage");

  return (
    <>
      <PageHeader
        title="Finding templates"
        lead="Reusable write-ups for common issues. Choosing a template when creating a finding fills the title, text, severity and weakness."
        actions={manage && <Button variant="primary" onClick={() => setEditing("new")}><Plus size={18} aria-hidden /> New template</Button>}
      />
      <div className="card overflow-hidden">
        <div className="border-b border-line p-4">
          <div className="relative max-w-md">
            <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput aria-label="Search templates" placeholder="Search templates" className="pl-11" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        {q.isPending && <LoadingRows />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title={search ? "No templates match" : "No templates yet"} body={search ? "Try different words." : manage ? "Add the write-ups you reuse most." : "An administrator has not added any templates yet."} />}
        {q.data && q.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="m-0 flex flex-wrap items-center gap-2 font-medium">{t.name}<SeverityBadge severity={t.severity} /></p>
                  <p className="m-0 truncate text-[14px] text-muted">{t.title}{t.cwe ? ` · CWE-${t.cwe.id}` : ""}</p>
                </div>
                {manage && (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => setEditing(t)}>Edit</Button>
                    <Button size="sm" variant="danger" aria-label={`Delete ${t.name}`} onClick={() => { remove.reset(); setRemoving(t); }}><Trash2 size={16} aria-hidden /></Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {editing && <TemplateForm key={editing === "new" ? "new" : `${editing.id}-${editing.version}`} template={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={!!removing} title="Delete template" body={`${removing?.name} is deleted. Findings already created from it keep their text.`} confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </>
  );
}

function TemplateForm({ template, onClose }: { template?: Template; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    name: template?.name ?? "", title: template?.title ?? "", description: template?.description ?? "", recommendation: template?.recommendation ?? "",
    severity: template?.severity || "medium", cvss_vector: template?.cvss_vector ?? "",
  });
  const [cwe, setCwe] = useState<Cwe | null>(template?.cwe ?? null);
  const [refs, setRefs] = useState<Reference[]>(template?.references ?? []);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...f, cwe_id: cwe?.id ?? null, references: refs.filter((r) => r.label.trim() || r.url.trim()) };
      if (f.cvss_vector) delete body.severity;
      return template ? api("PATCH", `/finding-templates/${template.id}`, { ...body, version: template.version }) : api("POST", "/finding-templates", body);
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["templates"] }); onClose(); },
    onError: (e) => { if (isConflict(e)) void qc.invalidateQueries({ queryKey: ["templates"] }); },
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open onClose={onClose} title={template ? "Edit template" : "New template"}>
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        {isConflict(save.error) ? <Alert tone="error">Someone else changed this template. Close this window and open it again to see the latest version.</Alert> : <ErrorNote error={noFieldErrors(save.error)} />}
        <Field label="Template name" hint="Shown in the picker. Must be unique." error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required maxLength={160} value={f.name} onChange={set("name")} />}</Field>
        <Field label="Finding title" error={fieldError(save.error, "title")}>{(p) => <TextInput {...p} required maxLength={200} value={f.title} onChange={set("title")} />}</Field>
        <Field label="Description (markdown)" error={fieldError(save.error, "description")}>{(p) => <Textarea {...p} rows={5} value={f.description} onChange={set("description")} />}</Field>
        <Field label="Recommendation (markdown)" error={fieldError(save.error, "recommendation")}>{(p) => <Textarea {...p} rows={4} value={f.recommendation} onChange={set("recommendation")} />}</Field>
        <Field label="Weakness (CWE)" error={fieldError(save.error, "cwe_id")}>{() => <CwePicker value={cwe} onChange={setCwe} />}</Field>
        <CvssBuilder value={f.cvss_vector} onChange={(v) => setF({ ...f, cvss_vector: v })} />
        {!f.cvss_vector && (
          <Field label="Severity" error={fieldError(save.error, "severity")}>{(p) => <Select {...p} value={f.severity} onChange={set("severity")}>{SEVERITIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
        )}
        <fieldset className="m-0 space-y-3 border-0 p-0">
          <legend className="label mb-2">References</legend>
          {refs.map((r, i) => (
            <div key={i} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
              <Field label="Label">{(p) => <TextInput {...p} value={r.label} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />}</Field>
              <Field label="Link" error={fieldError(save.error, "references")}>{(p) => <TextInput {...p} type="url" placeholder="https://" value={r.url} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />}</Field>
              <Button aria-label={`Remove reference ${i + 1}`} onClick={() => setRefs(refs.filter((_, j) => j !== i))}><Trash2 size={18} aria-hidden /></Button>
            </div>
          ))}
          {refs.length < 20 && <Button onClick={() => setRefs([...refs, { label: "", url: "" }])}><Plus size={18} aria-hidden /> Add reference</Button>}
        </fieldset>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!f.name.trim() || !f.title.trim()}>{template ? "Save changes" : "Create template"}</Button></div>
      </form>
    </Modal>
  );
}
