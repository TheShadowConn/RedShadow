"""Trace the Shadowconn wolf into a clean, symmetric vector silhouette.

The raster mask breaks up when scaled to wallpaper size, and its light muzzle
highlights read as false holes. This keeps only the outer outline and the two
eyes, mirrors the left half onto the right, and simplifies every edge to
straight lines to match the low-poly mark.

Writes wolf-silhouette.svg (fill-rule evenodd, eyes cut out).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

src = Path(sys.argv[1])
out = Path(sys.argv[2])
TOL = float(sys.argv[3]) if len(sys.argv) > 3 else 2.2   # simplification tolerance, source px

rgba = np.asarray(Image.open(src / "wolf-blue.png").convert("RGBA")).astype(float)
h, w = rgba.shape[:2]
solid = rgba[..., 3] > 128
solid = ndimage.binary_fill_holes(solid)
lab, n = ndimage.label(solid)
solid = lab == (np.argmax(ndimage.sum(solid, lab, range(1, n + 1))) + 1)

# Find the mirror axis that best overlaps the shape with its reflection.
best = None
for axis2 in range(int(w * 0.8), int(w * 1.2)):      # axis position * 2 (half-pixel steps)
    shift = axis2 - (w - 1)
    flipped = np.roll(solid[:, ::-1], shift, axis=1)
    score = (solid ^ flipped).sum()
    if best is None or score < best[0]:
        best = (score, shift)
shift = best[1]
mirror = lambda m: np.roll(m[:, ::-1], shift, axis=1)
axis = (w - 1 + shift) / 2

# Symmetric outline: keep the left half, reflect it.
left = solid.copy(); left[:, int(round(axis)):] = False
sym = left | mirror(left)
sym = ndimage.binary_closing(sym, iterations=1)

# Eyes: the two largest white regions in the upper-middle band; mirror the left one.
white = rgba[..., :3].min(2) > 200
band = np.zeros_like(white); band[int(h * .30):int(h * .62)] = True
lab, n = ndimage.label(white & band & solid)
sizes = ndimage.sum(np.ones_like(white), lab, range(1, n + 1))
cands = [i + 1 for i in np.argsort(sizes)[::-1][:2]]
eye_l = None
for c in cands:
    ys, xs = np.where(lab == c)
    if xs.mean() < axis:
        eye_l = lab == c
eye_l = ndimage.binary_closing(eye_l, iterations=1)
eyes = eye_l | mirror(eye_l)

shape = sym & ~eyes


def polys(mask):
    big = np.pad(mask.astype(float), 2)
    big = ndimage.gaussian_filter(big, 0.7)
    out = []
    for c in measure.find_contours(big, 0.5):
        if len(c) < 12:
            continue
        p = measure.approximate_polygon(c, tolerance=TOL)
        out.append([(x - 2, y - 2) for y, x in p])
    return out


paths = polys(shape)
d = " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p[:-1]) + " Z" for p in paths)
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
       f'<path fill="#000" fill-rule="evenodd" d="{d}"/></svg>\n')
(out / "wolf-silhouette.svg").write_text(svg)
print("axis", axis, "paths", len(paths), "vertices", sum(len(p) for p in paths))

# Preview raster for review.
if len(sys.argv) > 4:
    from PIL import ImageDraw
    k = 2
    im = Image.new("L", (w * k, h * k), 30)
    dr = ImageDraw.Draw(im)
    for i, p in enumerate(sorted(paths, key=lambda p: -len(p))):
        dr.polygon([(x * k, y * k) for x, y in p], fill=200 if i == 0 else 30)
    im.convert("RGB").save(sys.argv[4], quality=60)
