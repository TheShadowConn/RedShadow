import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, GitMerge, Plus, Search, Tags, Upload } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { api, downloadFile } from "../../api/client";
import {
  ASSET_TYPES, ENVIRONMENTS, type Asset, type AssetSummary, type AssetTag, type AssetUsage, type Organisation, type Page, type TagResult,
} from "../../api/types";
import {
  Alert, Badge, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, formatDate, label, LoadingRows, Modal, PageHeader, Pager, Select,
  Sheet, TextInput,
} from "../../design/ui";
import { AssetEditor, IdentifierManager, invalidateAssets } from "./AssetEditor";
import { ManageTagsDialog, TagSelectedDialog } from "./TagDialogs";
import { TagList, TagPicker, withDraft } from "./Tags";

const PAGE_SIZE = 25;
type Scope = "live" | "pending" | "onboarded" | "archived";
const SCOPES: Array<[Scope, string, keyof AssetSummary]> = [
  ["live", "All assets", "total"], ["onboarded", "Onboarded", "onboarded"], ["pending", "Not onboarded", "pending"], ["archived", "Archived", "archived"],
];

export function OnboardingBadge({ a }: { a: Pick<Asset, "onboarding_status"> }) {
  return a.onboarding_status === "pending" ? <Badge tone="warn">Not onboarded</Badge> : null;
}

export function Criticality({ n }: { n: number }) {
  return <Badge tone={n >= 4 ? "fail" : n === 3 ? "warn" : "info"}>{n} of 5</Badge>;
}

function IdentifierChips({ a, max = 2 }: { a: Asset; max?: number }) {
  if (a.identifiers.length === 0) return <span className="text-muted">{a.identifier || "No identifier"}</span>;
  const shown = a.identifiers.slice(0, max);
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {shown.map((i) => <span key={i.id} className="mono break-all text-[13px]">{i.value}</span>)}
      {a.identifiers.length > max && <span className="text-[13px] text-muted">+{a.identifiers.length - max} more</span>}
    </span>
  );
}

