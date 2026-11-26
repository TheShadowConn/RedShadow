import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, BookOpenCheck, CalendarClock, ChevronLeft, ChevronRight, GripVertical, History, ImagePlus, ListPlus, Pencil, Plus, Trash2 } from "lucide-react";

import { api, upload } from "../../api/client";
import { Link } from "react-router-dom";

import { useAuth } from "../../api/auth";
import { Markdown } from "../findings/shared";
import { MarkdownField } from "./MarkdownField";
import { SCENARIO_STATUSES, type ScenarioTemplate, type Engagement, type HistoryEvent, type Page, type Scenario, type ScenarioImage, type ScenarioStatus, type ScenarioSummary } from "../../api/types";
import {
  Alert, Badge, Button, EmptyState, ErrorNote, ErrorState, Field, fieldError, formatDate, formatDay, label, LoadingRows, Modal, Textarea, TextInput,
} from "../../design/ui";

const TONE: Record<ScenarioStatus, "ok" | "warn" | "fail" | "info"> = { planned: "info", in_progress: "warn", tested: "ok", deferred: "warn", cancelled: "fail" };
const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);
const MAX_PICTURES = 10;
const FORM = "space-y-6 p-6 sm:p-8";
const ACTIONS = "flex flex-wrap justify-end gap-3 border-t border-line pt-6";

/** Moves the user can make from each status, with the button text. Same rules as the backend. */
const MOVES: Record<ScenarioStatus, Array<[ScenarioStatus, string]>> = {
  planned: [["in_progress", "Start testing"], ["tested", "Mark tested"], ["deferred", "Defer"], ["cancelled", "Cancel"]],
  in_progress: [["tested", "Mark tested"], ["planned", "Back to planned"], ["deferred", "Defer"], ["cancelled", "Cancel"]],
  deferred: [["planned", "Plan again"], ["in_progress", "Start testing"], ["cancelled", "Cancel"]],
  tested: [["in_progress", "Reopen"]],
  cancelled: [["planned", "Restore"]],
};

export function dateRange(s: Pick<Scenario, "planned_start" | "planned_end">): string {
  if (!s.planned_start && !s.planned_end) return "Not scheduled";
  if (s.planned_start && s.planned_end && s.planned_start !== s.planned_end) return `${formatDay(s.planned_start)} to ${formatDay(s.planned_end)}`;
  return formatDay((s.planned_start ?? s.planned_end)!);
}

/** "3 of 5 tested" with a bar. Cancelled scenarios do not count. */
export function ScenarioProgress({ s, compact }: { s?: ScenarioSummary; compact?: boolean }) {
  if (!s || s.total === 0) return compact ? <span className="text-muted">No scenarios</span> : null;
  const pct = Math.round((s.tested / s.total) * 100);
  return (
    <div className={compact ? "min-w-28" : "space-y-1.5"}>
      <div role="progressbar" aria-valuemin={0} aria-valuemax={s.total} aria-valuenow={s.tested} aria-label={`${s.tested} of ${s.total} scenarios tested`} className="h-2 overflow-hidden rounded-full bg-raised">
        <div className="h-full rounded-full bg-ok" style={{ width: `${pct}%` }} />
      </div>
      <p className="m-0 text-[13px] text-muted">
        {s.tested} of {s.total} tested{!compact && s.overdue > 0 ? ` · ${s.overdue} overdue` : ""}{!compact && s.deferred > 0 ? ` · ${s.deferred} deferred` : ""}
      </p>
    </div>
  );
}

/* Tab */

