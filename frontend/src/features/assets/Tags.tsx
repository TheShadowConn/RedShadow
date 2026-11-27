import { useId, useState, type KeyboardEvent } from "react";
import { Check, Plus, X } from "lucide-react";

import { Button, TextInput } from "../../design/ui";

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/** The tags of one asset, read only unless `onRemove` is given. */
export function TagList({ tags, onRemove, empty, busy }: { tags: string[]; onRemove?: (tag: string) => void; empty?: string; busy?: boolean }) {
  if (tags.length === 0) return empty ? <span className="text-[14px] text-muted">{empty}</span> : null;
  return (
    <span className="flex flex-wrap items-center gap-2">
      {tags.map((t) => (
        <span key={t} className="tag">
          {t}
          {onRemove && <button type="button" className="tag-x" aria-label={`Remove tag ${t}`} disabled={busy} onClick={() => onRemove(t)}><X size={14} aria-hidden /></button>}
        </span>
      ))}
    </span>
  );
}

/**
 * Choose tags for an asset: pick from the tags already in use, or type a new one.
 * `draft` is the text typed but not yet added; include it with `withDraft` when saving.
 */
export function TagPicker({ value, onChange, known, draft, onDraft }: {
  value: string[]; onChange: (tags: string[]) => void; known: string[]; draft: string; onDraft: (text: string) => void;
}) {
  const name = useId();
  const [choice, setChoice] = useState<boolean | null>(null);
  const existing = choice ?? known.length > 0;
  const has = (t: string) => value.some((v) => same(v, t));
  const toggle = (t: string) => onChange(has(t) ? value.filter((v) => !same(v, t)) : [...value, t]);
  const add = () => { onChange(withDraft(value, draft, known)); onDraft(""); };
  const onKey = (e: KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); add(); } };

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="m-0 border-0 p-0">
        <legend className="label mb-1">Add to an existing tag?</legend>
        <div className="flex flex-wrap gap-x-6">
          <label className="check"><input type="radio" name={name} checked={existing} disabled={known.length === 0} onChange={() => setChoice(true)} /> Yes, choose a tag</label>
          <label className="check"><input type="radio" name={name} checked={!existing} onChange={() => setChoice(false)} /> No, create a new tag</label>
        </div>
        {known.length === 0 && <p className="field-hint m-0 mt-1">No tags exist yet.</p>}
      </fieldset>

      {existing && known.length > 0 ? (
        <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto rounded-md border border-line p-3" role="group" aria-label="Existing tags">
          {known.map((t) => (
            <button key={t} type="button" className="tag tag-pick" aria-pressed={has(t)} onClick={() => toggle(t)}>
              {has(t) ? <Check size={14} aria-hidden /> : <Plus size={14} aria-hidden />}
              {t}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row">
          <TextInput aria-label="New tag name" placeholder="For example Network Engineering" maxLength={40} value={draft} onChange={(e) => onDraft(e.target.value)} onKeyDown={onKey} />
          <Button onClick={add} disabled={!draft.trim()}>Add tag</Button>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <span className="label">Selected tags</span>
        <TagList tags={value} onRemove={(t) => toggle(t)} empty="None" />
      </div>
    </div>
  );
}

/** `value` plus whatever is still typed in the new-tag box (commas and semicolons separate tags). */
export function withDraft(value: string[], draft: string, known: string[]): string[] {
  const out = [...value];
  for (const part of draft.split(/[,;]/).map((t) => t.trim()).filter(Boolean)) {
    if (!out.some((v) => same(v, part))) out.push(known.find((k) => same(k, part)) ?? part);
  }
  return out;
}
