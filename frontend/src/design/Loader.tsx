/**
 * Loading animation: the eclipse "O" of the RedShadow logo. A crimson arc circles the O's ring while the
 * eclipse cut breathes. The O is drawn as a stroked rounded rectangle (centre line of the logo's ring), so the
 * arc can follow it. `mono` paints everything in currentColor for use on coloured buttons.
 * Under prefers-reduced-motion the arc and cut stay still (see components.css).
 */
const RING = { x: 10, y: 8.5, w: 64, h: 83, r: 17 };
const WEDGE = "M60 32V77C60 78.1 59.1 79 58 79H26C24.9 79 24 78.1 24 77V68Z";

export function EclipseO({ size = 48, mono = false, className = "" }: { size?: number; mono?: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 84 100"
      width={(size * 84) / 100}
      height={size}
      aria-hidden
      focusable="false"
      className={`eclipse-o${mono ? " eclipse-mono" : ""} ${className}`.trim()}
    >
      <rect className="eclipse-track" x={RING.x} y={RING.y} width={RING.w} height={RING.h} rx={RING.r} />
      <rect className="eclipse-arc" x={RING.x} y={RING.y} width={RING.w} height={RING.h} rx={RING.r} pathLength={100} />
      <path className="eclipse-wedge" d={WEDGE} />
    </svg>
  );
}

/** Centred loader with an accessible status message. */
export function Loader({ label = "Loading", size = 56, block = false }: { label?: string; size?: number; block?: boolean }) {
  return (
    <div role="status" className={`eclipse-loader${block ? " eclipse-block" : ""}`}>
      <EclipseO size={size} />
      <span className="eclipse-label">{label}</span>
    </div>
  );
}
