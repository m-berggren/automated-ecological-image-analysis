#!/usr/bin/env python3
"""Compose the qualitative failure-mode figure: one establishing field frame on
top, and a row of hand-picked false-negative flies below as large context crops
with the ground-truth box drawn and the insect's pixel size labelled.

Crops are fixed 640 x 640 px regions centred on each annotated box (clamped to
the frame), so the box size on screen reflects the insect's true scale: a small
box in a large crop is a genuinely small insect. Boxes are given as normalized
YOLO coordinates against the 3008 x 1692 frames.

Writes combined_failure_panel.png into paths.OUT_DIR. Needs PIL + matplotlib.
"""

import matplotlib.pyplot as plt
from PIL import Image, ImageDraw

from paths import GRID, IMAGES, OUT_DIR as OUT

CROP = 640  # fixed context-crop side in source pixels

MAIN = GRID / 'dia_WSCT0003.JPG'

# (source frame, cx, cy, w, h) normalized. Ordered small -> large by area.
CROPS = [
    ('various_WSCT1718', 0.732066, 0.416800, 0.007583, 0.019178),
    ('various_WSCT1722', 0.293007, 0.401043, 0.013567, 0.011874),
    ('dia_WSCT0075',     0.136208, 0.229199, 0.024159, 0.031566),
    ('dia_WSCT0057',     0.682259, 0.602893, 0.049890, 0.041483),
]


def find(stem):
    for d in (GRID, IMAGES):
        hits = list(d.glob(stem + '.*'))
        if hits:
            return hits[0]
    raise FileNotFoundError(stem)


def context_crop(stem, cx, cy, w, h):
    im = Image.open(find(stem)).convert('RGB')
    W, H = im.size
    bw, bh = w * W, h * H
    x1, y1, x2, y2 = (cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H
    fx, fy = (x1 + x2) / 2, (y1 + y2) / 2
    rx0 = int(max(0, min(W - CROP, fx - CROP / 2)))
    ry0 = int(max(0, min(H - CROP, fy - CROP / 2)))
    crop = im.crop((rx0, ry0, rx0 + CROP, ry0 + CROP))
    d = ImageDraw.Draw(crop)
    d.rectangle([x1 - rx0, y1 - ry0, x2 - rx0, y2 - ry0],
                outline=(230, 30, 30), width=5)
    return crop, int(round(bw)), int(round(bh))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = len(CROPS)
    # Square crops at full-width/n, main frame at its native 16:9 aspect, so the
    # height ratio (1/1.78 : 1/n) leaves no horizontal whitespace on either.
    fig = plt.figure(figsize=(7.4, 6.4))
    gs = fig.add_gridspec(2, n, height_ratios=[n / 1.78, 1], hspace=0.02, wspace=0.02)

    ax0 = fig.add_subplot(gs[0, :])
    ax0.imshow(Image.open(MAIN).convert('RGB'))
    ax0.axis('off')

    for i, (stem, cx, cy, w, h) in enumerate(CROPS):
        crop, bw, bh = context_crop(stem, cx, cy, w, h)
        ax = fig.add_subplot(gs[1, i])
        ax.imshow(crop)
        ax.text(0.04, 0.96, f'{bw} x {bh} px', transform=ax.transAxes,
                ha='left', va='top', fontsize=8, color='white',
                bbox=dict(boxstyle='round,pad=0.2', fc=(0, 0, 0, 0.55), ec='none'))
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    p = OUT / 'combined_failure_panel.png'
    fig.savefig(p, dpi=220, bbox_inches='tight', pad_inches=0.02)
    print(f'wrote {p}')


if __name__ == '__main__':
    main()
