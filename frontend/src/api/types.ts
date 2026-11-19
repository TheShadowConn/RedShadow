export type Restriction = "mfa_verify" | "password_change" | "mfa_setup" | null;

export type Me = {
  id: string;
  email: string;
  display_name: string;
  role: { id: string; name: string; all_engagements: boolean; finding_scope: string; mfa_required: boolean };
  mfa_enabled: boolean;
  must_change_password: boolean;
  session_idle_seconds?: number;
  restriction: Restriction;
  /** UX hints only. The backend enforces every permission. */
  permissions: string[];
};

export type RoleRef = { id: string; name: string };

export type User = {
  id: string;
  email: string;
  display_name: string;
  role: RoleRef;
  is_active: boolean;
  mfa_enabled: boolean;
  must_change_password: boolean;
  locked: boolean;
  last_login: string | null;
  last_password_change: string | null;
  created_at: string;
};

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type Role = {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  system_key: string | null;
  all_engagements: boolean;
  finding_scope: "all" | "assigned" | "own";
  mfa_required: boolean;
  permissions: string[];
  user_count: number;
};

export type Permission = {
  code: string;
  module: string;
  action: string;
  scope: "platform" | "engagement";
  description: string;
};

export type Organisation = {
  id: string;
  name: string;
  slug: string;
  industry: string;
  notes: string;
  logo_url: string | null;
  archived: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Contact = {
  id: string;
  organisation: string;
  name: string;
  email: string;
  phone: string;
  title: string;
  is_primary: boolean;
};

export const ASSET_TYPES = [
  ["web_app", "Web application"], ["api", "API"], ["host", "Host"], ["network_range", "Network range"],
  ["mobile_app", "Mobile application"], ["cloud_account", "Cloud account"], ["source_repo", "Source repository"],
  ["wireless", "Wireless network"], ["iot", "IoT or embedded device"], ["active_directory", "Active Directory"],
  ["thick_client", "Thick client"], ["other", "Other"],
] as const;
export const ENVIRONMENTS = [["prod", "Production"], ["staging", "Staging"], ["dev", "Development"]] as const;

export const IDENTIFIER_KINDS = [
  ["ip", "IP address"], ["cidr", "Network range"], ["hostname", "Hostname"], ["domain", "Domain"], ["url", "URL"],
  ["mac", "MAC address"], ["cloud_id", "Cloud resource ID"], ["repo", "Repository"], ["package", "App or package ID"], ["other", "Other"],
] as const;

export type AssetIdentifier = {
  id: string;
  kind: string;
  kind_label: string;
  value: string;
  normalized: string;
  is_primary: boolean;
  source: "manual" | "import" | "legacy";
  created_at: string;
};

export type Asset = {
  id: string;
  organisation: string;
  organisation_name: string;
  name: string;
  type: string;
  /** Display copy of the primary identifier. The list in `identifiers` is the real data. */
  identifier: string;
  identifiers: AssetIdentifier[];
  environment: string;
  criticality: number;
  tags: string[];
  archived: boolean;
  archived_at: string | null;
  onboarding_status: "onboarded" | "pending";
  origin: "manual" | "import";
  onboarded_at: string | null;
  engagement_count: number;
  created_at: string;
  updated_at: string;
};

export type AssetSummary = { total: number; onboarded: number; pending: number; archived: number };
export type AssetUsage = { engagements: number; findings: number; identifiers: number };
export type IdentifierCheck = {
  index: number;
  status: "free" | "owned" | "invalid";
  kind?: string;
  value?: string;
  normalized?: string;
  message?: string;
  asset?: { id: string; name: string };
};
export type DeletionImpact = {
  blockers: string[];
  removes: { memberships: number; saved_import_mappings: number };
  clears: { engagements_led: number; findings_assigned: number; findings_to_fix: number };
  history: Record<string, number>;
  mode: "remove" | "anonymise";
};

export const ENGAGEMENT_TYPES = [
  ["web", "Web"], ["api", "API"], ["mobile", "Mobile"], ["internal_network", "Internal network"],
  ["external_network", "External network"], ["cloud", "Cloud"], ["red_team", "Red team"],
  ["social_engineering", "Social engineering"], ["code_review", "Code review"], ["wireless", "Wireless"], ["other", "Other"],
] as const;

export const STATUSES = [
  ["planned", "Planned"], ["scheduled", "Scheduled"], ["in_progress", "In progress"],
  ["reporting", "Reporting"], ["completed", "Completed"], ["cancelled", "Cancelled"],
] as const;

/** Mirrors the backend state machine for button labels only. The server decides. */
export const TRANSITIONS: Record<string, string[]> = {
  planned: ["scheduled", "cancelled"],
  scheduled: ["planned", "in_progress", "cancelled"],
  in_progress: ["reporting", "cancelled"],
  reporting: ["in_progress", "completed"],
  completed: ["reporting"],
  cancelled: ["planned"],
};

export type UserRef = { id: string; display_name: string; email: string };

export type EngagementRow = {
  id: string;
  ref: string;
  organisation: { id: string; name: string };
  name: string;
  type: string;
  status: string;
  start_date: string;
  end_date: string;
  lead: UserRef | null;
  overdue: boolean;
  version: number;
  archived_at: string | null;
  deleted_at?: string | null;
};

export type Engagement = EngagementRow & {
  scope: string;
  out_of_scope: string;
  objectives: string;
  methodology: string;
  rules_of_engagement: string;
  permissions: string[];
};

export type Member = {
  id: string;
  user: UserRef;
  role: RoleRef;
  role_override: RoleRef | null;
  finding_scope: string;
  created_at: string;
};

export type ScopeLink = {
  id: string;
  asset: { id: string; name: string; type: string; identifier: string; identifiers: string[]; environment: string; criticality: number; archived: boolean };
  in_scope: boolean;
  notes: string;
};

export type Note = { id: string; author: UserRef; body: string; visibility: "team" | "all"; created_at: string };

export type Doc = {
  id: string;
  original_name: string;
  mime: string;
  size: number;
  sha256: string;
  uploaded_by: { id: string; display_name: string };
  download_url: string;
  created_at: string;
};

export type HistoryEvent = {
  id: number;
  occurred_at: string;
  actor_label: string;
  action: string;
  entity_type: string;
  entity_label: string;
  changes: Record<string, unknown>;
  outcome: string;
};

/** CVSS base score bands. Same rule as backend `apps/findings/cvss.py` (`BANDS`). */
export const SEVERITY_BANDS = [
  ["critical", "9.0 to 10.0"], ["high", "7.0 to 8.9"], ["medium", "4.0 to 6.9"], ["low", "0.1 to 3.9"], ["info", "0.0"],
] as const;

export const SEVERITIES = [["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"], ["info", "Info"]] as const;

export const FINDING_STATUSES = [
  ["draft", "Draft"], ["open", "Open"], ["in_progress", "In progress"], ["pending_verification", "Pending verification"],
  ["reopened", "Reopened"], ["closed", "Closed"], ["risk_accepted", "Risk accepted"], ["false_positive", "False positive"],
  ["duplicate", "Duplicate"],
] as const;

export type FindingRow = {
  id: string;
  ref: string;
  engagement: { id: string; ref: string; name: string };
  title: string;
  severity: string;
  cvss_score: string | null;
  status: string;
  asset: { id: string; name: string } | null;
  cwe_id: number | null;
  endpoint: string;
  assigned_pentester: UserRef | null;
  remediation_owner: UserRef | null;
  discovered_at: string;
  due_date: string | null;
  is_overdue: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Reference = { label: string; url: string };

export type Finding = FindingRow & {
  description: string;
  technical_details: string;
  poc: string;
  recommendation: string;
  references: Reference[];
  cvss_version: string;
  cvss_vector: string;
  cwe: { id: number; name: string } | null;
  reported_by: UserRef;
  duplicate_of: { id: string | null; ref: string; title: string } | null;
  permissions: string[];
  possible_duplicates: Array<{ id: string; ref: string; title: string; status: string }>;
  resolved_at: string | null;
  verified_at: string | null;
  verified_by: UserRef | null;
  closed_at: string | null;
  risk_accepted_until: string | null;
  risk_acceptance_reason: string;
  allowed_transitions: TransitionRule[];
};

/** A move the caller may make now. `needs` lists extra inputs: "expiry" or "duplicate_of". */
export type TransitionRule = { to: string; name: string; note_required: boolean; needs: Array<"expiry" | "duplicate_of"> };

export type Activity = {
  id: string;
  actor: UserRef | null;
  action: string;
  note: string;
  evidence_ids: string[];
  from_status: string;
  to_status: string;
  created_at: string;
};

export type QueueCounts = Record<string, number>;
export type QueueRow = FindingRow & {
  resolved_at: string | null;
  days_left: number | null;
  retest: { round_id: string; ref: string; assessor: UserRef } | null;
};
export type QueuePage = Page<QueueRow> & { counts: QueueCounts };

export type RetestItem = {
  id: string;
  finding: { id: string; ref: string; title: string; severity: string; status: string; version: number };
  result: "pending" | "passed" | "failed" | "not_tested";
  note: string;
  evidence_ids: string[];
  tested_by: UserRef | null;
  tested_at: string | null;
};

export type RetestRound = {
  id: string;
  ref: string;
  engagement: { id: string; ref: string; name: string };
  number: number;
  status: "queued" | "in_progress" | "completed" | "cancelled";
  note: string;
  requested_by: UserRef;
  assessor: UserRef;
  requested_at: string;
  completed_at: string | null;
  version: number;
  items: RetestItem[];
  counts: { pending: number; passed: number; failed: number; not_tested: number; total: number };
  can_record: boolean;
  can_manage: boolean;
};

export type FindingNote = { id: string; author: UserRef; kind: "technical" | "remediation" | "verification" | "retest"; visibility: "team" | "all"; body: string; created_at: string };

export type Evidence = Doc & { is_image: boolean; finding: string };

export type Template = {
  id: string;
  name: string;
  title: string;
  description: string;
  recommendation: string;
  severity: string;
  cvss_vector: string;
  cwe: { id: number; name: string } | null;
  references: Reference[];
  version: number;
};

export type Cwe = { id: number; name: string };

export type BulkResult = { results: Array<{ id: string; ok: boolean; error: { code: string; message: string } | null }>; succeeded: number; failed: number };

export type AuditEvent = {
  id: number;
  occurred_at: string;
  actor_id: string | null;
  actor_label: string;
  request_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  entity_label: string;
  engagement: { id: string; ref: string } | null;
  changes: Record<string, unknown>;
  metadata: Record<string, unknown>;
  outcome: "success" | "denied" | "failure";
  /** Super Admin only. */
  actor_ip?: string | null;
  user_agent?: string;
  hash?: string;
  prev_hash?: string;
};

export type AuditPage = { results: AuditEvent[]; has_more: boolean; next_before: number | null };

export type AuditFacets = {
  actions: string[];
  entity_types: string[];
  actors: Array<{ id: string; label: string }>;
  engagements: Array<{ id: string; ref: string; name: string }>;
  outcomes: string[];
};

export type IntegrityCheck = {
  id: number;
  status: "running" | "ok" | "failed" | "error";
  trigger: string;
  requested_by_label: string;
  started_at: string;
  finished_at: string | null;
  checked: number;
  first_bad_id: number | null;
  reason: string;
};

export type IntegrityState = { latest: IntegrityCheck | null; last_finished: IntegrityCheck | null; broken: boolean; events: number };

export type CalendarEvent = {
  id: string;
  ref: string;
  name: string;
  type: string;
  status: string;
  overdue: boolean;
  start_date: string;
  end_date: string;
  version: number;
  client: { id: string; name: string };
  lead: { id: string; display_name: string } | null;
  team: Array<{ id: string; display_name: string }>;
  findings: { total: number; active: number };
  conflicts: Array<{ user: { id: string; display_name: string }; with: { id: string; ref: string; name: string; start_date?: string; end_date?: string } }>;
};

export type RescheduleResult = { id: string; start_date: string; end_date: string; version: number; saved: boolean; conflicts: CalendarEvent["conflicts"] };

export const IMPORT_FIELDS = [
  ["title", "Title"], ["severity", "Severity"], ["cvss_vector", "CVSS vector"], ["description", "Description"],
  ["recommendation", "Recommendation"], ["technical_details", "Technical details"], ["poc", "Proof of concept"],
  ["endpoint", "Endpoint"], ["asset", "Asset"], ["cwe", "CWE"], ["discovered_at", "Discovered date"], ["references", "References"],
] as const;

export const IMPORT_STATUSES = [
  ["uploaded", "Uploaded"], ["parsing", "Reading file"], ["parsed", "Ready to map"], ["validating", "Checking rows"],
  ["previewed", "Ready to import"], ["importing", "Importing"], ["completed", "Completed"], ["failed", "Failed"], ["cancelled", "Cancelled"],
] as const;

export const ASSET_IMPORT_FIELDS = [
  ["name", "Name", "Optional: the first identifier is used when empty"],
  ["type", "Asset type", "Optional: guessed from the identifiers when empty"],
  ["environment", "Environment", "prod, staging or dev. Empty means production"],
  ["criticality", "Criticality", "1 to 5, or low, medium, high, critical"],
  ["tags", "Tags", "Separated by semicolons"],
  ["ip", "IP address", "One or more per cell"],
  ["hostname", "Hostname", "One or more per cell"],
  ["domain", "Domain", "One or more per cell"],
  ["url", "URL", "Full URLs, one or more per cell"],
  ["mac", "MAC address", ""],
  ["cloud_id", "Cloud resource ID", "ARN, account or subscription ID"],
  ["repo", "Repository", ""],
  ["identifiers", "Other identifiers", "Mixed values: the type of each is detected"],
] as const;
export const ASSET_IDENTIFIER_FIELDS = ["ip", "hostname", "domain", "url", "mac", "cloud_id", "repo", "identifiers"];

export type ImportAttempt = {
  number: number;
  original_name: string;
  file_sha256: string;
  file_size: number;
  counts: ImportJob["counts"];
  outcome: "in_progress" | "completed" | "failed" | "cancelled" | "superseded";
  error: string;
  uploaded_by: { id: string; display_name: string };
  created_at: string;
  finished_at: string | null;
};

export type ImportJob = {
  id: string;
  kind: "findings" | "assets";
  engagement: { id: string; ref: string; name: string } | null;
  organisation: { id: string; name: string } | null;
  attempt: number;
  can_delete: boolean;
  can_reupload: boolean;
  can_retry: boolean;
  original_name: string;
  file_size: number;
  file_sha256: string;
  encoding: string;
  delimiter: string;
  headers: string[];
  sample: string[][];
  status: (typeof IMPORT_STATUSES)[number][0];
  mapping: { column_map?: Record<string, string>; value_map?: { severity?: Record<string, string> } };
  mode: string;
  duplicates: string;
  counts: {
    total?: number; valid?: number; invalid?: number; duplicate?: number; imported?: number; skipped?: number;
    created?: number; merged?: number; to_create?: number; to_merge?: number;
  };
  error: string;
  uploaded_by: { id: string; display_name: string };
  suggested_mapping: Record<string, string>;
  file_available: boolean;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  version: number;
};

export type ImportRow = {
  id: number;
  row_number: number;
  status: "pending" | "valid" | "invalid" | "duplicate" | "skipped" | "imported";
  title: string;
  severity: string;
  cells: Record<string, string>;
  errors: Array<{ field: string; code: string; message: string }>;
  duplicate_of: { line?: number; finding?: { id: string; ref: string; title: string }; hidden?: boolean } | null;
  finding: { id: string; ref: string } | null;
  asset: {
    action: "create" | "merge" | "merge_in_file" | "known" | "known_in_file" | "";
    identifiers: Array<{ kind: string; value: string }>;
    new_identifiers: number;
    type: string | null;
    asset: { id: string; name: string } | null;
    target_line: number | null;
  } | null;
};

export type SavedMapping = { id: string; name: string; column_map: Record<string, string>; value_map: Record<string, Record<string, string>>; created_at: string };

export const REPORT_SECTIONS = [
  ["document_control", "Document control"], ["executive_summary", "Executive summary"], ["engagement_info", "Engagement overview"],
  ["scope", "Scope"], ["methodology", "Methodology and rating scale"], ["summary_table", "Findings at a glance"],
  ["severity_distribution", "Severity and status distribution"], ["findings", "Detailed findings"],
  ["remediation_roadmap", "Remediation roadmap"], ["retest_summary", "Retest results"], ["appendix", "Appendix"],
] as const;
export const REPORT_FONTS = [["geist", "Geist (sans-serif)"], ["serif", "DejaVu Serif"]] as const;
export const REPORT_STATUSES = [["queued", "Queued"], ["rendering", "Building"], ["done", "Ready"], ["failed", "Failed"]] as const;

export type ReportJob = {
  id: string;
  engagement: { id: string; ref: string; name: string };
  requested_by: { id: string; name: string };
  template: { id: string; name: string } | null;
  format: "pdf" | "csv";
  audience: "client" | "internal";
  title: string;
  version_label: string;
  classification: string;
  filters: { severities: string[]; statuses: string[] };
  status: (typeof REPORT_STATUSES)[number][0];
  error: string;
  finding_count: number;
  page_count: number | null;
  file_name: string;
  size: number;
  sha256: string;
  started_at: string | null;
  finished_at: string | null;
  expires_at: string | null;
  file_available: boolean;
  created_at: string;
};

export type ReportTemplate = {
  id: string;
  name: string;
  sections: string[];
  accent: string;
  font: "geist" | "serif";
  footer_text: string;
  is_default: boolean;
  has_logo: boolean;
  version: number;
  updated_at: string;
};

export type DashboardKind = "admin" | "pentester" | "remediation" | "vendor";
export type DashFinding = { id: string; ref: string; title: string; severity: string; status: string; due_date: string | null; engagement: { id: string; ref: string } };
export type DashEngagement = { id: string; ref: string; name: string; organisation: string; status: string; start_date: string; end_date: string; overdue: boolean };
export type Dashboard = {
  kind: DashboardKind;
  generated_at: string;
  findings: {
    total: number; open: number; overdue: number; due_soon: number; pending_verification: number; drafts: number; risk_acceptance_expiring: number;
    by_severity: Record<string, number>; by_status: Record<string, number>; open_by_severity: Record<string, number>;
  };
  engagements: { total: number; overdue: number; by_status: Record<string, number>; upcoming: DashEngagement[]; in_progress: DashEngagement[] };
  trend: Array<{ week_start: string; opened: number; closed: number }>;
  sla: { window_days: number; closed: number; dated: number; on_time: number; compliance_pct: number | null; mean_days_to_close: number | null };
  activity: Array<{ id: number; at: string; action: string; entity_type: string; entity_label: string; actor: string; engagement_ref: string; outcome: string }>;
  next_due: DashFinding[];
  top_organisations?: Array<{ id: string; name: string; critical: number; high: number }>;
  costs?: { totals: Array<{ currency: string; total: string; lines: number }>; top: Array<{ engagement: { id: string; ref: string; name: string }; currency: string; total: string }> } | null;
  integrity?: { status: string; finished_at: string | null; checked: number; reason: string } | null;
  mine?: { open: number; overdue: number; drafts: number };
  retests?: { active_rounds: number; items_pending: number; rounds: Array<{ id: string; ref: string; engagement: { id: string; ref: string }; status: string; pending: number }> };
  recently_closed?: number;
};

export const COST_CATEGORIES = [
  ["labour", "Labour"], ["tools", "Tools and licences"], ["travel", "Travel"], ["subcontractor", "Subcontractor"], ["other", "Other"],
] as const;
export const CURRENCIES = [
  ["USD", "US dollar"], ["EUR", "Euro"], ["GBP", "Pound sterling"], ["INR", "Indian rupee"], ["AED", "UAE dirham"], ["SAR", "Saudi riyal"],
  ["QAR", "Qatari riyal"], ["KWD", "Kuwaiti dinar"], ["BHD", "Bahraini dinar"], ["OMR", "Omani rial"], ["SGD", "Singapore dollar"],
  ["MYR", "Malaysian ringgit"], ["AUD", "Australian dollar"], ["NZD", "New Zealand dollar"], ["CAD", "Canadian dollar"], ["CHF", "Swiss franc"],
  ["SEK", "Swedish krona"], ["NOK", "Norwegian krone"], ["DKK", "Danish krone"], ["PLN", "Polish zloty"], ["CZK", "Czech koruna"],
  ["ZAR", "South African rand"], ["NGN", "Nigerian naira"], ["KES", "Kenyan shilling"], ["EGP", "Egyptian pound"], ["TRY", "Turkish lira"],
  ["ILS", "Israeli shekel"], ["JPY", "Japanese yen"], ["CNY", "Chinese yuan"], ["HKD", "Hong Kong dollar"], ["KRW", "South Korean won"],
  ["THB", "Thai baht"], ["IDR", "Indonesian rupiah"], ["PHP", "Philippine peso"], ["VND", "Vietnamese dong"], ["PKR", "Pakistani rupee"],
  ["BDT", "Bangladeshi taka"], ["LKR", "Sri Lankan rupee"], ["BRL", "Brazilian real"], ["MXN", "Mexican peso"], ["ARS", "Argentine peso"],
  ["CLP", "Chilean peso"], ["COP", "Colombian peso"], ["RUB", "Russian rouble"], ["UAH", "Ukrainian hryvnia"],
] as const;
export type CostLine = {
  id: string; amount: string; currency: string; category: string; description: string; incurred_on: string;
  created_by: { id: string; display_name: string; email: string } | null; created_at: string;
};
export type CostTotal = { currency: string; total: string; lines: number };
export type EngagementCosts = { totals: CostTotal[]; items: CostLine[] };

export type AppNotification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  actor: string | null;
  read: boolean;
  created_at: string;
};
