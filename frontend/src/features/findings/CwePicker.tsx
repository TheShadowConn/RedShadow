import { useEffect, useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";

import { api } from "../../api/client";
import type { Cwe } from "../../api/types";
import { TextInput } from "../../design/ui";

/** Searchable CWE list (id or words). Values come from the server's curated list only. */
export function CwePicker({ value, onChange }: { value: Cwe | null; onChange: (cwe: Cwe | null) => void }) {
  const listId = useId();
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(term), 200);
    return () => clearTimeout(t);
  }, [term]);
  const q = useQuery({
    queryKey: ["cwes", debounced],
    queryFn: () => api<Cwe[]>("GET", `/cwes?search=${encodeURIComponent(debounced)}`),
    enabled: open,
  });
  const options = q.data ?? [];

  function choose(c: Cwe) {
    onChange(c);
    setTerm("");
    setOpen(false);
  }

  if (value) {
    return (
      <div className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-line-strong bg-surface px-3">
        <span className="min-w-0 truncate"><span className="mono">CWE-{value.id}</span> {value.name}</span>
        <button type="button" className="btn btn-secondary btn-icon btn-sm" aria-label="Clear CWE" onClick={() => onChange(null)}>
          <X size={16} aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <TextInput
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder="Search by number or name, for example 89 or injection"
        value={term}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => { setTerm(e.target.value); setOpen(true); setActive(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" && open && options[active]) { e.preventDefault(); choose(options[active]); }
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-64 w-full list-none overflow-y-auto rounded-md border border-line-strong bg-surface p-1 shadow-lg">
          {q.isPending && <li className="px-3 py-2 text-muted">Searching…</li>}
          {q.data && options.length === 0 && <li className="px-3 py-2 text-muted">No match in the curated list.</li>}
          {options.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === active}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(c)} className={`block min-h-11 w-full rounded-sm px-3 py-2 text-left ${i === active ? "bg-raised" : ""}`}>
                <span className="mono">CWE-{c.id}</span> <span className="text-muted">{c.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
