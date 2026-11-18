import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus, Search } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import type { DeletionImpact, Page, Role, User } from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, fieldError, formatDate, LoadingRows,
  Modal, PageHeader, SecretOnce, Select, Sheet, TextInput,
} from "../../design/ui";

function StatusBadge({ user }: { user: User }) {
  if (!user.is_active) return <Badge tone="fail">Deactivated</Badge>;
  if (user.locked) return <Badge tone="warn">Locked</Badge>;
  if (user.must_change_password) return <Badge tone="info">Awaiting first sign-in</Badge>;
  return <Badge tone="ok">Active</Badge>;
}

export function UsersPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const users = useQuery({
    queryKey: ["users", search],
    queryFn: () => api<Page<User>>("GET", `/users?page_size=100&search=${encodeURIComponent(search)}`),
  });

  return (
    <>
      <PageHeader
        title="Users"
        lead="Everyone who can sign in to RedShadow. Deactivate an account to stop access. A deactivated account can be deleted: it is removed, or anonymised when findings and notes still refer to it, so history stays attributed."
        actions={can("users.create") && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} aria-hidden /> New user</Button>}
      />

      <div className="card overflow-hidden">
        <div className="border-b border-line p-4">
          <div className="relative max-w-md">
            <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput aria-label="Search users" placeholder="Search by name or email" className="pl-11" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>

        {users.isPending && <LoadingRows />}
        {users.isError && <ErrorState error={users.error} onRetry={() => void users.refetch()} />}
        {users.data && users.data.results.length === 0 && (
          <EmptyState
            title={search ? "No users match" : "No users yet"}
            body={search ? "Try a different name or email." : "Create the first account to get started."}
          />
        )}
        {users.data && users.data.results.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead>
                <tr><th>User</th><th>Role</th><th>Status</th><th>Two-step</th><th>Last sign-in</th><th><span className="sr-only">Open</span></th></tr>
              </thead>
              <tbody>
                {users.data.results.map((u) => (
                  <tr key={u.id} onClick={() => setSelected(u.id)}>
                    <td>
                      <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); setSelected(u.id); }}>
                        <span className="block font-medium">{u.display_name}</span>
                        <span className="block text-[14px] text-muted">{u.email}</span>
                      </button>
                    </td>
                    <td>{u.role.name}</td>
                    <td><StatusBadge user={u} /></td>
                    <td>{u.mfa_enabled ? "On" : <span className="text-muted">Off</span>}</td>
                    <td className="text-muted">{formatDate(u.last_login)}</td>
                    <td className="text-muted"><ChevronRight size={18} aria-hidden /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {users.data.results.map((u) => (
                <li key={u.id}>
                  <button type="button" onClick={() => setSelected(u.id)} className="flex min-h-[72px] w-full items-center justify-between gap-3 px-4 py-3 text-left">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{u.display_name}</span>
                      <span className="block truncate text-[14px] text-muted">{u.email} · {u.role.name}</span>
                    </span>
                    <StatusBadge user={u} />
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <CreateUser open={creating} onClose={() => setCreating(false)} />
      <UserSheet userId={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function useRoles(enabled = true) {
  return useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("GET", "/roles"), enabled });
}

function CreateUser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const roles = useRoles(open);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [roleId, setRoleId] = useState("");
  const [created, setCreated] = useState<{ email: string; temp: string } | null>(null);

  const create = useMutation({
    mutationFn: () => api<User & { temporary_password: string }>("POST", "/users", { email, display_name: name, role: roleId }),
    onSuccess: (u) => {
      setCreated({ email: u.email, temp: u.temporary_password });
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
  });

  function close() {
    setEmail(""); setName(""); setRoleId(""); setCreated(null); create.reset();
    onClose();
  }

  return (
    <Modal open={open} onClose={close} title={created ? "User created" : "New user"}>
      {created ? (
        <div className="space-y-5 p-6">
          <p className="m-0">
            Give <strong className="font-medium">{created.email}</strong> this temporary password. They must replace it at first sign-in.
          </p>
          <SecretOnce title="Shown once" value={created.temp} note="It cannot be retrieved later. Reset the password if it is lost." />
          <div className="flex justify-end"><Button variant="primary" onClick={close}>Done</Button></div>
        </div>
      ) : (
        <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }}>
          <ErrorNote error={create.error && !Object.keys((create.error as { fields?: object }).fields ?? {}).length ? create.error : null} />
          <Field label="Full name" error={fieldError(create.error, "display_name")}>
            {(p) => <TextInput {...p} required autoFocus value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Email" error={fieldError(create.error, "email")}>
            {(p) => <TextInput {...p} type="email" required autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Field label="Role" error={fieldError(create.error, "role")} hint={roles.isError ? "You need permission to view roles to choose one." : undefined}>
            {(p) => (
              <Select {...p} required value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                <option value="" disabled>Choose a role</option>
                {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </Select>
            )}
          </Field>
          <div className="flex flex-wrap justify-end gap-3">
            <Button onClick={close}>Cancel</Button>
            <Button type="submit" variant="primary" loading={create.isPending} disabled={!email || !name || !roleId}>Create user</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

type Action = "deactivate" | "reactivate" | "reset-password" | "reset-mfa" | "sessions/revoke";

const ACTIONS: Record<Action, { title: string; body: (u: User) => string; label: string; danger?: boolean; perm: string }> = {
  deactivate: { title: "Deactivate user", body: (u) => `${u.display_name} will be signed out everywhere and cannot sign in. Their history is kept.`, label: "Deactivate", danger: true, perm: "users.deactivate" },
  reactivate: { title: "Reactivate user", body: (u) => `${u.display_name} will be able to sign in again.`, label: "Reactivate", perm: "users.deactivate" },
  "reset-password": { title: "Reset password", body: (u) => `A new temporary password is generated for ${u.display_name}. Their current password stops working and they are signed out.`, label: "Reset password", danger: true, perm: "users.update" },
  "reset-mfa": { title: "Reset two-step verification", body: (u) => `${u.display_name}'s authenticator and recovery codes are removed and they are signed out. They enrol again at next sign-in.`, label: "Reset two-step", danger: true, perm: "users.update" },
  "sessions/revoke": { title: "Sign out everywhere", body: (u) => `All of ${u.display_name}'s sessions end immediately.`, label: "Sign out everywhere", perm: "users.update" },
};

function UserSheet({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { me, can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user", userId], queryFn: () => api<User>("GET", `/users/${userId}`), enabled: !!userId });
  const roles = useRoles(!!userId && can("roles.assign"));
  const [pending, setPending] = useState<Action | null>(null);
  const [temp, setTemp] = useState<string | null>(null);
  const [roleId, setRoleId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const user = q.data;
  const isSelf = user?.id === me?.id;

  const refresh = () => { void qc.invalidateQueries({ queryKey: ["users"] }); void qc.invalidateQueries({ queryKey: ["user", userId] }); void qc.invalidateQueries({ queryKey: ["roles"] }); };

  const run = useMutation({
    mutationFn: (a: Action) => api<{ temporary_password?: string } | undefined>("POST", `/users/${userId}/${a}`),
    onSuccess: (r) => { refresh(); setPending(null); if (r && "temporary_password" in r && r.temporary_password) setTemp(r.temporary_password); },
  });
  const changeRole = useMutation({
    mutationFn: () => api<User>("PATCH", `/users/${userId}`, { role: roleId }),
    onSuccess: () => { refresh(); setRoleId(null); },
  });

  function close() { setPending(null); setTemp(null); setRoleId(null); run.reset(); changeRole.reset(); onClose(); }

  const available = (Object.keys(ACTIONS) as Action[]).filter((a) => {
    if (!user || !can(ACTIONS[a].perm) || isSelf && a !== "sessions/revoke") return false;
    if (a === "deactivate") return user.is_active;
    if (a === "reactivate") return !user.is_active;
    if (a === "reset-mfa") return user.mfa_enabled;
    return true;
  });

  return (
    <>
      <Sheet open={!!userId} onClose={close} title={user?.display_name ?? "User"}>
        {q.isPending && <LoadingRows rows={4} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {user && (
          <div className="space-y-8 p-6">
            {temp && <SecretOnce title="New temporary password" value={temp} note="Shown once. The user must change it at next sign-in." />}
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Item k="Email" v={<span className="break-all">{user.email}</span>} />
              <Item k="Status" v={<StatusBadge user={user} />} />
              <Item k="Two-step verification" v={user.mfa_enabled ? "On" : "Off"} />
              <Item k="Last sign-in" v={formatDate(user.last_login)} />
              <Item k="Password changed" v={formatDate(user.last_password_change)} />
              <Item k="Created" v={formatDate(user.created_at)} />
            </dl>

            <section aria-labelledby="role-h" className="space-y-3">
              <h3 id="role-h" className="text-lg">Role</h3>
              {can("roles.assign") && can("users.update") && !isSelf ? (
                <>
                  <ErrorNote error={changeRole.error} />
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="min-w-[200px] flex-1">
                      <Select aria-label="Role" value={roleId ?? user.role.id} onChange={(e) => setRoleId(e.target.value)}>
                        {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                        {!roles.data && <option value={user.role.id}>{user.role.name}</option>}
                      </Select>
                    </div>
                    <Button variant="primary" disabled={!roleId || roleId === user.role.id} loading={changeRole.isPending} onClick={() => changeRole.mutate()}>Change role</Button>
                  </div>
                  <p className="m-0 text-[13px] text-muted">The user is signed out and gets the new access at next sign-in.</p>
                </>
              ) : (
                <p className="m-0">{user.role.name}{isSelf && <span className="text-muted"> (you cannot change your own role)</span>}</p>
              )}
            </section>

            {available.length > 0 && (
              <section aria-labelledby="act-h" className="space-y-3">
                <h3 id="act-h" className="text-lg">Account actions</h3>
                <div className="flex flex-wrap gap-3">
                  {available.map((a) => (
                    <Button key={a} variant={ACTIONS[a].danger ? "danger" : "secondary"} onClick={() => { run.reset(); setPending(a); }}>{ACTIONS[a].label}</Button>
                  ))}
                </div>
              </section>
            )}
            {can("users.delete") && !isSelf && (
              <section aria-labelledby="del-h" className="space-y-3">
                <h3 id="del-h" className="text-lg">Delete account</h3>
                {user.is_active ? (
                  <p className="m-0 text-muted">Deactivate this account first. Only a deactivated account can be deleted.</p>
                ) : (
                  <>
                    <p className="m-0 text-muted">Removes the account for good. If findings, notes or evidence still refer to it, the account stays as an anonymous “Deleted user” so the history keeps its shape.</p>
                    <Button variant="danger" onClick={() => setDeleting(true)}>Delete account…</Button>
                  </>
                )}
              </section>
            )}
          </div>
        )}
      </Sheet>

      {user && <DeleteUserDialog open={deleting} user={user} onClose={() => setDeleting(false)} onDeleted={() => { setDeleting(false); refresh(); close(); }} />}
      <ConfirmDialog
        open={!!pending && !!user}
        title={pending ? ACTIONS[pending].title : ""}
        body={pending && user ? ACTIONS[pending].body(user) : ""}
        confirmLabel={pending ? ACTIONS[pending].label : ""}
        danger={pending ? ACTIONS[pending].danger : false}
        busy={run.isPending}
        error={run.error}
        onConfirm={() => pending && run.mutate(pending)}
        onClose={() => { setPending(null); run.reset(); }}
      />
    </>
  );
}

function Item({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="label">{k}</dt>
      <dd className="m-0 mt-0.5">{v}</dd>
    </div>
  );
}

const HISTORY_LIMIT = 6;

/** Shows what deleting does to the user's records, then asks for the account's email as confirmation. */
function DeleteUserDialog({ open, user, onClose, onDeleted }: { open: boolean; user: User; onClose: () => void; onDeleted: () => void }) {
  const [typed, setTyped] = useState("");
  const impact = useQuery({ queryKey: ["user-impact", user.id], queryFn: () => api<DeletionImpact>("GET", `/users/${user.id}/deletion-impact`), enabled: open, staleTime: 0 });
  const del = useMutation({
    mutationFn: () => api("DELETE", `/users/${user.id}`, { confirm_email: typed.trim() }),
    onSuccess: onDeleted,
  });
  const close = () => { setTyped(""); del.reset(); onClose(); };
  const i = impact.data;
  const history = i ? Object.entries(i.history).slice(0, HISTORY_LIMIT) : [];
  const matches = typed.trim().toLowerCase() === user.email.toLowerCase();

  return (
    <Modal open={open} onClose={close} title="Delete account">
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); if (matches && i && i.blockers.length === 0) del.mutate(); }}>
        <p className="m-0">You are about to delete <strong className="font-medium">{user.display_name}</strong> ({user.email}). This cannot be undone.</p>
        {impact.isPending && <LoadingRows rows={2} />}
        {impact.isError && <ErrorState error={impact.error} onRetry={() => void impact.refetch()} />}
        {i && i.blockers.length > 0 && <Alert tone="error"><ul className="m-0 list-disc pl-5">{i.blockers.map((b) => <li key={b}>{b}</li>)}</ul></Alert>}
        {i && (
          <ul className="m-0 list-disc flex flex-col gap-1 pl-5 text-[15px]">
            <li>{i.removes.memberships} engagement membership{i.removes.memberships === 1 ? "" : "s"} and {i.removes.saved_import_mappings} saved import mapping{i.removes.saved_import_mappings === 1 ? "" : "s"} are removed.</li>
            <li>Unassigned: {i.clears.engagements_led} engagement{i.clears.engagements_led === 1 ? "" : "s"} led, {i.clears.findings_assigned} open finding{i.clears.findings_assigned === 1 ? "" : "s"} as pentester, {i.clears.findings_to_fix} as remediation owner.</li>
            {i.mode === "remove" ? <li>Nothing else refers to this account, so it is removed completely.</li> : <li>The account becomes an anonymous “Deleted user” with no name, email or sign-in, because {history.map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ")}{Object.keys(i.history).length > HISTORY_LIMIT ? " and more" : ""} still refer to it.</li>}
            <li>The audit log keeps the account’s email for the record.</li>
          </ul>
        )}
        <Field label="Type the account's email to confirm" error={fieldError(del.error, "confirm_email")}>
          {(p) => <TextInput {...p} autoComplete="off" autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={user.email} />}
        </Field>
        <ErrorNote error={del.error && !Object.keys((del.error as { fields?: object }).fields ?? {}).length ? del.error : null} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" variant="danger" loading={del.isPending} disabled={!matches || !i || i.blockers.length > 0}>Delete account</Button>
        </div>
      </form>
    </Modal>
  );
}
