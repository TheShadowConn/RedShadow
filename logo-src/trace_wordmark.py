"""Trace the "Shadowconn" wordmark into a vector path so it stays sharp at 4K.

Reads wordmark-mask.png (alpha), upsamples it, traces the 0.5 iso-contour and
writes wordmark.svg (fill-rule evenodd keeps the counters of a, d, o open).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

src = Path(sys.argv[1])
orig = Path(sys.argv[2])            # shadowconn_original.jpg
UP = 4
# Ink coverage from the source photo: dark pixels below the blue head. This keeps the
# white counters open (the old border flood-fill mask had them filled).
im = np.asarray(Image.open(orig).convert("RGB")).astype(float)
blue = (im[..., 2] - im[..., :2].max(2)) > 60
rows = np.where(blue.any(1))[0]
y0 = rows.max() + 10
lum = im[..., :3].mean(2)
ink = np.clip((190 - lum) / 120, 0, 1)
ink[:y0] = 0
ink[:6] = ink[-6:] = 0; ink[:, :6] = ink[:, -6:] = 0
ys, xs = np.where(ink > .5)
a = ink[ys.min() - 4:ys.max() + 5, xs.min() - 4:xs.max() + 5]
h, w = a.shape
a = ndimage.zoom(np.pad(a, 4), UP, order=3)
a = ndimage.gaussian_filter(a, UP * .45)
paths = []
for c in measure.find_contours(a, 0.5):
    if len(c) < 20:
        continue
    p = measure.approximate_polygon(c, tolerance=.5)
    paths.append("M" + " L".join(f"{x / UP - 4:.2f},{y / UP - 4:.2f}" for y, x in p[:-1]) + " Z")
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
       f'<path fill="#000" fill-rule="evenodd" d="{" ".join(paths)}"/></svg>\n')
(src / "wordmark.svg").write_text(svg)
print("paths", len(paths), "bytes", len(svg), "box", w, h)
