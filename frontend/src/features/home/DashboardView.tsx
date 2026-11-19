import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { type Dashboard, type DashboardKind, type DashEngagement, type DashFinding } from "../../api/types";
import { EmptyState, EngagementStatus, ErrorState, formatDate, formatDay, LoadingRows, money, PageHeader, Tabs } from "../../design/ui";
import { SeverityBadge } from "../findings/shared";
import { SeverityBars, StatusStrip, TrendChart } from "./charts";

const ACTIVE = "open,in_progress,pending_verification,reopened";
const TITLES: Record<DashboardKind, string> = { admin: "Administration", pentester: "Testing", remediation: "Remediation", vendor: "External testing" };
const LEADS: Record<DashboardKind, string> = {
  admin: "Everything across all engagements, from findings and deadlines to audit health.",
  pentester: "Your engagements, findings and retests.",
  remediation: "The findings assigned to you and when they are due.",
  vendor: "The findings you reported and imported, and your engagements.",
};

function Tile({ to, n, title, hint, tone }: { to: string; n: number | string; title: string; hint?: string; tone?: "fail" | "warn" }) {
  return (
    <Link to={to} className="card card-pad block transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      <span className="block text-[14px] text-muted">{title}</span>
      <span className={`mt-1 block text-[34px] leading-none font-semibold tabular-nums ${tone === "fail" && Number(n) > 0 ? "text-fail" : tone === "warn" && Number(n) > 0 ? "text-warn" : ""}`}>{n}</span>
      {hint && <span className="mt-2 block text-[14px] text-muted">{hint}</span>}
    </Link>
  );
}

/** Total engagement cost. Currencies are never converted into each other, so each gets its own line. */
function CostTile({ costs }: { costs: NonNullable<Dashboard["costs"]> }) {
  const [first, ...rest] = costs.totals;
  return (
    <Link to="/engagements" className="card card-pad block min-w-0 transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      <span className="block text-[14px] text-muted">Total engagement cost</span>
      {first ? (
        <>
          <span className="mt-1 block break-words text-[26px] leading-tight font-semibold tabular-nums">{money(first.total, first.currency)}</span>
          {rest.map((t) => <span key={t.currency} className="mt-1 block break-words text-[15px] font-medium tabular-nums">{money(t.total, t.currency)}</span>)}
          <span className="mt-2 block text-[14px] text-muted">{costs.totals.reduce((n, t) => n + t.lines, 0)} cost lines</span>
        </>
      ) : (
        <>
          <span className="mt-1 block text-[34px] leading-none font-semibold tabular-nums">0</span>
          <span className="mt-2 block text-[14px] text-muted">No cost recorded yet</span>
        </>
      )}
    </Link>
  );
}

function Panel({ title, children, wide, action }: { title: string; children: ReactNode; wide?: boolean; action?: ReactNode }) {
  return (
    <section className={`card card-pad ${wide ? "lg:col-span-2" : ""}`}>
      <div className="mb-4 flex items-center justify-between gap-3"><h2 className="text-xl">{title}</h2>{action}</div>
      {children}
    </section>
  );
}

const dueText = (d: string | null) => (d ? formatDay(d) : "No date");

