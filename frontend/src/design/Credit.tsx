/** "Built by" Shadowconn credit (wolf + wordmark). Colour follows the surrounding text colour. */
export function Credit({ size = "sm", className = "" }: { size?: "sm" | "lg"; className?: string }) {
  const wolf = size === "lg" ? "h-10" : "h-4";
  const word = size === "lg" ? "h-5" : "h-2.5";
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span className={`sc-wolf ${wolf}`} aria-hidden />
      <span className={`sc-word ${word}`} role="img" aria-label="Shadowconn" />
    </span>
  );
}
