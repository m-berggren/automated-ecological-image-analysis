#!/usr/bin/env python3
"""Generate two custom YOLO figures for the thesis.

1. Complementarity breakdown: how the 430 annotated flies on the vetted field
   set are recovered, split into both-branches / YOLO-only / crop-only /
   missed-by-both. Numbers from combined_pipeline_eval.py at the operating
   point (yolo 0.20, binary 0.20):
       YOLO TP=192, crop TP=131, combined TP=226, total flies=430
       both = 192 + 131 - 226 = 97
       YOLO-only = 192 - 97 = 95
       crop-only = 131 - 97 = 34
       missed by both = 430 - 226 = 204

2. Per-class recall on the held-out test split across the three iterations.
   Numbers from each run's results.json (test split, recall):
       fly       : 0.504 / 0.634 / 0.701   (iter 1 / 2 / 3)
       butterfly : 0.318 / 0.600 / 0.583
       other     : 0.208 /  n/a  / 0.257   (iter 2 did not train 'other')

No GPU or model needed. Only matplotlib. Writes PNGs into paths.OUT_DIR.
"""

import json

import matplotlib.pyplot as plt

from paths import OPERATING_CURVE_JSON, OUT_DIR as OUT

OUT.mkdir(parents=True, exist_ok=True)

# Muted, print-friendly palette.
C_BOTH = '#2c7a3f'  # green
C_YOLO = '#2b6cb0'  # blue
C_CROP = '#dd8a1f'  # orange
C_MISS = '#b0b0b0'  # grey


def complementarity():
    total = 430
    segs = [
        ('Both branches', 97, C_BOTH),
        ('YOLO only', 95, C_YOLO),
        ('Crop only', 34, C_CROP),
        ('Missed by both', 204, C_MISS),
    ]
    # Dark labels on the lighter fills (orange, grey); white on the dark fills (green, blue).
    dark_label = {C_CROP, C_MISS}
    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    left = 0
    for label, n, color in segs:
        ax.barh(0, n, left=left, color=color, edgecolor='white', height=0.6)
        ax.text(
            left + n / 2,
            0,
            f'{label}\n{n}',
            ha='center',
            va='center',
            color='black' if color in dark_label else 'white',
            fontsize=9,
        )
        left += n
    ax.set_xlim(0, total)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xlabel('Annotated flies (430 total)')
    ax.set_title('Fly recovery on the vetted field set, by detecting branch')
    for spine in ('top', 'right', 'left'):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    p = OUT / 'yolo_complementarity.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


def operating_curve():
    """Recall vs review burden (false positives) as the YOLO confidence
    threshold sweeps from 0.50 down to 0.05, binary gate held at 0.20.
    Data from sweep_operating_curve.py -> operating_curve.json."""
    data = json.loads(OPERATING_CURVE_JSON.read_text())
    rows = data['rows']
    comb_fp = [r['combined']['fp'] for r in rows]
    comb_r = [r['combined']['recall'] for r in rows]
    yolo_fp = [r['yolo_only']['fp'] for r in rows]
    yolo_r = [r['yolo_only']['recall'] for r in rows]
    crop_fp = [r['crop_only']['fp'] for r in data['crop_rows']]
    crop_r = [r['crop_only']['recall'] for r in data['crop_rows']]
    thr = [r['yolo_conf'] for r in rows]
    deployed = thr.index(0.20)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(
        crop_fp,
        crop_r,
        '-^',
        color=C_CROP,
        mfc='white',
        ms=5,
        lw=1.3,
        label='Crop branch only',
    )
    ax.plot(
        yolo_fp,
        yolo_r,
        '-s',
        color=C_MISS,
        mfc='white',
        ms=5,
        lw=1.3,
        label='YOLO branch only',
    )
    ax.plot(
        comb_fp, comb_r, '-o', color=C_YOLO, ms=5, lw=1.5, label='Combined pipeline'
    )

    # Label only the combined curve per point; it is the curve the operating
    # point is chosen on. The other two are reference baselines.
    for x, y, t in zip(comb_fp, comb_r, thr):
        ax.annotate(
            f'{t:.2f}',
            (x, y),
            textcoords='offset points',
            xytext=(0, 7),
            ha='center',
            fontsize=7,
            color='#11406b',
        )

    # Mark the deployed operating point.
    ax.plot(
        comb_fp[deployed],
        comb_r[deployed],
        'o',
        ms=13,
        mfc='none',
        mec='#222222',
        mew=2,
    )
    ax.annotate(
        'deployed\n(conf 0.20)',
        (comb_fp[deployed], comb_r[deployed]),
        textcoords='offset points',
        xytext=(34, -22),
        ha='left',
        fontsize=8,
        color='#222222',
        arrowprops=dict(arrowstyle='->', color='#222222', lw=1),
    )

    ax.set_xlabel('False positives to review (lower is less manual work)')
    ax.set_ylabel('Fly recall on the vetted field set')
    ax.set_title('Recall against review burden as the YOLO threshold varies')
    ax.legend(frameon=False, loc='lower right')
    ax.grid(alpha=0.25)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    p = OUT / 'yolo_operating_curve.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


