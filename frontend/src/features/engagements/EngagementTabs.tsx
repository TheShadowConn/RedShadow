import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Plus, Trash2, UploadCloud } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api, upload } from "../../api/client";
import {
  ASSET_TYPES, ENVIRONMENTS, type Asset, type Doc, type Engagement, type HistoryEvent, type Member, type Note, type Page, type Role,
  type ScopeLink, type User,
} from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, fieldError, formatBytes, formatDate, label,
  LoadingRows, Modal, Pager, Select, Textarea,
} from "../../design/ui";

const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);
const ReadOnlyNote = () => <Alert tone="warn">This engagement is archived. It is read-only.</Alert>;

/* Scope and assets */

export function ScopeTab({ eng }: { eng: Engagement }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [linking, setLinking] = useState(false);
  const [removing, setRemoving] = useState<ScopeLink | null>(null);
  const q = useQuery({ queryKey: ["eng-assets", eng.id], queryFn: () => api<ScopeLink[]>("GET", `/engagements/${eng.id}/assets`) });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["eng-assets", eng.id] }); void qc.invalidateQueries({ queryKey: ["history", eng.id] }); };
  const toggle = useMutation({ mutationFn: (l: ScopeLink) => api("PATCH", `/engagements/${eng.id}/assets/${l.id}`, { in_scope: !l.in_scope }), onSuccess: refresh });
  const unlink = useMutation({ mutationFn: (l: ScopeLink) => api("DELETE", `/engagements/${eng.id}/assets/${l.id}`), onSuccess: () => { refresh(); setRemoving(null); } });
  const writable = can("engagements.update") && !eng.archived_at;

  return (
    <div className="space-y-4">
      {eng.archived_at && <ReadOnlyNote />}
      <ErrorNote error={toggle.error} />
      <div className="card overflow-hidden">
        {writable && <div className="flex justify-end border-b border-line p-4"><Button variant="primary" onClick={() => setLinking(true)}><Plus size={18} aria-hidden /> Add asset</Button></div>}
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.length === 0 && <EmptyState title="No assets in scope" body="Link assets from this organisation to define what is being tested." />}
        {q.data && q.data.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="m-0 font-medium">{l.asset.name} <Badge tone={l.in_scope ? "ok" : "fail"}>{l.in_scope ? "In scope" : "Out of scope"}</Badge></p>
                  <p className="m-0 break-all text-[14px] text-muted">{label(ASSET_TYPES, l.asset.type)} · {label(ENVIRONMENTS, l.asset.environment)}</p>
                  {l.asset.identifiers.length > 0 && <p className="m-0 mt-1 flex flex-wrap gap-x-3 gap-y-1">{l.asset.identifiers.map((v) => <span key={v} className="mono break-all text-[13px] text-muted">{v}</span>)}</p>}
                </div>
                {writable && (
                  <div className="flex gap-2">
                    <Button size="sm" loading={toggle.isPending && toggle.variables?.id === l.id} onClick={() => toggle.mutate(l)}>{l.in_scope ? "Mark out of scope" : "Mark in scope"}</Button>
                    <Button size="sm" variant="danger" aria-label={`Remove ${l.asset.name}`} onClick={() => { unlink.reset(); setRemoving(l); }}><Trash2 size={16} aria-hidden /></Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {linking && <LinkAsset eng={eng} linked={new Set(q.data?.map((l) => l.asset.id))} onClose={() => setLinking(false)} onDone={refresh} />}
      <ConfirmDialog open={!!removing} title="Remove asset from scope" body={`${removing?.asset.name} is unlinked from this engagement. The asset itself is kept.`} confirmLabel="Remove" danger busy={unlink.isPending} error={unlink.error} onConfirm={() => removing && unlink.mutate(removing)} onClose={() => setRemoving(null)} />
    </div>
  );
}

function LinkAsset({ eng, linked, onClose, onDone }: { eng: Engagement; linked: Set<string>; onClose: () => void; onDone: () => void }) {
  const [assetId, setAssetId] = useState("");
  const [inScope, setInScope] = useState(true);
  const [notes, setNotes] = useState("");
  const assets = useQuery({ queryKey: ["org-assets", eng.organisation.id, false], queryFn: () => api<Asset[]>("GET", `/organisations/${eng.organisation.id}/assets?archived=false`) });
  const save = useMutation({ mutationFn: () => api("POST", `/engagements/${eng.id}/assets`, { asset: assetId, in_scope: inScope, notes }), onSuccess: () => { onDone(); onClose(); } });
  const options = assets.data?.filter((a) => !linked.has(a.id) && a.onboarding_status === "onboarded") ?? [];
  const waiting = assets.data?.filter((a) => a.onboarding_status === "pending").length ?? 0;
  return (
    <Modal open onClose={onClose} title="Add asset to scope">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        <ErrorNote error={assets.error} />
        <Field label="Asset" error={fieldError(save.error, "asset")} hint={assets.data && options.length === 0 ? "Every onboarded asset of this organisation is already linked." : waiting > 0 ? `${waiting} imported asset${waiting === 1 ? " is" : "s are"} not onboarded yet and cannot be added until onboarded.` : undefined}>
          {(p) => <Select {...p} required value={assetId} onChange={(e) => setAssetId(e.target.value)}><option value="" disabled>Choose an asset</option>{options.map((a) => <option key={a.id} value={a.id}>{a.name} ({label(ASSET_TYPES, a.type)})</option>)}</Select>}
        </Field>
        <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={inScope} onChange={(e) => setInScope(e.target.checked)} /> In scope (untick to record it as explicitly out of scope)</label>
        <Field label="Notes" hint="Optional" error={fieldError(save.error, "notes")}>{(p) => <Textarea {...p} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!assetId}>Add asset</Button></div>
      </form>
    </Modal>
  );
}

/* Team */

export function TeamTab({ eng }: { eng: Engagement }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Member | null>(null);
  const q = useQuery({ queryKey: ["eng-members", eng.id], queryFn: () => api<Member[]>("GET", `/engagements/${eng.id}/members`) });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["eng-members", eng.id] }); void qc.invalidateQueries({ queryKey: ["history", eng.id] }); };
  const remove = useMutation({ mutationFn: (m: Member) => api("DELETE", `/engagements/${eng.id}/members/${m.user.id}`), onSuccess: () => { refresh(); setRemoving(null); } });
  const writable = eng.permissions.includes("engagements.manage_members") && !eng.archived_at;

  return (
    <div className="space-y-4">
      {eng.archived_at && <ReadOnlyNote />}
      <div className="card overflow-hidden">
        {writable && <div className="flex justify-end border-b border-line p-4"><Button variant="primary" onClick={() => setAdding(true)}><Plus size={18} aria-hidden /> Add member</Button></div>}
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.length === 0 && <EmptyState title="No team members" body="Only members and users who can see every engagement can open this engagement." />}
        {q.data && q.data.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="m-0 font-medium">{m.user.display_name}{eng.lead?.id === m.user.id && <span className="ml-2"><Badge tone="info">Lead</Badge></span>}</p>
                  <p className="m-0 break-all text-[14px] text-muted">{m.user.email} · {m.role.name}{m.role_override ? " (override)" : ""}{m.finding_scope && ` · findings: ${m.finding_scope}`}</p>
                </div>
                {writable && <Button size="sm" variant="danger" onClick={() => { remove.reset(); setRemoving(m); }}>Remove</Button>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {adding && <AddMember eng={eng} existing={new Set(q.data?.map((m) => m.user.id))} onClose={() => setAdding(false)} onDone={refresh} />}
      <ConfirmDialog open={!!removing} title="Remove member" body={`${removing?.user.display_name} loses access to this engagement immediately.`} confirmLabel="Remove" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </div>
  );
}

