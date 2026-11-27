import { lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, useAuth } from "../api/auth";
import { Loader } from "../design/Loader";
import { Logo } from "../design/Logo";
import { Button, ErrorNote } from "../design/ui";
import { LoginPage } from "../features/auth/LoginPage";
import { MfaSetupRequired, MfaVerify, PasswordChange } from "../features/auth/RestrictionFlow";
import { OverviewPage } from "../features/home/OverviewPage";
import { Shell } from "./Shell";

const AboutPage = lazy(() => import("../features/about/AboutPage").then((m) => ({ default: m.AboutPage })));
const CostsPage = lazy(() => import("../features/costs/CostsPage").then((m) => ({ default: m.CostsPage })));
const BackupPage = lazy(() => import("../features/system/BackupPage").then((m) => ({ default: m.BackupPage })));
const DepartmentsPage = lazy(() => import("../features/assets/DepartmentsPage").then((m) => ({ default: m.DepartmentsPage })));
const AssetsPage = lazy(() => import("../features/assets/AssetsPage").then((m) => ({ default: m.AssetsPage })));
const AccountPage = lazy(() => import("../features/account/AccountPage").then((m) => ({ default: m.AccountPage })));
const ImportPage = lazy(() => import("../features/imports/ImportPage").then((m) => ({ default: m.ImportPage })));
const ImportsPage = lazy(() => import("../features/imports/ImportsPage").then((m) => ({ default: m.ImportsPage })));
const ReportsPage = lazy(() => import("../features/reports/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const ReportTemplatesPage = lazy(() => import("../features/reports/ReportTemplatesPage").then((m) => ({ default: m.ReportTemplatesPage })));
const CalendarPage = lazy(() => import("../features/calendar/CalendarPage").then((m) => ({ default: m.CalendarPage })));
const AuditPage = lazy(() => import("../features/audit/AuditPage").then((m) => ({ default: m.AuditPage })));
const EngagementPage = lazy(() => import("../features/engagements/EngagementPage").then((m) => ({ default: m.EngagementPage })));
const EngagementsPage = lazy(() => import("../features/engagements/EngagementsPage").then((m) => ({ default: m.EngagementsPage })));
const OrganisationPage = lazy(() => import("../features/organisations/OrganisationPage").then((m) => ({ default: m.OrganisationPage })));
const OrganisationsPage = lazy(() => import("../features/organisations/OrganisationsPage").then((m) => ({ default: m.OrganisationsPage })));
const FindingEditor = lazy(() => import("../features/findings/FindingEditor").then((m) => ({ default: m.FindingEditor })));
const FindingPage = lazy(() => import("../features/findings/FindingPage").then((m) => ({ default: m.FindingPage })));
const FindingsPage = lazy(() => import("../features/findings/FindingsPage").then((m) => ({ default: m.FindingsPage })));
const TemplatesPage = lazy(() => import("../features/templates/TemplatesPage").then((m) => ({ default: m.TemplatesPage })));
const RolesPage = lazy(() => import("../features/roles/RolesPage").then((m) => ({ default: m.RolesPage })));
const UsersPage = lazy(() => import("../features/users/UsersPage").then((m) => ({ default: m.UsersPage })));
const RemediationQueue = lazy(() => import("../features/remediation/RemediationQueue").then((m) => ({ default: m.RemediationQueue })));
const VerificationQueue = lazy(() => import("../features/remediation/VerificationQueue").then((m) => ({ default: m.VerificationQueue })));
const RetestPage = lazy(() => import("../features/retests/RetestPage").then((m) => ({ default: m.RetestPage })));
const RetestsPage = lazy(() => import("../features/retests/RetestsPage").then((m) => ({ default: m.RetestsPage })));

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: false } } });

function Splash({ children }: { children?: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <Logo height={34} className="text-ink" />
        {children}
      </div>
    </div>
  );
}

/** Everyone lands on the dashboard of their role. Remediation owners reach their queue from it. */
function Landing() {
  return <OverviewPage />;
}

function Gate() {
  const { me, loading, error, refresh } = useAuth();
  if (loading) return <Splash><Loader /></Splash>;
  if (error)
    return (
      <Splash>
        <ErrorNote error={error} />
        <Button onClick={() => void refresh()}>Try again</Button>
      </Splash>
    );
  if (!me) return <LoginPage />;
  if (me.restriction === "mfa_verify") return <MfaVerify />;
  if (me.restriction === "password_change") return <PasswordChange />;
  if (me.restriction === "mfa_setup") return <MfaSetupRequired />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Landing />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="imports" element={<ImportsPage />} />
        <Route path="imports/:id" element={<ImportPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="report-templates" element={<ReportTemplatesPage />} />
        <Route path="remediation" element={<RemediationQueue />} />
        <Route path="verification" element={<VerificationQueue />} />
        <Route path="retests" element={<RetestsPage />} />
        <Route path="retests/:id" element={<RetestPage />} />
        <Route path="engagements" element={<EngagementsPage />} />
        <Route path="engagements/:id" element={<EngagementPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="departments" element={<DepartmentsPage />} />
        <Route path="backup" element={<BackupPage />} />
        <Route path="costs" element={<CostsPage />} />
        <Route path="organisations" element={<OrganisationsPage />} />
        <Route path="organisations/:id" element={<OrganisationPage />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="findings/new" element={<FindingEditor />} />
        <Route path="findings/:id" element={<FindingPage />} />
        <Route path="findings/:id/edit" element={<FindingEditor />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="roles/:roleId?" element={<RolesPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Gate />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
