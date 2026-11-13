import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bug, Building2, Crosshair, CornerDownLeft, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "../api/auth";
import { api } from "../api/client";
import type { EngagementRow, FindingRow, Page } from "../api/types";
import { Modal } from "../design/ui";

type Nav = { to: string; label: string; icon: LucideIcon };
type Hit = { key: string; to: string; title: string; hint: string; icon: LucideIcon; group: string };

export function SearchButton({ onOpen }: { onOpen: () => void }) {
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  return (
    <button type="button" onClick={onOpen} className="flex min-h-11 items-center gap-3 rounded-lg border border-line bg-surface px-3.5 text-[15px] text-muted hover:border-line-strong max-md:size-11 max-md:justify-center max-md:p-0 md:w-72" aria-keyshortcuts="Control+K Meta+K /">
      <Search size={18} aria-hidden />
      <span className="sr-only md:not-sr-only md:flex-1 md:text-left">Search</span>
      <kbd className="mono hidden rounded border border-line px-1.5 text-[12px] md:inline" aria-hidden>{mac ? "⌘K" : "Ctrl K"}</kbd>
    </button>
  );
}

/** Jump to a page, finding, engagement or organisation. Keyboard: arrows, Enter, Esc. */
export function CommandPalette({ open, onClose, items }: { open: boolean; onClose: () => void; items: Nav[] }) {
  const { can } = useAuth();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { const t = setTimeout(() => setTerm(text.trim()), 200); return () => clearTimeout(t); }, [text]);
  useEffect(() => { if (open) { setText(""); setTerm(""); setAt(0); setTimeout(() => input.current?.focus(), 30); } }, [open]);

  const enabled = open && term.length >= 2;
  const q = (key: string, path: string, perm: string) => ({ queryKey: ["palette", key, term], queryFn: () => api<Page<never>>("GET", `${path}${encodeURIComponent(term)}`), enabled: enabled && can(perm) });
  const findings = useQuery(q("f", "/findings?page_size=5&search=", "findings.view"));
  const engagements = useQuery(q("e", "/engagements?page_size=5&search=", "engagements.view"));
  const orgs = useQuery(q("o", "/organisations?page_size=5&search=", "organisations.view"));

  const lower = term.toLowerCase();
  const pages: Hit[] = items.filter((i) => !lower || i.label.toLowerCase().includes(lower)).slice(0, 6).map((i) => ({ key: `p${i.to}`, to: i.to, title: i.label, hint: "Page", icon: i.icon, group: "Pages" }));
  const hits: Hit[] = [
    ...pages,
    ...((findings.data?.results ?? []) as unknown as FindingRow[]).map((f) => ({ key: `f${f.id}`, to: `/findings/${f.id}`, title: `${f.ref} ${f.title}`, hint: f.engagement.ref, icon: Bug, group: "Findings" })),
    ...((engagements.data?.results ?? []) as unknown as EngagementRow[]).map((e) => ({ key: `e${e.id}`, to: `/engagements/${e.id}`, title: e.name, hint: e.ref, icon: Crosshair, group: "Engagements" })),
    ...((orgs.data?.results ?? []) as unknown as Array<{ id: string; name: string }>).map((o) => ({ key: `o${o.id}`, to: `/organisations/${o.id}`, title: o.name, hint: "Organisation", icon: Building2, group: "Organisations" })),
  ];
  const go = (h: Hit) => { onClose(); nav(h.to); };
  const busy = enabled && (findings.isFetching || engagements.isFetching || orgs.isFetching);

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(a + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && hits[at]) { e.preventDefault(); go(hits[at]); }
  }

  return (
    <Modal open={open} onClose={onClose} title="Search">
      <div className="p-4" onKeyDown={onKey}>
        <label htmlFor="palette-input" className="sr-only">Search findings, engagements, organisations and pages</label>
        <input id="palette-input" ref={input} role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={hits[at] ? `pal-${hits[at].key}` : undefined} autoComplete="off" className="input" placeholder="Search findings, engagements, organisations, pages" value={text} onChange={(e) => { setText(e.target.value); setAt(0); }} />
        <ul id="palette-list" role="listbox" aria-label="Results" className="m-0 mt-3 max-h-[50vh] list-none overflow-y-auto p-0">
          {hits.map((h, i) => {
            const Icon = h.icon;
            const first = i === 0 || hits[i - 1].group !== h.group;
            return (
              <li key={h.key} role="presentation">
                {first && <p className="m-0 px-3 pt-3 pb-1 text-[12px] font-semibold tracking-wide text-muted uppercase">{h.group}</p>}
                <div id={`pal-${h.key}`} role="option" aria-selected={i === at} tabIndex={-1} onMouseEnter={() => setAt(i)} onClick={() => go(h)} className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 py-2 ${i === at ? "bg-raised" : ""}`}>
                  <Icon size={18} aria-hidden className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate">{h.title}</span>
                  <span className="shrink-0 text-[13px] text-muted">{h.hint}</span>
                  {i === at && <CornerDownLeft size={14} aria-hidden className="shrink-0 text-muted" />}
                </div>
              </li>
            );
          })}
        </ul>
        {term.length >= 2 && !busy && hits.length === 0 && <p className="m-0 mt-4 text-muted" role="status">Nothing matches "{term}".</p>}
        {term.length < 2 && <p className="m-0 mt-3 text-[14px] text-muted">Type two letters to search. Arrows to move, Enter to open, Esc to close.</p>}
      </div>
    </Modal>
  );
}