function AddMember({ eng, existing, onClose, onDone }: { eng: Engagement; existing: Set<string>; onClose: () => void; onDone: () => void }) {
  const { can } = useAuth();
  const [userId, setUserId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [scope, setScope] = useState("");
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => api<Page<User>>("GET", "/users?page_size=100&search="), enabled: can("users.view") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("GET", "/roles"), enabled: can("roles.view") });
  const save = useMutation({
    mutationFn: () => api("POST", `/engagements/${eng.id}/members`, { user: userId, role_override: roleId || null, finding_scope: scope }),
    onSuccess: () => { onDone(); onClose(); },
  });
  const candidates = users.data?.results.filter((u) => u.is_active && !existing.has(u.id)) ?? [];
  return (
    <Modal open onClose={onClose} title="Add team member">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        {!can("users.view") && <Alert tone="warn">You need permission to view users to pick a member.</Alert>}
        <Field label="User" error={fieldError(save.error, "user")}>
          {(p) => <Select {...p} required value={userId} onChange={(e) => setUserId(e.target.value)}><option value="" disabled>Choose a user</option>{candidates.map((u) => <option key={u.id} value={u.id}>{u.display_name} ({u.role.name})</option>)}</Select>}
        </Field>
        {can("roles.view") && (
          <Field label="Role on this engagement" hint="Leave on default to use the user's own role. You cannot grant more than you hold." error={fieldError(save.error, "role_override")}>
            {(p) => <Select {...p} value={roleId} onChange={(e) => setRoleId(e.target.value)}><option value="">Use the user's role</option>{roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select>}
          </Field>
        )}
        <Field label="Finding access" error={fieldError(save.error, "finding_scope")}>
          {(p) => <Select {...p} value={scope} onChange={(e) => setScope(e.target.value)}><option value="">Use the role's default</option><option value="all">All findings</option><option value="assigned">Assigned findings only</option><option value="own">Own findings only</option></Select>}
        </Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!userId}>Add member</Button></div>
      </form>
    </Modal>
  );
}

