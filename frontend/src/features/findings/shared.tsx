import { Circle, Diamond, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { ApiError } from "../../api/client";
import { FINDING_STATUSES, SEVERITIES } from "../../api/types";
import { Badge, label } from "../../design/ui";

const SEV_ICON: Record<string, LucideIcon> = { critical: OctagonAlert, high: TriangleAlert, medium: Diamond, low: Circle, info: Info };

export function SeverityBadge({ severity, score }: { severity: string; score?: string | null }) {
  const Icon = SEV_ICON[severity] ?? Info;
  return (
    <span className="sev" data-sev={severity}>
      <Icon size={14} aria-hidden />
      {label(SEVERITIES, severity)}
      {score ? <span className="mono font-normal">{score}</span> : null}
    </span>
  );
}

const STATUS_TONE: Record<string, "ok" | "warn" | "fail" | "info"> = {
  draft: "info", open: "warn", in_progress: "warn", pending_verification: "warn", reopened: "fail",
  closed: "ok", risk_accepted: "info", false_positive: "info", duplicate: "info",
};

export function FindingStatus({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "info"}>{label(FINDING_STATUSES, status)}</Badge>;
}

/** User markdown, rendered without raw HTML or images. Links open in a new tab without a referrer. */
export function Markdown({ text, empty = "Nothing written yet." }: { text: string; empty?: string }) {
  if (!text.trim()) return <p className="m-0 text-muted">{empty}</p>;
  return (
    <div className="md">
      <ReactMarkdown
        skipHtml
        disallowedElements={["img"]}
        unwrapDisallowed
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export const isConflict = (e: unknown) => e instanceof ApiError && e.status === 409;

export const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);

export function userName(u: { display_name: string } | null | undefined, fallback = "Unassigned") {
  return u ? u.display_name : fallback;
}
