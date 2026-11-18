import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, upload } from "../../api/client";
import { ASSET_TYPES, ENVIRONMENTS, type Asset, type Contact, type EngagementRow, type Organisation, type Page } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, EngagementStatus, ErrorNote, ErrorState, NotFoundOrError, Field, fieldError, formatDay, label,
  LoadingRows, Modal, TabPanel, Tabs, TextInput,
} from "../../design/ui";
import { AssetEditor } from "../assets/AssetEditor";
import { OnboardingBadge } from "../assets/AssetsPage";
import { OrgAvatar, OrganisationForm } from "./OrganisationsPage";

type Tab = "assets" | "contacts" | "engagements";

const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);

export function OrganisationPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("assets");
  const [editing, setEditing] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const q = useQuery({ queryKey: ["organisation", id], queryFn: () => api<Organisation>("GET", `/organisations/${id}`) });
  const org = q.data;
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["organisation", id] }); void qc.invalidateQueries({ queryKey: ["organisations"] }); };

  const archive = useMutation({
    mutationFn: () => api<Organisation>("POST", `/organisations/${id}/${org?.archived ? "unarchive" : "archive"}`),
    onSuccess: () => { refresh(); setConfirmArchive(false); },
  });
  const setLogo = useMutation({ mutationFn: (f: File) => upload("POST", `/organisations/${id}/logo`, f), onSuccess: refresh });
  const removeLogo = useMutation({ mutationFn: () => api("DELETE", `/organisations/${id}/logo`), onSuccess: refresh });

  if (q.isPending) return <LoadingRows rows={4} />;
  if (q.isError) {
    return (
      <>
        <BackLink />
        <div className="card"><NotFoundOrError error={q.error} what="Organisation" onRetry={() => void q.refetch()} /></div>
      </>
    );
  }
  const o = q.data!;
  const canEdit = can("organisations.update") && !o.archived;
  const logoError = setLogo.error ?? removeLogo.error;

  return (
    <>
      <BackLink />
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <OrgAvatar org={o} size={64} />
          <div className="min-w-0">
            <h1 className="text-[32px] max-sm:text-[28px]">{o.name}</h1>
            <p className="mt-1 text-muted">{o.industry || "No industry set"}{o.archived && " · Archived"}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {canEdit && <Button onClick={() => setEditing(true)}><Pencil size={18} aria-hidden /> Edit</Button>}
          {can("organisations.archive") && (
            <Button variant={o.archived ? "secondary" : "danger"} onClick={() => { archive.reset(); setConfirmArchive(true); }}>{o.archived ? "Unarchive" : "Archive"}</Button>
          )}
        </div>
      </header>

      {o.archived && <div className="mb-6"><Alert tone="warn">This organisation is archived and read-only. Unarchive it to make changes.</Alert></div>}

      {(o.notes || canEdit) && (
        <section aria-labelledby="org-notes" className="card card-pad mb-6">
          <h2 id="org-notes" className="text-lg">Notes</h2>
          <p className="mt-2 whitespace-pre-wrap text-muted">{o.notes || "No notes yet."}</p>
        </section>
      )}

      {canEdit && (
        <section aria-labelledby="org-logo" className="card card-pad mb-6 space-y-3">
          <h2 id="org-logo" className="text-lg">Logo</h2>
          <ErrorNote error={logoError} />
          <div className="flex flex-wrap items-center gap-3">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="sr-only" aria-label="Choose logo image"
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) { removeLogo.reset(); setLogo.mutate(f); } }} />
            <Button loading={setLogo.isPending} onClick={() => { setLogo.reset(); fileRef.current?.click(); }}>{o.logo_url ? "Replace logo" : "Upload logo"}</Button>
            {o.logo_url && <Button loading={removeLogo.isPending} onClick={() => { setLogo.reset(); removeLogo.mutate(); }}>Remove logo</Button>}
            <span className="text-[13px] text-muted">PNG, JPG, GIF or WebP, up to 25 MB. The image is re-encoded on upload.</span>
          </div>
        </section>
      )}

      <Tabs label="Organisation sections" value={tab} onChange={setTab} tabs={[{ id: "assets", label: "Assets" }, { id: "contacts", label: "Contacts" }, { id: "engagements", label: "Engagements" }]} />
      <TabPanel id={tab}>
        {tab === "assets" && <AssetsTab org={o} />}
        {tab === "contacts" && <ContactsTab org={o} />}
        {tab === "engagements" && <EngagementsTab org={o} />}
      </TabPanel>

      {editing && <OrganisationForm key={o.updated_at} open org={o} onClose={() => setEditing(false)} />}
      <ConfirmDialog
        open={confirmArchive}
        title={o.archived ? "Unarchive organisation" : "Archive organisation"}
        body={o.archived ? `${o.name} becomes editable again.` : `${o.name} becomes read-only and drops out of default lists. Nothing is deleted.`}
        confirmLabel={o.archived ? "Unarchive" : "Archive"}
        danger={!o.archived}
        busy={archive.isPending}
        error={archive.error}
        onConfirm={() => archive.mutate()}
        onClose={() => setConfirmArchive(false)}
      />
    </>
  );
}

