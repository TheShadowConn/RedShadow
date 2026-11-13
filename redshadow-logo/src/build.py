"""RedShadow wordmark generator.

Custom squared-geometric capitals built from rounded rectangles and 15-degree
diagonals, merged with skia-pathops booleans. Every output is pure <path>
geometry (no <text>, strokes, masks or filters).

Run:  <venv>/bin/python src/build.py   (needs skia-pathops + fonttools)
"""
import math
import os

import pathops
from fontTools.pens.svgPathPen import SVGPathPen

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "concepts")
os.makedirs(OUT, exist_ok=True)

RED = "#ff2a1a"
INK = "#0a0a0b"
PAPER = "#f1efe8"

H = 100.0            # cap height (baseline y=100, top y=0, y grows down)
K = 0.5523           # cubic circle constant
TAN15 = math.tan(math.radians(15))


# ---------------------------------------------------------------- primitives
def P():
    return pathops.Path()


def rect(x, y, w, h):
    p = P()
    p.moveTo(x, y); p.lineTo(x + w, y); p.lineTo(x + w, y + h); p.lineTo(x, y + h); p.close()
    return p


def poly(pts):
    p = P()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    p.close()
    return p


def rrect(x, y, w, h, tl=0, tr=0, br=0, bl=0):
    """Rounded rectangle, clockwise in y-down space, per-corner radii."""
    p = P()
    p.moveTo(x + tl, y)
    p.lineTo(x + w - tr, y)
    if tr:
        p.cubicTo(x + w - tr + tr * K, y, x + w, y + tr - tr * K, x + w, y + tr)
    p.lineTo(x + w, y + h - br)
    if br:
        p.cubicTo(x + w, y + h - br + br * K, x + w - br + br * K, y + h, x + w - br, y + h)
    p.lineTo(x + bl, y + h)
    if bl:
        p.cubicTo(x + bl - bl * K, y + h, x, y + h - bl + bl * K, x, y + h - bl)
    p.lineTo(x, y + tl)
    if tl:
        p.cubicTo(x, y + tl - tl * K, x + tl - tl * K, y, x + tl, y)
    p.close()
    return p


def union(paths):
    paths = [p for p in paths if p is not None]
    if not paths:
        return P()
    acc = paths[0]
    for p in paths[1:]:
        acc = pathops.op(acc, p, pathops.PathOp.UNION)
    return acc


def diff(a, b):
    return pathops.op(a, b, pathops.PathOp.DIFFERENCE)


def inter(a, b):
    return pathops.op(a, b, pathops.PathOp.INTERSECTION)


def translate(path, dx, dy):
    q = P()
    pen = q.getPen()

    class T:
        def moveTo(self, p): pen.moveTo((p[0] + dx, p[1] + dy))
        def lineTo(self, p): pen.lineTo((p[0] + dx, p[1] + dy))
        def curveTo(self, *ps): pen.curveTo(*[(a + dx, b + dy) for a, b in ps])
        def qCurveTo(self, *ps): pen.qCurveTo(*[(a + dx, b + dy) for a, b in ps])
        def closePath(self): pen.closePath()
        def endPath(self): pen.endPath()
    path.draw(T())
    return q


def scale(path, s, ox=0, oy=0):
    q = P()
    pen = q.getPen()
    f = lambda p: (ox + p[0] * s, oy + p[1] * s)

    class T:
        def moveTo(self, p): pen.moveTo(f(p))
        def lineTo(self, p): pen.lineTo(f(p))
        def curveTo(self, *ps): pen.curveTo(*[f(p) for p in ps])
        def qCurveTo(self, *ps): pen.qCurveTo(*[f(p) for p in ps])
        def closePath(self): pen.closePath()
        def endPath(self): pen.endPath()
    path.draw(T())
    return q


def dilate(path, r, n=64):
    """Approximate Minkowski dilation by a disc (union of shifted copies)."""
    return union([path] + [translate(path, r * math.cos(2 * math.pi * i / n),
                                     r * math.sin(2 * math.pi * i / n)) for i in range(n)])


