import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { ENGAGEMENT_TYPES, STATUSES, type Engagement, type EngagementRow, type Organisation, type Page, type User } from "../../api/types";
import {
  Button, EmptyState, EngagementStatus, ErrorNote, ErrorState, Field, fieldError, formatDay, label, LoadingRows, Modal, PageHeader,
  Pager, Select, TextInput,
} from "../../design/ui";
import { ScenarioProgress } from "./ScenariosTab";
import { MarkdownField } from "./MarkdownField";

const PAGE_SIZE = 25;

export function EngagementsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ search: "", status: "", type: "", organisation: "", archived: "false", overdue: false });
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const update = (patch: Partial<typeof f>) => { setF({ ...f, ...patch }); setPage(1); };

  const orgs = useQuery({ queryKey: ["organisations", "", "false"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100&archived=false"), enabled: can("organisations.view") });
  const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE), archived: f.archived, search: f.search });
  if (f.status) qs.set("status", f.status);
  if (f.type) qs.set("type", f.type);
  if (f.organisation) qs.set("organisation", f.organisation);
  if (f.overdue) qs.set("overdue", "true");
  const deletedView = f.archived === "deleted";
  if (deletedView) { qs.delete("archived"); qs.set("deleted", "true"); }
  const qc = useQueryClient();
  const restore = useMutation({ mutationFn: (id: string) => api("POST", `/engagements/${id}/restore`, {}), onSuccess: () => void qc.invalidateQueries({ queryKey: ["engagements"] }) });
  const list = useQuery({ queryKey: ["engagements", qs.toString()], queryFn: () => api<Page<EngagementRow>>("GET", `/engagements?${qs}`), placeholderData: (p) => p });
  const filtered = !!(f.search || f.status || f.type || f.organisation || f.overdue);

  return (
    <>
      <PageHeader
        title="Engagements"
        lead="Penetration tests you are assigned to. Each one has its own scope, team, documents and history."
        actions={can("engagements.create") && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} aria-hidden /> New engagement</Button>}
      />
      <div className="card overflow-hidden">
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-[minmax(220px,1.5fr)_repeat(4,minmax(0,1fr))]">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput aria-label="Search engagements" placeholder="Search engagements" className="pl-11" value={f.search} onChange={(e) => update({ search: e.target.value })} />
          </div>
          <Select aria-label="Status" value={f.status} onChange={(e) => update({ status: e.target.value })}>
            <option value="">All statuses</option>
            {STATUSES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select aria-label="Type" value={f.type} onChange={(e) => update({ type: e.target.value })}>
            <option value="">All types</option>
            {ENGAGEMENT_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          {can("organisations.view") && (
            <Select aria-label="Organisation" value={f.organisation} onChange={(e) => update({ organisation: e.target.value })}>
              <option value="">All organisations</option>
              {orgs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          )}
          <Select aria-label="Show" value={f.archived} onChange={(e) => update({ archived: e.target.value })}>
            <option value="false">Not archived</option>
            <option value="true">Archived</option>
            <option value="all">All</option>
            {can("engagements.delete") && <option value="deleted">Deleted</option>}
          </Select>
          <label className="flex min-h-11 items-center gap-2 text-[15px]"><input type="checkbox" checked={f.overdue} onChange={(e) => update({ overdue: e.target.checked })} /> Overdue only</label>
        </div>

        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && list.data.results.length === 0 && (
          <EmptyState
            title={filtered ? "No engagements match" : "No engagements yet"}
            body={filtered ? "Clear a filter or try a different search." : can("engagements.create") ? "Create the first engagement to get started." : "You will see engagements here once you are assigned to one."}
            action={filtered ? <Button onClick={() => { setF({ search: "", status: "", type: "", organisation: "", archived: "false", overdue: false }); setPage(1); }}>Clear filters</Button> : undefined}
          />
        )}
        {deletedView && <div className="p-4"><ErrorNote error={restore.error} /></div>}
        {deletedView && list.data && list.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {list.data.results.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <span className="min-w-0"><span className="block font-medium">{e.name}</span><span className="block text-[14px] text-muted"><span className="mono">{e.ref}</span> · {e.organisation.name} · deleted {e.deleted_at ? formatDay(e.deleted_at.slice(0, 10)) : ""}</span></span>
                <Button loading={restore.isPending && restore.variables === e.id} onClick={() => restore.mutate(e.id)}>Restore</Button>
              </li>
            ))}
          </ul>
        )}
        {!deletedView && list.data && list.data.results.length > 0 && (
          <>
            <table className="data-table hidden lg:table">
              <thead><tr><th>Engagement</th><th>Organisation</th><th>Type</th><th>Dates</th><th>Lead</th><th>Progress</th><th>Status</th><th><span className="sr-only">Open</span></th></tr></thead>
              <tbody>
                {list.data.results.map((e) => (
                  <tr key={e.id} onClick={() => nav(`/engagements/${e.id}`)}>
                    <td><button type="button" className="text-left" onClick={(ev) => { ev.stopPropagation(); nav(`/engagements/${e.id}`); }}><span className="block font-medium">{e.name}</span><span className="mono block text-[14px] text-muted">{e.ref}</span></button></td>
                    <td>{e.organisation.name}</td>
                    <td>{label(ENGAGEMENT_TYPES, e.type)}</td>
                    <td className="whitespace-nowrap text-muted">{formatDay(e.start_date)} to {formatDay(e.end_date)}</td>
                    <td>{e.lead?.display_name ?? <span className="text-muted">Unassigned</span>}</td>
                    <td><ScenarioProgress s={e.scenarios} compact /></td>
                    <td><EngagementStatus status={e.status} archived={!!e.archived_at} overdue={e.overdue} /></td>
                    <td className="text-muted"><ChevronRight size={18} aria-hidden /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 lg:hidden">
              {list.data.results.map((e) => (
                <li key={e.id}>
                  <button type="button" onClick={() => nav(`/engagements/${e.id}`)} className="block w-full space-y-1.5 px-4 py-3 text-left">
                    <span className="flex items-start justify-between gap-3"><span className="min-w-0 font-medium">{e.name}</span><EngagementStatus status={e.status} archived={!!e.archived_at} overdue={e.overdue} /></span>
                    <span className="block text-[14px] text-muted"><span className="mono">{e.ref}</span> · {e.organisation.name}</span>
                    <span className="block text-[14px] text-muted">{formatDay(e.start_date)} to {formatDay(e.end_date)}</span>
                    {!!e.scenarios?.total && <span className="block pt-1"><ScenarioProgress s={e.scenarios} compact /></span>}
                  </button>
                </li>
              ))}
            </ul>
            <Pager page={page} count={list.data.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>
      {creating && <CreateEngagement onClose={() => setCreating(false)} onCreated={(e) => nav(`/engagements/${e.id}`)} />}
    </>
  );
}

export function EngagementFields({ f, set, error }: { f: Record<string, string>; set: (k: string) => (e: { target: { value: string } }) => void; error: unknown }) {
  return (
    <>
      <Field label="Name" error={fieldError(error, "name")}>{(p) => <TextInput {...p} required maxLength={200} value={f.name} onChange={set("name")} />}</Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Type" error={fieldError(error, "type")}>{(p) => <Select {...p} value={f.type} onChange={set("type")}>{ENGAGEMENT_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
        <span />
        <Field label="Start date" error={fieldError(error, "start_date")}>{(p) => <TextInput {...p} type="date" required value={f.start_date} onChange={set("start_date")} />}</Field>
        <Field label="End date" error={fieldError(error, "end_date")}>{(p) => <TextInput {...p} type="date" required min={f.start_date} value={f.end_date} onChange={set("end_date")} />}</Field>
      </div>
      {(["scope", "out_of_scope", "objectives", "methodology", "rules_of_engagement"] as const).map((k) => (
        <Field key={k} label={{ scope: "In scope", out_of_scope: "Out of scope", objectives: "Objectives", methodology: "Methodology", rules_of_engagement: "Rules of engagement" }[k]} error={fieldError(error, k)}>
          {(p) => <MarkdownField {...p} value={f[k]} onChange={(v) => set(k)({ target: { value: v } })} />}
        </Field>
      ))}
    </>
  );
}

function CreateEngagement({ onClose, onCreated }: { onClose: () => void; onCreated: (e: Engagement) => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState<Record<string, string>>({ organisation: "", name: "", type: "web", start_date: today, end_date: today, scope: "", out_of_scope: "", objectives: "", methodology: "", rules_of_engagement: "", lead: "" });
  const orgs = useQuery({ queryKey: ["organisations", "", "false"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100&archived=false") });
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => api<Page<User>>("GET", "/users?page_size=100&search="), enabled: can("users.view") });
  const save = useMutation({
    mutationFn: () => api<Engagement>("POST", "/engagements", f),
    onSuccess: (e) => { void qc.invalidateQueries({ queryKey: ["engagements"] }); onClose(); onCreated(e); },
  });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const general = save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null;
  return (
    <Modal open wide="form" onClose={onClose} title="New engagement">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={general} />
        <Field label="Organisation" error={fieldError(save.error, "organisation")}>
          {(p) => <Select {...p} required value={f.organisation} onChange={set("organisation")}><option value="" disabled>Choose an organisation</option>{orgs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select>}
        </Field>
        <EngagementFields f={f} set={set} error={save.error} />
        {can("users.view") && (
          <Field label="Lead" hint="Required. The lead is added to the team." error={fieldError(save.error, "lead")}>
            {(p) => <Select {...p} required value={f.lead} onChange={set("lead")}><option value="" disabled>Choose a lead</option>{users.data?.results.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</Select>}
          </Field>
        )}
        <p className="m-0 text-[13px] text-muted">A reference like RS-E-{new Date().getFullYear()}-0001 is assigned automatically.</p>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!f.organisation || !f.name.trim() || !f.lead}>Create engagement</Button>
        </div>
      </form>
    </Modal>
  );
}
