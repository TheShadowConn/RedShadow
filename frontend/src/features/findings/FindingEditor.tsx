import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { SEVERITIES, type Cwe, type Engagement, type EngagementRow, type Finding, type Member, type Page, type Reference, type ScopeLink, type Template } from "../../api/types";
import { Alert, Button, ErrorNote, Field, fieldError, LoadingRows, NotFoundOrError, Select, TextInput } from "../../design/ui";
import { CvssBuilder } from "./CvssBuilder";
import { CwePicker } from "./CwePicker";
import { Markdown, SeverityScale, isConflict, noFieldErrors } from "./shared";

type Form = {
  engagement: string; template: string; title: string; severity: string; cvss_vector: string; cwe: Cwe | null; asset: string; endpoint: string;
  description: string; recommendation: string; technical_details: string; poc: string; references: Reference[]; discovered_at: string;
  assigned_pentester: string; remediation_owner: string;
};

const today = () => new Date().toISOString().slice(0, 10);

function MarkdownField({ name, text, onChange, error, hint }: { name: string; text: string; onChange: (v: string) => void; error?: string; hint?: string }) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <span className="label" id={`md-${name.replace(/\W+/g, "-")}-l`}>{name}</span>
        <div className="flex gap-1" role="group" aria-label={`${name} view`}>
          <Button size="sm" variant={preview ? "secondary" : "primary"} aria-pressed={!preview} onClick={() => setPreview(false)}>Write</Button>
          <Button size="sm" variant={preview ? "primary" : "secondary"} aria-pressed={preview} onClick={() => setPreview(true)}>Preview</Button>
        </div>
      </div>
      {preview ? (
        <div className="min-h-32 rounded-md border border-line bg-surface p-4"><Markdown text={text} empty="Nothing to preview." /></div>
      ) : (
        <textarea aria-labelledby={`md-${name.replace(/\W+/g, "-")}-l`} aria-invalid={error ? true : undefined} className="input min-h-40 py-3 font-mono text-[15px]" rows={7} maxLength={50000} value={text} onChange={(e) => onChange(e.target.value)} />
      )}
      {error ? <span className="field-error" role="alert">{error}</span> : hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

export function FindingEditor() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const editing = !!id;
  const nav = useNavigate();
  const qc = useQueryClient();
  const { can } = useAuth();

  const existing = useQuery({ queryKey: ["finding", id], queryFn: () => api<Finding>("GET", `/findings/${id}`), enabled: editing });
  const [form, setForm] = useState<Form | null>(null);

  useEffect(() => {
    const f = existing.data;
    if (!f || form) return;
    setForm({
      engagement: f.engagement.id, template: "", title: f.title, severity: f.severity, cvss_vector: f.cvss_vector, cwe: f.cwe, asset: f.asset?.id ?? "",
      endpoint: f.endpoint, description: f.description, recommendation: f.recommendation, technical_details: f.technical_details, poc: f.poc,
      references: f.references, discovered_at: f.discovered_at, assigned_pentester: f.assigned_pentester?.id ?? "", remediation_owner: f.remediation_owner?.id ?? "",
    });
  }, [existing.data, form]);

  useEffect(() => {
    if (editing || form) return;
    setForm({
      engagement: params.get("engagement") ?? "", template: "", title: "", severity: "medium", cvss_vector: "", cwe: null, asset: "", endpoint: "",
      description: "", recommendation: "", technical_details: "", poc: "", references: [], discovered_at: today(), assigned_pentester: "", remediation_owner: "",
    });
  }, [editing, form, params]);

  const engagementId = form?.engagement ?? "";
  const engagements = useQuery({ queryKey: ["engagements-pick-open"], queryFn: () => api<Page<EngagementRow>>("GET", "/engagements?page_size=100"), enabled: !editing });
  const eng = useQuery({ queryKey: ["engagement", engagementId], queryFn: () => api<Engagement>("GET", `/engagements/${engagementId}`), enabled: !!engagementId });
  const perms = new Set(eng.data?.permissions ?? existing.data?.permissions ?? []);
  const assets = useQuery({ queryKey: ["eng-assets", engagementId], queryFn: () => api<ScopeLink[]>("GET", `/engagements/${engagementId}/assets`), enabled: !!engagementId && perms.has("assets.view") });
  const members = useQuery({ queryKey: ["eng-members", engagementId], queryFn: () => api<Member[]>("GET", `/engagements/${engagementId}/members`), enabled: !!engagementId && perms.has("findings.assign") });
  const templates = useQuery({ queryKey: ["templates", ""], queryFn: () => api<Page<Template>>("GET", "/finding-templates?page_size=200"), enabled: !editing && can("templates.view") });

  const save = useMutation({
    mutationFn: () => {
      const f = form!;
      const body: Record<string, unknown> = {
        title: f.title, description: f.description, recommendation: f.recommendation, technical_details: f.technical_details, poc: f.poc,
        references: f.references.filter((r) => r.label.trim() || r.url.trim()), endpoint: f.endpoint, discovered_at: f.discovered_at,
        cwe_id: f.cwe?.id ?? null, asset: f.asset || null, cvss_vector: f.cvss_vector,
      };
      if (!f.cvss_vector) body.severity = f.severity;
      if (perms.has("findings.assign")) { body.assigned_pentester = f.assigned_pentester || null; body.remediation_owner = f.remediation_owner || null; }
      if (editing) return api<Finding>("PATCH", `/findings/${id}`, { ...body, version: existing.data!.version });
      return api<Finding>("POST", "/findings", { ...body, engagement: f.engagement, ...(f.template ? { template: f.template } : {}) });
    },
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: ["findings"] });
      void qc.invalidateQueries({ queryKey: ["finding", saved.id] });
      void qc.invalidateQueries({ queryKey: ["finding-history", saved.id] });
      nav(`/findings/${saved.id}`);
    },
    onError: (e) => { if (isConflict(e)) void qc.invalidateQueries({ queryKey: ["finding", id] }); },
  });

  if (editing && existing.isError) return <><BackLink /><div className="card"><NotFoundOrError error={existing.error} what="Finding" onRetry={() => void existing.refetch()} /></div></>;
  if (!form || (editing && existing.isPending)) return <LoadingRows rows={5} />;

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });
  const inputHandler = (k: keyof Form) => (e: { target: { value: string } }) => set(k, e.target.value as never);

  function applyTemplate(tid: string) {
    const t = templates.data?.results.find((x) => x.id === tid);
    if (!t) return setForm({ ...form!, template: "" });
    setForm({
      ...form!, template: tid, title: t.title, description: t.description, recommendation: t.recommendation,
      cvss_vector: t.cvss_vector, severity: t.severity || form!.severity, cwe: t.cwe, references: t.references,
    });
  }

  const general = noFieldErrors(save.error);
  const conflict = isConflict(save.error);
  const members_ = members.data ?? [];
  const writableEng = !!form.engagement;

  return (
    <>
      <BackLink to={editing ? `/findings/${id}` : form.engagement ? `/engagements/${form.engagement}` : "/findings"} label={editing ? "Finding" : "Back"} />
      <h1 className="mb-6 text-[32px] max-sm:text-[26px]">{editing ? `Edit ${existing.data?.ref}` : "New finding"}</h1>
      <form className="space-y-8" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        {conflict ? (
          <Alert tone="error">
            <p className="m-0">Someone else changed this finding while you were editing.</p>
            <div className="mt-3"><Button size="sm" onClick={() => { save.reset(); setForm(null); }}>Discard my edits and load the latest</Button></div>
          </Alert>
        ) : <ErrorNote error={general} />}

        {!editing && (
          <section className="card card-pad space-y-5">
            <Field label="Engagement" error={fieldError(save.error, "engagement")}>
              {(p) => <Select {...p} required value={form.engagement} onChange={inputHandler("engagement")}><option value="" disabled>Choose an engagement</option>{engagements.data?.results.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}</Select>}
            </Field>
            {can("templates.view") && (
              <Field label="Start from a template" hint="Optional. Fills the fields below, which you can still change." error={fieldError(save.error, "template")}>
                {(p) => <Select {...p} value={form.template} onChange={(e) => applyTemplate(e.target.value)}><option value="">No template</option>{templates.data?.results.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>}
              </Field>
            )}
          </section>
        )}

        <section className="card card-pad space-y-5">
          <h2 className="text-lg">Summary</h2>
          <Field label="Title" error={fieldError(save.error, "title")}>{(p) => <TextInput {...p} required maxLength={200} value={form.title} onChange={inputHandler("title")} />}</Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Weakness (CWE)" error={fieldError(save.error, "cwe_id")}>{() => <CwePicker value={form.cwe} onChange={(c) => set("cwe", c)} />}</Field>
            <Field label="Discovered on" error={fieldError(save.error, "discovered_at")}>{(p) => <TextInput {...p} type="date" required value={form.discovered_at} onChange={inputHandler("discovered_at")} />}</Field>
            <Field label="Asset" hint={assets.data && assets.data.length === 0 ? "Link assets to the engagement scope first." : undefined} error={fieldError(save.error, "asset")}>
              {(p) => <Select {...p} value={form.asset} onChange={inputHandler("asset")}><option value="">No specific asset</option>{assets.data?.filter((l) => l.in_scope).map((l) => <option key={l.asset.id} value={l.asset.id}>{l.asset.name}</option>)}</Select>}
            </Field>
            <Field label="Endpoint or location" hint="URL path, host and port, file and line." error={fieldError(save.error, "endpoint")}>{(p) => <TextInput {...p} maxLength={500} value={form.endpoint} onChange={inputHandler("endpoint")} />}</Field>
          </div>
        </section>

        <section className="card card-pad space-y-5">
          <h2 className="text-lg">Severity</h2>
          <SeverityScale />
          <CvssBuilder value={form.cvss_vector} onChange={(v) => set("cvss_vector", v)} />
          {fieldError(save.error, "cvss_vector") && <span className="field-error" role="alert">{fieldError(save.error, "cvss_vector")}</span>}
          {!form.cvss_vector && (
            <Field label="Severity" error={fieldError(save.error, "severity")}>
              {(p) => <Select {...p} value={form.severity} onChange={inputHandler("severity")}>{SEVERITIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}
            </Field>
          )}
        </section>

        <section className="card card-pad space-y-6">
          <h2 className="text-lg">Write-up</h2>
          <p className="m-0 text-[14px] text-muted">Markdown is supported. HTML and images are not rendered.</p>
          <MarkdownField name="Description" text={form.description} onChange={(v) => set("description", v)} error={fieldError(save.error, "description")} />
          <MarkdownField name="Recommendation" text={form.recommendation} onChange={(v) => set("recommendation", v)} error={fieldError(save.error, "recommendation")} hint="Required before publishing." />
          <MarkdownField name="Technical details" text={form.technical_details} onChange={(v) => set("technical_details", v)} error={fieldError(save.error, "technical_details")} hint="Testing team only." />
          <MarkdownField name="Proof of concept" text={form.poc} onChange={(v) => set("poc", v)} error={fieldError(save.error, "poc")} hint="Testing team only." />
        </section>

        <section className="card card-pad space-y-4">
          <h2 className="text-lg">References</h2>
          {form.references.map((r, i) => (
            <div key={i} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
              <Field label="Label (optional)">{(p) => <TextInput {...p} maxLength={120} placeholder="The link is used if empty" value={r.label} onChange={(e) => set("references", form.references.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />}</Field>
              <Field label="Link" error={fieldError(save.error, "references")}>{(p) => <TextInput {...p} type="url" maxLength={500} placeholder="https://" value={r.url} onChange={(e) => set("references", form.references.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />}</Field>
              <Button aria-label={`Remove reference ${i + 1}`} onClick={() => set("references", form.references.filter((_, j) => j !== i))}><Trash2 size={18} aria-hidden /></Button>
            </div>
          ))}
          {form.references.length < 20 && <Button onClick={() => set("references", [...form.references, { label: "", url: "" }])}><Plus size={18} aria-hidden /> Add reference</Button>}
        </section>

        {perms.has("findings.assign") && (
          <section className="card card-pad space-y-5">
            <h2 className="text-lg">Assignment</h2>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Assigned pentester" error={fieldError(save.error, "assigned_pentester")}>
                {(p) => <Select {...p} value={form.assigned_pentester} onChange={inputHandler("assigned_pentester")}><option value="">Unassigned</option>{members_.map((m) => <option key={m.user.id} value={m.user.id}>{m.user.display_name}</option>)}</Select>}
              </Field>
              <Field label="Remediation owner" hint="Sees the finding once it is published." error={fieldError(save.error, "remediation_owner")}>
                {(p) => <Select {...p} value={form.remediation_owner} onChange={inputHandler("remediation_owner")}><option value="">Unassigned</option>{members_.map((m) => <option key={m.user.id} value={m.user.id}>{m.user.display_name} ({m.role.name})</option>)}</Select>}
              </Field>
            </div>
          </section>
        )}

        <div className="flex flex-wrap items-center justify-end gap-3">
          <Link to={editing ? `/findings/${id}` : "/findings"} className="btn btn-secondary">Cancel</Link>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!form.title.trim() || !writableEng}>{editing ? "Save changes" : "Create draft"}</Button>
        </div>
        {!editing && <p className="m-0 text-right text-[13px] text-muted">New findings start as drafts. Add evidence and publish from the finding page.</p>}
      </form>
    </>
  );
}

function BackLink({ to = "/findings", label = "Findings" }: { to?: string; label?: string }) {
  return <Link to={to} className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink"><ArrowLeft size={18} aria-hidden /> {label}</Link>;
}