function BackLink() {
  return <Link to="/organisations" className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink"><ArrowLeft size={18} aria-hidden /> Organisations</Link>;
}

/* Assets */

function AssetsTab({ org }: { org: Organisation }) {
  const { can } = useAuth();
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Asset | "new" | null>(null);
  const [toggling, setToggling] = useState<Asset | null>(null);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["org-assets", org.id, archived], queryFn: () => api<Asset[]>("GET", `/organisations/${org.id}/assets?archived=${archived ? "all" : "false"}`) });
  const toggle = useMutation({
    mutationFn: (a: Asset) => api("POST", `/assets/${a.id}/${a.archived ? "unarchive" : "archive"}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["org-assets", org.id] }); setToggling(null); },
  });
  const writable = !org.archived;

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <label className="flex min-h-11 items-center gap-2 text-[15px]"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Show archived</label>
        {can("assets.create") && writable && <Button variant="primary" onClick={() => setEditing("new")}><Plus size={18} aria-hidden /> New asset</Button>}
      </div>
      {q.isPending && <LoadingRows />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title="No assets" body="Assets are the systems, apps and networks you can put in an engagement's scope." />}
      {q.data && q.data.length > 0 && (
        <>
          <table className="data-table hidden md:table">
            <thead><tr><th>Asset</th><th>Type</th><th>Environment</th><th>Criticality</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {q.data.map((a) => (
                <tr key={a.id}>
                  <td><span className="block font-medium">{a.name}{a.archived && <span className="ml-2 text-[13px] font-normal text-muted">Archived</span>}</span><span className="block break-all text-[14px] text-muted">{a.identifiers.length ? a.identifiers.map((i) => i.value).join(", ") : "No identifier"}</span>{a.onboarding_status === "pending" && <OnboardingBadge a={a} />}</td>
                  <td>{label(ASSET_TYPES, a.type)}</td>
                  <td>{label(ENVIRONMENTS, a.environment)}</td>
                  <td><Criticality n={a.criticality} /></td>
                  <td className="text-right">{writable && <AssetActions a={a} onEdit={() => setEditing(a)} onToggle={() => { toggle.reset(); setToggling(a); }} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
            {q.data.map((a) => (
              <li key={a.id} className="space-y-2 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><p className="m-0 font-medium">{a.name}{a.archived && <span className="ml-2 text-[13px] font-normal text-muted">Archived</span>}</p><p className="m-0 break-all text-[14px] text-muted">{a.identifiers.length ? a.identifiers.map((i) => i.value).join(", ") : "No identifier"}</p></div>
                  <Criticality n={a.criticality} />
                </div>
                <p className="m-0 text-[14px] text-muted">{label(ASSET_TYPES, a.type)} · {label(ENVIRONMENTS, a.environment)}</p>
                {writable && <AssetActions a={a} onEdit={() => setEditing(a)} onToggle={() => { toggle.reset(); setToggling(a); }} />}
              </li>
            ))}
          </ul>
        </>
      )}
      {editing && <AssetEditor key={editing === "new" ? "new" : editing.id} org={{ id: org.id, name: org.name }} asset={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!toggling}
        title={toggling?.archived ? "Unarchive asset" : "Archive asset"}
        body={toggling?.archived ? `${toggling.name} becomes available for new engagements again.` : `${toggling?.name} can no longer be added to engagements. Existing links stay.`}
        confirmLabel={toggling?.archived ? "Unarchive" : "Archive"}
        danger={!toggling?.archived}
        busy={toggle.isPending}
        error={toggle.error}
        onConfirm={() => toggling && toggle.mutate(toggling)}
        onClose={() => setToggling(null)}
      />
    </div>
  );
}

function Criticality({ n }: { n: number }) {
  return <Badge tone={n >= 4 ? "fail" : n === 3 ? "warn" : "info"}>{n} of 5</Badge>;
}

function AssetActions({ a, onEdit, onToggle }: { a: Asset; onEdit: () => void; onToggle: () => void }) {
  const { can } = useAuth();
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {can("assets.update") && !a.archived && <Button size="sm" onClick={onEdit}>Edit</Button>}
      {can("assets.archive") && <Button size="sm" onClick={onToggle}>{a.archived ? "Unarchive" : "Archive"}</Button>}
    </div>
  );
}

/* Contacts */

function ContactsTab({ org }: { org: Organisation }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Contact | "new" | null>(null);
  const [removing, setRemoving] = useState<Contact | null>(null);
  const q = useQuery({ queryKey: ["org-contacts", org.id], queryFn: () => api<Contact[]>("GET", `/organisations/${org.id}/contacts`) });
  const remove = useMutation({
    mutationFn: (c: Contact) => api("DELETE", `/contacts/${c.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["org-contacts", org.id] }); setRemoving(null); },
  });
  const writable = can("organisations.update") && !org.archived;
  return (
    <div className="card overflow-hidden">
      {writable && <div className="flex justify-end border-b border-line p-4"><Button variant="primary" onClick={() => setEditing("new")}><Plus size={18} aria-hidden /> New contact</Button></div>}
      {q.isPending && <LoadingRows rows={3} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title="No contacts" body="Add the people at this organisation who receive reports or approve testing." />}
      {q.data && q.data.length > 0 && (
        <ul className="m-0 list-none divide-y divide-line p-0">
          {q.data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <p className="m-0 font-medium">{c.name}{c.is_primary && <span className="ml-2"><Badge tone="info">Primary</Badge></span>}</p>
                <p className="m-0 break-all text-[14px] text-muted">{[c.title, c.email, c.phone].filter(Boolean).join(" · ") || "No details"}</p>
              </div>
              {writable && (
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => setEditing(c)}>Edit</Button>
                  <Button size="sm" variant="danger" aria-label={`Remove ${c.name}`} onClick={() => { remove.reset(); setRemoving(c); }}><Trash2 size={16} aria-hidden /></Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {editing && <ContactForm key={editing === "new" ? "new" : editing.id} org={org} contact={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={!!removing} title="Remove contact" body={`${removing?.name} is removed from this organisation. Personal details are deleted.`} confirmLabel="Remove" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </div>
  );
}

function ContactForm({ org, contact, onClose }: { org: Organisation; contact?: Contact; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ name: contact?.name ?? "", title: contact?.title ?? "", email: contact?.email ?? "", phone: contact?.phone ?? "", is_primary: contact?.is_primary ?? false });
  const save = useMutation({
    mutationFn: () => (contact ? api("PATCH", `/contacts/${contact.id}`, f) : api("POST", "/contacts", { ...f, organisation: org.id })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["org-contacts", org.id] }); onClose(); },
  });
  const set = (k: "name" | "title" | "email" | "phone") => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open onClose={onClose} title={contact ? "Edit contact" : "New contact"}>
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        <Field label="Name" error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required autoFocus maxLength={120} value={f.name} onChange={set("name")} />}</Field>
        <Field label="Job title" error={fieldError(save.error, "title")}>{(p) => <TextInput {...p} maxLength={120} value={f.title} onChange={set("title")} />}</Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Email" error={fieldError(save.error, "email")}>{(p) => <TextInput {...p} type="email" value={f.email} onChange={set("email")} />}</Field>
          <Field label="Phone" error={fieldError(save.error, "phone")}>{(p) => <TextInput {...p} type="tel" maxLength={40} value={f.phone} onChange={set("phone")} />}</Field>
        </div>
        <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={f.is_primary} onChange={(e) => setF({ ...f, is_primary: e.target.checked })} /> Primary contact</label>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!f.name.trim()}>{contact ? "Save changes" : "Add contact"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/* Engagements of this organisation */

function EngagementsTab({ org }: { org: Organisation }) {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["org-engagements", org.id], queryFn: () => api<Page<EngagementRow>>("GET", `/engagements?organisation=${org.id}&archived=all&page_size=100`) });
  return (
    <div className="card overflow-hidden">
      {q.isPending && <LoadingRows rows={3} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.results.length === 0 && <EmptyState title="No engagements you can see" body="Engagements for this organisation that you are assigned to appear here." />}
      {q.data && q.data.results.length > 0 && (
        <ul className="m-0 list-none divide-y divide-line p-0">
          {q.data.results.map((e) => (
            <li key={e.id}>
              <button type="button" onClick={() => nav(`/engagements/${e.id}`)} className="flex min-h-[72px] w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left hover:bg-raised">
                <span className="min-w-0"><span className="block truncate font-medium">{e.name}</span><span className="block text-[14px] text-muted"><span className="mono">{e.ref}</span> · {formatDay(e.start_date)} to {formatDay(e.end_date)}</span></span>
                <EngagementStatus status={e.status} archived={!!e.archived_at} overdue={e.overdue} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
