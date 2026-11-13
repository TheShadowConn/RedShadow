"""Cut the Shadowconn marks out of the supplied logo images.

Outputs (transparent PNGs, trimmed):
  wolf-blue.png      blue wolf head, full colour (from shadowconn_original.jpg)
  wolf-gold.png      gold wolf head, full colour (from shadowconn_dark_mode.png)
  wolf-mask.png      wolf silhouette, alpha only (for CSS mask tinting)
  wordmark-mask.png  "Shadowconn" wordmark, alpha only
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

root = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def trim(rgba, pad=8):
    a = rgba[..., 3]
    ys, xs = np.where(a > 8)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    return rgba[max(0, y0 - pad):y1 + pad + 1, max(0, x0 - pad):x1 + pad + 1]


def save(arr, name):
    Image.fromarray(arr.astype(np.uint8), "RGBA").save(out / name)
    print(name, arr.shape[1], "x", arr.shape[0])


def row_split(alpha):
    """Return the row index in the widest empty band between head and wordmark."""
    rows = (alpha > 20).sum(1) > 0
    best, start, run, best_mid = 0, None, 0, None
    for i, filled in enumerate(rows):
        if not filled:
            start = i if start is None else start
            run = i - start + 1
            if run > best and rows[:start].any() and rows[i + 1:].any():
                best, best_mid = run, start + run // 2
        else:
            start = None
    return best_mid


# ---- Blue logo on white -------------------------------------------------
im = np.asarray(Image.open(root / "shadowconn_original.jpg").convert("RGB")).astype(float)
h, w, _ = im.shape
mn = im.min(2)
light = mn > 200
lab, _ = ndimage.label(light)
border = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
bg = np.isin(lab, list(border))
near = ndimage.binary_dilation(bg, iterations=3)
alpha = np.where(bg, 0.0, 1.0)
edge = near & ~bg
alpha[edge] = np.clip((255 - mn[edge]) / 255 * 1.4, 0, 1)
a3 = np.maximum(alpha, 1e-3)[..., None]
rgb = np.clip((im - (1 - alpha[..., None]) * 255) / a3, 0, 255)
rgba = np.dstack([rgb, alpha * 255])

# The source has a thin grey line on its top edge: clear the outer border.
rgba[:6, :, 3] = rgba[-6:, :, 3] = rgba[:, :6, 3] = rgba[:, -6:, 3] = 0
blue = (im[..., 2] - im[..., :2].max(2)) > 60
lab, n = ndimage.label(blue)
big = np.argmax(ndimage.sum(blue, lab, range(1, n + 1))) + 1
ys, xs = np.where(lab == big)
split = ys.max() + 6
head = rgba.copy(); head[split:, :, 3] = 0; head[:ys.min() - 6, :, 3] = 0
word = rgba.copy(); word[:split, :, 3] = 0
head, word = trim(head), trim(word)
save(head, "wolf-blue.png")

mask = np.zeros_like(head); mask[..., 3] = head[..., 3]
# Punch the white eyes out of the silhouette so a tinted mark keeps its face.
eyes = head[..., :3].min(2) > 170
mask[..., 3] = np.where(eyes, 0, mask[..., 3])
print("brand blue", "#%02x%02x%02x" % tuple(np.median(im[blue], 0).astype(int)))
save(mask, "wolf-mask.png")
wm = np.zeros_like(word); wm[..., 3] = word[..., 3]
save(wm, "wordmark-mask.png")

# ---- Gold logo on dark texture -------------------------------------------
g = np.asarray(Image.open(root / "shadowconn_dark_mode.png").convert("RGB")).astype(float)
r, gg, b = g[..., 0], g[..., 1], g[..., 2]
mx, mn2 = g.max(2), g.min(2)
sat = (mx - mn2) / np.maximum(mx, 1)
warm = (r > b + 25)
ga = np.clip((sat - 0.28) / 0.25, 0, 1) * np.clip((mx - 55) / 70, 0, 1) * warm
# keep only large connected gold regions (drop texture specks)
lab, n = ndimage.label(ga > 0.3)
sizes = ndimage.sum(np.ones_like(ga), lab, range(1, n + 1))
keep = np.isin(lab, np.where(sizes > 400)[0] + 1)
keep = ndimage.binary_dilation(keep, iterations=2)
ga = ga * keep
# fill dark facet seams inside the head so it reads solid
hull = ndimage.binary_fill_holes(ndimage.binary_closing(ga > 0.3, iterations=4))
grgba = np.dstack([g, np.maximum(ga, hull * 1.0) * 255])
split = row_split(grgba[..., 3])
ghead = grgba.copy(); ghead[split:, :, 3] = 0
save(trim(ghead), "wolf-gold.png")
