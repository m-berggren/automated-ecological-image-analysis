"""Overlap-based duplicate suppression on Detection rows.

When two detectors fire on the same insect their bboxes overlap — often one
strictly contains the other (a tight YOLO crop inside a broader preprocessing
window), but sometimes they only partly overlap. Both rows survive review and
both would otherwise land in the CSV.

apps/analysis/engulfment.apply_engulfment_exclusions treats two accepted
detections on the same image as the *same insect* when either box's center
lies inside the other, or their IoU meets the run's threshold
(``review_settings.dedup_iou_threshold``, default 0.5). The *larger* box of
each such pair is marked ``excluded_from_export=True``, keeping the tighter
crop.

Runs on the Export step, not at inference time — there is no point deciding
which duplicate to keep before the reviewer has filtered out rejected
detections in Review. Only accepted (confirmed or corrected) detections are
considered.

Idempotent full recompute: auto-exclusions (``export_exclusion_user_set=False``)
are cleared first, then re-derived, so raising the threshold re-includes boxes.
Reviewer-toggled rows (``export_exclusion_user_set=True``) are never touched.
"""

from __future__ import annotations

from django.db import transaction

from .models import Detection, DetectionStatus, InferenceRun

DEFAULT_DEDUP_IOU = 0.5


def _area(b: dict) -> float:
    return (b['x2'] - b['x1']) * (b['y2'] - b['y1'])


def _center_in(box: dict, other: dict) -> bool:
    """True if the center of ``other`` lies inside ``box``."""
    cx = (other['x1'] + other['x2']) / 2
    cy = (other['y1'] + other['y2']) / 2
    return box['x1'] <= cx <= box['x2'] and box['y1'] <= cy <= box['y2']


def _iou(a: dict, b: dict) -> float:
    ix1, iy1 = max(a['x1'], b['x1']), max(a['y1'], b['y1'])
    ix2, iy2 = min(a['x2'], b['x2']), min(a['y2'], b['y2'])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _same_insect(larger: dict, smaller: dict, iou_threshold: float) -> bool:
    return (
        _center_in(larger, smaller)
        or _center_in(smaller, larger)
        or _iou(larger, smaller) >= iou_threshold
    )


def apply_engulfment_exclusions(run_id: int) -> int:
    """Recompute overlap-based export exclusions for a run.

    Per source image, for each ordered pair (outer, inner): if outer is the
    larger box and the two are the same insect (center-in-box or IoU >=
    threshold), outer is flagged. Returns the number of rows currently
    excluded by the rule.
    """
    run = InferenceRun.objects.filter(pk=run_id).only('review_settings').first()
    rs = (run.review_settings if run else None) or {}
    t = rs.get('dedup_iou_threshold')
    iou_threshold = float(t) if isinstance(t, (int, float)) else DEFAULT_DEDUP_IOU

    with transaction.atomic():
        # Clear prior auto-exclusions (keep reviewer-set ones) so the recompute
        # is bidirectional: raising the threshold re-includes boxes.
        Detection.objects.filter(
            inference_run_id=run_id,
            excluded_from_export=True,
            export_exclusion_user_set=False,
        ).update(excluded_from_export=False)

        rows = list(
            Detection.objects.filter(
                inference_run_id=run_id,
                status=DetectionStatus.ACCEPTED,
            ).values('id', 'image_id', 'bbox', 'export_exclusion_user_set')
        )
        by_image: dict[int, list[dict]] = {}
        for row in rows:
            if row['bbox']:
                by_image.setdefault(row['image_id'], []).append(row)

        to_exclude: set[int] = set()
        for items in by_image.values():
            if len(items) < 2:
                continue
            for outer in items:
                if outer['export_exclusion_user_set']:
                    continue
                ob = outer['bbox']
                outer_area = _area(ob)
                for inner in items:
                    if inner['id'] == outer['id']:
                        continue
                    ib = inner['bbox']
                    if _area(ib) >= outer_area:
                        continue  # only drop the larger of a same-insect pair
                    if _same_insect(ob, ib, iou_threshold):
                        to_exclude.add(outer['id'])
                        break

        if to_exclude:
            Detection.objects.filter(pk__in=to_exclude).update(
                excluded_from_export=True,
            )
    return len(to_exclude)
