import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";

import { api } from "../../api/client";
import { Credit } from "../../design/Credit";
import { Logo } from "../../design/Logo";
import { Badge, formatBytes, formatDate, PageHeader } from "../../design/ui";

type Backup = { status: "ok" | "stale" | "none"; last_at: string | null; name: string; size_bytes: number; age_days: number | null; warn_after_days: number };
type About = { name: string; version: string; build: string; build_date: string; django: string; python: string; backup: Backup | null };

const GITHUB = "https://github.com/TheShadowConn";

export function AboutPage() {
  const q = useQuery({ queryKey: ["about"], queryFn: () => api<About>("GET", "/about"), staleTime: Infinity });
  const a = q.data;
  return (
    <>
      <PageHeader title="About" lead="Version, build and who made RedShadow." />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card card-pad" aria-labelledby="about-app-h">
          <Logo height={34} className="mb-6 text-ink" />
          <h2 id="about-app-h" className="sr-only">Application</h2>
          <p className="m-0 mb-5 text-muted">Pentest management platform: engagements, findings, evidence, remediation, audit and reporting in one self-hosted application.</p>
          {q.isError && <p role="alert" className="m-0 text-muted">Build details are not available right now.</p>}
          {a && (
            <dl className="m-0 grid gap-x-8 gap-y-3 sm:grid-cols-2">
              <div><dt className="label">Version</dt><dd className="m-0">{a.version}</dd></div>
              <div><dt className="label">Build</dt><dd className="m-0 font-mono text-[15px]">{a.build}</dd></div>
              <div><dt className="label">Build date</dt><dd className="m-0">{a.build_date || "Not recorded"}</dd></div>
              <div><dt className="label">Runtime</dt><dd className="m-0">Python {a.python}, Django {a.django}</dd></div>
            </dl>
          )}
        </section>

        <section className="card card-pad" aria-labelledby="about-maker-h">
          <h2 id="about-maker-h" className="mb-5 text-xl">Creator</h2>
          <div className="mb-5 text-ink"><Credit size="lg" /></div>
          <p className="m-0 mb-5 text-muted">Designed and built by Shadowconn.</p>
          <a href={GITHUB} target="_blank" rel="noopener noreferrer" className="btn btn-secondary inline-flex items-center gap-2">
            GitHub: TheShadowConn <ExternalLink size={16} aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </section>
        {a?.backup && (
          <section className="card card-pad lg:col-span-2" aria-labelledby="about-backup-h">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <h2 id="about-backup-h" className="text-xl">Backups</h2>
              <Badge tone={a.backup.status === "ok" ? "ok" : "warn"}>{a.backup.status === "ok" ? "Up to date" : a.backup.status === "stale" ? "Backup is old" : "No backup recorded"}</Badge>
            </div>
            {a.backup.last_at ? (
              <dl className="m-0 grid gap-x-8 gap-y-3 sm:grid-cols-3">
                <div><dt className="label">Last backup</dt><dd className="m-0">{formatDate(a.backup.last_at)}</dd></div>
                <div><dt className="label">Age</dt><dd className="m-0">{a.backup.age_days === 0 ? "Today" : `${a.backup.age_days} day${a.backup.age_days === 1 ? "" : "s"} ago`}</dd></div>
                <div><dt className="label">Size</dt><dd className="m-0">{formatBytes(a.backup.size_bytes)}</dd></div>
              </dl>
            ) : (
              <p className="m-0 text-muted">No backup has been recorded yet.</p>
            )}
            {a.backup.status !== "ok" && (
              <p className="m-0 mt-4 text-[15px]">
                {a.backup.status === "stale" ? `The newest backup is more than ${a.backup.warn_after_days} days old. ` : ""}
                Run <code className="mono">scripts/backup.sh</code> on the server, and copy the result somewhere safe off the machine.
              </p>
            )}
            <p className="m-0 mt-4 text-[14px] text-muted">Only Super Admins see this. The backup script records each finished backup here; the backup files themselves are never visible to the app.</p>
          </section>
        )}
      </div>
    </>
  );
}