def iteration_progression():
    classes = ['fly', 'butterfly', 'other']
    # recall per class, per iteration; None where not trained.
    data = {
        'Iteration 1': [0.504, 0.318, 0.208],
        'Iteration 2': [0.634, 0.600, None],
        'Iteration 3': [0.701, 0.583, 0.257],
    }
    colors = {
        'Iteration 1': '#9ecae1',
        'Iteration 2': '#4292c6',
        'Iteration 3': '#08519c',
    }

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    n_iter = len(data)
    bar_w = 0.25
    x = range(len(classes))
    for i, (it, vals) in enumerate(data.items()):
        offsets = [xi + (i - (n_iter - 1) / 2) * bar_w for xi in x]
        heights = [v if v is not None else 0 for v in vals]
        bars = ax.bar(
            offsets, heights, bar_w, label=it, color=colors[it], edgecolor='white'
        )
        for off, v in zip(offsets, vals):
            if v is None:
                ax.text(
                    off,
                    0.02,
                    'n/a',
                    ha='center',
                    va='bottom',
                    fontsize=8,
                    rotation=90,
                    color='grey',
                )
            else:
                ax.text(
                    off, v + 0.012, f'{v:.2f}', ha='center', va='bottom', fontsize=8
                )
    ax.set_xticks(list(x))
    ax.set_xticklabels(classes)
    ax.set_ylabel('Recall (held-out test split)')
    ax.set_ylim(0, 0.85)
    ax.set_title('Per-class recall across training iterations')
    ax.legend(frameon=False, loc='upper right')
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    ax.grid(axis='y', alpha=0.25)
    fig.tight_layout()
    p = OUT / 'yolo_iteration_recall.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


def class_imbalance():
    # Annotated bounding-box counts in subset 1 (per-plot table totals).
    counts = [
        ('fly', 3636, C_YOLO),
        ('other', 526, C_CROP),
        ('butterfly', 165, C_BOTH),
        ('bumblebee', 14, C_MISS),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    labels = [c[0] for c in counts]
    vals = [c[1] for c in counts]
    colors = [c[2] for c in counts]
    bars = ax.bar(labels, vals, color=colors, edgecolor='white')
    for b, v in zip(bars, vals):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + 40,
            f'{v:,}',
            ha='center',
            va='bottom',
            fontsize=10,
        )
    ax.set_ylabel('Annotated bounding boxes')
    ax.set_title('Annotated pollinator instances per class (subset 1)')
    ax.set_ylim(0, 3950)
    ax.text(
        3,
        220,
        'excluded from\nYOLO (too few)',
        ha='center',
        va='bottom',
        fontsize=8,
        color='grey',
    )
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    p = OUT / 'yolo_class_imbalance.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


