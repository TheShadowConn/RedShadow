import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { AlertCircle, AlertTriangle, Check, CheckCircle2, Copy, X } from "lucide-react";

import { ApiError } from "../api/client";
import { EclipseO } from "./Loader";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  size?: "md" | "sm";
  loading?: boolean;
  block?: boolean;
};

export function Button({ variant = "secondary", size = "md", loading, block, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx("btn", `btn-${variant}`, size === "sm" && "btn-sm", block && "btn-block", className)}
    >
      {loading && <EclipseO size={20} mono />}
      {children}
    </button>
  );
}

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: (props: { id: string; "aria-invalid"?: true; "aria-describedby"?: string }) => ReactNode;
}) {
  const id = useId();
  const descId = error || hint ? `${id}-d` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": descId })}
      {error ? (
        <span id={descId} className="field-error" role="alert">
          {error}
        </span>
      ) : (
        hint && (
          <span id={descId} className="field-hint">
            {hint}
          </span>
        )
      )}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("input", props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx("select input", props.className)} />;
}

const BADGE_ICON = { ok: CheckCircle2, warn: AlertTriangle, fail: AlertCircle, info: Check } as const;

export function Badge({ tone, children }: { tone: "ok" | "warn" | "fail" | "info"; children: ReactNode }) {
  const Icon = BADGE_ICON[tone];
  return (
    <span className={cx("badge", `badge-${tone}`)}>
      <Icon size={14} aria-hidden />
      {children}
    </span>
  );
}

export function Alert({ tone, children }: { tone: "error" | "warn" | "ok"; children: ReactNode }) {
  const Icon = tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : AlertCircle;
  return (
    <div className={cx("alert", `alert-${tone}`)} role={tone === "error" ? "alert" : "status"}>
      <Icon size={20} className="mt-0.5 flex-none" aria-hidden />
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">{children}</div>
    </div>
  );
}

/** Renders any thrown value as a message plus the request id support needs. */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <Alert tone="error">
      <p className="m-0">{e ? e.message : "Something went wrong."}</p>
      {e?.requestId && <p className="m-0 mt-1 text-[13px]">Request id: {e.requestId}</p>}
    </Alert>
  );
}

export function fieldError(error: unknown, name: string): string | undefined {
  return error instanceof ApiError ? error.fields[name]?.[0] : undefined;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading">
      <div className="flex justify-center py-2"><EclipseO size={32} /></div>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="px-6 py-14 text-center">
      <h3 className="text-xl">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-muted">{body}</p>
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="space-y-4 p-6">
      <ErrorNote error={error} />
      {onRetry && (
        <Button onClick={onRetry} variant="secondary">
          Try again
        </Button>
      )}
    </div>
  );
}

export function PageHeader({ title, lead, actions }: { title: string; lead?: string; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[32px] max-sm:text-[28px]">{title}</h1>
        {lead && <p className="mt-2 max-w-2xl text-muted">{lead}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
    </div>
  );
}

function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const handler = () => onClose();
    d.addEventListener("close", handler);
    return () => d.removeEventListener("close", handler);
  }, [onClose]);
  return ref;
}

function DialogShell({ open, onClose, title, kind, wide, children }: { open: boolean; onClose: () => void; title: string; kind: "modal" | "sheet"; wide?: boolean | "form"; children: ReactNode }) {
  const ref = useDialog(open, onClose);
  return (
    <dialog
      ref={ref}
      className={cx(kind, wide === "form" ? "modal-form" : wide && "modal-wide")}
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      {open && (
        <div className={cx("flex flex-col", kind === "sheet" ? "h-full" : "max-h-[calc(100vh-48px)]")}>
          <header className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
            <h2 className="min-w-0 text-xl [overflow-wrap:anywhere]">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Close" className="btn btn-secondary btn-icon btn-sm">
              <X size={18} aria-hidden />
            </button>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </div>
      )}
    </dialog>
  );
}

