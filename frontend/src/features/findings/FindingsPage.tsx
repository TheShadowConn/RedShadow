import { PageHeader } from "../../design/ui";
import { FindingsList } from "./FindingsList";

export function FindingsPage() {
  return (
    <>
      <PageHeader title="Findings" lead="Vulnerabilities you are allowed to see, across engagements. Drafts are visible to the testing team only." />
      <FindingsList />
    </>
  );
}
