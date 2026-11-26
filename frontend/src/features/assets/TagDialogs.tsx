import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Asset, AssetTag, TagResult } from "../../api/types";
import { Alert, Button, ConfirmDialog, ErrorNote, Field, fieldError, Modal, TextInput } from "../../design/ui";
import { invalidateAssets } from "./AssetEditor";

const split = (text: string) => text.split(/[,;]/).map((t) => t.trim()).filter(Boolean);
const plural = (n: number) => `${n} asset${n === 1 ? "" : "s"}`;

/** Add tags to, or remove tags from, the assets ticked in the list. */
export function TagSelectedDialog({ assets, known, onClose, onDone }: { assets: Asset[]; known: AssetTag[]; onClose: () => void; onDone: (r: TagResult) => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [remove, setRemove] = useState<Set<string>>(new Set());
  const present = [...new Set(assets.flatMap((a) => a.tags))].sort((a, b) => a.localeCompare(b));
  const add = split(text);
  const save = useMutation({
    mutationFn: () => api<TagResult>("POST", "/assets/tags/assign", { ids: assets.map((a) => a.id), add, remove: [...remove] }),
    onSuccess: (r) => { invalidateAssets(qc); onDone(r); onClose(); },
  });
  const toggle = (t: string) => setRemove((s) => { const n = new Set(s); if (n.has(t)) n.delete(t); else n.add(t); return n; });
  const submit = (e: FormEvent) => { e.preventDefault(); if (add.length || remove.size) save.mutate(); };

  return (
    <Modal open onClose={onClose} title={`Tag ${plural(assets.length)}`}>
      <form className="space-y-5 p-6" onSubmit={submit}>
        <Field label="Add tags" hint="Comma separated, for example service-delivery" error={fieldError(save.error, "add")}>
          {(p) => <TextInput {...p} list="known-tags" value={text} onChange={(e) => setText(e.target.value)} />}
        </Field>
        <datalist id="known-tags">{known.map((t) => <option key={t.tag} value={t.tag} />)}</datalist>
        {present.length > 0 && (
          <fieldset className="m-0 border-0 p-0">
            <legend className="mb-2 font-medium">Remove tags</legend>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {present.map((t) => <label key={t} className="check"><input type="checkbox" checked={remove.has(t)} onChange={() => toggle(t)} /> {t}</label>)}
            </div>
          </fieldset>
        )}
        <ErrorNote error={save.error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={add.length === 0 && remove.size === 0}>Save tags</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Rename or delete a tag on every asset that carries it, within the organisation filter. */
export function ManageTagsDialog({ tags, organisation, organisationName, onClose, onChanged }: {
  tags: AssetTag[]; organisation: string; organisationName?: string; onClose: () => void; onChanged: (from: string, to: string) => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [removing, setRemoving] = useState<AssetTag | null>(null);
  const [result, setResult] = useState<TagResult | null>(null);
  const body = organisation ? { organisation } : {};
  const done = (r: TagResult, from: string, to: string) => {
    invalidateAssets(qc);
    setResult(r);
    setEditing(null);
    setRemoving(null);
    // A tag that stayed on a skipped asset is still a valid filter.
    if (r.skipped.length === 0) onChanged(from, to);
  };
  const rename = useMutation({
    mutationFn: (from: string) => api<TagResult>("POST", "/assets/tags/rename", { ...body, tag: from, new_name: name.trim() }),
    onSuccess: (r, from) => done(r, from, name.trim()),
  });
  const remove = useMutation({
    mutationFn: (tag: string) => api<TagResult>("POST", "/assets/tags/delete", { ...body, tag }),
    onSuccess: (r, tag) => done(r, tag, ""),
  });
  const merges = editing !== null && tags.some((t) => t.tag.toLowerCase() === name.trim().toLowerCase() && t.tag !== editing);

  return (
    <>
      <Modal open={!removing} onClose={() => { if (!removing) onClose(); }} title="Manage tags">
        <div className="space-y-4 p-6">
          <p className="m-0 text-muted">
            Changes apply to every asset {organisationName ? `of ${organisationName}` : "in all organisations"}. To add a tag, tick assets in the list and choose Tag selected.
          </p>
          {result && (
            <Alert tone={result.skipped.length ? "warn" : "ok"}>
              <p className="m-0">{plural(result.updated)} updated.{result.skipped.length > 0 && ` ${result.skipped.length} skipped:`}</p>
              {result.skipped.length > 0 && <ul className="m-0 mt-1 list-disc pl-5">{result.skipped.slice(0, 5).map((s) => <li key={s.id}>{s.name}: {s.reason}</li>)}</ul>}
            </Alert>
          )}
          {tags.length === 0 && <p className="m-0">No tags yet.</p>}
          <ul className="m-0 list-none divide-y divide-line p-0">
            {tags.map((t) => (
              <li key={t.tag} className="py-3">
                {editing === t.tag ? (
                  <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (name.trim() && name.trim() !== t.tag) rename.mutate(t.tag); }}>
                    <Field label={`New name for ${t.tag}`} hint={merges ? "That tag exists. The two will be merged." : undefined} error={fieldError(rename.error, "new_name")}>
                      {(p) => <TextInput {...p} autoFocus maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />}
                    </Field>
                    <ErrorNote error={rename.error} />
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button size="sm" onClick={() => setEditing(null)}>Cancel</Button>
                      <Button size="sm" type="submit" variant="primary" loading={rename.isPending} disabled={!name.trim() || name.trim() === t.tag}>{merges ? "Merge" : "Rename"}</Button>
                    </div>
                  </form>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      <span className="block font-medium">{t.tag}</span>
                      <span className="block text-[14px] text-muted">{plural(t.assets)}, {t.onboarded} onboarded{t.archived > 0 && `, ${t.archived} archived`}</span>
                    </span>
                    <span className="flex gap-2">
                      <Button size="sm" aria-label={`Rename ${t.tag}`} onClick={() => { rename.reset(); setResult(null); setName(t.tag); setEditing(t.tag); }}>Rename</Button>
                      <Button size="sm" variant="danger" aria-label={`Delete ${t.tag}`} onClick={() => { remove.reset(); setResult(null); setRemoving(t); }}>Delete</Button>
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </Modal>
      <ConfirmDialog
        open={!!removing}
        title={`Delete tag ${removing?.tag ?? ""}`}
        body={`The tag is taken off ${plural(removing?.assets ?? 0)}${organisationName ? ` of ${organisationName}` : ""}. The assets stay. Archived assets keep it.`}
        confirmLabel="Delete tag"
        danger
        busy={remove.isPending}
        error={remove.error}
        onConfirm={() => removing && remove.mutate(removing.tag)}
        onClose={() => setRemoving(null)}
      />
    </>
  );
}
