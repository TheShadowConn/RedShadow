import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Star, Trash2 } from "lucide-react";

import { api, ApiError } from "../../api/client";
import {
  ASSET_TYPES, ENVIRONMENTS, IDENTIFIER_KINDS, type Asset, type AssetIdentifier, type IdentifierCheck, type Organisation, type Page,
} from "../../api/types";
import { Badge, Button, ErrorNote, Field, fieldError, Modal, Select, TextInput } from "../../design/ui";

export const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);

/** Every list that shows assets refetches after a change. */
export function invalidateAssets(qc: ReturnType<typeof useQueryClient>, orgId?: string) {
  void qc.invalidateQueries({ queryKey: ["assets"] });
  void qc.invalidateQueries({ queryKey: ["asset-summary"] });
  void qc.invalidateQueries({ queryKey: ["org-assets", orgId] });
  void qc.invalidateQueries({ queryKey: ["org-assets"] });
}

type Draft = { key: number; kind: string; value: string; primary: boolean };
let draftKey = 1;
const blank = (primary = false): Draft => ({ key: draftKey++, kind: "", value: "", primary });

function useDebounced<T>(value: T, ms = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Asks the server whether each typed identifier is valid and who owns it, as the user types. */
function useIdentifierCheck(orgId: string, assetId: string | undefined, rows: Array<{ kind: string; value: string }>) {
  const filled = rows.map((r) => ({ kind: r.kind, value: r.value.trim() })).filter((r) => r.value);
  const debounced = useDebounced(JSON.stringify(filled));
  const q = useQuery({
    queryKey: ["identifier-check", orgId, assetId, debounced],
    queryFn: () => api<IdentifierCheck[]>("POST", "/assets/identifiers/check", { organisation: orgId, asset: assetId, identifiers: JSON.parse(debounced) as unknown[] }),
    enabled: !!orgId && filled.length > 0,
    staleTime: 5_000,
  });
  // Results line up with the filled rows. While the user is still typing they describe an older text: show none.
  const out = new Map<number, IdentifierCheck>();
  if (debounced !== JSON.stringify(filled) || !q.data) return out;
  let n = 0;
  rows.forEach((r, i) => {
    if (!r.value.trim()) return;
    const res = q.data[n++];
    if (res) out.set(i, res);
  });
  return out;
}

function CheckLine({ res, typed }: { res?: IdentifierCheck; typed: boolean }) {
  if (!typed || !res) return null;
  if (res.status === "invalid") return <span className="field-error" role="alert">{res.message}</span>;
  if (res.status === "owned") return <span className="field-error" role="alert">{res.message} Open that asset to change it, or merge the two assets.</span>;
  return <span className="field-hint">{res.kind && `${IDENTIFIER_KINDS.find(([k]) => k === res.kind)?.[1] ?? res.kind}: `}saved as <span className="mono break-all">{res.normalized}</span></span>;
}

function KindSelect({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <Select aria-label={label} className="sm:max-w-44" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Detect type</option>
      {IDENTIFIER_KINDS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </Select>
  );
}

/** Create or edit an asset. When editing, identifiers are managed live; when creating they are sent with the form. */
export function AssetEditor({ asset, org, onClose, onSaved }: { asset?: Asset; org?: { id: string; name: string }; onClose: () => void; onSaved?: (a: Asset) => void }) {
  const qc = useQueryClient();
  const orgs = useQuery({ queryKey: ["organisations-pick"], queryFn: () => api<Page<Organisation>>("GET", "/organisations?page_size=100"), enabled: !asset && !org });
  const [orgId, setOrgId] = useState(asset?.organisation ?? org?.id ?? "");
  const [f, setF] = useState({ name: asset?.name ?? "", type: asset?.type ?? "host", environment: asset?.environment ?? "prod", criticality: asset?.criticality ?? 3, tags: (asset?.tags ?? []).join(", ") });
  const [drafts, setDrafts] = useState<Draft[]>([blank(true)]);
  const checks = useIdentifierCheck(orgId, asset?.id, drafts);

  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, criticality: Number(f.criticality), tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean) };
      if (asset) return api<Asset>("PATCH", `/assets/${asset.id}`, body);
      const identifiers = drafts.filter((d) => d.value.trim()).map((d) => ({ ...(d.kind ? { kind: d.kind } : {}), value: d.value.trim(), is_primary: d.primary }));
      return api<Asset>("POST", "/assets", { ...body, organisation: orgId, identifiers });
    },
    onSuccess: (a) => { invalidateAssets(qc, a.organisation); onSaved?.(a); onClose(); },
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const blocked = [...checks.values()].some((c) => c.status !== "free");
  const idErrors = (save.error as ApiError | null)?.fields?.identifiers;

  return (
    <Modal open onClose={onClose} title={asset ? "Edit asset" : "New asset"}>
      <form className="flex flex-col gap-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        {!asset && !org && (
          <Field label="Organisation" error={fieldError(save.error, "organisation")}>
            {(p) => (
              <Select {...p} required value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                <option value="" disabled>{orgs.isPending ? "Loading…" : "Choose an organisation"}</option>
                {orgs.data?.results.filter((o) => !o.archived).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </Select>
            )}
          </Field>
        )}
        {org && !asset && <p className="m-0 text-muted">In {org.name}</p>}
        <Field label="Name" error={fieldError(save.error, "name")}>{(p) => <TextInput {...p} required autoFocus maxLength={160} value={f.name} onChange={set("name")} />}</Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Type" error={fieldError(save.error, "type")}>{(p) => <Select {...p} value={f.type} onChange={set("type")}>{ASSET_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
          <Field label="Environment" error={fieldError(save.error, "environment")}>{(p) => <Select {...p} value={f.environment} onChange={set("environment")}>{ENVIRONMENTS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Criticality" hint="1 is lowest, 5 is business critical." error={fieldError(save.error, "criticality")}>{(p) => <Select {...p} value={f.criticality} onChange={set("criticality")}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</Select>}</Field>
          <Field label="Tags" hint="Comma separated" error={fieldError(save.error, "tags")}>{(p) => <TextInput {...p} value={f.tags} onChange={set("tags")} />}</Field>
        </div>

        {asset ? (
          <IdentifierManager asset={asset} />
        ) : (
          <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
            <legend className="label mb-1">Identifiers</legend>
            <p className="m-0 text-[14px] text-muted">One asset can be known by several: an IP address, a hostname, a domain, a URL. Each identifier can belong to one asset only.</p>
            {idErrors && <p className="field-error m-0" role="alert">{idErrors.join(" ")}</p>}
            {drafts.map((d, i) => (
              <div key={d.key} className="flex flex-col gap-1">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <KindSelect label={`Identifier ${i + 1} type`} value={d.kind} onChange={(v) => setDrafts(drafts.map((x) => (x.key === d.key ? { ...x, kind: v } : x)))} />
                  <TextInput aria-label={`Identifier ${i + 1}`} placeholder="10.0.0.5, web01.acme.test, https://…" maxLength={500} value={d.value} onChange={(e) => setDrafts(drafts.map((x) => (x.key === d.key ? { ...x, value: e.target.value } : x)))} />
                  <Button aria-label={d.primary ? "Primary identifier" : "Make primary"} aria-pressed={d.primary} onClick={() => setDrafts(drafts.map((x) => ({ ...x, primary: x.key === d.key })))}><Star size={16} aria-hidden fill={d.primary ? "currentColor" : "none"} /></Button>
                  {drafts.length > 1 && <Button aria-label="Remove identifier" onClick={() => setDrafts(drafts.filter((x) => x.key !== d.key).map((x, j) => (j === 0 && !drafts.some((y) => y.key !== d.key && y.primary) ? { ...x, primary: true } : x)))}><Trash2 size={16} aria-hidden /></Button>}
                </div>
                <CheckLine res={checks.get(i)} typed={!!d.value.trim()} />
              </div>
            ))}
            <Button size="sm" onClick={() => setDrafts([...drafts, blank()])}><Plus size={16} aria-hidden /> Add another identifier</Button>
          </fieldset>
        )}

        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!f.name.trim() || (!asset && !orgId) || blocked}>{asset ? "Save changes" : "Create asset"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Add, promote and remove the identifiers of a saved asset. Every change is saved at once. */
export function IdentifierManager({ asset }: { asset: Asset }) {
  const qc = useQueryClient();
  const live = useQuery({ queryKey: ["assets", "one", asset.id], queryFn: () => api<Asset>("GET", `/assets/${asset.id}`), initialData: asset, staleTime: 0 });
  const rows = live.data.identifiers;
  const [draft, setDraft] = useState({ kind: "", value: "" });
  const checks = useIdentifierCheck(asset.organisation, asset.id, [draft]);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["assets"] }); void qc.invalidateQueries({ queryKey: ["org-assets"] }); };
  const add = useMutation({
    mutationFn: () => api<AssetIdentifier>("POST", `/assets/${asset.id}/identifiers`, { ...(draft.kind ? { kind: draft.kind } : {}), value: draft.value.trim() }),
    onSuccess: () => { setDraft({ kind: "", value: "" }); refresh(); },
  });
  const primary = useMutation({ mutationFn: (i: AssetIdentifier) => api("PATCH", `/assets/${asset.id}/identifiers/${i.id}`, { is_primary: true }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (i: AssetIdentifier) => api("DELETE", `/assets/${asset.id}/identifiers/${i.id}`), onSuccess: refresh });
  const err = add.error ?? primary.error ?? remove.error;
  const check = checks.get(0);

  return (
    <section className="flex flex-col gap-3" aria-labelledby={`idents-${asset.id}`}>
      <h3 id={`idents-${asset.id}`} className="label m-0">Identifiers</h3>
      <ErrorNote error={err instanceof ApiError && Object.keys(err.fields).length === 0 ? err : null} />
      {err instanceof ApiError && err.fields.identifiers && <p className="field-error m-0" role="alert">{err.fields.identifiers.join(" ")}</p>}
      {rows.length === 0 && <p className="m-0 text-muted">No identifiers yet.</p>}
      <ul className="m-0 list-none divide-y divide-line rounded-md border border-line p-0">
        {rows.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
            <Badge tone="info">{i.kind_label}</Badge>
            <span className="mono min-w-0 flex-1 break-all text-[14px]">{i.value}</span>
            {i.is_primary ? <span className="text-[13px] text-muted">Primary</span> : <Button size="sm" loading={primary.isPending && primary.variables?.id === i.id} onClick={() => primary.mutate(i)}>Make primary</Button>}
            <Button size="sm" aria-label={`Remove ${i.value}`} loading={remove.isPending && remove.variables?.id === i.id} onClick={() => remove.mutate(i)}><Trash2 size={14} aria-hidden /></Button>
          </li>
        ))}
      </ul>
      <form className="flex flex-col gap-1" onSubmit={(e) => { e.preventDefault(); if (draft.value.trim()) add.mutate(); }}>
        <div className="flex flex-col gap-2 sm:flex-row">
          <KindSelect label="New identifier type" value={draft.kind} onChange={(v) => setDraft({ ...draft, kind: v })} />
          <TextInput aria-label="New identifier" placeholder="Add an identifier" maxLength={500} value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
          <Button type="submit" loading={add.isPending} disabled={!draft.value.trim() || (!!check && check.status !== "free")}><Plus size={16} aria-hidden /> Add</Button>
        </div>
        <CheckLine res={check} typed={!!draft.value.trim()} />
      </form>
    </section>
  );
}