/* Notes */

export function NotesPanel({ eng }: { eng: Engagement }) {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<"team" | "all">("team");
  const q = useQuery({ queryKey: ["eng-notes", eng.id, page], queryFn: () => api<Page<Note>>("GET", `/engagements/${eng.id}/notes?page=${page}`), placeholderData: (p) => p });
  const add = useMutation({
    mutationFn: () => api("POST", `/engagements/${eng.id}/notes`, { body, visibility }),
    onSuccess: () => { setBody(""); setPage(1); void qc.invalidateQueries({ queryKey: ["eng-notes", eng.id] }); void qc.invalidateQueries({ queryKey: ["history", eng.id] }); },
  });
  const canAdd = eng.permissions.includes("engagement_notes.create") && !eng.archived_at;
  return (
    <section aria-labelledby="notes-h" className="space-y-4">
      <h2 id="notes-h" className="text-xl">Notes</h2>
      {canAdd && (
        <form className="card card-pad space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }}>
          <ErrorNote error={add.error} />
          <Field label="Add a note" error={fieldError(add.error, "body")}>{(p) => <Textarea {...p} rows={3} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} />}</Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Select aria-label="Who can read this note" className="max-w-xs" value={visibility} onChange={(e) => setVisibility(e.target.value as "team" | "all")}>
              <option value="team">Testing team only</option>
              <option value="all">Everyone on the engagement</option>
            </Select>
            <Button type="submit" variant="primary" loading={add.isPending} disabled={!body.trim()}>Add note</Button>
          </div>
        </form>
      )}
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title="No notes yet" body="Notes record decisions and observations for this engagement." />}
        {q.data && q.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((n) => (
              <li key={n.id} className="space-y-1.5 p-4">
                <p className="m-0 flex flex-wrap items-center gap-2 text-[14px] text-muted"><span className="font-medium text-ink">{n.author.display_name}</span>{formatDate(n.created_at)}<Badge tone="info">{n.visibility === "team" ? "Team only" : "Everyone"}</Badge></p>
                <p className="m-0 whitespace-pre-wrap">{n.body}</p>
              </li>
            ))}
          </ul>
        )}
        {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
      </div>
    </section>
  );
}

/* Documents */

const MAX_BYTES = 25 * 1024 * 1024;

