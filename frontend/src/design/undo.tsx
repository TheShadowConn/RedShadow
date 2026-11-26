import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Undo2, X } from "lucide-react";

type Pending = { id: number; message: string; undo: () => Promise<unknown> };
type Listener = (p: Pending | null) => void;

let next = 1;
const listeners = new Set<Listener>();

/**
 * Show "<message> Undo" for a few seconds. `undo` runs if the person presses Undo. Use after a delete so a slip of
 * the mouse is not permanent. The bar lives in the app shell, so it survives moving to another page.
 */
export function announceUndo(message: string, undo: () => Promise<unknown>) {
  const p = { id: next++, message, undo };
  listeners.forEach((l) => l(p));
}

const SHOW_MS = 12_000;

export function UndoBar() {
  const qc = useQueryClient();
  const [p, setP] = useState<Pending | null>(null);
  const [state, setState] = useState<"idle" | "working" | "done" | "failed">("idle");

  useEffect(() => {
    const l: Listener = (x) => { setP(x); setState("idle"); };
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);

  useEffect(() => {
    if (!p || state === "working") return;
    const t = setTimeout(() => setP(null), state === "idle" ? SHOW_MS : 4000);
    return () => clearTimeout(t);
  }, [p, state]);

  if (!p) return null;
  async function run() {
    setState("working");
    try {
      await p!.undo();
      setState("done");
      void qc.invalidateQueries();
    } catch {
      setState("failed");
    }
  }
  return (
    <div role="status" aria-live="polite" className="fixed bottom-20 left-1/2 z-40 flex w-[min(92vw,34rem)] -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-ink px-4 py-3 text-surface shadow-lg md:bottom-6">
      <span className="min-w-0 flex-1 text-[15px]">
        {state === "done" ? "Restored." : state === "failed" ? "Could not undo. Ask a Super Admin." : p.message}
      </span>
      {state === "idle" && (
        <button type="button" onClick={() => void run()} className="inline-flex min-h-11 items-center gap-1.5 rounded-md bg-surface px-3 text-[15px] font-medium text-ink"><Undo2 size={16} aria-hidden /> Undo</button>
      )}
      {state === "working" && <span className="text-[14px]">Restoring…</span>}
      <button type="button" aria-label="Dismiss" onClick={() => setP(null)} className="grid h-11 w-11 place-items-center rounded-md text-surface/80 hover:text-surface"><X size={18} aria-hidden /></button>
    </div>
  );
}
