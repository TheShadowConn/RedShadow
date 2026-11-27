import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Bug, Building2, Coins, Info, Server, CalendarDays, ClipboardCheck, FileUp, FileText, Palette, Crosshair, FileStack, ScrollText, LayoutDashboard, MoreHorizontal, LogOut, Moon, Repeat2, ShieldCheck, Sun, UserCircle, Users, Wrench, type LucideIcon, Network } from "lucide-react";

import { useAuth } from "../api/auth";
import { Credit } from "../design/Credit";
import { Loader } from "../design/Loader";
import { Logo, Mark } from "../design/Logo";
import { Sheet } from "../design/ui";
import { IntegrityBanner } from "../features/audit/IntegrityBanner";
import { CommandPalette, SearchButton } from "./CommandPalette";
import { IdleWarning } from "./IdleWarning";
import { NotificationBell } from "./NotificationBell";
import { useSignOut } from "../features/auth/RestrictionFlow";
import { UndoBar } from "../design/undo";
import { ErrorBoundary } from "./ErrorBoundary";

type Item = { to: string; label: string; short?: string; icon: LucideIcon; perm?: string; end?: boolean };

const ITEMS: Item[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/engagements", label: "Engagements", short: "Tests", icon: Crosshair, perm: "engagements.view" },
  { to: "/calendar", label: "Calendar", short: "Calendar", icon: CalendarDays, perm: "calendar.view" },
  { to: "/remediation", label: "Remediation", short: "Fixes", icon: Wrench, perm: "remediation.update_status" },
  { to: "/findings", label: "Findings", short: "Findings", icon: Bug, perm: "findings.view" },
  { to: "/imports", label: "Imports", icon: FileUp, perm: "imports.view" },
  { to: "/reports", label: "Reports", short: "Reports", icon: FileText, perm: "reports.view" },
  { to: "/verification", label: "Verification", short: "Verify", icon: ClipboardCheck, perm: "findings.verify" },
  { to: "/retests", label: "Retests", icon: Repeat2, perm: "retests.view" },
  { to: "/organisations", label: "Organisations", short: "Orgs", icon: Building2, perm: "organisations.view" },
  { to: "/assets", label: "Assets", short: "Assets", icon: Server, perm: "assets.view" },
  { to: "/departments", label: "Departments", icon: Network, perm: "assets.view" },
  { to: "/costs", label: "Costs", icon: Coins, perm: "engagement_costs.view" },
  { to: "/templates", label: "Templates", icon: FileStack, perm: "templates.view" },
  { to: "/report-templates", label: "Report styles", icon: Palette, perm: "reports.manage_templates" },
  { to: "/audit", label: "Audit", icon: ScrollText, perm: "audit.view_engagement" },
  { to: "/users", label: "Users", icon: Users, perm: "users.view" },
  { to: "/roles", label: "Roles", icon: ShieldCheck, perm: "roles.view" },
  { to: "/account", label: "Account", icon: UserCircle },
  { to: "/about", label: "About", icon: Info },
];

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      return localStorage.getItem("rs-theme") === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("rs-theme", theme);
    } catch {
      /* storage blocked: theme still applies for this visit */
    }
  }, [theme]);
  return { theme, toggle: () => setTheme((t) => (t === "light" ? "dark" : "light")) };
}

const MOBILE_PRIMARY = new Set(["/", "/engagements", "/findings"]);
const MOBILE_PRIMARY_FIXERS = new Set(["/", "/remediation", "/findings"]);

/** Fixers (can start work, cannot create findings) work from the queue: it is one tap from their dashboard and in their mobile bar. */
export const useFixerLanding = () => {
  const { can } = useAuth();
  return can("remediation.update_status") && !can("findings.create");
};

