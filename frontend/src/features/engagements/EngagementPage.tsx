import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Copy, Pencil, Trash2, UserCog } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { ApiError, api } from "../../api/client";
import { ENGAGEMENT_TYPES, TRANSITIONS, type Engagement, type Page, type User } from "../../api/types";
import {
  Alert, Button, ConfirmDialog, EngagementStatus, ErrorNote, Field, fieldError, NotFoundOrError, formatDay, label, LoadingRows, Modal, Select, TabPanel, Tabs, Textarea, TextInput,
} from "../../design/ui";
import { FindingsList } from "../findings/FindingsList";
import { EngagementFields } from "./EngagementsPage";
import { ReportsList } from "../reports/ReportsList";
import { CostTab } from "./CostTab";
import { DocumentsPanel, HistoryTab, NotesPanel, ScopeTab, TeamTab } from "./EngagementTabs";

type Tab = "overview" | "scope" | "findings" | "reports" | "team" | "costs" | "notes" | "history";

const STATUS_VERB: Record<string, string> = { planned: "Move back to planned", scheduled: "Mark scheduled", in_progress: "Start testing", reporting: "Move to reporting", completed: "Mark completed", cancelled: "Cancel engagement" };

export function conflictHint(e: unknown): string | null {
  return e instanceof ApiError && e.status === 409 ? "Someone else changed this engagement. Reload to see the latest version, then try again." : null;
}

export function EngagementPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState(false);
  const [moving, setMoving] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [leadOpen, setLeadOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [cloning, setCloning] = useState(false);

  const q = useQuery({ queryKey: ["engagement", id], queryFn: () => api<Engagement>("GET", `/engagements/${id}`) });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["engagement", id] }); void qc.invalidateQueries({ queryKey: ["engagements"] }); void qc.invalidateQueries({ queryKey: ["history", id] }); };
  const e = q.data;

  const move = useMutation({
    mutationFn: (status: string) => api<Engagement>("POST", `/engagements/${id}/status`, { status, version: e!.version }),
    onSuccess: () => { refresh(); setMoving(null); },
    onError: (err) => { if (conflictHint(err)) void qc.invalidateQueries({ queryKey: ["engagement", id] }); },
  });
  const archive = useMutation({
    mutationFn: () => api<Engagement>("POST", `/engagements/${id}/${e!.archived_at ? "unarchive" : "archive"}`, { version: e!.version }),
    onSuccess: () => { refresh(); setArchiving(false); },
    onError: (err) => { if (conflictHint(err)) void qc.invalidateQueries({ queryKey: ["engagement", id] }); },
  });

  if (q.isPending) return <LoadingRows rows={4} />;
  if (q.isError) return <><Back /><div className="card"><NotFoundOrError error={q.error} what="Engagement" onRetry={() => void q.refetch()} /></div></>;
  const eng = q.data!;
  const perms = new Set(eng.permissions);
  const archived = !!eng.archived_at;
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "overview", label: "Overview" },
    ...(perms.has("assets.view") ? [{ id: "scope" as const, label: "Scope and assets" }] : []),
    ...(perms.has("findings.view") ? [{ id: "findings" as const, label: "Findings" }] : []),
    ...(perms.has("reports.view") ? [{ id: "reports" as const, label: "Reports" }] : []),
    { id: "team", label: "Team" },
    ...(can("engagement_costs.view") ? [{ id: "costs" as const, label: "Cost" }] : []),
    ...(perms.has("engagement_notes.view_shared") || perms.has("documents.view") ? [{ id: "notes" as const, label: "Notes and documents" }] : []),
    ...(perms.has("audit.view_engagement") ? [{ id: "history" as const, label: "History" }] : []),
  ];
  const active = tabs.some((t) => t.id === tab) ? tab : "overview";
  const nextStatuses = archived || !perms.has("engagements.update_status") ? [] : TRANSITIONS[eng.status] ?? [];

  return (
    <>
      <Back />
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mono m-0 text-[14px] text-muted">{eng.ref}</p>
          <h1 className="mt-1 text-[32px] max-sm:text-[28px]">{eng.name}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-muted">
            {can("organisations.view") ? <Link to={`/organisations/${eng.organisation.id}`} className="text-accent underline-offset-2 hover:underline">{eng.organisation.name}</Link> : eng.organisation.name}
            <span aria-hidden>·</span>{label(ENGAGEMENT_TYPES, eng.type)}
            <EngagementStatus status={eng.status} archived={archived} overdue={eng.overdue} />
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {can("calendar.view") && !archived && <Link to={`/calendar?engagement=${eng.id}&date=${eng.start_date}`} className="btn btn-secondary">Open in calendar</Link>}
          {nextStatuses.map((s) => <Button key={s} variant={s === "cancelled" ? "danger" : "secondary"} onClick={() => { move.reset(); setMoving(s); }}>{STATUS_VERB[s]}</Button>)}
          {can("engagements.update") && !archived && <Button onClick={() => setEditing(true)}><Pencil size={18} aria-hidden /> Edit</Button>}
          {can("engagements.update") && !archived && <Button onClick={() => setLeadOpen(true)}><UserCog size={18} aria-hidden /> Change lead</Button>}
          {can("engagements.create") && <Button onClick={() => setCloning(true)}><Copy size={18} aria-hidden /> Clone</Button>}
          {can("engagements.archive") && <Button onClick={() => { archive.reset(); setArchiving(true); }}>{archived ? "Unarchive" : "Archive"}</Button>}
          {can("engagements.delete") && <Button variant="danger" onClick={() => setDeleting(true)}><Trash2 size={18} aria-hidden /> Delete</Button>}
        </div>
      </header>
      {archived && <div className="mb-6"><Alert tone="warn">This engagement is archived and read-only. Unarchive it to make changes.</Alert></div>}

      <Tabs label="Engagement sections" value={active} onChange={setTab} tabs={tabs} />
      <TabPanel id={active}>
        {active === "overview" && <Overview eng={eng} />}
        {active === "scope" && <ScopeTab eng={eng} />}
        {active === "findings" && <FindingsList engagement={eng} />}
        {active === "reports" && <ReportsList engagement={eng} canCreate={!archived && (perms.has("reports.generate_pdf") || perms.has("exports.csv"))} />}
        {active === "team" && <TeamTab eng={eng} />}
        {active === "costs" && <CostTab eng={eng} />}
        {active === "notes" && (
          <div className="space-y-8">
            {perms.has("engagement_notes.view_shared") && <NotesPanel eng={eng} />}
            {perms.has("documents.view") && <DocumentsPanel eng={eng} />}
          </div>
        )}
        {active === "history" && <HistoryTab eng={eng} />}
      </TabPanel>

      {leadOpen && <ChangeLead eng={eng} onClose={() => setLeadOpen(false)} onSaved={refresh} />}
      {cloning && <CloneEngagement eng={eng} onClose={() => setCloning(false)} />}
      {deleting && <DeleteEngagement eng={eng} onClose={() => setDeleting(false)} />}
      {editing && <EditEngagement key={eng.version} eng={eng} onClose={() => setEditing(false)} onSaved={refresh} />}
      <ConfirmDialog
        open={!!moving}
        title={moving ? STATUS_VERB[moving] : ""}
        body={moving ? `Status changes from ${eng.status.replace("_", " ")} to ${moving.replace("_", " ")}. The change is recorded in the history.` : ""}
        confirmLabel="Confirm"
        danger={moving === "cancelled"}
        busy={move.isPending}
        error={move.error}
        onConfirm={() => moving && move.mutate(moving)}
        onClose={() => setMoving(null)}
      />
      <ConfirmDialog
        open={archiving}
        title={archived ? "Unarchive engagement" : "Archive engagement"}
        body={archived ? "The engagement returns to its previous status and becomes editable." : "The engagement becomes read-only and drops out of default lists. Nothing is deleted."}
        confirmLabel={archived ? "Unarchive" : "Archive"}
        danger={!archived}
        busy={archive.isPending}
        error={archive.error}
        onConfirm={() => archive.mutate()}
        onClose={() => setArchiving(false)}
      />
    </>
  );
}

