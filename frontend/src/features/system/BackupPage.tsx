import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, UploadCloud } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api, downloadPost, upload } from "../../api/client";
import { Alert, Button, ConfirmDialog, ErrorNote, ErrorState, Field, fieldError, formatBytes, formatDate, LoadingRows, PageHeader, TextInput } from "../../design/ui";

type Overview = {
  last_backup: { status: "ok" | "stale" | "none"; last_at: string | null; size_bytes: number; age_days: number | null } | null;
  restore_allowed: boolean;
  restore: { state: "idle" | "queued" | "running" | "done" | "failed"; message: string };
};

const MIN = 12;
const noFields = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);

/** The password and, with two-step sign-in, a fresh code: asked again before anything leaves or replaces the data. */
function Identity({ password, setPassword, code, setCode, mfa, error }: {
  password: string; setPassword: (v: string) => void; code: string; setCode: (v: string) => void; mfa: boolean; error: unknown;
}) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Field label="Your password" error={fieldError(error, "password")}>{(p) => <TextInput {...p} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
      {mfa && <Field label="Authentication code" hint="A new 6-digit code from your app." error={fieldError(error, "code")}>{(p) => <TextInput {...p} inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />}</Field>}
    </div>
  );
}

function BackupCard({ mfa, onDone }: { mfa: boolean; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [again, setAgain] = useState("");
  const run = useMutation({
    mutationFn: () => downloadPost("/system/backup", { password, code, passphrase }, "redshadow-backup.rsbk"),
    onSuccess: () => { setPassword(""); setCode(""); setPassphrase(""); setAgain(""); onDone(); },
  });
  const short = passphrase.length > 0 && passphrase.length < MIN;
  const differs = again.length > 0 && again !== passphrase;

  return (
    <form className="card card-pad flex flex-col gap-5" onSubmit={(e: FormEvent) => { e.preventDefault(); if (!short && !differs) run.mutate(); }}>
      <div>
        <h2 className="text-xl">Download a backup</h2>
        <p className="m-0 mt-2 text-muted">One encrypted file with every organisation, asset, engagement, finding, user, file and the audit log.</p>
      </div>
      <Alert tone="warn">Write the passphrase down somewhere safe. Without it the file cannot be opened, and nobody can recover it.</Alert>
      <ErrorNote error={noFields(run.error)} />
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Backup passphrase" hint={`At least ${MIN} characters.`} error={short ? `Use at least ${MIN} characters.` : fieldError(run.error, "passphrase")}>{(p) => <TextInput {...p} type="password" autoComplete="new-password" required value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />}</Field>
        <Field label="Repeat the passphrase" error={differs ? "The two do not match." : undefined}>{(p) => <TextInput {...p} type="password" autoComplete="new-password" required value={again} onChange={(e) => setAgain(e.target.value)} />}</Field>
      </div>
      <Identity password={password} setPassword={setPassword} code={code} setCode={setCode} mfa={mfa} error={run.error} />
      {run.isSuccess && <Alert tone="ok">Backup downloaded. Keep the file and the passphrase in separate places.</Alert>}
      <div className="flex justify-end"><Button type="submit" variant="primary" loading={run.isPending} disabled={!password || passphrase.length < MIN || again !== passphrase}><Download size={18} aria-hidden /> Create and download</Button></div>
    </form>
  );
}

function RestoreCard({ mfa, overview, refresh }: { mfa: boolean; overview: Overview; refresh: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const state = overview.restore.state;
  const busy = state === "queued" || state === "running";
  const run = useMutation({
    mutationFn: () => upload("POST", "/system/restore", file!, setProgress, { password, code, passphrase }),
    onSuccess: refresh,
    onSettled: () => { setProgress(null); setConfirm(false); },
  });

  return (
    <form className="card card-pad flex flex-col gap-5" onSubmit={(e: FormEvent) => { e.preventDefault(); setConfirm(true); }}>
      <div>
        <h2 className="text-xl">Restore from a backup</h2>
        <p className="m-0 mt-2 text-muted">Only for a new installation that has no organisations or engagements yet, running the same RedShadow version as the backup.</p>
      </div>
      {!overview.restore_allowed && !busy && <Alert tone="warn">This installation already holds data, so restoring is switched off. Your data cannot be overwritten from here.</Alert>}
      {busy && <Alert tone="warn">Restoring. Keep this page open; you will be signed out when it finishes.</Alert>}
      {state === "failed" && <Alert tone="error">{overview.restore.message}</Alert>}
      <ErrorNote error={noFields(run.error)} />
      {overview.restore_allowed && !busy && (
        <>
          <div className="flex flex-col items-start gap-2">
            <span className="label">Backup file (.rsbk)</span>
            <input ref={input} type="file" accept=".rsbk" className="sr-only" aria-label="Choose backup file" onChange={(e) => { run.reset(); setFile(e.target.files?.[0] ?? null); }} />
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => input.current?.click()}><UploadCloud size={18} aria-hidden /> {file ? "Choose another file" : "Choose file"}</Button>
              {file && <span className="break-all">{file.name} <span className="text-muted">({formatBytes(file.size)})</span></span>}
            </div>
            {fieldError(run.error, "file") && <p className="field-error m-0" role="alert">{fieldError(run.error, "file")}</p>}
          </div>
          <Field label="Backup passphrase" error={fieldError(run.error, "passphrase")}>{(p) => <TextInput {...p} type="password" autoComplete="off" required value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />}</Field>
          <Identity password={password} setPassword={setPassword} code={code} setCode={setCode} mfa={mfa} error={run.error} />
          {progress !== null && <p className="m-0 text-muted" role="status">Uploading {Math.round(progress * 100)}%</p>}
          <div className="flex justify-end"><Button type="submit" variant="danger" loading={run.isPending} disabled={!file || !password || !passphrase}>Restore</Button></div>
        </>
      )}
      <ConfirmDialog open={confirm} title="Restore this backup" body="Every account and record in this new installation is replaced by those in the backup. You will be signed out and sign in with an account from the backup." confirmLabel="Restore" danger busy={run.isPending} onConfirm={() => run.mutate()} onClose={() => setConfirm(false)} />
    </form>
  );
}

export function BackupPage() {
  const { me } = useAuth();
  const q = useQuery({
    queryKey: ["system-overview"],
    queryFn: () => api<Overview>("GET", "/system/overview"),
    refetchInterval: (query) => (["queued", "running"].includes(query.state.data?.restore.state ?? "") ? 2000 : false),
    retry: false,
  });
  // A finished restore replaces the accounts and sessions, so the next request is refused: go to sign-in.
  const was = useRef(false);
  useEffect(() => {
    const busy = ["queued", "running"].includes(q.data?.restore.state ?? "");
    if (busy) was.current = true;
    if (was.current && (q.isError || q.data?.restore.state === "done")) window.location.assign("/login");
  }, [q.data, q.isError]);

  const last = q.data?.last_backup;
  const mfa = !!me?.mfa_enabled;

  return (
    <>
      <PageHeader title="Backup and restore" lead="Take a copy of everything in this installation, or bring a copy back into a new one." />
      {q.isPending && <LoadingRows rows={4} />}
      {q.isError && !was.current && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && (
        <div className="flex max-w-3xl flex-col gap-6">
          <p className="m-0 text-muted">{last?.last_at ? `Last backup: ${formatDate(last.last_at)}${last.size_bytes ? `, ${formatBytes(last.size_bytes)}` : ""}.` : "No backup has been taken yet."}</p>
          <BackupCard mfa={mfa} onDone={() => void q.refetch()} />
          <RestoreCard mfa={mfa} overview={q.data} refresh={() => void q.refetch()} />
        </div>
      )}
    </>
  );
}
