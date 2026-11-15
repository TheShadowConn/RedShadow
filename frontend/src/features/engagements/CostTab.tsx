import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { useAuth } from "../../api/auth";
import { api } from "../../api/client";
import { COST_CATEGORIES, CURRENCIES, type CostLine, type Engagement, type EngagementCosts } from "../../api/types";
import {
  Alert, Button, ConfirmDialog, EmptyState, ErrorNote, ErrorState, Field, fieldError, formatDay, label, LoadingRows, Modal, money,
  Select, TextInput,
} from "../../design/ui";

const noFieldErrors = (e: unknown) => (e && !Object.keys((e as { fields?: object }).fields ?? {}).length ? e : null);
const today = () => new Date().toISOString().slice(0, 10);

export function CostTab({ eng }: { eng: Engagement }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<CostLine | "new" | null>(null);
  const [removing, setRemoving] = useState<CostLine | null>(null);
  const key = ["eng-costs", eng.id];
  const q = useQuery({ queryKey: key, queryFn: () => api<EngagementCosts>("GET", `/engagements/${eng.id}/costs`) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ["history", eng.id] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const remove = useMutation({ mutationFn: (c: CostLine) => api("DELETE", `/engagements/${eng.id}/costs/${c.id}`), onSuccess: () => { refresh(); setRemoving(null); } });
  const writable = can("engagement_costs.manage") && !eng.archived_at;

  return (
    <div className="space-y-4">
      {eng.archived_at && <Alert tone="warn">This engagement is archived. It is read-only.</Alert>}
      <section aria-labelledby="cost-total-h" className="card card-pad">
        <h2 id="cost-total-h" className="mb-3 text-xl">Total cost</h2>
        {q.isPending && <LoadingRows rows={1} />}
        {q.data && q.data.totals.length === 0 && <p className="m-0 text-muted">No cost recorded yet.</p>}
        {q.data && q.data.totals.length > 0 && (
          <ul className="m-0 flex list-none flex-wrap gap-x-10 gap-y-3 p-0">
            {q.data.totals.map((t) => (
              <li key={t.currency}>
                <p className="mono m-0 text-[28px] font-semibold leading-tight">{money(t.total, t.currency)}</p>
                <p className="m-0 text-[14px] text-muted">{t.currency} · {t.lines} {t.lines === 1 ? "line" : "lines"}</p>
              </li>
            ))}
          </ul>
        )}
        {q.data && q.data.totals.length > 1 && <p className="mb-0 mt-3 text-[14px] text-muted">Currencies are shown separately. No exchange rate is applied.</p>}
      </section>

      <div className="card overflow-hidden">
        {writable && <div className="flex justify-end border-b border-line p-4"><Button variant="primary" onClick={() => setEditing("new")}><Plus size={18} aria-hidden /> Add cost</Button></div>}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && q.data.items.length === 0 && <EmptyState title="No cost lines" body="Add labour, tools, travel or other costs. Each line has its own currency." />}
        {q.data && q.data.items.length > 0 && (
          <ul className="m-0 list-none divide-y divide-line p-0">
            {q.data.items.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="m-0 font-medium"><span className="mono">{money(c.amount, c.currency)}</span> <span className="text-[14px] font-normal text-muted">{label(COST_CATEGORIES, c.category)}</span></p>
                  <p className="m-0 break-words text-[14px] text-muted">{formatDay(c.incurred_on)}{c.description && ` · ${c.description}`}{c.created_by && ` · ${c.created_by.display_name}`}</p>
                </div>
                {writable && (
                  <div className="flex gap-2">
                    <Button size="sm" aria-label={`Edit cost ${money(c.amount, c.currency)}`} onClick={() => setEditing(c)}><Pencil size={16} aria-hidden /></Button>
                    <Button size="sm" variant="danger" aria-label={`Delete cost ${money(c.amount, c.currency)}`} onClick={() => { remove.reset(); setRemoving(c); }}><Trash2 size={16} aria-hidden /></Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {editing && <CostForm eng={eng} line={editing === "new" ? null : editing} onClose={() => setEditing(null)} onDone={refresh} />}
      <ConfirmDialog open={!!removing} title="Delete cost line" body={removing ? `${money(removing.amount, removing.currency)} is removed from this engagement. The deletion is recorded in the history.` : ""} confirmLabel="Delete" danger busy={remove.isPending} error={remove.error} onConfirm={() => removing && remove.mutate(removing)} onClose={() => setRemoving(null)} />
    </div>
  );
}

function CostForm({ eng, line, onClose, onDone }: { eng: Engagement; line: CostLine | null; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(line?.amount ?? "");
  const [currency, setCurrency] = useState(line?.currency ?? "USD");
  const [category, setCategory] = useState(line?.category ?? "labour");
  const [incurredOn, setIncurredOn] = useState(line?.incurred_on ?? today());
  const [description, setDescription] = useState(line?.description ?? "");
  const save = useMutation({
    mutationFn: () => {
      const body = { amount, currency, category, incurred_on: incurredOn, description };
      return line ? api("PATCH", `/engagements/${eng.id}/costs/${line.id}`, body) : api("POST", `/engagements/${eng.id}/costs`, body);
    },
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={line ? "Edit cost" : "Add cost"}>
      <form className="space-y-5 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <ErrorNote error={noFieldErrors(save.error)} />
        <div className="grid grid-cols-[1fr_auto] gap-4 max-sm:grid-cols-1">
          <Field label="Amount" error={fieldError(save.error, "amount")}>{(p) => <TextInput {...p} required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="1500.00" />}</Field>
          <Field label="Currency" error={fieldError(save.error, "currency")}>{(p) => <Select {...p} value={currency} onChange={(e) => setCurrency(e.target.value)}>{CURRENCIES.map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}</Select>}</Field>
        </div>
        <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
          <Field label="Category" error={fieldError(save.error, "category")}>{(p) => <Select {...p} value={category} onChange={(e) => setCategory(e.target.value)}>{COST_CATEGORIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</Select>}</Field>
          <Field label="Date" error={fieldError(save.error, "incurred_on")}>{(p) => <TextInput {...p} required type="date" value={incurredOn} onChange={(e) => setIncurredOn(e.target.value)} />}</Field>
        </div>
        <Field label="Description" hint="Optional" error={fieldError(save.error, "description")}>{(p) => <TextInput {...p} maxLength={300} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <div className="flex justify-end gap-3"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>{line ? "Save" : "Add cost"}</Button></div>
      </form>
    </Modal>
  );
}