export function ScenariosTab({ eng }: { eng: Engagement }) {
  const qc = useQueryClient();
  const perms = new Set(eng.permissions);
  const { can } = useAuth();
  const canRetest = can("retests.create");
  const writable = perms.has("engagement_scenarios.manage") && !eng.archived_at;
  const key = ["scenarios", eng.id];
  const [dialog, setDialog] = useState<null | { kind: "add" } | { kind: "bulk" } | { kind: "template" } | { kind: "edit" | "reschedule" | "status" | "history"; s: Scenario; to?: ScenarioStatus }>(null);
  const [view, setView] = useState<{ images: ScenarioImage[]; at: number } | null>(null);
  const dragId = useRef<string | null>(null);
  const q = useQuery({ queryKey: key, queryFn: () => api<Scenario[]>("GET", `/engagements/${eng.id}/scenarios`) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ["engagement", eng.id] });
    void qc.invalidateQueries({ queryKey: ["engagements"] });
    void qc.invalidateQueries({ queryKey: ["history", eng.id] });
    void qc.invalidateQueries({ queryKey: ["calendar-scenarios"] });
  };
  const reorder = useMutation({
    mutationFn: (ids: string[]) => api<Scenario[]>("POST", `/engagements/${eng.id}/scenario-order`, { ids }),
    onMutate: (ids) => {
      const old = qc.getQueryData<Scenario[]>(key);
      if (old) qc.setQueryData(key, ids.map((id) => old.find((s) => s.id === id)!).filter(Boolean));
      return { old };
    },
    onError: (_e, _v, ctx) => { if (ctx?.old) qc.setQueryData(key, ctx.old); },
    onSettled: refresh,
  });
  const rows = q.data ?? [];
  const move = (id: string, to: number) => {
    const ids = rows.map((s) => s.id);
    const from = ids.indexOf(id);
    if (from < 0 || to < 0 || to >= ids.length || from === to) return;
    ids.splice(to, 0, ...ids.splice(from, 1));
    reorder.mutate(ids);
  };

  return (
    <div className="space-y-4">
      {eng.archived_at && <Alert tone="warn">This engagement is archived. It is read-only.</Alert>}
      <div className="card card-pad flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0 flex-1 basis-64">
          <h2 className="text-lg">Test scenarios</h2>
          <p className="m-0 mt-1 text-[15px] text-muted">What is tested in this engagement and when. Findings stay with the whole engagement.</p>
          <div className="mt-3 max-w-md"><ScenarioProgress s={eng.scenarios} /></div>
        </div>
        {writable && (
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => setDialog({ kind: "template" })}><BookOpenCheck size={18} aria-hidden /> From template</Button>
            <Button onClick={() => setDialog({ kind: "bulk" })}><ListPlus size={18} aria-hidden /> Add several</Button>
            <Button variant="primary" onClick={() => setDialog({ kind: "add" })}><Plus size={18} aria-hidden /> Add scenario</Button>
          </div>
        )}
      </div>
      <ErrorNote error={reorder.error} />
      {q.isPending && <div className="card"><LoadingRows rows={3} /></div>}
      {q.isError && <div className="card"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>}
      {q.data && rows.length === 0 && (
        <div className="card"><EmptyState title="No scenarios yet" body={writable ? "List the use cases of this test. Each one gets its own description, pictures and dates." : "Nothing has been listed for this engagement yet."} /></div>
      )}
      {rows.length > 0 && (
        <ol className="m-0 list-none space-y-3 p-0">
          {rows.map((s, i) => (
            <li key={s.id}
              onDragOver={(e) => { if (dragId.current) e.preventDefault(); }}
              onDrop={(e) => { e.preventDefault(); if (dragId.current && dragId.current !== s.id) move(dragId.current, i); dragId.current = null; }}
              className="card card-pad">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 basis-72 items-start gap-2">
                  {writable && rows.length > 1 && (
                    <span draggable aria-hidden onDragStart={() => { dragId.current = s.id; }} onDragEnd={() => { dragId.current = null; }} className="mt-1 hidden cursor-grab text-muted md:inline"><GripVertical size={18} /></span>
                  )}
                  <div className="min-w-0">
                    <h3 className="m-0 break-words text-lg">{s.name}</h3>
                    <p className="m-0 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[14px] text-muted">
                      <Badge tone={TONE[s.status]}>{label(SCENARIO_STATUSES, s.status)}</Badge>
                      {s.overdue && <Badge tone="fail">Overdue</Badge>}
                      <span>{dateRange(s)}</span>
                      {s.completed_on && <span>Tested {formatDay(s.completed_on)}</span>}
                    </p>
                    {s.status_reason && <p className="m-0 mt-2 text-[14px] text-muted">Reason: {s.status_reason}</p>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {writable && rows.length > 1 && (
                    <>
                      <Button size="sm" aria-label={`Move ${s.name} up`} disabled={i === 0 || reorder.isPending} onClick={() => move(s.id, i - 1)}><ArrowUp size={16} aria-hidden /></Button>
                      <Button size="sm" aria-label={`Move ${s.name} down`} disabled={i === rows.length - 1 || reorder.isPending} onClick={() => move(s.id, i + 1)}><ArrowDown size={16} aria-hidden /></Button>
                    </>
                  )}
                  {perms.has("audit.view_engagement") && <Button size="sm" aria-label={`History of ${s.name}`} onClick={() => setDialog({ kind: "history", s })}><History size={16} aria-hidden /></Button>}
                  {writable && <Button size="sm" onClick={() => setDialog({ kind: "edit", s })}><Pencil size={16} aria-hidden /> Edit</Button>}
                  {writable && !["tested", "cancelled"].includes(s.status) && <Button size="sm" onClick={() => setDialog({ kind: "reschedule", s })}><CalendarClock size={16} aria-hidden /> Reschedule</Button>}
                </div>
              </div>
              {s.description && <div className="md-breaks mt-3"><Markdown text={s.description} /></div>}
              {s.images.length > 0 && (
                <ul className="m-0 mt-4 flex list-none flex-wrap gap-3 p-0">
                  {s.images.map((im, at) => (
                    <li key={im.id} className="h-52 min-w-0 max-w-full sm:h-72">
                      <button type="button" aria-label={`Open picture ${im.original_name}`} onClick={() => setView({ images: s.images, at })} className="block h-full cursor-zoom-in overflow-hidden rounded-md border border-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                        <img src={im.download_url} alt={im.original_name} loading="lazy" className="block h-full w-auto max-w-full object-contain" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {(writable && MOVES[s.status].length > 0) || (s.status === "tested" && canRetest && !eng.archived_at) ? (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
                  {s.status === "tested" && canRetest && !eng.archived_at && (
                    <Link to={`/verification?engagement=${eng.id}&scenario=${encodeURIComponent(s.name)}`} className="btn btn-secondary btn-sm">Retest this scenario</Link>
                  )}
                  {writable && MOVES[s.status].map(([to, text]) => (
                    <Button key={to} size="sm" variant={to === "cancelled" ? "danger" : "secondary"} onClick={() => setDialog({ kind: "status", s, to })}>{text}</Button>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      )}

      {dialog?.kind === "add" && <ScenarioForm eng={eng} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "edit" && <ScenarioForm eng={eng} scenario={rows.find((r) => r.id === dialog.s.id) ?? dialog.s} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "template" && <TemplateDialog eng={eng} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "bulk" && <BulkAdd eng={eng} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "reschedule" && <Reschedule eng={eng} s={dialog.s} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "status" && dialog.to && <StatusDialog eng={eng} s={dialog.s} to={dialog.to} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "history" && <ScenarioHistory eng={eng} s={dialog.s} onClose={() => setDialog(null)} />}
      {view && <Lightbox images={view.images} at={view.at} onClose={() => setView(null)} />}
    </div>
  );
}

/* Add and edit, with pictures */

function ScenarioForm({ eng, scenario, onClose, onDone }: { eng: Engagement; scenario?: Scenario; onClose: () => void; onDone: () => void }) {
  const editing = !!scenario;
  const [name, setName] = useState(scenario?.name ?? "");
  const [description, setDescription] = useState(scenario?.description ?? "");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [pictureError, setPictureError] = useState<unknown>(null);
  const [saved, setSaved] = useState<Scenario | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const base = `/engagements/${eng.id}/scenarios`;
  const live = saved ?? scenario;
  const room = MAX_PICTURES - (live?.images.length ?? 0) - files.length;

  const uploadAll = async (id: string, list: File[]) => {
    for (const f of list) await upload("POST", `${base}/${id}/images`, f);
  };
  const save = useMutation({
    mutationFn: async () => {
      const sc = editing
        ? await api<Scenario>("PATCH", `${base}/${scenario.id}`, { name, description })
        : await api<Scenario>("POST", base, { name, description, planned_start: start || null, planned_end: end || null });
      setSaved(sc);
      try {
        await uploadAll(sc.id, files);
      } catch (err) {
        setPictureError(err);
        setFiles([]);
        throw err;
      }
      return sc;
    },
    onSuccess: () => { onDone(); onClose(); },
    onError: onDone,
  });
  const addNow = useMutation({
    mutationFn: (list: File[]) => uploadAll(scenario!.id, list),
    onSuccess: onDone,
  });
  const removePicture = useMutation({
    mutationFn: (id: string) => api("DELETE", `${base}/${scenario!.id}/images/${id}`),
    onSuccess: onDone,
  });
  const pick = (list: FileList | null) => {
    if (!list) return;
    const chosen = [...list].slice(0, Math.max(room, 0));
    if (editing) addNow.mutate(chosen);
    else setFiles((f) => [...f, ...chosen]);
    if (fileInput.current) fileInput.current.value = "";
  };

  return (
    <Modal open wide="form" onClose={onClose} title={editing ? "Edit scenario" : "Add scenario"}>
      <form className={FORM} onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        <Field label="Name" hint="Kept exactly as you type it. Must be unique in this engagement." error={fieldError(save.error, "name")}>
          {(p) => <TextInput {...p} required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Description" hint="What is tested and how. Markdown works: bullets, numbers and links. Pictures go below." error={fieldError(save.error, "description")}>
          {(p) => <MarkdownField {...p} maxLength={20000} value={description} onChange={setDescription} />}
        </Field>
        {!editing && (
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label="Planned start" hint="Optional" error={fieldError(save.error, "planned_start")}>{(p) => <TextInput {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
            <Field label="Planned end" hint="Optional" error={fieldError(save.error, "planned_end")}>{(p) => <TextInput {...p} type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
          </div>
        )}
        <section aria-labelledby="pics-h" className="space-y-4 rounded-lg border border-line bg-raised/40 p-5">
          <div className="space-y-1">
            <h3 id="pics-h" className="m-0 text-[15px] font-medium">Pictures</h3>
            <p className="m-0 text-[14px] text-muted">PNG, JPEG, GIF or WebP. Up to {MAX_PICTURES} per scenario.</p>
          </div>
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0 empty:hidden">
            {live?.images.map((im) => (
              <li key={im.id} className="relative h-36 max-w-full">
                <img src={im.download_url} alt={im.original_name} className="block h-full w-auto max-w-full rounded-md border border-line object-contain" />
                {editing && (
                  <button type="button" aria-label={`Remove picture ${im.original_name}`} disabled={removePicture.isPending} onClick={() => removePicture.mutate(im.id)} className="absolute top-1 right-1 rounded bg-surface/90 p-1 text-fail shadow-sm"><Trash2 size={14} aria-hidden /></button>
                )}
              </li>
            ))}
            {files.map((f, i) => (
              <li key={`${f.name}${i}`} className="flex h-36 min-w-40 max-w-full flex-col justify-between rounded-md border border-dashed border-line p-3 text-[13px]">
                <span className="[overflow-wrap:anywhere]">{f.name}</span>
                <button type="button" className="self-start text-fail underline" onClick={() => setFiles((l) => l.filter((_, j) => j !== i))}>Remove</button>
              </li>
            ))}
          </ul>
          <ErrorNote error={addNow.error ?? removePicture.error ?? pictureError} />
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden onChange={(e) => pick(e.target.files)} />
          <Button size="sm" disabled={room <= 0} loading={addNow.isPending} onClick={() => fileInput.current?.click()}><ImagePlus size={16} aria-hidden /> Add pictures</Button>
        </section>
        <div className={ACTIONS}>
          <Button onClick={onClose}>{editing ? "Close" : "Cancel"}</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!name.trim()}>{editing ? "Save changes" : "Add scenario"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/* Starter templates */

function TemplateDialog({ eng, onClose, onDone }: { eng: Engagement; onClose: () => void; onDone: () => void }) {
  const [key, setKey] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [skipped, setSkipped] = useState<string[] | null>(null);
  const q = useQuery({ queryKey: ["scenario-templates", eng.id], queryFn: () => api<ScenarioTemplate[]>("GET", `/engagements/${eng.id}/scenario-templates`) });
  const tpl = q.data?.find((t) => t.key === key);
  const choose = (k: string) => { setKey(k); setPicked(new Set(q.data?.find((t) => t.key === k)?.items.map((i) => i.index))); };
  const toggle = (i: number) => setPicked((p) => { const n = new Set(p); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const save = useMutation({
    mutationFn: () => api<{ created: Scenario[]; skipped: string[] }>("POST", `/engagements/${eng.id}/scenario-templates/apply`, { template: key, items: [...picked] }),
    onSuccess: (r) => { onDone(); if (r.skipped.length) setSkipped(r.skipped); else onClose(); },
  });
  return (
    <Modal open onClose={onClose} title="Add from a template">
      <div className={FORM}>
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {skipped ? (
          <>
            <Alert tone="ok">Added. {skipped.length} already in this engagement and skipped: {skipped.join(", ")}.</Alert>
            <div className={ACTIONS}><Button variant="primary" onClick={onClose}>Done</Button></div>
          </>
        ) : q.data && (
          <form className="space-y-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
            <ErrorNote error={noFieldErrors(save.error)} />
            <Field label="Template" hint="A starting list. Everything can be edited afterwards. Names already in this engagement are skipped.">
              {(p) => (
                <select {...p} className="select" required value={key} onChange={(e) => choose(e.target.value)}>
                  <option value="" disabled>Choose a template</option>
                  {q.data.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
                </select>
              )}
            </Field>
            {tpl && (
              <fieldset className="m-0 space-y-1 border-0 p-0">
                <legend className="label mb-2 flex w-full items-center justify-between gap-3">
                  <span>{picked.size} of {tpl.items.length} selected</span>
                  <button type="button" className="text-accent underline-offset-2 hover:underline" onClick={() => setPicked(picked.size === tpl.items.length ? new Set() : new Set(tpl.items.map((i) => i.index)))}>{picked.size === tpl.items.length ? "Clear all" : "Select all"}</button>
                </legend>
                <ul className="m-0 max-h-80 list-none divide-y divide-line overflow-y-auto rounded-lg border border-line p-0">
                  {tpl.items.map((i) => (
                    <li key={i.index}>
                      <label className="flex cursor-pointer items-start gap-3 p-3 hover:bg-raised">
                        <input type="checkbox" className="mt-1 h-5 w-5 flex-none accent-[var(--color-accent)]" checked={picked.has(i.index)} onChange={() => toggle(i.index)} />
                        <span className="min-w-0"><span className="block font-medium">{i.name}</span><span className="block text-[14px] text-muted">{i.description}</span></span>
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            )}
            <div className={ACTIONS}>
              <Button onClick={onClose}>Cancel</Button>
              <Button type="submit" variant="primary" loading={save.isPending} disabled={!tpl || picked.size === 0}>Add {picked.size || ""} scenario{picked.size === 1 ? "" : "s"}</Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}

/* Add several at once */

function BulkAdd({ eng, onClose, onDone }: { eng: Engagement; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("");
  const names = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const save = useMutation({
    mutationFn: () => api<Scenario[]>("POST", `/engagements/${eng.id}/scenarios-bulk`, { names }),
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title="Add several scenarios">
      <form className={FORM} onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        <Field label="One scenario per line" hint="Names are kept as typed. Dates, descriptions and pictures can be added afterwards." error={fieldError(save.error, "names")}>
          {(p) => <Textarea {...p} rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Login and session handling\nPayment flow\nAdmin portal"} />}
        </Field>
        <p className="m-0 text-[14px] text-muted">{names.length} scenario{names.length === 1 ? "" : "s"} (at most 50 at once). If one name is taken, none are added.</p>
        <div className={ACTIONS}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={names.length === 0 || names.length > 50}>Add {names.length || ""} scenario{names.length === 1 ? "" : "s"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/* Reschedule and status */

function Reschedule({ eng, s, onClose, onDone }: { eng: Engagement; s: Scenario; onClose: () => void; onDone: () => void }) {
  const [start, setStart] = useState(s.planned_start ?? "");
  const [end, setEnd] = useState(s.planned_end ?? "");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => api<Scenario>("POST", `/engagements/${eng.id}/scenarios/${s.id}/reschedule`, { planned_start: start || null, planned_end: end || null, reason }),
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={`Reschedule: ${s.name}`}>
      <form className={FORM} onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        {s.status === "deferred" && <p className="m-0 text-[14px] text-muted">Setting dates makes this scenario planned again.</p>}
        <div className="grid gap-6 sm:grid-cols-2">
          <Field label="Planned start" error={fieldError(save.error, "planned_start")}>{(p) => <TextInput {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
          <Field label="Planned end" error={fieldError(save.error, "planned_end")}>{(p) => <TextInput {...p} type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
        </div>
        <Field label="Reason" hint="Optional. Recorded in the history." error={fieldError(save.error, "reason")}>{(p) => <TextInput {...p} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        <div className={ACTIONS}><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save dates</Button></div>
      </form>
    </Modal>
  );
}

const STATUS_TITLES: Record<ScenarioStatus, string> = { planned: "Plan scenario", in_progress: "Start testing", tested: "Mark as tested", deferred: "Defer scenario", cancelled: "Cancel scenario" };

function StatusDialog({ eng, s, to, onClose, onDone }: { eng: Engagement; s: Scenario; to: ScenarioStatus; onClose: () => void; onDone: () => void }) {
  const needsReason = to === "deferred" || to === "cancelled";
  const [reason, setReason] = useState("");
  const [doneOn, setDoneOn] = useState(new Date().toISOString().slice(0, 10));
  const [start, setStart] = useState(to === "deferred" ? "" : (s.planned_start ?? ""));
  const [end, setEnd] = useState(to === "deferred" ? "" : (s.planned_end ?? ""));
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { status: to };
      if (needsReason) body.reason = reason;
      if (to === "tested") body.completed_on = doneOn;
      if (to === "deferred" && (start || end)) { body.planned_start = start || null; body.planned_end = end || null; }
      return api<Scenario>("POST", `/engagements/${eng.id}/scenarios/${s.id}/status`, body);
    },
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={`${STATUS_TITLES[to]}: ${s.name}`}>
      <form className={FORM} onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        {needsReason && <Field label="Reason" hint="Required. Recorded in the history." error={fieldError(save.error, "reason")}>{(p) => <TextInput {...p} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>}
        {to === "tested" && <Field label="Tested on" error={fieldError(save.error, "completed_on")}>{(p) => <TextInput {...p} type="date" required max={new Date().toISOString().slice(0, 10)} value={doneOn} onChange={(e) => setDoneOn(e.target.value)} />}</Field>}
        {to === "deferred" && (
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label="New start" hint="Optional: when it will be done" error={fieldError(save.error, "planned_start")}>{(p) => <TextInput {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
            <Field label="New end" hint="Optional" error={fieldError(save.error, "planned_end")}>{(p) => <TextInput {...p} type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
          </div>
        )}
        {!needsReason && to !== "tested" && <p className="m-0">The scenario becomes {label(SCENARIO_STATUSES, to).toLowerCase()}. The change is recorded in the history.</p>}
        <div className={ACTIONS}>
          <Button onClick={onClose}>Close</Button>
          <Button type="submit" variant={to === "cancelled" ? "danger" : "primary"} loading={save.isPending} disabled={needsReason && !reason.trim()}>{STATUS_TITLES[to]}</Button>
        </div>
      </form>
    </Modal>
  );
}

/* History of one scenario */

const ACTION_TEXT: Record<string, string> = {
  "engagement.scenario_added": "Added",
  "engagement.scenario_updated": "Edited",
  "engagement.scenario_rescheduled": "Rescheduled",
  "engagement.scenario_status_changed": "Status changed",
  "attachment.uploaded": "Picture added",
  "attachment.deleted": "Picture removed",
};

function changeLines(changes: Record<string, unknown>): string[] {
  return Object.entries(changes ?? {}).map(([k, v]) => {
    const [a, b] = Array.isArray(v) ? v : [null, v];
    return `${k.replace(/_/g, " ")}: ${a === null || a === "" ? "none" : String(a)} to ${b === null || b === "" ? "none" : String(b)}`;
  });
}

function ScenarioHistory({ eng, s, onClose }: { eng: Engagement; s: Scenario; onClose: () => void }) {
  const q = useQuery({ queryKey: ["scenario-history", eng.id, s.id], queryFn: () => api<Page<HistoryEvent>>("GET", `/engagements/${eng.id}/scenarios/${s.id}/history`) });
  return (
    <Modal open onClose={onClose} title={`History: ${s.name}`}>
      <div className="space-y-5 p-6 sm:p-8">
        {q.isPending && <LoadingRows rows={3} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.results.length === 0 && <p className="m-0 text-muted">Nothing recorded yet.</p>}
        {q.data && q.data.results.length > 0 && (
          <ol className="m-0 list-none divide-y divide-line p-0">
            {q.data.results.map((ev) => (
              <li key={ev.id} className="space-y-1 py-3">
                <p className="m-0 font-medium">{ACTION_TEXT[ev.action] ?? ev.action}</p>
                <p className="m-0 text-[14px] text-muted">{ev.actor_label} · {formatDate(ev.occurred_at)}</p>
                {changeLines(ev.changes).map((l) => <p key={l} className="m-0 text-[14px]">{l}</p>)}
              </li>
            ))}
          </ol>
        )}
        <div className={ACTIONS}><Button onClick={onClose}>Close</Button></div>
      </div>
    </Modal>
  );
}

/* Picture viewer */

function Lightbox({ images, at, onClose }: { images: ScenarioImage[]; at: number; onClose: () => void }) {
  const [i, setI] = useState(at);
  const im = images[i];
  return (
    <Modal open wide onClose={onClose} title={im.original_name}>
      <div className="space-y-4 p-4 sm:p-6" onKeyDown={(e) => { if (e.key === "ArrowLeft" && i > 0) setI(i - 1); if (e.key === "ArrowRight" && i < images.length - 1) setI(i + 1); }}>
        <img src={im.download_url} alt={im.original_name} className="mx-auto max-h-[78vh] w-full rounded-md object-contain" />
        <div className="flex items-center justify-between gap-3">
          <Button aria-label="Previous picture" disabled={i === 0} onClick={() => setI(i - 1)}><ChevronLeft size={18} aria-hidden /></Button>
          <span className="text-[14px] text-muted">{i + 1} of {images.length}</span>
          <Button aria-label="Next picture" disabled={i === images.length - 1} onClick={() => setI(i + 1)}><ChevronRight size={18} aria-hidden /></Button>
        </div>
      </div>
    </Modal>
  );
}