def d_of(path):
    pen = SVGPathPen(None, ntos=lambda v: ("%.2f" % v).rstrip("0").rstrip("."))
    path.draw(pen)
    return pen.getCommands()


def bounds(path):
    return path.bounds  # (xmin, ymin, xmax, ymax)


def ring(x, y, w, h, r, sv, sh, ri, corners=(1, 1, 1, 1)):
    tl, tr, br, bl = [r * c for c in corners]
    itl, itr, ibr, ibl = [ri * c for c in corners]
    outer = rrect(x, y, w, h, tl, tr, br, bl)
    inner = rrect(x + sv, y + sh, w - 2 * sv, h - 2 * sh, itl, itr, ibr, ibl)
    return diff(outer, inner)


def slant(xt, yt, xb, yb, hw):
    """Diagonal stroke: top edge [xt, xt+hw] at yt, bottom edge [xb, xb+hw] at yb."""
    return poly([(xt, yt), (xt + hw, yt), (xb + hw, yb), (xb, yb)])


# ---------------------------------------------------------------- alphabet
class Font:
    """Squared geometric caps. sv = vertical stem, sh = horizontal bar (optically thinner)."""

    def __init__(self, sv=20.0, sh=17.0, r=27.0, track=0.0):
        self.sv, self.sh, self.r, self.track = sv, sh, r, track
        self.ri = max(r - sv * 1.05, 3.5)
        self.hw = sv / math.cos(math.radians(15))      # horizontal width of a 15deg stroke
        self.mid = 47.0                                # optical middle (slightly high)
        s = sv / 20.0
        # side bearings by side shape: straight / round / diagonal / open
        self.sb = {"st": 9 * s + 1, "rd": 6 * s + 0.6, "dg": 1.5 * s, "op": 5 * s}

    def glyph(self, ch):
        sv, sh, r, ri, hw, m = self.sv, self.sh, self.r, self.ri, self.hw, self.mid
        sb = self.sb
        if ch == "O":
            w = 84
            g = ring(0, 0, w, H, r, sv, sh, ri)
            return g, w, sb["rd"], sb["rd"]
        if ch == "D":
            w = 80
            g = ring(0, 0, w, H, r, sv, sh, ri, corners=(0, 1, 1, 0))
            return g, w, sb["st"], sb["rd"]
        if ch == "E":
            w = 64
            g = union([rect(0, 0, sv, H), rect(0, 0, w, sh),
                       rect(0, m - sh / 2, w - 6, sh), rect(0, H - sh, w, sh)])
            return g, w, sb["st"], sb["op"]
        if ch == "H":
            w = 78
            g = union([rect(0, 0, sv, H), rect(w - sv, 0, sv, H), rect(0, m - sh / 2, w, sh)])
            return g, w, sb["st"], sb["st"]
        if ch == "R":
            w = 78
            bowl_h = 59.0
            rb = r * 0.92
            bowl = ring(0, 0, w - 2, bowl_h, rb, sv, sh, max(rb - sv * 1.05, 3.5), corners=(0, 1, 1, 0))
            # 15deg leg from the bowl down to the baseline, right edge lands on w
            yb, yt = H, bowl_h - sh
            xb = w - hw
            xt = xb - (yb - yt) * TAN15
            leg = slant(xt, yt, xb, yb, hw)
            g = union([rect(0, 0, sv, H), bowl, leg])
            return g, w, sb["st"], sb["dg"] + 1.5
        if ch == "S":
            w = 74
            hh = (H + sh) / 2
            rs = r * 0.95
            ris = min(max(rs - sv * 1.05, 3.5), (hh - 2 * sh) / 2)
            top = ring(0, 0, w, hh, rs, sv, sh, ris)
            # terminals stop where the corner curve ends, so the S never closes into an 8
            t = max(sh + 3, rs * 0.55)
            top = diff(top, rect(w - rs, t, rs + 1, hh))          # open lower right of top ring
            bot = ring(0, H - hh, w, hh, rs, sv, sh, ris)
            bot = diff(bot, rect(-1, H - hh - 1, rs + 1, hh - t + 1))   # open upper left of bottom ring
            g = union([top, bot])
            return g, w, sb["rd"], sb["rd"]
        if ch == "A":
            dx = H * TAN15
            apex = hw + 3
            w = 2 * dx + apex
            left = slant(dx, 0, 0, H, hw)
            right = slant(dx + apex - hw, 0, w - hw, H, hw)
            # cross bar sits low (optically centred in the triangle)
            yc = 64.0
            xl = dx - (yc) * TAN15
            bar = rect(xl + 1, yc - sh / 2, w - 2 * xl - 2, sh)
            g = union([left, right, inter(bar, poly([(dx, 0), (dx + apex, 0), (w, H), (0, H)])), rect(dx, 0, apex, sh * 0.6)])
            return g, w, sb["dg"], sb["dg"]
        if ch == "W":
            dx = H * TAN15
            foot = hw + 3
            # four strokes: down, up, down, up; middle peak at cap height
            x0 = 0
            s1 = slant(x0, 0, x0 + dx, H, hw)
            b1 = x0 + dx                       # left foot left edge
            s2 = slant(b1 + foot - hw + dx, 0, b1 + foot - hw, H, hw)
            p2 = b1 + foot - hw + dx           # middle peak left edge
            s3 = slant(p2, 0, p2 + dx, H, hw)
            b3 = p2 + dx
            s4 = slant(b3 + foot - hw + dx, 0, b3 + foot - hw, H, hw)
            w = b3 + foot - hw + dx + hw
            g = union([s1, s2, s3, s4])
            return g, w, sb["dg"], sb["dg"]
        raise KeyError(ch)

    def word(self, text, x=0.0, kern=None):
        """Return (list of (char, path)), advance end x."""
        kern = kern or {}
        out, prev_rsb, prev = [], None, None
        for ch in text:
            g, w, lsb, rsb = self.glyph(ch)
            if prev_rsb is not None:
                x += prev_rsb + lsb + self.track + kern.get(prev + ch, 0)
            out.append((ch, translate(g, x, 0), x, w))
            x += w
            prev_rsb, prev = rsb, ch
        return out, x