export function AssetsPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [scope, setScope] = useState<Scope>(() => (["pending", "onboarded", "archived"].includes(params.get("scope") ?? "") ? (params.get("scope") as Scope) : "live"));
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [filters, setFilters] = useState({ organisation: "", type: "", environment: "", criticality: "", tag: params.get("tag") ?? "", untagged: params.get("untagged") === "true" ? "true" : "" });
  const [tagging, setTagging] = useState(false);
  const [managing, setManaging] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(params.get("asset"));
  const [creating, setCreating] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<"onboard" | "archive" | "unarchive" | null>(null);

  useEffect(() => { const t = setTimeout(() => { setTerm(search.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (scope === "archived") query.set("archived", "true");
  if (scope === "pending" || scope === "onboarded") query.set("onboarding_status", scope);
  if (term) query.set("search", term);
  for (const [k, v] of Object.entries(filters)) if (v) query.set(k, v);

  const list = useQuery({ queryKey: ["assets", query.toString()], queryFn: () => api<Page<Asset>>("GET", `/assets?${query}`), placeholderData: (p) => p });
  const summaryQuery = new URLSearchParams();
  if (filters.organisation) summaryQuery.set("organisation", filters.organisation);
  if (filters.tag) summaryQuery.set("tag", filters.tag);
  if (filters.untagged) summaryQuery.set("untagged", filters.untagged);
  const summary = useQuery({ queryKey: ["asset-summary", summaryQuery.toString()], queryFn: () => api<AssetSummary>("GET", `/assets/summary?${summaryQuery}`) });
  const tags = useQuery({ queryKey: ["asset-tags", filters.organisation], queryFn: () => api<AssetTag[]>("GET", `/assets/tags${filters.organisation ? `?organisation=${filters.organisation}` : ""}`) });
  const orgs = useQuery({ queryKey: ["organisations-pick"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100&archived=all") });
  const rows = list.data?.results ?? [];
  const setFilter = (k: keyof typeof filters) => (e: { target: { value: string } }) => { setFilters({ ...filters, [k]: e.target.value }); setPage(1); };
  const pickTag = (tag: string, untagged = "") => { setFilters((f) => ({ ...f, tag, untagged })); setPage(1); setPicked(new Set()); };
  const filtered = !!(term || Object.values(filters).some(Boolean));
  const open = (id: string | null) => { setSelected(id); setParams(id ? { asset: id } : {}, { replace: true }); };

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  async function exportCsv() {
    const x = new URLSearchParams(query);
    x.delete("page");
    x.delete("page_size");
    setExporting(true);
    setExportError(null);
    try { await downloadFile(`/assets/export.csv?${x}`, "redshadow-assets.csv"); } catch (e) { setExportError(e); } finally { setExporting(false); }
  }

  const [skipped, setSkipped] = useState<Array<{ name: string; reason: string }>>([]);
  const bulkRun = useMutation({
    mutationFn: (kind: "onboard" | "archive" | "unarchive") =>
      kind === "onboard"
        ? api<{ skipped: Array<{ name: string; reason: string }> }>("POST", "/assets/onboard", { ids: [...picked] })
        : api<{ skipped: Array<{ name: string; reason: string }> }>("POST", "/assets/archive", { ids: [...picked], archived: kind === "archive" }),
    onSuccess: (r) => { setSkipped(r.skipped); setPicked(new Set()); setBulk(null); invalidateAssets(qc); },
  });
  const selectable = can("assets.update") || can("assets.archive");
  const pickedRows = rows.filter((a) => picked.has(a.id));
  const canOnboard = can("assets.update") && pickedRows.some((a) => a.onboarding_status === "pending" && !a.archived);
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <>
      <PageHeader
        title="Assets"
        lead="Every system, application and network you test. One asset can have several identifiers, such as an IP address, a hostname and a URL, and each identifier belongs to exactly one asset."
        actions={
          <>
            {can("assets.import") && can("imports.create") && <Link to="/imports?new=assets" className="btn btn-secondary"><Upload size={18} aria-hidden /> Import assets</Link>}
            {can("exports.csv") && <Button onClick={exportCsv} loading={exporting}><Download size={18} aria-hidden /> Export CSV</Button>}
            {can("assets.update") && <Button onClick={() => setManaging(true)}><Tags size={18} aria-hidden /> Manage tags</Button>}
            {can("assets.create") && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} aria-hidden /> New asset</Button>}
          </>
        }
      />

      {summary.data && summary.data.pending > 0 && scope !== "pending" && (
        <div className="mb-6"><Alert tone="warn"><p className="m-0"><strong className="font-medium">{summary.data.pending} asset{summary.data.pending === 1 ? " is" : "s are"} not onboarded yet.</strong> They came in through an import and cannot join an engagement until someone checks their details and onboards them. <button type="button" className="text-accent underline" onClick={() => { setScope("pending"); setPage(1); }}>Show them</button></p></Alert></div>
      )}

      {!!exportError && <div className="mb-6"><ErrorNote error={exportError} /></div>}

      <div className="card overflow-hidden">
        <div className="flex flex-wrap gap-2 border-b border-line p-4" role="group" aria-label="Show assets">
          {SCOPES.map(([id, name, key]) => (
            <Button key={id} size="sm" aria-pressed={scope === id} variant={scope === id ? "primary" : "secondary"} onClick={() => { setScope(id); setPage(1); setPicked(new Set()); }}>
              {name}{summary.data ? <span className="ml-1.5 opacity-70">{summary.data[key]}</span> : null}
            </Button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 border-b border-line p-4 lg:grid-cols-4">
          <div className="relative col-span-2 lg:col-span-4">
            <Search size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput aria-label="Search assets" placeholder="Search name, IP, hostname, URL, tag" className="pl-11" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Organisation" value={filters.organisation} onChange={setFilter("organisation")}>
            <option value="">All organisations</option>{orgs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
          <Select aria-label="Type" value={filters.type} onChange={setFilter("type")}><option value="">All types</option>{ASSET_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Environment" value={filters.environment} onChange={setFilter("environment")}><option value="">Any environment</option>{ENVIRONMENTS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Criticality" value={filters.criticality} onChange={setFilter("criticality")}><option value="">Any criticality</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} of 5</option>)}</Select>
        </div>

        {!!(tags.data?.length || filters.tag || filters.untagged) && (
          <div className="flex flex-col gap-2 border-b border-line p-4">
            <span className="label">Tags</span>
            <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto" role="group" aria-label="Filter by tag">
              <button type="button" className="tag tag-pick" aria-pressed={!filters.tag && !filters.untagged} onClick={() => pickTag("")}>All</button>
              {tags.data?.filter((t) => t.assets > 0 || t.tag === filters.tag).map((t) => (
                <button key={t.tag} type="button" className="tag tag-pick" aria-pressed={filters.tag === t.tag} onClick={() => pickTag(filters.tag === t.tag ? "" : t.tag)}>{t.tag} <span className="text-muted">{t.assets}</span></button>
              ))}
              <button type="button" className="tag tag-pick" aria-pressed={!!filters.untagged} onClick={() => pickTag("", filters.untagged ? "" : "true")}>Untagged</button>
            </div>
          </div>
        )}

        {skipped.length > 0 && (
          <div className="border-b border-line p-4"><Alert tone="warn"><p className="m-0 font-medium">{skipped.length} asset{skipped.length === 1 ? " was" : "s were"} skipped.</p><ul className="m-0 mt-1 list-disc pl-5">{skipped.slice(0, 5).map((s) => <li key={s.name}>{s.name}: {s.reason}</li>)}</ul></Alert></div>
        )}
        {selectable && rows.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-raised px-4 py-2">
            <label className="check"><input type="checkbox" checked={rows.every((a) => picked.has(a.id))} onChange={(e) => setPicked(e.target.checked ? new Set(rows.map((a) => a.id)) : new Set())} /> Select all on this page{picked.size > 0 && <span className="text-muted">({picked.size} selected)</span>}</label>
            <div className="flex flex-wrap gap-2">
              {can("assets.update") && scope !== "archived" && <Button size="sm" disabled={pickedRows.length === 0} onClick={() => setTagging(true)}>Tag selected</Button>}
              {canOnboard && <Button size="sm" variant="primary" onClick={() => { bulkRun.reset(); setBulk("onboard"); }}>Onboard selected</Button>}
              {can("assets.archive") && <Button size="sm" disabled={picked.size === 0} onClick={() => { bulkRun.reset(); setBulk(scope === "archived" ? "unarchive" : "archive"); }}>{scope === "archived" ? "Unarchive selected" : "Archive selected"}</Button>}
            </div>
          </div>
        )}

        {list.isPending && <LoadingRows />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data && rows.length === 0 && (
          <EmptyState
            title={filtered ? "No assets match" : scope === "pending" ? "Nothing waiting for onboarding" : "No assets yet"}
            body={filtered ? "Try a different search or clear a filter." : scope === "pending" ? "Assets that arrive through an import wait here until you onboard them." : "Create an asset by hand, or import a CSV of assets."}
            action={!filtered && can("assets.create") ? <Button variant="primary" onClick={() => setCreating(true)}>New asset</Button> : undefined}
          />
        )}
        {rows.length > 0 && (
          <>
            <div className="hidden overflow-x-auto md:block"><table className="data-table min-w-[920px]">
              <thead><tr>{selectable && <th className="w-10"><span className="sr-only">Select</span></th>}<th>Asset</th><th>Identifiers</th><th>Tags</th><th>Organisation</th><th>Type</th><th className="hidden xl:table-cell">Env</th><th>Criticality</th><th>Engagements</th><th><span className="sr-only">Open</span></th></tr></thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} onClick={() => open(a.id)}>
                    {selectable && <td onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`Select ${a.name}`} checked={picked.has(a.id)} onChange={() => toggle(a.id)} /></td>}
                    <td>
                      <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); open(a.id); }}>
                        <span className="block font-medium whitespace-nowrap">{a.name}</span>
                        <span className="mt-1 flex flex-wrap gap-1.5"><OnboardingBadge a={a} />{a.archived && <Badge tone="info">Archived</Badge>}</span>
                      </button>
                    </td>
                    <td className="max-w-72"><IdentifierChips a={a} /></td>
                    <td className="min-w-40 max-w-64"><TagList tags={a.tags} empty="None" /></td>
                    <td className="whitespace-nowrap">{a.organisation_name}</td>
                    <td className="whitespace-nowrap">{label(ASSET_TYPES, a.type)}</td>
                    <td className="hidden xl:table-cell">{label(ENVIRONMENTS, a.environment)}</td>
                    <td className="whitespace-nowrap"><Criticality n={a.criticality} /></td>
                    <td>{a.engagement_count}</td>
                    <td className="text-muted"><ChevronRight size={18} aria-hidden /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <ul className="m-0 list-none divide-y divide-line p-0 md:hidden">
              {rows.map((a) => (
                <li key={a.id}>
                  <button type="button" onClick={() => open(a.id)} className="block w-full flex flex-col gap-1.5 px-4 py-4 text-left">
                    <span className="flex flex-wrap items-center gap-2"><span className="font-medium">{a.name}</span><OnboardingBadge a={a} />{a.archived && <Badge tone="info">Archived</Badge>}</span>
                    <span className="block"><IdentifierChips a={a} /></span>
                    <TagList tags={a.tags} />
                    <span className="block text-[14px] text-muted">{a.organisation_name} · {label(ASSET_TYPES, a.type)} · {label(ENVIRONMENTS, a.environment)} · {a.criticality} of 5</span>
                  </button>
                </li>
              ))}
            </ul>
            <Pager page={page} count={list.data!.count} size={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>

      {tagging && <TagSelectedDialog assets={pickedRows} known={tags.data ?? []} onClose={() => setTagging(false)} onDone={(r) => { setSkipped(r.skipped); setPicked(new Set()); }} />}
      {managing && (
        <ManageTagsDialog
          tags={tags.data ?? []}
          organisation={filters.organisation}
          organisationName={orgs.data?.results.find((o) => o.id === filters.organisation)?.name}
          onClose={() => setManaging(false)}
          onChanged={(from, to) => { if (filters.tag.toLowerCase() === from.toLowerCase()) { setFilters((f) => ({ ...f, tag: to })); setPage(1); } setPicked(new Set()); }}
        />
      )}
      {creating && <AssetEditor onClose={() => setCreating(false)} onSaved={(a) => open(a.id)} />}
      <AssetSheet assetId={selected} onClose={() => open(null)} />
      <ConfirmDialog
        open={!!bulk}
        title={bulk === "onboard" ? "Onboard assets" : bulk === "unarchive" ? "Unarchive assets" : "Archive assets"}
        body={`${picked.size} asset${picked.size === 1 ? "" : "s"}: ${bulk === "onboard" ? "marked as onboarded so they can join engagements. Assets without an identifier are skipped." : bulk === "unarchive" ? "available for new engagements again." : "can no longer be added to engagements. Links and findings stay, identifiers stay reserved."}`}
        confirmLabel={bulk === "onboard" ? "Onboard" : bulk === "unarchive" ? "Unarchive" : "Archive"}
        danger={bulk === "archive"}
        busy={bulkRun.isPending}
        error={bulkRun.error}
        onConfirm={() => bulk && bulkRun.mutate(bulk)}
        onClose={() => setBulk(null)}
      />
    </>
  );
}

function Item({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><dt className="label">{k}</dt><dd className="m-0 mt-0.5">{v}</dd></div>;
}

/** Tags in the side panel: add from the existing tags or create one, remove with the cross. */
function AssetTagsSection({ a, editable }: { a: Asset; editable: boolean }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const catalogue = useQuery({ queryKey: ["asset-tags", a.organisation], queryFn: () => api<AssetTag[]>("GET", `/assets/tags?organisation=${a.organisation}`), enabled: editable });
  const known = catalogue.data?.map((t) => t.tag) ?? [];
  const available = known.filter((k) => !a.tags.some((t) => t.toLowerCase() === k.toLowerCase()));
  const reset = () => { setAdding(false); setPicked([]); setDraft(""); };
  const save = useMutation({
    mutationFn: (change: { add?: string[]; remove?: string[] }) => api<TagResult>("POST", "/assets/tags/assign", { ids: [a.id], ...change }),
    onSuccess: (r) => { invalidateAssets(qc, a.organisation); if (r.skipped.length === 0) reset(); },
  });
  const add = withDraft(picked, draft, known);
  const skippedReason = save.data?.skipped[0]?.reason;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="label m-0">Tags</h3>
        {editable && !adding && <Button size="sm" onClick={() => { save.reset(); setAdding(true); }}><Plus size={16} aria-hidden /> Add tag</Button>}
      </div>
      <TagList tags={a.tags} empty="No tags yet." busy={save.isPending} onRemove={editable ? (t) => save.mutate({ remove: [t] }) : undefined} />
      {adding && (
        <form className="flex flex-col gap-4 rounded-md border border-line p-4" onSubmit={(e) => { e.preventDefault(); if (add.length) save.mutate({ add }); }}>
          <TagPicker value={picked} onChange={setPicked} known={available} draft={draft} onDraft={setDraft} />
          <div className="flex flex-wrap justify-end gap-3">
            <Button size="sm" onClick={reset}>Cancel</Button>
            <Button size="sm" type="submit" variant="primary" loading={save.isPending} disabled={add.length === 0}>Save tags</Button>
          </div>
        </form>
      )}
      <ErrorNote error={save.error} />
      {skippedReason && <Alert tone="warn">{skippedReason}</Alert>}
    </section>
  );
}

type Pending = "archive" | "unarchive" | "delete" | "onboard" | null;

function AssetSheet({ assetId, onClose }: { assetId: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["assets", "one", assetId], queryFn: () => api<Asset>("GET", `/assets/${assetId}`), enabled: !!assetId });
  const usage = useQuery({ queryKey: ["asset-usage", assetId], queryFn: () => api<AssetUsage>("GET", `/assets/${assetId}/usage`), enabled: !!assetId });
  const [pending, setPending] = useState<Pending>(null);
  const [editing, setEditing] = useState(false);
  const [merging, setMerging] = useState(false);
  const a = q.data;

  const done = () => { setPending(null); invalidateAssets(qc, a?.organisation); void qc.invalidateQueries({ queryKey: ["asset-usage", assetId] }); };
  const act = useMutation({
    mutationFn: (kind: Exclude<Pending, null>) =>
      kind === "delete" ? api("DELETE", `/assets/${assetId}`) : api("POST", `/assets/${assetId}/${kind}`, kind === "onboard" ? {} : undefined),
    onSuccess: (_r, kind) => { done(); if (kind === "delete") onClose(); },
  });

  const copy: Record<Exclude<Pending, null>, { title: string; body: string; label: string; danger?: boolean }> = {
    archive: { title: "Archive asset", body: `${a?.name} can no longer be added to engagements. Existing links and findings stay. Its identifiers stay reserved so it is not created again.`, label: "Archive", danger: true },
    unarchive: { title: "Unarchive asset", body: `${a?.name} becomes available for new engagements again.`, label: "Unarchive" },
    onboard: { title: "Onboard asset", body: `${a?.name} will be marked as onboarded and can then be added to engagements.`, label: "Onboard" },
    delete: {
      title: "Delete asset",
      body: usage.data && (usage.data.engagements || usage.data.findings)
        ? `${a?.name} is used by ${usage.data.engagements} engagement(s) and ${usage.data.findings} finding(s), so it cannot be deleted. Archive it, or merge it into another asset.`
        : `${a?.name} and its ${usage.data?.identifiers ?? ""} identifier(s) are deleted for good. Nothing uses this asset. This cannot be undone.`,
      label: "Delete asset", danger: true,
    },
  };
  const inUse = !!usage.data && (usage.data.engagements > 0 || usage.data.findings > 0);

  return (
    <>
      <Sheet open={!!assetId} onClose={onClose} title={a?.name ?? "Asset"}>
        {q.isPending && <LoadingRows rows={4} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {a && (
          <div className="flex flex-col gap-8 p-6">
            {a.onboarding_status === "pending" && (
              <Alert tone="warn">
                <p className="m-0 font-medium">This asset is not onboarded.</p>
                <p className="m-0 mt-1">It was imported. Check the details and identifiers, then onboard it so it can join engagements.</p>
                {can("assets.update") && !a.archived && <div className="mt-3"><Button size="sm" variant="primary" onClick={() => { act.reset(); setPending("onboard"); }}>Onboard asset</Button></div>}
              </Alert>
            )}
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Item k="Organisation" v={a.organisation_name} />
              <Item k="Status" v={<span className="flex flex-wrap gap-1.5">{a.archived ? <Badge tone="info">Archived</Badge> : <Badge tone="ok">Active</Badge>}<OnboardingBadge a={a} /></span>} />
              <Item k="Type" v={label(ASSET_TYPES, a.type)} />
              <Item k="Environment" v={label(ENVIRONMENTS, a.environment)} />
              <Item k="Criticality" v={<Criticality n={a.criticality} />} />
              <Item k="Engagements" v={a.engagement_count} />
              <Item k="Origin" v={a.origin === "import" ? "Imported from CSV" : "Added by hand"} />
              <Item k="Created" v={formatDate(a.created_at)} />
            </dl>

            <AssetTagsSection key={a.id} a={a} editable={!a.archived && can("assets.update")} />

            {a.archived || !can("assets.update") ? (
              <section className="flex flex-col gap-2"><h3 className="label m-0">Identifiers</h3>
                <ul className="m-0 list-none divide-y divide-line rounded-md border border-line p-0">
                  {a.identifiers.map((i) => <li key={i.id} className="flex flex-wrap items-center gap-2 px-3 py-2"><Badge tone="info">{i.kind_label}</Badge><span className="mono min-w-0 flex-1 break-all text-[14px]">{i.value}</span>{i.is_primary && <span className="text-[13px] text-muted">Primary</span>}</li>)}
                  {a.identifiers.length === 0 && <li className="px-3 py-2 text-muted">No identifiers.</li>}
                </ul>
              </section>
            ) : (
              <IdentifierManager asset={a} />
            )}

            <section aria-labelledby="asset-actions" className="flex flex-col gap-3">
              <h3 id="asset-actions" className="text-lg">Actions</h3>
              <ErrorNote error={act.error} />
              <div className="flex flex-wrap gap-3">
                {can("assets.update") && !a.archived && <Button onClick={() => setEditing(true)}>Edit details</Button>}
                {can("assets.delete") && !a.archived && <Button onClick={() => setMerging(true)}><GitMerge size={16} aria-hidden /> Merge a duplicate into this</Button>}
                {can("assets.archive") && <Button onClick={() => { act.reset(); setPending(a.archived ? "unarchive" : "archive"); }}>{a.archived ? "Unarchive" : "Archive"}</Button>}
                {can("assets.delete") && <Button variant="danger" onClick={() => { act.reset(); setPending("delete"); }}>Delete</Button>}
              </div>
              {can("assets.delete") && inUse && <p className="m-0 text-[14px] text-muted">Used by {usage.data!.engagements} engagement(s) and {usage.data!.findings} finding(s): archive instead of deleting.</p>}
            </section>
          </div>
        )}
      </Sheet>
      {editing && a && <AssetEditor asset={a} onClose={() => setEditing(false)} />}
      {merging && a && <MergeDialog target={a} onClose={() => setMerging(false)} />}
      <ConfirmDialog
        open={!!pending && !!a}
        title={pending ? copy[pending].title : ""}
        body={pending ? copy[pending].body : ""}
        confirmLabel={pending ? copy[pending].label : ""}
        danger={pending ? copy[pending].danger : false}
        busy={act.isPending}
        error={act.error}
        onConfirm={() => pending && act.mutate(pending)}
        onClose={() => setPending(null)}
      />
    </>
  );
}

/** Folds a duplicate asset into the open one: identifiers, engagement links and findings move across. */
function MergeDialog({ target, onClose }: { target: Asset; onClose: () => void }) {
  const qc = useQueryClient();
  const [term, setTerm] = useState("");
  const [source, setSource] = useState<Asset | null>(null);
  const found = useQuery({
    queryKey: ["assets", "merge-pick", target.organisation, term],
    queryFn: () => api<Page<Asset>>("GET", `/assets?organisation=${target.organisation}&page_size=8&archived=all${term ? `&search=${encodeURIComponent(term)}` : ""}`),
  });
  const merge = useMutation({
    mutationFn: () => api<Asset>("POST", `/assets/${target.id}/merge`, { source: source!.id }),
    onSuccess: () => { invalidateAssets(qc, target.organisation); void qc.invalidateQueries({ queryKey: ["assets", "one", target.id] }); onClose(); },
  });
  const options = found.data?.results.filter((x) => x.id !== target.id) ?? [];
  return (
    <Modal open onClose={onClose} title="Merge a duplicate">
      <div className="flex flex-col gap-5 p-6">
        <p className="m-0">Choose the duplicate to fold into <strong className="font-medium">{target.name}</strong>. Its identifiers, engagement links and findings move here, then the duplicate is deleted. This cannot be undone.</p>
        <TextInput aria-label="Find the duplicate" placeholder="Search by name or identifier" value={term} onChange={(e) => { setTerm(e.target.value); setSource(null); }} />
        <ul className="m-0 max-h-64 list-none divide-y divide-line overflow-y-auto rounded-md border border-line p-0">
          {options.map((x) => (
            <li key={x.id}>
              <button type="button" aria-pressed={source?.id === x.id} onClick={() => setSource(x)} className={`block w-full px-3 py-2 text-left ${source?.id === x.id ? "bg-raised" : ""}`}>
                <span className="block font-medium">{x.name}</span><span className="block break-all text-[13px] text-muted">{x.identifiers.map((i) => i.value).join(", ") || "No identifiers"}</span>
              </button>
            </li>
          ))}
          {found.data && options.length === 0 && <li className="px-3 py-2 text-muted">No other asset found.</li>}
        </ul>
        <ErrorNote error={merge.error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="danger" loading={merge.isPending} disabled={!source} onClick={() => merge.mutate()}>Merge and delete {source ? source.name : "duplicate"}</Button>
        </div>
      </div>
    </Modal>
  );
}
