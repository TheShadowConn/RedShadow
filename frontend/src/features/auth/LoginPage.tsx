import { useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { ME_KEY } from "../../api/auth";
import type { Me } from "../../api/types";
import { Button, ErrorNote, Field, TextInput } from "../../design/ui";
import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("POST", "/auth/login", { email, password });
      qc.setQueryData(ME_KEY, me);
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Sign in" lead="Use the account an administrator created for you.">
      <form onSubmit={submit} className="space-y-5" noValidate>
        <ErrorNote error={error} />
        <Field label="Email">
          {(p) => (
            <TextInput {...p} type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label="Password">
          {(p) => (
            <div className="relative">
              <TextInput
                {...p}
                type={show ? "text" : "password"}
                autoComplete="current-password"
                required
                className="pr-14"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                aria-label={show ? "Hide password" : "Show password"}
                aria-pressed={show}
                className="absolute top-0 right-0 grid h-12 w-12 place-items-center text-muted hover:text-ink"
              >
                {show ? <EyeOff size={20} aria-hidden /> : <Eye size={20} aria-hidden />}
              </button>
            </div>
          )}
        </Field>
        <Button type="submit" variant="primary" block loading={busy} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