/** `wide` is for pictures (up to 1100px); `wide="form"` gives long forms with text editors room (up to 860px). */
export const Modal = (p: { open: boolean; onClose: () => void; title: string; wide?: boolean | "form"; children: ReactNode }) => <DialogShell {...p} kind="modal" />;
export const Sheet = (p: { open: boolean; onClose: () => void; title: string; children: ReactNode }) => <DialogShell {...p} kind="sheet" />;

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  error?: unknown;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="space-y-5 p-6">
        <p className="m-0">{body}</p>
        <ErrorNote error={error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1800);
        } catch {
          /* clipboard blocked: the value stays selectable on screen */
        }
      }}
    >
      {done ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
      {done ? "Copied" : label}
    </Button>
  );
}

/** A secret shown exactly once (temporary password, recovery codes). */
export function SecretOnce({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <div className="space-y-3">
      <Alert tone="warn">
        <strong className="font-medium">{title}</strong>
        <p className="m-0 mt-1">{note}</p>
      </Alert>
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-line-strong bg-raised p-3">
        <code className="mono min-w-0 flex-1 break-all text-[17px] select-all">{value}</code>
        <CopyButton value={value} />
      </div>
    </div>
  );
}

export function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={4} {...props} className={cx("input", "min-h-24 py-3", props.className)} />;
}

/** Accessible tab strip. Panels are rendered by the caller, keyed on `value`. */
export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: Array<{ id: T; label: string }>; value: T; onChange: (id: T) => void; label: string }) {
  function onKey(e: React.KeyboardEvent, i: number) {
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = tabs[(next + tabs.length) % tabs.length];
    onChange(t.id);
    document.getElementById(`tab-${t.id}`)?.focus();
  }
  return (
    <div role="tablist" aria-label={label} className="tabs">
      {tabs.map((t, i) => (
        <button
          key={t.id}
          id={`tab-${t.id}`}
          type="button"
          role="tab"
          aria-selected={t.id === value}
          aria-controls={`panel-${t.id}`}
          tabIndex={t.id === value ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0} className="mt-6 focus:outline-none">
      {children}
    </div>
  );
}

export function formatDay(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(`${iso}T00:00:00`));
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function label(list: ReadonlyArray<readonly [string, string]>, key: string): string {
  return list.find(([k]) => k === key)?.[1] ?? key;
}

const STATUS_TONE: Record<string, "ok" | "warn" | "fail" | "info"> = {
  planned: "info", scheduled: "info", in_progress: "warn", reporting: "warn", completed: "ok", cancelled: "fail",
};

export function EngagementStatus({ status, archived, overdue }: { status: string; archived?: boolean; overdue?: boolean }) {
  if (archived) return <Badge tone="info">Archived</Badge>;
  const names: Record<string, string> = { planned: "Planned", scheduled: "Scheduled", in_progress: "In progress", reporting: "Reporting", completed: "Completed", cancelled: "Cancelled" };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Badge tone={STATUS_TONE[status] ?? "info"}>{names[status] ?? status}</Badge>
      {overdue && <Badge tone="fail">Overdue</Badge>}
    </span>
  );
}

export function Pager({ page, count, size, onPage }: { page: number; count: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / size));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 border-t border-line p-4">
      <span className="text-[14px] text-muted">Page {page} of {pages} · {count} total</span>
      <div className="flex gap-2">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </nav>
  );
}

/** Detail-page load failure. A 404 means missing or out of scope: the server does not say which. */
export function NotFoundOrError({ error, what, onRetry }: { error: unknown; what: string; onRetry: () => void }) {
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyState title={`${what} not found`} body="It may not exist, or you may not have access to it." />;
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}

/** Money in its own currency, never converted. Falls back to "1,234.50 CODE" for a code the browser does not know. */
export function money(amount: string | number, currency: string): string {
  const n = Number(amount);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n);
  } catch {
    return `${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
  }
}
