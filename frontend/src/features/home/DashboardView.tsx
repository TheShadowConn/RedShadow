import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { type Dashboard, type DashboardKind, type DashEngagement, type DashFinding } from "../../api/types";
import { EmptyState, EngagementStatus, ErrorState, formatDate, formatDay, LoadingRows, money, PageHeader, Tabs } from "../../design/ui";
import { ScenarioProgress } from "../engagements/ScenariosTab";
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

const TILE = "card card-pad flex h-full min-w-0 flex-col transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

/**
 * One stat card. Every card has the same three parts at the same heights (two-line title slot, value slot, hint
 * pinned to the bottom), so numbers line up across a row at any width. The grid stretches cards to equal height.
 */
function Stat({ to, title, value, hint, tone }: { to: string; title: string; value: ReactNode; hint?: ReactNode; tone?: "fail" | "warn" }) {
  return (
    <Link to={to} className={TILE}>
      <span className="block min-h-[2.5rem] text-[14px] leading-snug text-muted [overflow-wrap:anywhere]">{title}</span>
      <span className={`flex min-h-10 items-center text-[30px] leading-none font-semibold tabular-nums [overflow-wrap:anywhere] sm:text-[32px] ${tone === "fail" ? "text-fail" : tone === "warn" ? "text-warn" : ""}`}>{value}</span>
      <span className="mt-auto block pt-3 text-[14px] leading-snug text-muted [overflow-wrap:anywhere]">{hint ?? "\u00a0"}</span>
    </Link>
  );
}

function Tile({ to, n, title, hint, tone }: { to: string; n: number | string; title: string; hint?: ReactNode; tone?: "fail" | "warn" }) {
  return <Stat to={to} title={title} value={n} hint={hint} tone={Number(n) > 0 ? tone : undefined} />;
}

/** Engagements running: the count, plus which engagement it is (names, not just a number). */
function RunningTile({ d }: { d: Dashboard }) {
  const rows = d.engagements.in_progress;
  const n = d.engagements.by_status.in_progress ?? 0;
  const hint = rows.length === 0 ? `${d.engagements.total} active` : (
    <>
      <span className="block font-medium text-ink">{rows[0].name}</span>
      {n > 1 && <span className="block">and {n - 1} more</span>}
    </>
  );
  return <Stat to="/engagements" title="Engagements running" value={n} hint={hint} />;
}

/** Total engagement cost. Currencies are never converted into each other, so each gets its own line. */
function CostTile({ costs }: { costs: NonNullable<Dashboard["costs"]> }) {
  const [first, ...rest] = costs.totals;
  const lines = costs.totals.reduce((n, t) => n + t.lines, 0);
  return (
    <Stat
      to="/costs"
      title="Total engagement cost"
      value={first ? <span className="text-[19px] leading-tight whitespace-nowrap sm:text-[20px]">{money(first.total, first.currency)}</span> : 0}
      hint={first ? (
        <>
          {rest.map((t) => <span key={t.currency} className="block font-medium tabular-nums text-ink">{money(t.total, t.currency)}</span>)}
          <span className="block">{lines} cost lines</span>
        </>
      ) : "No cost recorded yet"}
    />
  );
}