export function DocumentsPanel({ eng }: { eng: Engagement }) {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [progress, setProgress] = useState<number | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Doc | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ["eng-docs", eng.id, page], queryFn: () => api<Page<Doc>>("GET", `/engagements/${eng.id}/documents?page=${page}`), placeholderData: (p) => p });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["eng-docs", eng.id] }); void qc.invalidateQueries({ queryKey: ["history", eng.id] }); };
  const send = useMutation({
    mutationFn: (f: File) => upload("POST", `/engagements/${eng.id}/documents`, f, setProgress),
    onSuccess: () => { setPage(1); refresh(); },
    onSettled: () => setProgress(null),
  });
  const remove = useMutation({ mutationFn: (d: Doc) => api("DELETE", `/attachments/${d.id}`), onSuccess: () => { refresh(); setRemoving(null); } });
  const canUpload = eng.permissions.includes("documents.upload") && !eng.archived_at;
  const canDelete = eng.permissions.includes("documents.delete") && !eng.archived_at;

  function pick(file: File | undefined) {
    if (!file) return;
    send.reset();
    if (file.size === 0) return setClientError("That file is empty.");
    if (file.size > MAX_BYTES) return setClientError(`${file.name} is ${formatBytes(file.size)}. The limit is 25 MB.`);
    setClientError(null);
    send.mutate(file);
  }
  function onDrop(e: DragEvent) { e.preventDefault(); setOver(false); if (canUpload && progress === null) pick(e.dataTransfer.files[0]); }

  return (
    <section aria-labelledby="docs-h" className="space-y-4">
      <h2 id="docs-h" className="text-xl">Documents</h2>
      {canUpload && (
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          className={`card card-pad flex flex-col items-center gap-3 border-dashed text-center ${over ? "bg-raised" : ""}`}
        >
          <UploadCloud size={28} className="text-muted" aria-hidden />
          <p className="m-0">Drop a file here, or choose one.</p>
          <input ref={input} type="file" className="sr-only" aria-label="Choose document to upload" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          <Button variant="primary" loading={progress !== null} onClick={() => input.current?.click()}>Choose file</Button>
          <p className="m-0 text-[13px] text-muted">Images, PDF, text, log, CSV, JSON, XML, ZIP, PCAP, DOCX or XLSX up to 25 MB. HTML and SVG are refused.</p>
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
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <EmptyState title="No documents" body="Rules of engagement, scoping sheets and other files for this engagement appear here." />}
        {q.data && q.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <FileText size={22} className="flex-none text-muted" aria-hidden />
                  <div className="min-w-0">
                    <p className="m-0 break-all font-medium">{d.original_name}</p>
                    <p className="m-0 text-[14px] text-muted">{formatBytes(d.size)} · {d.uploaded_by.display_name} · {formatDate(d.created_at)}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <a href={d.download_url} download={d.original_name} className="btn btn-secondary btn-sm"><Download size={16} aria-hidden /> Download</a>
                  {canDelete && <Button size="sm" variant="danger" aria-label={`Delete ${d.original_name}`} onClick={() => { remove.reset(); setRemoving(d); }}><Trash2 size={16} aria-hidden /></Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
      </div>
      <ConfirmDialog open={!!removing} title="Delete document" body={`${removing?.original_name} is removed now and permanently purged after 30 days.`} confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </section>
  );
}

/* History */

export function describe(changes: Record<string, unknown>): string[] {
  return Object.entries(changes ?? {}).map(([k, v]) => {
    const name = k.replace(/_/g, " ");
    return Array.isArray(v) && v.length === 2 ? `${name}: ${show(v[0])} → ${show(v[1])}` : `${name}: ${show(v)}`;
  });
}
const show = (v: unknown) => (v === null || v === undefined || v === "" ? "empty" : typeof v === "string" ? (v.length > 80 ? `${v.slice(0, 80)}…` : v) : JSON.stringify(v));

export function HistoryTab({ eng }: { eng: Engagement }) {
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["history", eng.id, page], queryFn: () => api<Page<HistoryEvent>>("GET", `/engagements/${eng.id}/history?page=${page}`), placeholderData: (p) => p });
  return (
    <div className="card overflow-hidden">
      {q.isPending && <LoadingRows />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.results.length === 0 && <EmptyState title="No history yet" body="Every change to this engagement is recorded here." />}
      {q.data && q.data.results.length > 0 && (
        <ol className="m-0 list-none divide-y divide-line p-0">
          {q.data.results.map((ev) => (
            <li key={ev.id} className="space-y-1 p-4">
              <p className="m-0 flex flex-wrap items-center gap-2"><span className="mono text-[14px]">{ev.action}</span>{ev.outcome !== "success" && <Badge tone="fail">{ev.outcome}</Badge>}</p>
              <p className="m-0 text-[14px] text-muted">{ev.actor_label} · {formatDate(ev.occurred_at)}{ev.entity_label && ` · ${ev.entity_label}`}</p>
              {describe(ev.changes).map((line) => <p key={line} className="m-0 break-words text-[14px]">{line}</p>)}
            </li>
          ))}
        </ol>
      )}
      {q.data && <Pager page={page} count={q.data.count} size={50} onPage={setPage} />}
    </div>
  );
}
