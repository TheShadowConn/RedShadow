import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Lock, Plus } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import type { Permission, Role } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, cx, ErrorNote, ErrorState, Field, fieldError, LoadingRows, PageHeader, Select, TextInput,
} from "../../design/ui";

const NEW = "new";

export function RolesPage() {
  const { roleId } = useParams();
  const { can } = useAuth();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("GET", "/roles") });
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Permission[]>("GET", "/permissions"), staleTime: Infinity });

  return (
    <>
      <PageHeader
        title="Roles"
        lead="A role is a set of permissions plus how far it reaches. Changing a role signs out everyone who holds it."
        actions={can("roles.manage") && <Link to={`/roles/${NEW}`} className="btn btn-primary"><Plus size={18} aria-hidden /> New role</Link>}
      />
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className={cx("card h-fit overflow-hidden", roleId && "max-lg:hidden")}>
          {roles.isPending && <LoadingRows rows={4} />}
          {roles.isError && <ErrorState error={roles.error} onRetry={() => void roles.refetch()} />}
          {roles.data && (
            <ul className="m-0 list-none divide-y divide-line p-0">
              {roles.data.map((r) => (
                <li key={r.id}>
                  <Link
                    to={`/roles/${r.id}`}
                    aria-current={roleId === r.id ? "page" : undefined}
                    className="flex min-h-[64px] items-center justify-between gap-3 px-4 py-3 no-underline hover:bg-raised aria-[current=page]:bg-raised aria-[current=page]:shadow-[inset_2px_0_0_var(--color-accent)]"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-ink">{r.name}</span>
                      <span className="block text-[14px] text-muted">{r.user_count} {r.user_count === 1 ? "user" : "users"} · {r.permissions.length} permissions</span>
                    </span>
                    {r.is_system && <Badge tone="info">System</Badge>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={cx(!roleId && "max-lg:hidden")}>
          {!roleId && (
            <div className="card px-6 py-14 text-center text-muted">Select a role to see what it can do.</div>
          )}
          {roleId && roles.data && perms.data && <Editor key={roleId} roleId={roleId} roles={roles.data} perms={perms.data} />}
          {roleId && perms.isError && <ErrorState error={perms.error} onRetry={() => void perms.refetch()} />}
        </div>
      </div>
    </>
  );
}

type Draft = { name: string; description: string; all_engagements: boolean; finding_scope: "all" | "assigned" | "own"; mfa_required: boolean; permissions: Set<string> };

function toDraft(r?: Role): Draft {
  return {
    name: r?.name ?? "",
    description: r?.description ?? "",
    all_engagements: r?.all_engagements ?? false,
    finding_scope: r?.finding_scope ?? "all",
    mfa_required: r?.mfa_required ?? false,
    permissions: new Set(r?.permissions ?? []),
  };
}

function Editor({ roleId, roles, perms }: { roleId: string; roles: Role[]; perms: Permission[] }) {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const isNew = roleId === NEW;
  const role = roles.find((r) => r.id === roleId);
  const [draft, setDraft] = useState<Draft>(() => toDraft(role));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => setDraft(toDraft(role)), [role]);

  const mine = useMemo(() => new Set(me?.permissions ?? []), [me]);
  const isOwn = role?.id === me?.role.id;
  const readOnly = !can("roles.manage") || role?.system_key === "super_admin" || isOwn;
  const why = !can("roles.manage") ? "You can view roles but not change them." : role?.system_key === "super_admin" ? "The Super Admin role is fixed: it always holds every permission." : isOwn ? "You cannot edit your own role." : "";

  const grouped = useMemo(() => {
    const m = new Map<string, Permission[]>();
    perms.forEach((p) => m.set(p.module, [...(m.get(p.module) ?? []), p]));
    return [...m.entries()];
  }, [perms]);

  const body = () => ({
    name: draft.name,
    description: draft.description,
    all_engagements: draft.all_engagements,
    finding_scope: draft.finding_scope,
    mfa_required: draft.mfa_required,
    permissions: [...draft.permissions].sort(),
  });
  const save = useMutation({
    mutationFn: () => (isNew ? api<Role>("POST", "/roles", body()) : api<Role>("PATCH", `/roles/${roleId}`, body())),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["roles"] });
      setSaved(true);
      if (isNew) nav(`/roles/${r.id}`, { replace: true });
    },
  });
  const del = useMutation({
    mutationFn: () => api<void>("DELETE", `/roles/${roleId}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["roles"] }); nav("/roles", { replace: true }); },
  });

  if (!isNew && !role) return <div className="card"><ErrorState error={new Error("Role not found")} /></div>;

  const set = (patch: Partial<Draft>) => { setSaved(false); setDraft((d) => ({ ...d, ...patch })); };
  const toggle = (code: string, on: boolean) => {
    const next = new Set(draft.permissions);
    if (on) next.add(code); else next.delete(code);
    set({ permissions: next });
  };
  const sysName = role?.is_system;

  return (
    <div className="card">
      <header className="flex items-center gap-3 border-b border-line px-6 py-4">
        <Link to="/roles" className="btn btn-secondary btn-icon btn-sm lg:hidden" aria-label="Back to roles"><ChevronLeft size={18} aria-hidden /></Link>
        <h2 className="min-w-0 flex-1 truncate text-xl">{isNew ? "New role" : role?.name}</h2>
        {role?.is_system && <Badge tone="info">System</Badge>}
      </header>

      <div className="space-y-8 p-6">
        {readOnly && !isNew && <Alert tone="warn"><span className="inline-flex items-center gap-2"><Lock size={16} aria-hidden />{why}</span></Alert>}
        {saved && <Alert tone="ok">Saved. Everyone with this role was signed out so the change applies.</Alert>}
        <ErrorNote error={save.error && !Object.keys((save.error as { fields?: object }).fields ?? {}).length ? save.error : null} />

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Name" error={fieldError(save.error, "name")}>
            {(p) => <TextInput {...p} disabled={readOnly || sysName} value={draft.name} onChange={(e) => set({ name: e.target.value })} />}
          </Field>
          <Field label="Finding access" hint="Assigned only limits a user to findings assigned to them. Own only adds findings they reported or imported.">
            {(p) => (
              <Select {...p} disabled={readOnly} value={draft.finding_scope} onChange={(e) => set({ finding_scope: e.target.value as "all" | "assigned" | "own" })}>
                <option value="all">All findings on reachable engagements</option>
                <option value="assigned">Assigned findings only</option>
                <option value="own">Own findings only (reported or assigned)</option>
              </Select>
            )}
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              {(p) => <TextInput {...p} disabled={readOnly} value={draft.description} onChange={(e) => set({ description: e.target.value })} />}
            </Field>
          </div>
          <label className="check"><input type="checkbox" disabled={readOnly || (!me?.role.all_engagements && !draft.all_engagements)} checked={draft.all_engagements} onChange={(e) => set({ all_engagements: e.target.checked })} /> Reaches every engagement</label>
          <label className="check"><input type="checkbox" disabled={readOnly} checked={draft.mfa_required} onChange={(e) => set({ mfa_required: e.target.checked })} /> Require two-step verification</label>
        </div>

        <section aria-labelledby="perm-h">
          <h3 id="perm-h" className="mb-1 text-lg">Permissions <span className="text-muted">({draft.permissions.size})</span></h3>
          <p className="mt-0 mb-4 text-[14px] text-muted">
            You can only grant permissions you hold yourself.{" "}
            <span className="whitespace-nowrap">Platform</span> permissions apply everywhere; <span className="whitespace-nowrap">engagement</span> permissions apply on engagements the user can reach.
          </p>
          <div className="divide-y divide-line rounded-md border border-line">
            {grouped.map(([module, list]) => {
              const all = list.every((p) => draft.permissions.has(p.code));
              const grantable = list.filter((p) => mine.has(p.code));
              return (
                <fieldset key={module} className="m-0 min-w-0 border-0 p-4">
                  <legend className="float-left mb-2 w-full text-[15px] font-medium capitalize">
                    <span className="flex items-center justify-between gap-3">
                      {module.replace(/_/g, " ")}
                      {!readOnly && grantable.length > 0 && (
                        <button type="button" className="link text-[13px]" onClick={() => {
                          const next = new Set(draft.permissions);
                          grantable.forEach((p) => (all ? next.delete(p.code) : next.add(p.code)));
                          set({ permissions: next });
                        }}>{all ? "Clear" : "Select all"}</button>
                      )}
                    </span>
                  </legend>
                  <div className="clear-both grid gap-x-4 sm:grid-cols-2 xl:grid-cols-3">
                    {list.map((p) => {
                      const locked = !readOnly && !mine.has(p.code) && !draft.permissions.has(p.code);
                      return (
                        <label key={p.code} className={cx("check", locked && "opacity-50")} title={locked ? "You do not hold this permission, so you cannot grant it." : p.description}>
                          <input type="checkbox" disabled={readOnly || (!mine.has(p.code) && !draft.permissions.has(p.code))} checked={draft.permissions.has(p.code)} onChange={(e) => toggle(p.code, e.target.checked)} />
                          <span>{p.action.replace(/_/g, " ")}<span className="ml-1.5 text-[13px] text-muted">{p.scope === "platform" ? "platform" : "engagement"}</span></span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              );
            })}
          </div>
          {fieldError(save.error, "permissions") && <p className="field-error mt-2">{fieldError(save.error, "permissions")}</p>}
        </section>

        {!readOnly && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6">
            <div>{!isNew && !role?.is_system && can("roles.manage") && <Button variant="danger" onClick={() => { del.reset(); setConfirmDelete(true); }}>Delete role</Button>}</div>
            <Button variant="primary" loading={save.isPending} disabled={!draft.name.trim()} onClick={() => save.mutate()}>{isNew ? "Create role" : "Save changes"}</Button>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete role"
        body={`Delete "${role?.name}"? A role that still has users cannot be deleted.`}
        confirmLabel="Delete role"
        danger
        busy={del.isPending}
        error={del.error}
        onConfirm={() => del.mutate()}
        onClose={() => setConfirmDelete(false)}
      />
    </div>
  );
}