KERN = {"RE": -1, "DS": -1, "HA": 0, "AD": 0, "OW": -1}


# ---------------------------------------------------------------- svg output
def svg(layers, bbox, pad=None, bg=None):
    """layers: list of (path, fill). bbox from geometry; pad around."""
    x0, y0, x1, y1 = bbox
    if pad is None:
        pad = 0.12 * (y1 - y0)
    vb = (x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad)
    body = []
    if bg:
        body.append(f'<rect x="{vb[0]:.2f}" y="{vb[1]:.2f}" width="{vb[2]:.2f}" height="{vb[3]:.2f}" fill="{bg}"/>')
    for path, fill in layers:
        d = d_of(path)
        if d:
            body.append(f'<path fill="{fill}" d="{d}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%.2f %.2f %.2f %.2f">\n<title>RedShadow</title>\n' % vb
            + "\n".join(body) + "\n</svg>\n")


def total_bounds(paths):
    bs = [bounds(p) for p in paths if d_of(p)]
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def write(name, text):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(text)


def emit(name, parts, square=False, pad=None):
    """parts: dict role->path. roles: 'red', 'ink', 'knock' (unused). Writes colour, reversed, mono variants."""
    paths = [p for p in parts.values()]
    bb = total_bounds(paths)
    if square:
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        s = max(bb[2] - bb[0], bb[3] - bb[1]) / 2
        bb = (cx - s, cy - s, cx + s, cy + s)
    red, ink = parts.get("red", P()), parts.get("ink", P())
    write(f"{name}.svg", svg([(red, RED), (ink, INK)], bb, pad))
    write(f"{name}-reversed.svg", svg([(red, RED), (ink, PAPER)], bb, pad, bg=INK))
    write(f"{name}-mono.svg", svg([(union([red, ink]), INK)], bb, pad))


