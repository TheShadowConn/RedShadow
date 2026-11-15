import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { api, upload } from "../../api/client";
import { REPORT_FONTS, REPORT_SECTIONS, type Page, type ReportTemplate } from "../../api/types";
import { Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, LoadingRows, Modal, PageHeader, Select, TextInput, fieldError, label } from "../../design/ui";
import { isConflict } from "../findings/shared";

const NAMES = Object.fromEntries(REPORT_SECTIONS);

export function ReportTemplatesPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<ReportTemplate | "new" | null>(null);
  const [removing, setRemoving] = useState<ReportTemplate | null>(null);
  const q = useQuery({ queryKey: ["report-templates"], queryFn: () => api<Page<ReportTemplate>>("GET", "/report-templates?page_size=100") });
  const remove = useMutation({
    mutationFn: (t: ReportTemplate) => api("DELETE", `/report-templates/${t.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["report-templates"] }); setRemoving(null); },
  });

  return (
    <>
      <PageHeader
        title="Report templates"
        lead="Set the look and contents of PDF reports: logo, accent colour, font, footer and which sections appear, in what order."
        actions={<Button variant="primary" onClick={() => setEditing("new")}><Plus size={18} aria-hidden /> New template</Button>}
      />
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title="No templates" body="Create a template to brand your reports." />}
        {q.data && q.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div className="flex min-w-0 items-center gap-4">
                  <span aria-hidden className="size-9 shrink-0 rounded-lg border border-line" style={{ background: t.accent }} />
                  <div className="min-w-0">
                    <p className="m-0 flex flex-wrap items-center gap-2 font-medium">{t.name}{t.is_default && <Badge tone="ok">Default</Badge>}</p>
                    <p className="m-0 text-[14px] text-muted">{label(REPORT_FONTS, t.font)} · {t.sections.length} sections · {t.has_logo ? "own logo" : "RedShadow logo"}{t.footer_text ? ` · “${t.footer_text}”` : ""}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => setEditing(t)}>Edit</Button>
                  <Button size="sm" variant="danger" aria-label={`Delete ${t.name}`} disabled={t.is_default} onClick={() => { remove.reset(); setRemoving(t); }}><Trash2 size={16} aria-hidden /></Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {editing && <TemplateForm key={editing === "new" ? "new" : `${editing.id}-${editing.version}`} template={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={!!removing} title="Delete template" body={`${removing?.name} is deleted. Reports already built from it are not changed.`} confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </>
  );
}

type Item = { key: string; on: boolean };

function initialItems(sections: string[] | undefined): Item[] {
  const chosen = sections ?? REPORT_SECTIONS.map(([k]) => k as string);
  return [...chosen.map((key) => ({ key, on: true })), ...REPORT_SECTIONS.map(([k]) => k as string).filter((k) => !chosen.includes(k)).map((key) => ({ key, on: false }))];
}

function TemplateForm({ template, onClose }: { template?: ReportTemplate; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(template?.name ?? "");
  const [accent, setAccent] = useState(template?.accent ?? "#ef233c");
  const [font, setFont] = useState<string>(template?.font ?? "geist");
  const [footer, setFooter] = useState(template?.footer_text ?? "");
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false);
  const [items, setItems] = useState<Item[]>(() => initialItems(template?.sections));
  const [logoKey, setLogoKey] = useState(0);
  const [logoError, setLogoError] = useState<unknown>(null);
  const [hasLogo, setHasLogo] = useState(template?.has_logo ?? false);
  const input = useRef<HTMLInputElement>(null);

  const move = (i: number, d: -1 | 1) => setItems((cur) => { const next = [...cur]; const j = i + d; if (j < 0 || j >= next.length) return cur; [next[i], next[j]] = [next[j], next[i]]; return next; });
  const flip = (i: number) => setItems((cur) => cur.map((it, n) => (n === i ? { ...it, on: !it.on } : it)));

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { name, accent, font, footer_text: footer, sections: items.filter((i) => i.on).map((i) => i.key) };
      if (isDefault) body.is_default = true;
      return template ? api<ReportTemplate>("PATCH", `/report-templates/${template.id}`, { ...body, version: template.version }) : api<ReportTemplate>("POST", "/report-templates", body);
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["report-templates"] }); onClose(); },
  });
  const setLogo = useMutation({
    mutationFn: (file: File) => upload<ReportTemplate>("POST", `/report-templates/${template!.id}/logo`, file, undefined, {}, "logo"),
    onSuccess: () => { setHasLogo(true); setLogoKey((k) => k + 1); setLogoError(null); void qc.invalidateQueries({ queryKey: ["report-templates"] }); },
    onError: setLogoError,
  });
  const clearLogo = useMutation({
    mutationFn: () => api<ReportTemplate>("DELETE", `/report-templates/${template!.id}/logo`),
    onSuccess: () => { setHasLogo(false); setLogoError(null); void qc.invalidateQueries({ queryKey: ["report-templates"] }); },
    onError: setLogoError,
  });

  return (
    <Modal open onClose={onClose} title={template ? "Edit template" : "New template"}>
      <form className="flex flex-col gap-5 p-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={save.error} />
        {isConflict(save.error) && <Alert tone="warn">Someone else changed this template. Close and reopen it to see the latest version.</Alert>}
        <Field label="Name" error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Accent colour" error={fieldError(save.error, "accent")} hint="Used for the cover bar, numbers and rules.">
            {(p) => (
              <div className="flex items-center gap-3">
                <input type="color" aria-label="Pick accent colour" className="h-11 w-14 cursor-pointer rounded-lg border border-line bg-transparent p-1" value={accent} onChange={(e) => setAccent(e.target.value)} />
                <TextInput {...p} className="mono" maxLength={7} value={accent} onChange={(e) => setAccent(e.target.value)} />
              </div>
            )}
          </Field>
          <Field label="Font">{(p) => <Select {...p} value={font} onChange={(e) => setFont(e.target.value)}>{REPORT_FONTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        </div>
        <Field label="Footer text" hint="Printed bottom left on every page. Empty shows the engagement reference.">{(p) => <TextInput {...p} maxLength={160} value={footer} onChange={(e) => setFooter(e.target.value)} />}</Field>

        <fieldset className="m-0 border-0 p-0">
          <legend className="label mb-1 p-0">Sections</legend>
          <p className="m-0 mb-3 text-[14px] text-muted">The cover and contents page are always first. Tick the sections to include and use the arrows to reorder.</p>
          <ol className="m-0 list-none divide-y divide-line overflow-hidden rounded-lg border border-line p-0">
            {items.map((it, i) => (
              <li key={it.key} className="flex items-center gap-2 px-3 py-1.5">
                <label className="flex min-h-11 flex-1 cursor-pointer items-center gap-3">
                  <input type="checkbox" className="size-4 accent-[var(--color-accent)]" checked={it.on} disabled={it.key === "findings"} onChange={() => flip(i)} />
                  <span className={it.on ? "" : "text-muted"}>{NAMES[it.key]}</span>
                  {it.key === "findings" && <span className="text-[13px] text-muted">required</span>}
                </label>
                <Button size="sm" className="btn-icon" aria-label={`Move ${NAMES[it.key]} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={16} aria-hidden /></Button>
                <Button size="sm" className="btn-icon" aria-label={`Move ${NAMES[it.key]} down`} disabled={i === items.length - 1} onClick={() => move(i, 1)}><ArrowDown size={16} aria-hidden /></Button>
              </li>
            ))}
          </ol>
          {fieldError(save.error, "sections") && <p className="field-error mt-2" role="alert">{fieldError(save.error, "sections")}</p>}
        </fieldset>

        <div>
          <span className="label">Logo</span>
          {template ? (
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex h-16 w-40 items-center justify-center overflow-hidden rounded-lg border border-line bg-white p-2">
                {hasLogo ? <img key={logoKey} src={`/api/v1/report-templates/${template.id}/logo?v=${logoKey}`} alt="Current report logo" className="max-h-full max-w-full object-contain" /> : <span className="text-[13px] text-muted">RedShadow logo</span>}
              </div>
              <input ref={input} type="file" accept="image/png,image/jpeg" className="sr-only" aria-label="Choose logo file" onChange={(e) => { const f = e.target.files?.[0]; if (f) setLogo.mutate(f); e.target.value = ""; }} />
              <Button onClick={() => input.current?.click()} loading={setLogo.isPending}>{hasLogo ? "Replace logo" : "Upload logo"}</Button>
              {hasLogo && <Button variant="danger" onClick={() => clearLogo.mutate()} loading={clearLogo.isPending}>Remove</Button>}
              <p className="m-0 basis-full text-[14px] text-muted">PNG or JPEG, up to 1 MB and 2000 px. It sits on the dark cover on a white tile.</p>
            </div>
          ) : (
            <p className="m-0 text-[14px] text-muted">Save the template first, then reopen it to upload a logo.</p>
          )}
          <ErrorNote error={logoError} />
        </div>

        <label className="flex min-h-11 cursor-pointer items-center gap-3">
          <input type="checkbox" className="size-4 accent-[var(--color-accent)]" checked={isDefault} disabled={template?.is_default} onChange={(e) => setIsDefault(e.target.checked)} />
          <span>Use as the default template{template?.is_default ? " (it is the default now)" : ""}</span>
        </label>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!name.trim() || !items.some((i) => i.on)}>{template ? "Save changes" : "Create template"}</Button>
        </div>
      </form>
    </Modal>
  );
}