function Back() {
  return <Link to="/engagements" className="mb-4 inline-flex min-h-11 items-center gap-2 text-muted hover:text-ink"><ArrowLeft size={18} aria-hidden /> Engagements</Link>;
}

function Overview({ eng }: { eng: Engagement }) {
  const blocks: Array<[string, string]> = [["In scope", eng.scope], ["Out of scope", eng.out_of_scope], ["Objectives", eng.objectives], ["Methodology", eng.methodology], ["Rules of engagement", eng.rules_of_engagement]];
  return (
    <div className="space-y-6">
      <dl className="card card-pad grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        <Fact k="Start" v={formatDay(eng.start_date)} />
        <Fact k="End" v={formatDay(eng.end_date)} />
        <Fact k="Lead" v={eng.lead?.display_name ?? "Unassigned"} />
        <Fact k="Type" v={label(ENGAGEMENT_TYPES, eng.type)} />
      </dl>
      {blocks.map(([title, text]) => (
        <section key={title} className="card card-pad">
          <h2 className="text-lg">{title}</h2>
          <p className="mt-2 whitespace-pre-wrap text-ink">{text || <span className="text-muted">Not written yet.</span>}</p>
        </section>
      ))}
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return <div><dt className="label">{k}</dt><dd className="m-0 mt-0.5">{v}</dd></div>;
}

function ChangeLead({ eng, onClose, onSaved }: { eng: Engagement; onClose: () => void; onSaved: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [lead, setLead] = useState("");
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => api<Page<User>>("GET", "/users?page_size=100&search="), enabled: can("users.view") });
  const save = useMutation({
    mutationFn: () => api<Engagement>("POST", `/engagements/${eng.id}/lead`, { lead, version: eng.version }),
    onSuccess: () => { onSaved(); void qc.invalidateQueries({ queryKey: ["eng-members", eng.id] }); onClose(); },
  });
  const candidates = users.data?.results.filter((u) => u.is_active && u.id !== eng.lead?.id) ?? [];
  const general = save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null;
  return (
    <Modal open onClose={onClose} title="Change lead">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={general} />
        <p className="m-0 text-muted">Current lead: <span className="text-ink">{eng.lead?.display_name ?? "Unassigned"}</span>. The new lead is added to the team. The previous lead stays on the team until removed.</p>
        <Field label="New lead" error={fieldError(save.error, "lead")}>
          {(p) => <Select {...p} required value={lead} onChange={(e) => setLead(e.target.value)}><option value="" disabled>Choose a user</option>{candidates.map((u) => <option key={u.id} value={u.id}>{u.display_name} ({u.role.name})</option>)}</Select>}
        </Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!lead}>Change lead</Button></div>
      </form>
    </Modal>
  );
}

