import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { Alert, Badge, PageHeader } from "../../design/ui";
import { MfaEnrol, PasswordForm } from "../auth/RestrictionFlow";

export function AccountPage() {
  const { me, refresh } = useAuth();
  const [saved, setSaved] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  if (!me) return null;

  return (
    <>
      <PageHeader title="Account" lead="Your sign-in details and security." />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card card-pad lg:col-span-2" aria-labelledby="profile-h">
          <h2 id="profile-h" className="text-xl">Profile</h2>
          <dl className="m-0 mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-3">
            <div><dt className="label">Name</dt><dd className="m-0">{me.display_name}</dd></div>
            <div><dt className="label">Email</dt><dd className="m-0 break-all">{me.email}</dd></div>
            <div><dt className="label">Role</dt><dd className="m-0">{me.role.name}</dd></div>
          </dl>
          <p className="m-0 mt-4 text-[15px]"><Link to="/about" className="text-accent underline underline-offset-2">About RedShadow: version, build and creator</Link></p>
        </section>

        <section className="card card-pad" aria-labelledby="pw-h">
          <h2 id="pw-h" className="mb-5 text-xl">Change password</h2>
          {saved && (
            <div className="mb-5">
              <Alert tone="ok">Password changed. Your other sessions were signed out.</Alert>
            </div>
          )}
          <PasswordForm onDone={() => { setSaved(true); void refresh(); }} />
        </section>

        <section className="card card-pad" aria-labelledby="mfa-h">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h2 id="mfa-h" className="text-xl">Two-step verification</h2>
            {me.mfa_enabled ? <Badge tone="ok">On</Badge> : <Badge tone="warn">Off</Badge>}
          </div>
          {me.mfa_enabled ? (
            <p className="m-0 text-muted">An authenticator app protects this account. If you lose access, ask an administrator to reset it.</p>
          ) : enrolling ? (
            <MfaEnrol onFinished={() => { setEnrolling(false); void refresh(); }} />
          ) : (
            <>
              <p className="mt-0 mb-5 text-muted">Add an authenticator app for a second sign-in step.</p>
              <button type="button" className="btn btn-primary" onClick={() => setEnrolling(true)}>Set up</button>
            </>
          )}
        </section>
        <section className="card card-pad lg:col-span-2" aria-labelledby="keys-h">
          <h2 id="keys-h" className="mb-4 text-xl">Keyboard shortcuts</h2>
          <dl className="m-0 grid gap-x-8 gap-y-2 sm:grid-cols-2">
            {[["Ctrl K or Cmd K", "Open search"], ["/", "Open search (when not typing)"], ["Up and Down", "Move in search results and menus"], ["Enter", "Open the highlighted result"], ["Esc", "Close a dialog or search"], ["Tab and Shift Tab", "Move between controls"], ["Left and Right", "Switch tabs"], ["Space or Enter", "Open or drag-pick a calendar bar"]].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-4 border-b border-line py-2"><dt className="text-muted">{v}</dt><dd className="m-0"><kbd className="mono rounded border border-line px-2 py-0.5 text-[13px]">{k}</kbd></dd></div>
            ))}
          </dl>
        </section>
      </div>
    </>
  );
}