export function Shell() {
  const { me, can } = useAuth();
  const { theme, toggle } = useTheme();
  const signOut = useSignOut();
  const fixer = useFixerLanding();
  const items = ITEMS.filter((i) => !i.perm || can(i.perm));
  const primarySet = fixer ? MOBILE_PRIMARY_FIXERS : MOBILE_PRIMARY;
  const [more, setMore] = useState(false);
  const [search, setSearch] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement)?.tagName) || (e.target as HTMLElement)?.isContentEditable;
      if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey)) { e.preventDefault(); setSearch(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const primary = items.filter((i) => primarySet.has(i.to));
  const rest = items.filter((i) => !primarySet.has(i.to));
  const location = useLocation();
  useEffect(() => setMore(false), [location.pathname]);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[72px_minmax(0,1fr)] xl:grid-cols-[256px_minmax(0,1fr)]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:p-3">
        Skip to content
      </a>

      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-surface md:flex" aria-label="Primary">
        <div className="flex h-16 shrink-0 items-center border-b border-line px-4 xl:px-6">
          <span className="xl:hidden"><Mark size={36} /></span>
          <Logo height={26} className="hidden text-ink xl:block" />
        </div>
        <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4" aria-label="Main">
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {items.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} className="shell-link max-xl:justify-center" title={label} aria-label={label}>
                  <Icon size={20} aria-hidden className="flex-none" />
                  <span className="hidden xl:inline">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="shrink-0 border-t border-line p-3">
          <div className="mb-2 hidden px-3 xl:block">
            <p className="m-0 truncate text-[15px] font-medium">{me?.display_name}</p>
            <p className="m-0 truncate text-[13px] text-muted">{me?.role.name}</p>
          </div>
          <button type="button" onClick={signOut} className="shell-link w-full max-xl:justify-center" title="Sign out" aria-label="Sign out">
            <LogOut size={20} aria-hidden className="flex-none" />
            <span className="hidden xl:inline">Sign out</span>
          </button>
        </div>
      </aside>

      <IdleWarning />
      <div className="flex min-w-0 flex-col pb-16 md:pb-0">
        <IntegrityBanner />
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-line bg-ground px-4 md:px-8">
          <Logo height={24} className="text-ink md:hidden" />
          <SearchButton onOpen={() => setSearch(true)} />
          <div className="flex items-center gap-2">
            <NotificationBell />
            <button
              type="button"
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              className="btn btn-secondary btn-icon"
            >
              {theme === "dark" ? <Sun size={20} aria-hidden /> : <Moon size={20} aria-hidden />}
            </button>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 p-3 sm:p-4 lg:p-6">
          <UndoBar />
          <ErrorBoundary key={location.pathname}>
            <Suspense fallback={<Loader block />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
        <footer className="mx-auto w-full max-w-[1600px] px-3 pb-6 text-[13px] text-muted sm:px-4 lg:px-6">
          <Link to="/about" className="inline-flex items-center gap-2 border-t border-line pt-4 text-muted no-underline hover:text-ink">
            Built by <Credit />
            <span className="sr-only">: about RedShadow</span>
          </Link>
        </footer>
      </div>

      <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-10 flex h-16 border-t border-line bg-surface md:hidden">
        {primary.map(({ to, label, short, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className="flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[13px] font-medium text-muted aria-[current=page]:text-accent"
          >
            <Icon size={22} aria-hidden />
            <span className="max-w-full truncate px-0.5">{short ?? label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMore(true)}
          aria-haspopup="dialog"
          className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[13px] font-medium ${rest.some((r) => location.pathname.startsWith(r.to)) ? "text-accent" : "text-muted"}`}
        >
          <MoreHorizontal size={22} aria-hidden />
          More
        </button>
      </nav>
      <CommandPalette open={search} onClose={() => setSearch(false)} items={items} />
      <Sheet open={more} onClose={() => setMore(false)} title="More">
        <ul className="m-0 list-none p-2">
          {rest.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={to} className="shell-link">
                <Icon size={20} aria-hidden className="flex-none" />
                {label}
              </NavLink>
            </li>
          ))}
          <li>
            <button type="button" onClick={signOut} className="shell-link w-full">
              <LogOut size={20} aria-hidden className="flex-none" />
              Sign out
            </button>
          </li>
        </ul>
      </Sheet>
    </div>
  );
}