# ---------------------------------------------------------------- concepts
def concept_a_redacted():
    """A - Redacted: 'RED' knocked out of a hard redaction bar, SHADOW follows in ink."""
    f = Font()
    red_word, xe = f.word("RED", kern=KERN)
    padx, pady = 15.0, 15.0
    bar = rect(-padx, -pady, xe + 2 * padx, H + 2 * pady)
    letters = union([p for _, p, _, _ in red_word])
    bar = diff(bar, letters)
    sh_word, _ = f.word("SHADOW", x=xe + padx + 17.0, kern=KERN)
    ink = union([p for _, p, _, _ in sh_word])
    emit("a-redacted", {"red": bar, "ink": ink})
    # icon: bar with R knocked out
    g, w, *_ = f.glyph("R")
    side = H + 2 * pady
    ix = (side - w) / 2 + 2  # optical: R has open right leg, nudge right
    tile = diff(rect(0, 0, side, side), translate(g, ix, pady))
    emit("a-redacted-icon", {"red": tile}, square=True, pad=0)


def concept_b_scanline():
    """B - Scanline: one horizontal cut runs through every letter; RED in red."""
    f = Font()
    word, xe = f.word("REDSHADOW", kern=KERN)
    y, gap = 29.0, 5.0
    cut = rect(-50, y, xe + 100, gap)
    red = diff(union([p for c, p, _, _ in word[:3]]), cut)
    ink = diff(union([p for c, p, _, _ in word[3:]]), cut)
    emit("b-scanline", {"red": red, "ink": ink})
    g, w, *_ = f.glyph("R")
    icon = diff(g, rect(-10, y, w + 20, gap + 2))
    emit("b-scanline-icon", {"red": icon}, square=True)


def concept_c_weight():
    """C - Weight shift: RED is solid and heavy, SHADOW is its light trace."""
    heavy = Font(sv=23, sh=19.5, r=27)
    light = Font(sv=7.5, sh=6.8, r=27)
    rw, xe = heavy.word("RED", kern=KERN)
    sw, _ = light.word("SHADOW", x=xe + heavy.sb["rd"] + light.sb["rd"] + 4, kern=KERN)
    emit("c-weight", {"red": union([p for _, p, _, _ in rw]), "ink": union([p for _, p, _, _ in sw])})
    gr, wr, *_ = heavy.glyph("R")
    gs, ws, *_ = light.glyph("S")
    icon_ink = translate(gs, wr + 10, 0)
    emit("c-weight-icon", {"red": gr, "ink": icon_ink}, square=True)


def concept_d_cast():
    """D - Cast: only the S throws a hard, flat 45deg shadow in red."""
    f = Font()
    word, xe = f.word("REDSHADOW", kern={**KERN, "DS": 3, "SH": 4})
    s_path = [p for c, p, _, _ in word if c == "S"][0]
    off, gap = 9.0, 3.6
    ink = union([p for _, p, _, _ in word])
    shadow = diff(translate(s_path, off, off), dilate(s_path, gap))
    emit("d-cast", {"red": shadow, "ink": ink})
    g, w, *_ = f.glyph("S")
    icon_sh = diff(translate(g, off, off), dilate(g, gap))
    emit("d-cast-icon", {"red": icon_sh, "ink": g}, square=True)


