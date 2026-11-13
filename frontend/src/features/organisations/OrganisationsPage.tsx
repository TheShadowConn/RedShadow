import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ChevronRight, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import type { Organisation, Page } from "../../api/types";
import {
  Button, EmptyState, ErrorNote, ErrorState, Field, fieldError, LoadingRows, Modal, PageHeader, Select, Textarea, TextInput,
} from "../../design/ui";

export function OrgAvatar({ org, size = 40 }: { org: Pick<Organisation, "name" | "logo_url">; size?: number }) {
  return org.logo_url ? (
    <img src={org.logo_url} alt="" width={size} height={size} className="flex-none rounded-md border border-line bg-surface object-contain" style={{ width: size, height: size }} />
  ) : (
    <span aria-hidden className="grid flex-none place-items-center rounded-md border border-line bg-raised text-muted" style={{ width: size, height: size }}>
      <Building2 size={size * 0.5} />
    </span>
  );
}

export function OrganisationsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState("false");
  const [creating, setCreating] = useState(false);

  const orgs = useQuery({
    queryKey: ["organisations", search, archived],
    queryFn: () => api<Page<Organisation>>("GET", `/organisations?page_size=100&archived=${archived}&search=${encodeURIComponent(search)}`),
  });

  return (
    <>
      <PageHeader
        title="Organisations"
        lead="The clients and business units you test. Organisations are archived, never deleted, so engagement history stays intact."
        actions={can("organisations.create") && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} aria-hidden /> New organisation</Button>}
      />
      <div className="card overflow-hidden">
        <div className="flex flex-wrap gap-3 border-b border-line p-4">
          <div className="relative min-w-[220px] max-w-md flex-1">
            <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput aria-label="Search organisations" placeholder="Search by name or industry" className="pl-11" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="w-44">
            <Select aria-label="Show" value={archived} onChange={(e) => setArchived(e.target.value)}>
              <option value="false">Active</option>
              <option value="true">Archived</option>
              <option value="all">All</option>
            </Select>
          </div>
        </div>
        {orgs.isPending && <LoadingRows />}
        {orgs.isError && <ErrorState error={orgs.error} onRetry={() => void orgs.refetch()} />}
        {orgs.data && orgs.data.results.length === 0 && (
          <EmptyState
            title={search ? "No organisations match" : archived === "true" ? "Nothing archived" : "No organisations yet"}
            body={search ? "Try a different name or industry." : can("organisations.create") ? "Add the first client organisation to start planning engagements." : "Organisations appear here once you are added to an engagement."}
            action={!search && can("organisations.create") && archived !== "true" ? <Button variant="primary" onClick={() => setCreating(true)}>New organisation</Button> : undefined}
          />
        )}
        {orgs.data && orgs.data.results.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {orgs.data.results.map((o) => (
              <li key={o.id}>
                <button type="button" onClick={() => nav(`/organisations/${o.id}`)} className="flex min-h-[72px] w-full items-center gap-4 px-4 py-3 text-left hover:bg-raised">
                  <OrgAvatar org={o} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{o.name}{o.archived && <span className="ml-2 text-[13px] font-normal text-muted">Archived</span>}</span>
                    <span className="block truncate text-[14px] text-muted">{o.industry || "No industry set"}</span>
                  </span>
                  <ChevronRight size={18} className="flex-none text-muted" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <OrganisationForm open={creating} onClose={() => setCreating(false)} onSaved={(o) => nav(`/organisations/${o.id}`)} />
    </>
  );
}

export function OrganisationForm({ open, onClose, org, onSaved }: { open: boolean; onClose: () => void; org?: Organisation; onSaved?: (o: Organisation) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(org?.name ?? "");
  const [industry, setIndustry] = useState(org?.industry ?? "");
  const [notes, setNotes] = useState(org?.notes ?? "");
  const save = useMutation({
    mutationFn: () => api<Organisation>(org ? "PATCH" : "POST", org ? `/organisations/${org.id}` : "/organisations", { name, industry, notes }),
    onSuccess: (o) => {
      void qc.invalidateQueries({ queryKey: ["organisations"] });
      void qc.invalidateQueries({ queryKey: ["organisation", o.id] });
      close();
      onSaved?.(o);
    },
  });
  function close() { save.reset(); onClose(); }
  const general = save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null;
  return (
    <Modal open={open} onClose={close} title={org ? "Edit organisation" : "New organisation"}>
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={general} />
        <Field label="Name" error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required autoFocus maxLength={160} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Industry" hint="Optional" error={fieldError(save.error, "industry")}>{(p) => <TextInput {...p} maxLength={80} value={industry} onChange={(e) => setIndustry(e.target.value)} />}</Field>
        <Field label="Notes" hint="Visible to anyone who can see this organisation." error={fieldError(save.error, "notes")}>{(p) => <Textarea {...p} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!name.trim()}>{org ? "Save changes" : "Create organisation"}</Button>
        </div>
      </form>
    </Modal>
  );
}
