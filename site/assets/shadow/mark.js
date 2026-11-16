/* Footer: the eclipse wordmark. The pointer is the light; the logo's O casts a long red shadow away from it.
   The shadow is the convex hull of the O's box and the same box pushed away from the light. */
const svg = document.getElementById('mark');
const cast = document.getElementById('mark-cast');
if (svg && cast) init();

function init() {
  const O = [[623.3, 0], [707.3, 0], [707.3, 100], [623.3, 100]]; // the O's box in logo units
  const cx = 665.3, cy = 50, LEN = 120;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function hull(pts) {
    pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    for (const p of pts) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of pts.reverse()) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  function draw(lx, ly) {
    let dx = cx - lx, dy = cy - ly; const d = Math.hypot(dx, dy) || 1;
    dx /= d; dy /= d;
    const len = LEN * Math.min(1.6, 260 / Math.max(80, d) + 0.4);
    const pts = O.concat(O.map(([x, y]) => [x + dx * len, y + dy * len]));
    cast.setAttribute('d', 'M' + hull(pts).map((p) => p.map((v) => v.toFixed(1)).join(' ')).join('L') + 'Z');
  }
  // resting light: up and to the left, like the logo's own wedge
  draw(cx - 160, cy - 140);
  if (reduce) return;

  let raf = 0, tx = cx - 160, ty = cy - 140, x = tx, y = ty;
  function tick() {
    x += (tx - x) * 0.18; y += (ty - y) * 0.18; draw(x, y);
    raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.5 ? requestAnimationFrame(tick) : 0;
  }
  const toLogo = (e) => {
    const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    const m = svg.getScreenCTM(); if (!m) return null;
    return p.matrixTransform(m.inverse());
  };
  const foot = svg.closest('footer') || svg;
  foot.addEventListener('pointermove', (e) => {
    const p = toLogo(e); if (!p) return;
    tx = p.x; ty = p.y; if (!raf) raf = requestAnimationFrame(tick);
  });
  foot.addEventListener('pointerleave', () => { tx = cx - 160; ty = cy - 140; if (!raf) raf = requestAnimationFrame(tick); });
}
