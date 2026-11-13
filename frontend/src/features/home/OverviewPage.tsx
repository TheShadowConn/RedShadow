import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, XCircle } from "lucide-react";

import { useAuth } from "../../api/auth";
import { fetchReadiness, type Readiness } from "../../api/client";
import type { DashboardKind } from "../../api/types";
import { Button, PageHeader, Skeleton } from "../../design/ui";
import { DashboardView } from "./DashboardView";

function useReadiness() {
  const [state, setState] = useState<{ s: "loading" } | { s: "done"; data: Readiness } | { s: "error" }>({ s: "loading" });
  const [n, setN] = useState(0);
  useEffect(() => {
    const ctl = new AbortController();
    setState({ s: "loading" });
    fetchReadiness(ctl.signal)
      .then((data) => setState({ s: "done", data }))
      .catch(() => !ctl.signal.aborted && setState({ s: "error" }));
    return () => ctl.abort();
  }, [n]);
  return { state, retry: () => setN((x) => x + 1) };
}

/** Role dashboards when the user holds one; otherwise the plain access and status page. */
export function OverviewPage() {
  const { can } = useAuth();
  const kinds = (["admin", "pentester", "remediation", "vendor"] as DashboardKind[]).filter((k) => can(`dashboards.${k}`));
  if (kinds.length === 0) return <Plain />;
  return (
    <>
      <DashboardView kinds={kinds} />
      {can("users.view") && <div className="mt-8"><Plain compact /></div>}
    </>
  );
}

function Plain({ compact }: { compact?: boolean }) {
  const { me, can } = useAuth();
  const { state, retry } = useReadiness();
  const first = me?.display_name.split(" ")[0] ?? "";

  return (
    <>
      {!compact && <PageHeader title={`Welcome, ${first}`} lead="Your access and the state of the platform." />}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card card-pad" aria-labelledby="access-h">
          <h2 id="access-h" className="text-xl">Your access</h2>
          <dl className="m-0 mt-4 divide-y divide-line">
            <Row k="Role" v={me?.role.name} />
            <Row k="Engagements" v={me?.role.all_engagements ? "All engagements" : "Assigned engagements only"} />
            <Row k="Two-step verification" v={me?.mfa_enabled ? "On" : "Off"} />
            <Row k="Permissions" v={`${me?.permissions.length ?? 0} granted`} />
          </dl>
          <div className="mt-6 flex flex-wrap gap-3">
            {can("users.view") && (
              <Link to="/users" className="btn btn-primary">
                Manage users <ArrowRight size={18} aria-hidden />
              </Link>
            )}
            {can("roles.view") && (
              <Link to="/roles" className="btn btn-secondary">
                Manage roles
              </Link>
            )}
          </div>
        </section>

        <section className="card card-pad" aria-labelledby="status-h">
          <h2 id="status-h" className="text-xl">System status</h2>
          {state.s === "loading" && (
            <div className="mt-4 space-y-3" aria-busy="true" aria-label="Checking services">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-2/3" />
            </div>
          )}
          {state.s === "done" && (
            <ul className="m-0 mt-2 list-none p-0">
              {Object.entries(state.data.checks).map(([name, v]) => (
                <li key={name} className="flex items-center justify-between border-b border-line py-3 last:border-0">
                  <span className="capitalize">{name}</span>
                  <span className={`inline-flex items-center gap-2 ${v === "ok" ? "text-ok" : "text-fail"}`}>
                    {v === "ok" ? <CheckCircle2 size={18} aria-hidden /> : <XCircle size={18} aria-hidden />}
                    {v === "ok" ? "Operational" : "Unavailable"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {state.s === "error" && <p className="mt-4 text-fail" role="alert">Cannot reach the API.</p>}
          <Button className="mt-4" size="sm" onClick={retry}>Check again</Button>
        </section>
      </div>
    </>
  );
}

function Row({ k, v }: { k: string; v?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-muted">{k}</dt>
      <dd className="m-0 text-right">{v}</dd>
    </div>
  );
}