function CloneEngagement({ eng, onClose }: { eng: Engagement; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ name: `${eng.name} (copy)`, start_date: today, end_date: today, lead: eng.lead?.id ?? "" });
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => api<Page<User>>("GET", "/users?page_size=100&search="), enabled: can("users.view") });
  const save = useMutation({
    mutationFn: () => api<Engagement>("POST", `/engagements/${eng.id}/clone`, f),
    onSuccess: (e) => { void qc.invalidateQueries({ queryKey: ["engagements"] }); navigate(`/engagements/${e.id}`); },
  });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const general = save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null;
  return (
    <Modal open onClose={onClose} title="Clone engagement">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={general} />
        <p className="m-0 text-muted">Creates a new Planned engagement with the same organisation, type, scope text, team and in-scope assets. Findings, notes, documents and costs are not copied.</p>
        <Field label="Name" error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required maxLength={200} value={f.name} onChange={set("name")} />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Start date" error={fieldError(save.error, "start_date")}>{(p) => <TextInput {...p} type="date" required value={f.start_date} onChange={set("start_date")} />}</Field>
          <Field label="End date" error={fieldError(save.error, "end_date")}>{(p) => <TextInput {...p} type="date" required value={f.end_date} onChange={set("end_date")} />}</Field>
        </div>
        <Field label="Lead" hint="Required." error={fieldError(save.error, "lead")}>
          {(p) => <Select {...p} required value={f.lead} onChange={set("lead")}><option value="" disabled>Choose a lead</option>{users.data?.results.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</Select>}
        </Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!f.name.trim() || !f.lead}>Clone engagement</Button></div>
      </form>
    </Modal>
  );
}

function DeleteEngagement({ eng, onClose }: { eng: Engagement; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState("");
  const [reason, setReason] = useState("");
  const del = useMutation({
    mutationFn: () => api("POST", `/engagements/${eng.id}/delete`, { version: eng.version, confirm_ref: confirm, reason }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["engagements"] }); navigate("/engagements"); },
  });
  return (
    <Modal open onClose={onClose} title="Delete engagement">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); del.mutate(); }}>
        <Alert tone="error">Deleting removes this engagement, its findings and evidence from every screen for all users. Use Archive to keep it read-only instead. The deletion is recorded in the audit log and cannot be undone from the app.</Alert>
        <ErrorNote error={del.error} />
        <Field label={`Type ${eng.ref} to confirm`} error={fieldError(del.error, "confirm_ref")}>
          {(p) => <TextInput {...p} autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
        </Field>
        <Field label="Reason (optional)" hint="Saved in the audit entry." error={fieldError(del.error, "reason")}>
          {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        <div className="flex flex-wrap justify-end gap-3"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="danger" loading={del.isPending} disabled={confirm.trim() !== eng.ref}>Delete engagement</Button></div>
      </form>
    </Modal>
  );
}

function EditEngagement({ eng, onClose, onSaved }: { eng: Engagement; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Record<string, string>>({ name: eng.name, type: eng.type, start_date: eng.start_date, end_date: eng.end_date, scope: eng.scope, out_of_scope: eng.out_of_scope, objectives: eng.objectives, methodology: eng.methodology, rules_of_engagement: eng.rules_of_engagement });
  const save = useMutation({
    mutationFn: () => api<Engagement>("PATCH", `/engagements/${eng.id}`, { ...f, version: eng.version }),
    onSuccess: () => { onSaved(); onClose(); },
  });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const general = save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null;
  const conflict = save.error instanceof ApiError && save.error.status === 409;
  return (
    <Modal open onClose={onClose} title="Edit engagement">
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        {conflict ? (
          <Alert tone="error">
            <p className="m-0">{conflictHint(save.error)}</p>
            <div className="mt-3"><Button size="sm" onClick={() => { onSaved(); onClose(); }}>Reload latest</Button></div>
          </Alert>
        ) : <ErrorNote error={general} />}
        <EngagementFields f={f} set={set} error={save.error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!f.name.trim() || conflict}>Save changes</Button>
        </div>
      </form>
    </Modal>
  );
}