function DueList({ rows }: { rows: DashFinding[] }) {
  const today = new Date().toISOString().slice(0, 10);
  if (!rows.length) return <p className="m-0 text-muted">Nothing is waiting for a fix.</p>;
  return (
    <ul className="m-0 list-none divide-y divide-line p-0">
      {rows.map((f) => (
        <li key={f.id}>
          <Link to={`/findings/${f.id}`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 py-3 hover:bg-raised">
            <SeverityBadge severity={f.severity} />
            <span className="min-w-0 flex-1 basis-48"><span className="mono text-[14px] text-muted">{f.ref}</span> {f.title}</span>
            <span className={`text-[14px] ${f.due_date && f.due_date < today ? "font-semibold text-fail" : "text-muted"}`}>{f.due_date && f.due_date < today ? "Overdue · " : ""}{dueText(f.due_date)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function EngagementList({ rows, empty }: { rows: DashEngagement[]; empty: string }) {
  if (!rows.length) return <p className="m-0 text-muted">{empty}</p>;
  return (
    <ul className="m-0 list-none divide-y divide-line p-0">
      {rows.map((e) => (
        <li key={e.id}>
          <Link to={`/engagements/${e.id}`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 py-3 hover:bg-raised">
            <span className="min-w-0 flex-1 basis-48"><span className="block font-medium">{e.name}</span><span className="block text-[14px] text-muted">{e.organisation} · {e.ref}</span></span>
            <span className="text-[14px] text-muted">{formatDay(e.start_date)} to {formatDay(e.end_date)}</span>
            <EngagementStatus status={e.status} overdue={e.overdue} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Sla({ d }: { d: Dashboard }) {
  const s = d.sla;
  return (
    <dl className="m-0 grid grid-cols-2 gap-4">
      <div><dt className="text-[14px] text-muted">Closed on time</dt><dd className="m-0 mt-1 text-[30px] leading-none font-semibold tabular-nums">{s.compliance_pct === null ? "n/a" : `${s.compliance_pct}%`}</dd><dd className="m-0 mt-1 text-[14px] text-muted">{s.dated ? `${s.on_time} of ${s.dated} with a due date` : "Nothing closed with a due date yet"}</dd></div>
      <div><dt className="text-[14px] text-muted">Time to close</dt><dd className="m-0 mt-1 text-[30px] leading-none font-semibold tabular-nums">{s.mean_days_to_close === null ? "n/a" : `${s.mean_days_to_close} d`}</dd><dd className="m-0 mt-1 text-[14px] text-muted">Average, last {s.window_days} days, {s.closed} closed</dd></div>
    </dl>
  );
}

const actionText = (a: string) => a.replace(/[._]/g, " ");

function Body({ d }: { d: Dashboard }) {
  const f = d.findings;
  const kind = d.kind;
  const empty = f.total === 0 && d.engagements.total === 0;
  return (
    <div className="space-y-6">
      <div className={`grid grid-cols-2 gap-4 ${kind === "admin" && d.costs ? "lg:grid-cols-3 xl:grid-cols-6" : "lg:grid-cols-5"}`}>
        {kind === "admin" && <>
          <Tile to={`/findings?status=${ACTIVE}`} n={f.open} title="Open findings" hint={`${f.total} in total`} />
          <Tile to="/remediation" n={f.overdue} title="Overdue" hint="Past the fix date" tone="fail" />
          <Tile to="/remediation" n={f.due_soon} title="Due in 7 days" tone="warn" />
          <Tile to="/verification" n={f.pending_verification} title="To verify" hint="Waiting for a retest" />
          <Tile to="/engagements" n={d.engagements.by_status.in_progress ?? 0} title="Engagements running" hint={`${d.engagements.total} active`} />
          {d.costs && <CostTile costs={d.costs} />}
        </>}
        {kind === "pentester" && <>
          <Tile to={`/findings?assigned=me&status=${ACTIVE}`} n={d.mine?.open ?? 0} title="My open findings" hint={`${f.open} across my engagements`} />
          <Tile to="/remediation" n={f.overdue} title="Overdue" hint={`${d.mine?.overdue ?? 0} assigned to me`} tone="fail" />
          <Tile to="/verification" n={f.pending_verification} title="To verify" hint="Waiting for a retest" />
          <Tile to="/findings?status=draft" n={f.drafts} title="Drafts" hint="Not yet published" />
          <Tile to="/retests" n={d.retests?.active_rounds ?? 0} title="Retest rounds" hint={`${d.retests?.items_pending ?? 0} findings to test`} />
        </>}
        {kind === "vendor" && <>
          <Tile to={`/findings?status=${ACTIVE}`} n={d.mine?.open ?? 0} title="My open findings" hint={`${f.total} reported by me in total`} />
          <Tile to="/findings?status=draft" n={f.drafts} title="Drafts" hint="Publish when ready" />
          <Tile to={`/findings?status=${ACTIVE}`} n={d.mine?.overdue ?? 0} title="Overdue" hint="Past the fix date" tone="fail" />
          <Tile to="/imports" n={f.total} title="Findings uploaded" hint="Import a CSV for more" />
          <Tile to="/retests" n={d.retests?.active_rounds ?? 0} title="Retest rounds" hint={`${d.retests?.items_pending ?? 0} findings to test`} />
        </>}
        {kind === "remediation" && <>
          <Tile to="/remediation" n={f.open} title="To work on" hint={`${f.total} assigned in total`} />
          <Tile to="/remediation" n={f.overdue} title="Overdue" hint="Past the fix date" tone="fail" />
          <Tile to="/remediation" n={f.due_soon} title="Due in 7 days" tone="warn" />
          <Tile to="/findings?status=pending_verification" n={f.pending_verification} title="Awaiting verification" hint="Submitted by you" />
          <Tile to="/findings?status=closed" n={d.recently_closed ?? 0} title="Closed, last 30 days" />
        </>}
      </div>
      {empty && <div className="card"><EmptyState title="Nothing to show yet" body={kind === "remediation" ? "Findings assigned to you appear here once they are published." : kind === "vendor" ? "Findings you report or import on your engagements appear here." : "Create an engagement and add findings to see numbers here."} /></div>}
      {!empty && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title="Open by severity"><SeverityBars counts={f.open_by_severity} mine={false} /></Panel>
          <Panel title="All findings by status"><StatusStrip counts={f.by_status} /></Panel>
          <Panel title="Opened and closed, last 12 weeks" wide><TrendChart data={d.trend} /></Panel>
          <Panel title="Next due" action={kind === "vendor" ? undefined : <Link to="/remediation" className="inline-flex min-h-11 items-center text-accent hover:underline">Open queue</Link>}><DueList rows={d.next_due} /></Panel>
          <Panel title="Fix deadlines"><Sla d={d} /></Panel>
          {kind !== "remediation" && <Panel title="Starting soon" action={<Link to="/calendar" className="inline-flex min-h-11 items-center text-accent hover:underline">Calendar</Link>}><EngagementList rows={d.engagements.upcoming} empty="No engagements start in the next 30 days." /></Panel>}
          {kind !== "remediation" && <Panel title="In progress"><EngagementList rows={d.engagements.in_progress} empty="No engagement is running." /></Panel>}
          {(kind === "pentester" || kind === "vendor") && d.retests && (
            <Panel title="My retests" action={<Link to="/retests" className="inline-flex min-h-11 items-center text-accent hover:underline">All retests</Link>}>
              {d.retests.rounds.length === 0 ? <p className="m-0 text-muted">No retest round is waiting for you.</p> : (
                <ul className="m-0 list-none divide-y divide-line p-0">{d.retests.rounds.map((r) => <li key={r.id}><Link to={`/retests/${r.id}`} className="flex min-h-11 items-center justify-between gap-3 py-3 hover:bg-raised"><span><span className="mono">{r.ref}</span> <span className="text-muted">{r.engagement.ref}</span></span><span className="text-[14px] text-muted">{r.pending} to test</span></Link></li>)}</ul>
              )}
            </Panel>
          )}
          {kind === "admin" && d.costs && (
            <Panel title="Engagement cost" wide>
              {d.costs.totals.length === 0 ? <p className="m-0 text-muted">No cost recorded yet. Add cost lines on an engagement's Cost tab.</p> : (
                <div className="grid gap-6 md:grid-cols-2">
                  <div>
                    <h3 className="mb-2 text-[14px] font-medium text-muted">Total by currency</h3>
                    <ul className="m-0 list-none divide-y divide-line p-0">{d.costs.totals.map((t) => <li key={t.currency} className="flex min-h-11 items-center justify-between gap-3 py-2"><span><span className="mono font-medium">{t.currency}</span> <span className="text-[14px] text-muted">{t.lines} {t.lines === 1 ? "line" : "lines"}</span></span><span className="mono text-[20px] font-semibold">{money(t.total, t.currency)}</span></li>)}</ul>
                  </div>
                  <div>
                    <h3 className="mb-2 text-[14px] font-medium text-muted">Highest-cost engagements</h3>
                    <ul className="m-0 list-none divide-y divide-line p-0">{d.costs.top.map((r) => <li key={`${r.engagement.id}${r.currency}`}><Link to={`/engagements/${r.engagement.id}`} className="flex min-h-11 items-center justify-between gap-3 py-2 hover:bg-raised"><span className="min-w-0"><span className="mono text-[14px] text-muted">{r.engagement.ref}</span> <span className="font-medium">{r.engagement.name}</span></span><span className="mono shrink-0">{money(r.total, r.currency)}</span></Link></li>)}</ul>
                  </div>
                </div>
              )}
            </Panel>
          )}
          {kind === "admin" && d.top_organisations && (
            <Panel title="Most critical exposure">
              {d.top_organisations.length === 0 ? <p className="m-0 text-muted">No open critical or high findings.</p> : (
                <ul className="m-0 list-none divide-y divide-line p-0">{d.top_organisations.map((o) => <li key={o.id}><Link to={`/organisations/${o.id}`} className="flex min-h-11 items-center justify-between gap-3 py-3 hover:bg-raised"><span className="font-medium">{o.name}</span><span className="flex gap-3 text-[14px]"><span className="text-fail">{o.critical} critical</span><span className="text-warn">{o.high} high</span></span></Link></li>)}</ul>
              )}
            </Panel>
          )}
          {d.activity.length > 0 && (
            <Panel title="Recent activity" wide>
              <ul className="m-0 list-none divide-y divide-line p-0">
                {d.activity.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
                    <span className="min-w-0 flex-1 basis-56"><span className="font-medium">{actionText(e.action)}</span>{e.entity_label ? <span className="text-muted"> · {e.entity_label}</span> : null}</span>
                    <span className="text-[14px] text-muted">{e.actor || "System"}{e.engagement_ref ? ` · ${e.engagement_ref}` : ""} · {formatDate(e.at)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}

/** The role dashboards. Users who hold more than one (a custom role, or Super Admin) get tabs. */
export function DashboardView({ kinds }: { kinds: DashboardKind[] }) {
  const { me } = useAuth();
  const [kind, setKind] = useState<DashboardKind>(kinds[0]);
  const q = useQuery({ queryKey: ["dashboard", kind], queryFn: () => api<Dashboard>("GET", `/dashboards/${kind}`), refetchInterval: 60_000 });
  const first = me?.display_name.split(" ")[0] ?? "";
  const integrity = q.data?.integrity;
  return (
    <>
      <PageHeader title={`Welcome, ${first}`} lead={LEADS[kind]} actions={integrity && integrity.status !== "ok" ? <Link to="/audit" className="btn btn-danger">Audit chain needs attention</Link> : undefined} />
      {kinds.length > 1 && <Tabs label="Dashboards" value={kind} onChange={setKind} tabs={kinds.map((k) => ({ id: k, label: TITLES[k] }))} />}
      <div className={kinds.length > 1 ? "mt-6" : ""} role={kinds.length > 1 ? "tabpanel" : undefined} id={kinds.length > 1 ? `panel-${kind}` : undefined} aria-labelledby={kinds.length > 1 ? `tab-${kind}` : undefined}>
        {q.isPending && <LoadingRows rows={4} />}
        {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
        {q.data && <Body d={q.data} />}
      </div>
    </>
  );
}

