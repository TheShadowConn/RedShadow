import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import type { IntegrityState } from "../../api/types";

/** Shell banner for Super Admin: shown only while the last finished check failed. */
export function IntegrityBanner() {
  const { can } = useAuth();
  const q = useQuery({
    queryKey: ["audit-integrity"],
    queryFn: () => api<IntegrityState>("GET", "/audit/integrity"),
    enabled: can("audit.verify_integrity"),
    refetchInterval: 5 * 60_000,
  });
  if (!q.data?.broken) return null;
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 bg-fail px-4 py-3 text-on-accent md:px-8">
      <span className="font-medium">The audit log failed its integrity check. Records after event #{q.data.last_finished?.first_bad_id} cannot be trusted.</span>
      <Link to="/audit" className="underline">Open audit</Link>
    </div>
  );
}