/** Engagements in testing, each with the scenarios running inside it. */
function RunningNow({ d }: { d: Dashboard }) {
  const eng = d.engagements.in_progress;
  const byEng = new Map<string, NonNullable<Dashboard["scenarios"]>["running"]>();
  for (const s of d.scenarios?.running ?? []) byEng.set(s.engagement.id, [...(byEng.get(s.engagement.id) ?? []), s]);
  if (!eng.length) return <p className="m-0 text-muted">No engagement is running.</p>;
  return (
    <ul className="m-0 list-none divide-y divide-line p-0">
      {eng.map((e) => {
        const scenarios = byEng.get(e.id) ?? [];
        return (
          <li key={e.id} className="py-3">
            <Link to={`/engagements/${e.id}`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 hover:bg-raised">
              <span className="min-w-0 flex-1 basis-48"><span className="block font-medium [overflow-wrap:anywhere]">{e.name}</span><span className="block text-[14px] text-muted [overflow-wrap:anywhere]">{e.organisation} · {e.ref}</span></span>
              <span className="text-[14px] text-muted">{formatDay(e.start_date)} to {formatDay(e.end_date)}</span>
              <EngagementStatus status={e.status} overdue={e.overdue} />
            </Link>
            {scenarios.length > 0 && (
              <ul className="m-0 mt-2 ml-1 list-none space-y-1 border-l-2 border-line p-0 pl-4">
                {scenarios.map((s) => (
                  <li key={s.id}>
                    <Link to={`/engagements/${e.id}?tab=scenarios`} className="flex min-h-9 flex-wrap items-center gap-x-3 gap-y-1 hover:bg-raised">
                      <span className="min-w-0 flex-1 basis-40 text-[15px] [overflow-wrap:anywhere]"><span className="text-muted">Scenario · </span>{s.name}</span>
                      <span className={`text-[14px] ${s.overdue ? "font-semibold text-fail" : "text-muted"}`}>{s.overdue ? "Overdue · " : ""}{s.planned_end ? `ends ${formatDay(s.planned_end)}` : "No end date"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
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
      <div className={`grid grid-cols-2 gap-3 sm:gap-4 [&>:last-child:nth-child(odd)]:col-span-2 ${kind === "admin" && d.costs ? "lg:grid-cols-3 lg:[&>:last-child:nth-child(odd)]:col-span-1 xl:grid-cols-6" : "lg:grid-cols-5 lg:[&>:last-child:nth-child(odd)]:col-span-1"}`}>
        {kind === "admin" && <>
          <Tile to={`/findings?status=${ACTIVE}`} n={f.open} title="Open findings" hint={`${f.total} in total`} />
          <Tile to="/remediation" n={f.overdue} title="Overdue" hint="Past the fix date" tone="fail" />
          <Tile to="/remediation" n={f.due_soon} title="Due in 7 days" tone="warn" />
          <Tile to="/verification" n={f.pending_verification} title="To verify" hint="Waiting for a retest" />
          <RunningTile d={d} />
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
        <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
          <Panel title="Open by severity"><SeverityBars counts={f.open_by_severity} mine={false} /></Panel>
          <Panel title="All findings by status"><StatusStrip counts={f.by_status} /></Panel>
          <Panel title="Opened and closed, last 12 weeks" wide><TrendChart data={d.trend} /></Panel>
          {kind === "pentester" && d.scenarios?.this_week && (
            <Panel title="Scenarios this week" wide action={<Link to="/calendar?view=week" className="inline-flex min-h-11 items-center text-accent hover:underline">Open week</Link>}>
              <p className="m-0 mb-3 text-[14px] text-muted">{formatDay(d.scenarios.this_week.from)} to {formatDay(d.scenarios.this_week.to)}</p>
              {d.scenarios.this_week.items.length === 0 ? <p className="m-0 text-muted">No scenarios are planned for this week.</p> : (
                <ul className="m-0 list-none divide-y divide-line p-0">
                  {d.scenarios.this_week.items.map((s) => (
                    <li key={s.id}>
                      <Link to={`/engagements/${s.engagement.id}?tab=scenarios`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 py-3 hover:bg-raised">
                        <span className="min-w-0 flex-1 basis-48"><span className="block font-medium">{s.name}</span><span className="block text-[14px] text-muted"><span className="mono">{s.engagement.ref}</span> · {s.engagement.name}</span></span>
                        <span className="text-[14px] text-muted">{s.status === "in_progress" ? "In progress · " : s.status === "deferred" ? "Deferred · " : ""}{s.planned_start ? formatDay(s.planned_start) : ""}{s.planned_end && s.planned_end !== s.planned_start ? ` to ${formatDay(s.planned_end)}` : ""}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
          <Panel title="Next due" action={kind === "vendor" ? undefined : <Link to="/remediation" className="inline-flex min-h-11 items-center text-accent hover:underline">Open queue</Link>}><DueList rows={d.next_due} /></Panel>
          <Panel title="Fix deadlines"><Sla d={d} /></Panel>
          {kind !== "remediation" && <Panel title="Starting soon" action={<Link to="/calendar" className="inline-flex min-h-11 items-center text-accent hover:underline">Calendar</Link>}><EngagementList rows={d.engagements.upcoming} empty="No engagements start in the next 30 days." /></Panel>}
          {kind !== "remediation" && <Panel title="Running now" wide><RunningNow d={d} /></Panel>}
          {d.scenarios && d.scenarios.total > 0 && (
            <Panel title="Test scenarios" action={<Link to="/calendar" className="inline-flex min-h-11 items-center text-accent hover:underline">Calendar</Link>}>
              <ScenarioProgress s={{ total: d.scenarios.total, tested: d.scenarios.tested, planned: 0, in_progress: d.scenarios.in_progress, deferred: d.scenarios.deferred, cancelled: 0, overdue: d.scenarios.overdue, next_date: null }} />
              <dl className="m-0 mt-4 grid grid-cols-3 gap-3 text-center">
                <div><dt className="text-[13px] text-muted">Overdue</dt><dd className={`m-0 text-2xl font-semibold tabular-nums ${d.scenarios.overdue ? "text-fail" : ""}`}>{d.scenarios.overdue}</dd></div>
                <div><dt className="text-[13px] text-muted">Starting in 7 days</dt><dd className="m-0 text-2xl font-semibold tabular-nums">{d.scenarios.starting_soon}</dd></div>
                <div><dt className="text-[13px] text-muted">Deferred</dt><dd className="m-0 text-2xl font-semibold tabular-nums">{d.scenarios.deferred}</dd></div>
              </dl>
              {d.scenarios.items.length > 0 && (
                <ul className="m-0 mt-5 list-none divide-y divide-line border-t border-line p-0">
                  {d.scenarios.items.map((s) => (
                    <li key={s.id}>
                      <Link to={`/engagements/${s.engagement.id}?tab=scenarios`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 py-3 hover:bg-raised">
                        <span className="min-w-0 flex-1 basis-48"><span className="block font-medium">{s.name}</span><span className="block text-[14px] text-muted"><span className="mono">{s.engagement.ref}</span> · {s.engagement.name}</span></span>
                        <span className={`text-[14px] ${s.overdue ? "font-semibold text-fail" : "text-muted"}`}>{s.overdue ? "Overdue · " : s.status === "deferred" ? "Deferred · " : ""}{s.planned_start ? formatDay(s.planned_start) : "No date"}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
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
      <PageHeader title={`Welcome, ${first}`} lead={LEADS[kind]} actions={integrity && integrity.status !== "ok" ? <Link to="/audit" className="btn btn-danger">Audit chain needs attention</Link> : kind === "remediation" ? <Link to="/remediation" className="btn btn-primary">Open my queue</Link> : undefined} />
      {kinds.length > 1 && <Tabs label="Dashboards" value={kind} onChange={setKind} tabs={kinds.map((k) => ({ id: k, label: TITLES[k] }))} />}
      <div className={kinds.length > 1 ? "mt-6" : ""} role={kinds.length > 1 ? "tabpanel" : undefined} id={kinds.length > 1 ? `panel-${kind}` : undefined} aria-labelledby={kinds.length > 1 ? `tab-${kind}` : undefined}>
        {q.isPending && <LoadingRows rows={4} />}
        {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
        {q.data && <Body d={q.data} />}
      </div>
    </>
  );
}

