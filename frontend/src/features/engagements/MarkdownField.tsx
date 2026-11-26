import { useRef, useState } from "react";
import { Bold, Code, Italic, Link2, List, ListOrdered } from "lucide-react";
import { cx } from "../../design/ui";
import { Markdown } from "../findings/shared";

type Edit = { text: string; start: number; end: number };

/** Wrap the selection (or a placeholder) in `before`/`after`; the placeholder ends up selected so typing replaces it. */
function wrap(value: string, s: number, e: number, before: string, after: string, placeholder: string): Edit {
  const chosen = value.slice(s, e) || placeholder;
  const text = value.slice(0, s) + before + chosen + after + value.slice(e);
  return { text, start: s + before.length, end: s + before.length + chosen.length };
}

/** Prefix every selected line, or strip the prefix when all of them already have it. */
function prefixLines(value: string, s: number, e: number, prefix: (n: number) => string, test: RegExp): Edit {
  const from = value.lastIndexOf("\n", s - 1) + 1;
  const nl = value.indexOf("\n", e);
  const to = nl === -1 ? value.length : nl;
  const lines = value.slice(from, to).split("\n");
  const all = lines.every((l) => test.test(l));
  const out = lines.map((l, i) => (all ? l.replace(test, "") : prefix(i + 1) + l)).join("\n");
  return { text: value.slice(0, from) + out + value.slice(to), start: from, end: from + out.length };
}

const MAX = 50000; // matches the API limit

/**
 * Markdown editor with a small toolbar and a live preview. The stored value is plain markdown text; it is only ever
 * rendered through `Markdown`, which drops raw HTML and images and allows http(s) and mailto links only.
 * Pass the props `Field` hands to its render function so the label and error stay wired up.
 */
export function MarkdownField({ value, onChange, id, ...aria }: { value: string; onChange: (v: string) => void; id?: string; "aria-invalid"?: true; "aria-describedby"?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [mode, setMode] = useState<"write" | "preview">("write");

  function apply(fn: (v: string, s: number, e: number) => Edit) {
    const el = ref.current;
    if (!el) return;
    const r = fn(value, el.selectionStart, el.selectionEnd);
    if (r.text.length > MAX) return;
    onChange(r.text);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(r.start, r.end); });
  }

  const tools: Array<[string, typeof Bold, () => void]> = [
    ["Bold", Bold, () => apply((v, s, e) => wrap(v, s, e, "**", "**", "bold text"))],
    ["Italic", Italic, () => apply((v, s, e) => wrap(v, s, e, "_", "_", "italic text"))],
    ["Bulleted list", List, () => apply((v, s, e) => prefixLines(v, s, e, () => "- ", /^\s*[-*]\s+/))],
    ["Numbered list", ListOrdered, () => apply((v, s, e) => prefixLines(v, s, e, (n) => `${n}. `, /^\s*\d+\.\s+/))],
    ["Link", Link2, () => apply((v, s, e) => {
      const label = v.slice(s, e) || "link text";
      const text = v.slice(0, s) + `[${label}](https://)` + v.slice(e);
      const url = s + label.length + 3; // just after "]("
      return { text, start: url, end: url + "https://".length };
    })],
    ["Code", Code, () => apply((v, s, e) => wrap(v, s, e, "`", "`", "code"))],
  ];

  return (
    <div className="overflow-hidden rounded-md border border-line focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-raised px-2 py-1.5">
        <div className="flex flex-wrap gap-1" role="toolbar" aria-label="Formatting">
          {tools.map(([name, Icon, run]) => (
            <button key={name} type="button" title={name} aria-label={name} disabled={mode === "preview"} onClick={run} className="btn btn-secondary btn-icon btn-sm disabled:opacity-40"><Icon size={16} aria-hidden /></button>
          ))}
        </div>
        <div className="flex gap-1" role="group" aria-label="Editor mode">
          {(["write", "preview"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)} className={cx("btn btn-sm", mode === m ? "btn-primary" : "btn-secondary")}>{m === "write" ? "Write" : "Preview"}</button>
          ))}
        </div>
      </div>
      {mode === "write" ? (
        <textarea
          {...aria}
          id={id}
          ref={ref}
          rows={6}
          maxLength={MAX}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="block min-h-32 w-full resize-y border-0 bg-surface px-3 py-3 leading-relaxed text-ink outline-none"
        />
      ) : (
        <div className="min-h-32 bg-surface px-3 py-3"><Markdown text={value} empty="Nothing to preview." /></div>
      )}
      <p className="m-0 border-t border-line bg-raised px-3 py-1.5 text-[13px] text-muted">Markdown: <code>- item</code> for bullets, <code>1. item</code> for numbers, <code>[text](https://…)</code> for links. HTML and images are not shown.</p>
    </div>
  );
}
