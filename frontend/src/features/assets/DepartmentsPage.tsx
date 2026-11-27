import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { SEVERITIES, type Organisation, type Page } from "../../api/types";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Select } from "../../design/ui";

type Row = {
  tag: string | null;
  assets: number;
  open: number;
  open_by_severity: Record<string, number>;
  overdue: number;
  due_soon: number;
  risk_accepted: number;
};
type Overview = { rows: Row[]; total: Row; open_statuses: string[] };

function Count({ n, to }: { n: number; to?: string }) {
  if (n === 0 || !to) return <span className={n === 0 ? "text-muted" : undefined}>{n}</span>;
  return <Link to={to} className="inline-flex min-h-8 min-w-8 items-center justify-end text-accent underline">{n}</Link>;
}

/** Findings per department (asset tag). Numbers link to the findings behind them. */
export function DepartmentsPage() {
  const { can } = useAuth();
  const [organisation, setOrganisation] = useState("");
  const orgs = useQuery({ queryKey: ["organisations-pick"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100&archived=all"), enabled: can("organisations.view") });
  const q = useQuery({ queryKey: ["assets", "departments", organisation], queryFn: () => api<Overview>("GET", `/assets/departments${organisation ? `?organisation=${organisation}` : ""}`) });
  const data = q.data;

  // The findings list has no organisation filter, so numbers are links only while all organisations are shown.
  const link = (row: Row, extra: Record<string, string>) => {
    if (organisation || !can("findings.view")) return undefined;
    const p = new URLSearchParams(extra);
    if (row.tag === null) p.set("untagged", "true");
    else p.set("tag", row.tag);
    return `/findings?${p}`;
  };
  const open = data?.open_statuses.join(",") ?? "";

  const cells = (r: Row, linked: boolean) => (
    <>
      <td className="num">{r.assets}</td>
      <td className="num"><Count n={r.open} to={linked ? link(r, { status: open }) : undefined} /></td>
      {SEVERITIES.map(([k]) => <td key={k} className="num"><Count n={r.open_by_severity[k] ?? 0} to={linked ? link(r, { status: open, severity: k }) : undefined} /></td>)}
      <td className="num">{r.overdue > 0 ? <span className="font-medium text-fail">{r.overdue}</span> : <span className="text-muted">0</span>}</td>
      <td className="num">{r.due_soon}</td>
      <td className="num"><Count n={r.risk_accepted} to={linked ? link(r, { status: "risk_accepted" }) : undefined} /></td>
    </>
  );

  return (
    <>
      <PageHeader title="Departments" lead="Open findings for each department, taken from the tags on your assets. An asset with two tags counts in both rows; the total counts it once." />
      <div className="card overflow-hidden">
        {can("organisations.view") && (
          <div className="border-b border-line p-4">
            <Select aria-label="Organisation" className="sm:max-w-xs" value={organisation} onChange={(e) => setOrganisation(e.target.value)}>
              <option value="">All organisations</option>
              {orgs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </div>
        )}
        {q.isPending && <LoadingRows rows={4} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {data && data.rows.length === 0 && <EmptyState title="Nothing to show yet" body="Add tags to your assets to see findings by department." />}
        {data && data.rows.length > 0 && (
          <div className="table-scroll">
            <table className="data-table min-w-[860px]">
              <thead>
                <tr>
                  <th>Department</th>
                  <th className="!text-right">Assets</th>
                  <th className="!text-right">Open</th>
                  {SEVERITIES.map(([k, v]) => <th key={k} className="!text-right">{v}</th>)}
                  <th className="!text-right">Overdue</th>
                  <th className="!text-right">Due in 7 days</th>
                  <th className="!text-right">Risk accepted</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.tag ?? ""} className="!cursor-default">
                    <td className="wrap font-medium">
                      {can("assets.view") ? <Link className="inline-flex min-h-8 items-center hover:underline" to={`/assets?${r.tag === null ? "untagged=true" : `tag=${encodeURIComponent(r.tag)}`}`}>{r.tag ?? "Untagged"}</Link> : (r.tag ?? "Untagged")}
                    </td>
                    {cells(r, true)}
                  </tr>
                ))}
                <tr className="!cursor-default font-semibold">
                  <td>Total</td>
                  {cells(data.total, false)}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