def concept_e_eclipse():
    """E - Eclipse: the O's counter is half in shadow - a red 45deg terminator inside the ring."""
    f = Font()
    word, xe = f.word("REDSHADOW", kern=KERN)
    o = [(p, x, w) for c, p, x, w in word if c == "O"][0]
    _, ox, ow = o
    gap = 4.0
    cx0, cy0 = ox + f.sv + gap, f.sh + gap
    cw, chh = ow - 2 * (f.sv + gap), H - 2 * (f.sh + gap)
    counter = rrect(cx0, cy0, cw, chh, *([max(f.ri - gap, 2)] * 4))
    # 45deg terminator through the counter centre: lower-right half falls into shadow
    mx, my = cx0 + cw / 2, cy0 + chh / 2
    L = 200
    half = inter(counter, poly([(mx + L, my - L), (mx + L, my + L), (mx - L, my + L)]))
    ink = union([p for _, p, _, _ in word])
    emit("e-eclipse", {"red": half, "ink": ink})
    g, w, *_ = f.glyph("O")
    cc = rrect(f.sv + gap, f.sh + gap, w - 2 * (f.sv + gap), chh, *([max(f.ri - gap, 2)] * 4))
    mx, my = w / 2, H / 2
    hh = inter(cc, poly([(mx + 200, my - 200), (mx + 200, my + 200), (mx - 200, my + 200)]))
    emit("e-eclipse-icon", {"red": hh, "ink": g}, square=True)


# ---------------------------------------------------------------- recommended direction (A) deliverables
def final_redacted():
    """Light / dark / one-colour wordmark + icon for concept A. Dark version thins SHADOW ~3% (irradiation)."""
    fdir = os.path.join(os.path.dirname(OUT), "final")
    os.makedirs(fdir, exist_ok=True)
    padx = pady = 15.0

    def build(f_ink):
        f = Font()
        red_word, xe = f.word("RED", kern=KERN)
        bar = diff(rect(-padx, -pady, xe + 2 * padx, H + 2 * pady), union([p for _, p, _, _ in red_word]))
        sh_word, _ = f_ink.word("SHADOW", x=xe + padx + 17.0, kern=KERN)
        return bar, union([p for _, p, _, _ in sh_word])

    bar, ink = build(Font())
    bb = total_bounds([bar, ink])
    _, ink_thin = build(Font(sv=19.4, sh=16.5))

    def w(name, layers, bg=None):
        with open(os.path.join(fdir, name), "w") as fh:
            fh.write(svg(layers, bb, pad=15.0, bg=bg))

    w("redshadow-wordmark-light.svg", [(bar, RED), (ink, INK)])
    w("redshadow-wordmark-dark.svg", [(bar, RED), (ink_thin, PAPER)])
    w("redshadow-wordmark-black.svg", [(union([bar, ink]), INK)])
    w("redshadow-wordmark-white.svg", [(union([bar, ink_thin]), "#ffffff")])
    w("redshadow-wordmark-red.svg", [(union([bar, ink]), RED)])
    # previews with backgrounds (for viewing only)
    w("preview-light-on-paper.svg", [(bar, RED), (ink, INK)], bg=PAPER)
    w("preview-dark-on-ink.svg", [(bar, RED), (ink_thin, PAPER)], bg=INK)

    # icon: square redaction tile, R knocked out, optically nudged right (open leg side)
    f = Font()
    g, gw, *_ = f.glyph("R")
    side = H + 2 * pady
    tile = diff(rect(0, 0, side, side), translate(g, (side - gw) / 2 + 2, pady))
    with open(os.path.join(fdir, "redshadow-icon.svg"), "w") as fh:
        fh.write(svg([(tile, RED)], (0, 0, side, side), pad=0))
    # small-size cut: R scaled up inside the tile, thinner gutter, for 16-32 px
    gs = scale(g, 1.12)
    m = (side - 112) / 2
    tile_s = diff(rect(0, 0, side, side), translate(gs, (side - gw * 1.12) / 2 + 2, m))
    with open(os.path.join(fdir, "redshadow-icon-small.svg"), "w") as fh:
        fh.write(svg([(tile_s, RED)], (0, 0, side, side), pad=0))


if __name__ == "__main__":
    concept_a_redacted()
    concept_b_scanline()
    concept_c_weight()
    concept_d_cast()
    concept_e_eclipse()
    final_redacted()
    print("wrote", sorted(os.listdir(OUT)))
