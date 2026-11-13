import { useState, type FormEvent } from "react";
import { Download } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ME_KEY, useAuth } from "../../api/auth";
import { api } from "../../api/client";
import type { Me } from "../../api/types";
import { Alert, Button, CopyButton, ErrorNote, Field, fieldError, TextInput } from "../../design/ui";
import { AuthLayout } from "./AuthLayout";

type Setup = { secret: string; otpauth_uri: string; qr_svg: string };

export function useSignOut() {
  const qc = useQueryClient();
  return async () => {
    try {
      await api("POST", "/auth/logout");
    } finally {
      qc.setQueryData(ME_KEY, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    }
  };
}

function SignOutLink() {
  const signOut = useSignOut();
  return (
    <p className="mt-8 text-center text-muted">
      Not you?{" "}
      <button type="button" className="link" onClick={signOut}>
        Sign out
      </button>
    </p>
  );
}

export function MfaVerify() {
  const qc = useQueryClient();
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("POST", "/auth/mfa/verify", recovery ? { recovery_code: code } : { code });
      qc.setQueryData(ME_KEY, me);
    } catch (err) {
      setError(err);
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Two-step verification"
      lead={recovery ? "Enter one of your saved recovery codes. Each works once." : "Enter the 6-digit code from your authenticator app."}
    >
      <form onSubmit={submit} className="space-y-5">
        <ErrorNote error={error} />
        <Field label={recovery ? "Recovery code" : "Authentication code"}>
          {(p) => (
            <TextInput
              {...p}
              autoFocus
              autoComplete="one-time-code"
              inputMode={recovery ? "text" : "numeric"}
              maxLength={recovery ? 16 : 6}
              className="mono tracking-[0.2em]"
              value={code}
              onChange={(e) => setCode(e.target.value.trim())}
            />
          )}
        </Field>
        <Button type="submit" variant="primary" block loading={busy} disabled={code.length < 6}>
          Verify
        </Button>
        <button type="button" className="link block w-full text-center" onClick={() => { setRecovery((r) => !r); setCode(""); setError(null); }}>
          {recovery ? "Use authenticator app instead" : "Use a recovery code"}
        </button>
      </form>
      <SignOutLink />
    </AuthLayout>
  );
}

export function PasswordForm({ onDone, requireCurrentHint }: { onDone: (me: Me) => void; requireCurrentHint?: string }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mismatch = confirm.length > 0 && confirm !== next;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("POST", "/auth/password/change", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      onDone(me);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <ErrorNote error={error && !fieldError(error, "new_password") && !fieldError(error, "current_password") ? error : null} />
      <Field label="Current password" hint={requireCurrentHint} error={fieldError(error, "current_password")}>
        {(p) => <TextInput {...p} type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />}
      </Field>
      <Field label="New password" hint="At least 12 characters. Avoid common passwords." error={fieldError(error, "new_password")}>
        {(p) => <TextInput {...p} type="password" autoComplete="new-password" required minLength={12} value={next} onChange={(e) => setNext(e.target.value)} />}
      </Field>
      <Field label="Confirm new password" error={mismatch ? "Passwords do not match." : undefined}>
        {(p) => <TextInput {...p} type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
      </Field>
      <Button type="submit" variant="primary" block loading={busy} disabled={!current || next.length < 12 || next !== confirm}>
        Change password
      </Button>
    </form>
  );
}

export function PasswordChange() {
  const qc = useQueryClient();
  return (
    <AuthLayout title="Choose a new password" lead="Your administrator set a temporary password. Replace it to continue.">
      <PasswordForm
        requireCurrentHint="The temporary password you just signed in with."
        onDone={(me) => qc.setQueryData(ME_KEY, me)}
      />
      <SignOutLink />
    </AuthLayout>
  );
}

/** Enrolment steps shared by the forced flow and the voluntary one on the Account page. */
export function MfaEnrol({ onFinished }: { onFinished: () => void }) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setSetup(await api<Setup>("POST", "/auth/mfa/setup"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ recovery_codes: string[] }>("POST", "/auth/mfa/confirm", { code });
      setCodes(r.recovery_codes);
    } catch (err) {
      setError(err);
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  if (codes) {
    const text = codes.join("\n");
    return (
      <div className="space-y-5">
        <Alert tone="warn">
          Save these recovery codes now. They are shown once and let you in if you lose your phone.
        </Alert>
        <ul className="grid list-none grid-cols-2 gap-2 p-0">
          {codes.map((c) => (
            <li key={c} className="mono rounded-md border border-line bg-raised px-3 py-2 text-center select-all">
              {c}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3">
          <CopyButton value={text} label="Copy codes" />
          <a
            className="btn btn-secondary btn-sm"
            download="redshadow-recovery-codes.txt"
            href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
          >
            <Download size={16} aria-hidden /> Download
          </a>
        </div>
        <Button variant="primary" block onClick={onFinished}>
          I have saved my codes
        </Button>
      </div>
    );
  }

  if (!setup) {
    return (
      <div className="space-y-5">
        <ErrorNote error={error} />
        <p className="m-0 text-muted">
          You will need an authenticator app such as 1Password, Authy or Google Authenticator.
        </p>
        <Button variant="primary" block loading={busy} onClick={start}>
          Set up authenticator app
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={confirm} className="space-y-5">
      <ErrorNote error={error} />
      <p className="m-0 text-muted">Scan this code with your authenticator app, then enter the 6-digit code it shows.</p>
      <div className="mx-auto w-48 rounded-md border border-line bg-white p-2">
        <img src={setup.qr_svg} alt="QR code for your authenticator app" className="block w-full" />
      </div>
      <details>
        <summary className="link inline cursor-pointer">Can't scan? Enter the key manually</summary>
        <p className="mono mt-2 break-all select-all">{setup.secret}</p>
      </details>
      <Field label="Authentication code">
        {(p) => (
          <TextInput {...p} autoFocus autoComplete="one-time-code" inputMode="numeric" maxLength={6} className="mono tracking-[0.2em]" value={code} onChange={(e) => setCode(e.target.value.trim())} />
        )}
      </Field>
      <Button type="submit" variant="primary" block loading={busy} disabled={code.length !== 6}>
        Turn on two-step verification
      </Button>
    </form>
  );
}

export function MfaSetupRequired() {
  const { refresh } = useAuth();
  return (
    <AuthLayout title="Set up two-step verification" lead="Your role requires an authenticator app before you can continue.">
      <MfaEnrol onFinished={() => void refresh()} />
      <SignOutLink />
    </AuthLayout>
  );
}