def pipeline_diagram():
    """Two-branch inference pipeline: a field frame fans out to the YOLO branch
    and the crop branch, which are merged by bounding-box overlap and sent to the
    web app for review and export."""
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(7.0, 6.4))
    ax.set_xlim(-3, 3)
    ax.set_ylim(-2.4, 7)
    ax.axis('off')

    def box(x, y, text, color, tcolor='white', w=2.5, h=0.9):
        ax.add_patch(
            FancyBboxPatch(
                (x - w / 2, y - h / 2),
                w,
                h,
                boxstyle='round,pad=0.02,rounding_size=0.10',
                facecolor=color,
                edgecolor='none',
            )
        )
        ax.text(
            x, y, text, ha='center', va='center', color=tcolor, fontsize=9, zorder=5
        )
        return (x, y)

    def arrow(p1, p2):
        ax.annotate(
            '',
            xy=p2,
            xytext=p1,
            arrowprops=dict(
                arrowstyle='-|>', color='#444', lw=1.4, shrinkA=14, shrinkB=14
            ),
        )

    frame = box(0, 6.0, 'Field frame', C_MISS, tcolor='black')
    tiling = box(-1.45, 4.4, 'SAHI tiling\n(640 px, 20% overlap)', C_YOLO)
    detector = box(-1.45, 2.8, 'YOLO26n\ndetector', C_YOLO)
    bgsub = box(1.45, 4.4, 'Median-background\nsubtraction', C_CROP)
    binary = box(1.45, 2.8, 'Binary insect /\nbackground gate', C_CROP)
    classifier = box(1.45, 1.2, 'InsectNet\ngroup classifier', C_CROP)
    merge = box(0, -0.3, 'IoU merge', C_BOTH)
    output = box(0, -1.9, 'Review and export (web app)', '#444')

    arrow(frame, tiling)
    arrow(frame, bgsub)
    arrow(tiling, detector)
    arrow(bgsub, binary)
    arrow(binary, classifier)
    arrow(detector, merge)
    arrow(classifier, merge)
    arrow(merge, output)

    ax.text(
        -1.45,
        5.55,
        'YOLO branch',
        ha='center',
        fontsize=8.5,
        color=C_YOLO,
        style='italic',
    )
    ax.text(
        1.45,
        5.55,
        'Crop branch',
        ha='center',
        fontsize=8.5,
        color='#9a5a00',
        style='italic',
    )

    fig.tight_layout()
    p = OUT / 'yolo_pipeline.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


def _tile_origins(extent, tile, overlap):
    stride = max(1, int(tile * (1 - overlap)))
    starts = list(range(0, extent - tile, stride))
    if not starts or starts[-1] != extent - tile:
        starts.append(extent - tile)
    return starts


def slicing_schematic():
    # Idealised uniform grid (not the full 6x4 real count, and not the uneven
    # edge overlaps): a schematic that shows the principle cleanly.
    from matplotlib.patches import Rectangle

    tile, stride = 640, 512  # stride = 640 * 0.8 -> 20% overlap
    ncols, nrows = 4, 2
    W = (ncols - 1) * stride + tile  # frame chosen to fit the grid exactly
    H = (nrows - 1) * stride + tile
    xs = [i * stride for i in range(ncols)]
    ys = [j * stride for j in range(nrows)]

    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, edgecolor='black', lw=1.5))
    for x0 in xs:
        for y0 in ys:
            ax.add_patch(
                Rectangle(
                    (x0, y0),
                    tile,
                    tile,
                    facecolor=C_YOLO,
                    alpha=0.13,
                    edgecolor=C_YOLO,
                    lw=0.5,
                )
            )

    # Label one tile and one overlap band.
    ax.annotate(
        'one 640\\,px tile'.replace('\\,', ' '),
        xy=(tile / 2, tile * 0.12),
        ha='center',
        fontsize=8,
        color='#11406b',
    )
    band_cx = xs[1] + (tile - stride) / 2  # centre of the first vertical overlap band
    ax.annotate(
        '20% overlap',
        xy=(band_cx, H * 0.9),
        xytext=(band_cx, H + 150),
        ha='center',
        fontsize=8,
        arrowprops=dict(arrowstyle='->', lw=0.8),
    )

    # Insect (30 x 70 px, to scale with the 640 tile) on an interior vertical seam.
    iw, ih = 30, 70
    ix, iy = stride - iw / 2, 250
    ax.add_patch(
        Rectangle((ix, iy), iw, ih, facecolor='#cc3333', edgecolor='black', lw=0.6)
    )
    ax.annotate(
        'insect on a tile seam\n(appears in both tiles, merged by SAHI)',
        xy=(ix + iw / 2, iy + ih / 2),
        xytext=(W * 0.42, H * 0.55),
        fontsize=9,
        ha='left',
        va='center',
        arrowprops=dict(arrowstyle='->', lw=1),
    )

    ax.text(
        W / 2,
        -110,
        'source frame (schematic; 640\\,px tiles at 20% overlap)'.replace('\\,', ' '),
        ha='center',
        fontsize=9,
    )
    ax.set_xlim(-60, W + 60)
    ax.set_ylim(H + 170, -170)  # invert y so origin is top-left, image-style
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Tile slicing (schematic)')
    fig.tight_layout()
    p = OUT / 'yolo_slicing_schematic.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


if __name__ == '__main__':
    complementarity()
    operating_curve()
    pipeline_diagram()
    iteration_progression()
    class_imbalance()
    slicing_schematic()
