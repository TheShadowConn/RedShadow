import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { COST_CATEGORIES } from "../../api/types";
import { EmptyState, ErrorState, Field, formatDay, label, LoadingRows, money, PageHeader, Select, Button } from "../../design/ui";

type Total = { currency: string; total: number | string; lines: number };
type Report = {
  totals: Total[];
  timeline: Array<Total & { month: string }>;
  by_engagement: Array<Total & { engagement: { id: string; ref: string; name: string } }>;
  items: Array<{
    id: string; incurred_on: string; amount: number | string; currency: string; category: string; description: string;
    engagement: { id: string; ref: string; name: string };
  }>;
  truncated: boolean;
  options: { years: number[]; engagements: Array<{ id: string; ref: string; name: string }>; currencies: string[] };
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
type Filters = { year: string; month: string; engagement: string; category: string; currency: string };
const EMPTY: Filters = { year: "", month: "", engagement: "", category: "", currency: "" };

const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-");
  return `${MONTHS[Number(m) - 1].slice(0, 3)} ${y}`;
};

/** Bars for one currency: one row per month, scaled to that currency's largest month. */
function Timeline({ currency, rows }: { currency: string; rows: Array<{ month: string; total: number | string; lines: number }> }) {
  const max = Math.max(...rows.map((r) => Number(r.total)), 1);
  return (
    <div>
      <h3 className="mb-3 text-[15px] font-medium text-muted">{currency}</h3>
      <ul className="m-0 list-none space-y-2 p-0">
        {rows.map((r) => (
          <li key={r.month} className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-3">
            <span className="text-[14px] text-muted">{monthLabel(r.month)}</span>
            <span className="h-3 overflow-hidden rounded-full bg-raised" aria-hidden>
              <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(2, (Number(r.total) / max) * 100)}%` }} />
            </span>
            <span className="mono text-[14px] font-medium tabular-nums">{money(r.total, currency)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CostsPage() {
  const { can } = useAuth();
  const [f, setF] = useState<Filters>(EMPTY);
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) qs.set(k, v);
  const q = useQuery({ queryKey: ["costs", qs.toString()], queryFn: () => api<Report>("GET", `/costs?${qs}`), placeholderData: (p) => p, enabled: can("engagement_costs.view") });
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const filtered = Object.values(f).some(Boolean);

  if (!can("engagement_costs.view")) {
    return <><PageHeader title="Engagement costs" /><div className="card"><EmptyState title="No access" body="Your role cannot see engagement costs." /></div></>;
  }
  const d = q.data;
  const currencies = d ? [...new Set(d.timeline.map((t) => t.currency))] : [];

  return (
    <>
      <PageHeader title="Engagement costs" lead="Every cost line across your engagements, with the engagement name and a timeline. Currencies are never converted into each other, so each has its own total." />

      <section className="card card-pad mb-6" aria-label="Filters">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Year">{(p) => <Select {...p} value={f.year} onChange={set("year")}><option value="">All years</option>{d?.options.years.map((y) => <option key={y} value={y}>{y}</option>)}</Select>}</Field>
          <Field label="Month">{(p) => <Select {...p} value={f.month} onChange={set("month")}><option value="">All months</option>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</Select>}</Field>
          <Field label="Engagement">{(p) => <Select {...p} value={f.engagement} onChange={set("engagement")}><option value="">All engagements</option>{d?.options.engagements.map((e) => <option key={e.id} value={e.id}>{e.ref} {e.name}</option>)}</Select>}</Field>
          <Field label="Category">{(p) => <Select {...p} value={f.category} onChange={set("category")}><option value="">All categories</option>{COST_CATEGORIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
          <Field label="Currency">{(p) => <Select {...p} value={f.currency} onChange={set("currency")}><option value="">All currencies</option>{d?.options.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select>}</Field>
        </div>
        {filtered && <div className="mt-4"><Button size="sm" onClick={() => setF(EMPTY)}>Clear filters</Button></div>}
      </section>

      {q.isPending && <div className="card"><LoadingRows rows={4} /></div>}
      {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
      {d && d.items.length === 0 && <div className="card"><EmptyState title={filtered ? "No cost lines match" : "No cost recorded yet"} body={filtered ? "Try a different year, month or engagement." : "Add cost lines on an engagement's Cost tab."} /></div>}

      {d && d.items.length > 0 && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
            {d.totals.map((t) => (
              <div key={t.currency} className="card card-pad min-w-0">
                <p className="m-0 text-[14px] text-muted">Total in {t.currency}</p>
                <p className="m-0 mt-2 text-[26px] leading-tight font-semibold tabular-nums [overflow-wrap:anywhere]">{money(t.total, t.currency)}</p>
                <p className="m-0 mt-2 text-[14px] text-muted">{t.lines} cost line{t.lines === 1 ? "" : "s"}</p>
              </div>
            ))}
          </div>

          <section className="card card-pad">
            <h2 className="mb-4 text-xl">Cost over time</h2>
            <div className="grid gap-8 md:grid-cols-2">
              {currencies.map((c) => <Timeline key={c} currency={c} rows={d.timeline.filter((t) => t.currency === c)} />)}
            </div>
          </section>

          <section className="card overflow-hidden">
            <h2 className="px-5 pt-5 pb-3 text-xl">By engagement</h2>
            <div className="table-scroll">
              <table className="data-table min-w-[480px]">
                <thead><tr><th>Engagement</th><th className="text-right">Lines</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {d.by_engagement.map((b) => (
                    <tr key={`${b.engagement.id}${b.currency}`}>
                      <td className="wrap-long"><Link to={`/engagements/${b.engagement.id}?tab=costs`} className="font-medium hover:underline">{b.engagement.name}</Link><span className="mono block text-[14px] text-muted">{b.engagement.ref}</span></td>
                      <td className="num">{b.lines}</td>
                      <td className="num font-medium">{money(b.total, b.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card overflow-hidden">
            <h2 className="px-5 pt-5 pb-3 text-xl">All cost lines</h2>
            <div className="table-scroll hidden md:block">
              <table className="data-table min-w-[720px]">
                <thead><tr><th>Date</th><th>Engagement</th><th>Category</th><th>Description</th><th className="text-right">Amount</th></tr></thead>
                <tbody>
                  {d.items.map((c) => (
                    <tr key={c.id}>
                      <td className="nw">{formatDay(c.incurred_on)}</td>
                      <td className="wrap-long"><Link to={`/engagements/${c.engagement.id}?tab=costs`} className="font-medium hover:underline">{c.engagement.name}</Link><span className="mono block text-[14px] text-muted">{c.engagement.ref}</span></td>
                      <td className="nw">{label(COST_CATEGORIES, c.category)}</td>
                      <td className="wrap-long">{c.description || <span className="text-muted">No description</span>}</td>
                      <td className="num font-medium">{money(c.amount, c.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {d.items.map((c) => (
                <li key={c.id} className="space-y-1 px-4 py-3">
                  <p className="m-0 flex items-baseline justify-between gap-3"><span className="font-medium [overflow-wrap:anywhere]">{c.engagement.name}</span><span className="mono shrink-0 font-medium">{money(c.amount, c.currency)}</span></p>
                  <p className="m-0 text-[14px] text-muted">{formatDay(c.incurred_on)} · {label(COST_CATEGORIES, c.category)} · <span className="mono">{c.engagement.ref}</span></p>
                  {c.description && <p className="m-0 text-[15px] [overflow-wrap:anywhere]">{c.description}</p>}
                </li>
              ))}
            </ul>
            {d.truncated && <p className="m-0 border-t border-line px-5 py-3 text-[14px] text-muted">Showing the 1,000 most recent lines. Narrow the filters to see the rest. The totals above include every matching line.</p>}
          </section>
        </div>
      )}
    </>
  );
}
