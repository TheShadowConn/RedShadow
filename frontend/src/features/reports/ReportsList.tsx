import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, FileText, Plus, Table2 } from "lucide-react";
import { Link } from "react-router-dom";

import { api, downloadFile } from "../../api/client";
import type { ReportJob, Page } from "../../api/types";
import { Button, EmptyState, ErrorNote, ErrorState, LoadingRows, Pager, formatBytes, formatDate } from "../../design/ui";
import { GenerateReportDialog } from "./GenerateReportDialog";
import { ReportStatus, WORKING } from "./shared";

const PAGE_SIZE = 25;

function Kind({ job }: { job: ReportJob }) {
  const Icon = job.format === "pdf" ? FileText : Table2;
  return <span className="inline-flex items-center gap-2"><Icon size={16} aria-hidden className="text-muted" />{job.format.toUpperCase()}<span className="text-muted">{job.audience === "internal" ? " · internal" : ""}</span></span>;
}

function detail(job: ReportJob): string {
  if (job.status === "failed") return job.error || "The report could not be built.";
  if (job.status === "done") {
    const bits = [`${job.finding_count} finding${job.finding_count === 1 ? "" : "s"}`];
    if (job.page_count) bits.push(`${job.page_count} pages`);
    bits.push(formatBytes(job.size));
    if (!job.file_available) return `${bits.join(", ")} · file expired`;
    return bits.join(", ");
  }
  return "Building the file. This takes a few seconds.";
}

/** Report history for one engagement or for everything the caller may see. */
export function ReportsList({ engagement, canCreate }: { engagement?: { id: string; permissions: string[] }; canCreate: boolean }) {
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const q = useQuery({
    queryKey: ["reports", engagement?.id ?? "all", page],
    queryFn: () => api<Page<ReportJob>>("GET", `/reports?page=${page}&page_size=${PAGE_SIZE}${engagement ? `&engagement=${engagement.id}` : ""}`),
    placeholderData: (p) => p,
    refetchInterval: (query) => (query.state.data?.results.some((j) => WORKING.includes(j.status)) ? 2500 : false),
  });
  const get = useMutation({ mutationFn: (j: ReportJob) => downloadFile(`/reports/${j.id}/download`, j.file_name || "report") });
  const rows = q.data?.results ?? [];
  const open = (j: ReportJob) => (j.status === "done" && j.file_available ? <Button size="sm" onClick={() => get.mutate(j)} loading={get.isPending && get.variables?.id === j.id}><Download size={16} aria-hidden /> Download</Button> : null);

  return (
    <section aria-label="Reports">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-muted">Reports are built in the background from the findings you can see. Files are kept for a limited time.</p>
        {canCreate && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} aria-hidden /> New report</Button>}
      </div>
      <ErrorNote error={get.error} />
      <div className="card overflow-hidden">
        {q.isPending && <LoadingRows />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && rows.length === 0 && <EmptyState title="No reports yet" body="Create a PDF for the client or a CSV for your own analysis." action={canCreate ? <Button variant="primary" onClick={() => setCreating(true)}>New report</Button> : undefined} />}
        {rows.length > 0 && (
          <>
            <table className="data-table hidden md:table">
              <thead><tr><th>Report</th>{!engagement && <th>Engagement</th>}<th>Status</th><th>Details</th><th>By</th><th>Created</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((j) => (
                  <tr key={j.id}>
                    <td><span className="block font-medium"><Kind job={j} /></span><span className="block text-[14px] text-muted">{j.title || j.template?.name || "Standard"} · v{j.version_label}</span></td>
                    {!engagement && <td><Link to={`/engagements/${j.engagement.id}`} className="hover:underline">{j.engagement.ref}</Link><span className="block text-[14px] text-muted">{j.engagement.name}</span></td>}
                    <td><ReportStatus status={j.status} /></td>
                    <td className="max-w-[22rem] text-[14px] text-muted">{detail(j)}</td>
                    <td>{j.requested_by.name}</td>
                    <td className="whitespace-nowrap text-muted">{formatDate(j.created_at)}</td>
                    <td className="text-right">{open(j)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((j) => (
                <li key={j.id} className="space-y-2 px-4 py-4">
                  <span className="flex flex-wrap items-center gap-2 font-medium"><Kind job={j} /><ReportStatus status={j.status} /></span>
                  {!engagement && <Link to={`/engagements/${j.engagement.id}`} className="block text-[15px] hover:underline">{j.engagement.ref} {j.engagement.name}</Link>}
                  <span className="block text-[14px] text-muted">{detail(j)}</span>
                  <span className="block text-[14px] text-muted">{j.requested_by.name} · {formatDate(j.created_at)}</span>
                  {open(j)}
                </li>
              ))}
            </ul>
            <Pager page={page} count={q.data!.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>
      <GenerateReportDialog key={creating ? "open" : "closed"} engagement={engagement} open={creating} onClose={() => setCreating(false)} />
    </section>
  );
}
