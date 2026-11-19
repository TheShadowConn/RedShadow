import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Settings } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { AppNotification, Page } from "../api/types";
import { formatDate } from "../design/ui";

type Prefs = { muted: string[]; email_enabled: boolean; email_available: boolean; groups: Array<{ key: string; label: string; email: boolean }> };

function Preferences() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications", "settings"], queryFn: () => api<Prefs>("GET", "/notifications/settings") });
  const save = useMutation({
    mutationFn: (p: { muted: string[]; email_enabled: boolean }) => api<Prefs>("PUT", "/notifications/settings", p),
    onSuccess: (d) => qc.setQueryData(["notifications", "settings"], d),
  });
  if (q.isPending) return <p className="m-0 p-4 text-muted">Loading…</p>;
  if (q.isError) return <p className="m-0 p-4 text-fail">Could not load settings.</p>;
  const p = q.data;
  const toggle = (key: string) => save.mutate({ muted: p.muted.includes(key) ? p.muted.filter((k) => k !== key) : [...p.muted, key], email_enabled: p.email_enabled });
  return (
    <div className="flex flex-col gap-3 p-4">
      <p className="m-0 text-[14px] text-muted">Choose what appears in your bell.</p>
      {p.groups.map((g) => (
        <label key={g.key} className="check"><input type="checkbox" checked={!p.muted.includes(g.key)} onChange={() => toggle(g.key)} /> {g.label}</label>
      ))}
      <label className="check"><input type="checkbox" checked={p.email_enabled} disabled={!p.email_available} onChange={() => save.mutate({ muted: p.muted, email_enabled: !p.email_enabled })} /> Also email me assignments, due dates and retests</label>
      {!p.email_available && <p className="m-0 text-[13px] text-muted">Email is off. An administrator sets it up in the server settings.</p>}
      {save.isError && <p className="m-0 text-[14px] text-fail">Could not save.</p>}
    </div>
  );
}

/** Header bell: unread count polled once a minute (only while the tab is visible), list loaded when opened. */
export function NotificationBell() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const count = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => api<{ count: number }>("GET", "/notifications/unread-count"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => api<Page<AppNotification>>("GET", "/notifications?page_size=20"),
    enabled: open,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["notifications"] });
  const readOne = useMutation({ mutationFn: (id: string) => api("POST", `/notifications/${id}/read`, {}), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("POST", "/notifications/read-all", {}), onSuccess: refresh });

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const unread = count.data?.count ?? 0;
  const go = (n: AppNotification) => {
    if (!n.read) readOne.mutate(n.id);
    setOpen(false);
    if (n.link.startsWith("/")) nav(n.link);
  };

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        className="btn btn-secondary btn-icon relative"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((o) => !o)}
      >
        <Bell size={20} aria-hidden />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#e5383b] px-1 text-[11px] font-semibold leading-none text-white" aria-hidden>
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications" className="card absolute right-0 top-full z-30 mt-2 flex max-h-[70vh] w-[min(92vw,380px)] flex-col overflow-hidden shadow-lg">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <h2 className="m-0 text-[16px]">{prefs ? "Notification settings" : "Notifications"}</h2>
            <span className="flex items-center gap-1">
            <button type="button" className="btn btn-secondary btn-icon" aria-label={prefs ? "Back to notifications" : "Notification settings"} aria-pressed={prefs} onClick={() => setPrefs((v) => !v)}><Settings size={16} aria-hidden /></button>
            {!prefs && <button type="button" className="inline-flex min-h-9 items-center gap-1.5 text-[14px] text-accent hover:underline disabled:text-muted disabled:no-underline" disabled={unread === 0 || readAll.isPending} onClick={() => readAll.mutate()}>
              <CheckCheck size={16} aria-hidden /> Mark all read
            </button>}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {prefs ? <Preferences /> : <>
            {list.isPending && <p className="m-0 p-4 text-muted">Loading…</p>}
            {list.isError && <p className="m-0 p-4 text-fail">Could not load notifications.</p>}
            {list.data && list.data.results.length === 0 && <p className="m-0 p-6 text-center text-muted">Nothing yet. Assignments and changes to your work appear here.</p>}
            {list.data && list.data.results.length > 0 && (
              <ul className="m-0 list-none divide-y divide-line p-0">
                {list.data.results.map((n) => (
                  <li key={n.id}>
                    <button type="button" onClick={() => go(n)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-raised">
                      <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${n.read ? "bg-transparent" : "bg-accent"}`} aria-hidden />
                      <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                        <span className={`block text-[15px] ${n.read ? "" : "font-medium"}`}>{n.title}</span>
                        {n.body && <span className="block text-[14px] text-muted">{n.body}</span>}
                        <span className="mt-0.5 block text-[13px] text-muted">{n.actor ? `${n.actor} · ` : ""}{formatDate(n.created_at)}{n.read ? "" : " · unread"}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            </>}
          </div>
        </div>
      )}
    </div>
  );
}
