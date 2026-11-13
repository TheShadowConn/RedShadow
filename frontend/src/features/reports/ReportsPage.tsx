import { useAuth } from "../../api/auth";
import { PageHeader } from "../../design/ui";
import { ReportsList } from "./ReportsList";

export function ReportsPage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader title="Reports" lead="PDF reports for clients and CSV exports of findings, built from your own scope." />
      <ReportsList canCreate={can("reports.generate_pdf") || can("exports.csv")} />
    </>
  );
}
