import { useEffect, useState } from "react";
import { Bug, Server } from "lucide-react";

import { cx } from "../../design/ui";

export type ImportKind = "findings" | "assets";

const COPY: Record<ImportKind, { chip: string; toast: string }> = {
  assets: { chip: "Importing assets", toast: "Now importing assets" },
  findings: { chip: "Importing findings", toast: "Now importing findings" },
};
const ICON = { assets: Server, findings: Bug };

/** Small label that says which kind of import the user is in. Quiet by design: no colour alone, always an icon and text. */
export function ImportKindChip({ kind, className }: { kind: ImportKind; className?: string }) {
  const Icon = ICON[kind];
  return (
    <span className={cx("inline-flex min-h-8 items-center gap-2 rounded-full border border-line bg-raised px-3 text-[13px] font-medium text-ink", className)}>
      <Icon size={14} className="text-accent" aria-hidden />
      {COPY[kind].chip}
    </span>
  );
}

/** A short, polite pop-up when the import kind changes (or is entered). Fades out by itself and is announced to screen readers. */
export function ImportKindToast({ kind }: { kind: ImportKind }) {
  const [shown, setShown] = useState(true);
  useEffect(() => {
    setShown(true);
    const t = setTimeout(() => setShown(false), 2800);
    return () => clearTimeout(t);
  }, [kind]);
  const Icon = ICON[kind];
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-24 z-40 flex justify-center px-4 md:bottom-8">
      <div
        className={cx(
          "inline-flex items-center gap-2 rounded-full border border-line-strong bg-ink px-4 py-2.5 text-[14px] font-medium text-surface shadow-lg transition-all duration-300 motion-reduce:transition-none",
          shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        )}
      >
        <Icon size={16} aria-hidden />
        {shown ? COPY[kind].toast : ""}
      </div>
    </div>
  );
}
