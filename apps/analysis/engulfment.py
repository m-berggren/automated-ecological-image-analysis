"""Engulfment-based duplicate suppression on Detection rows.

When two detectors fire on the same insect, one bbox often strictly
contains the other (e.g. a tight YOLO crop sitting inside a broader
preprocessing window). Both rows survive review, both end up in the CSV.

apps/analysis/engulfment.apply_engulfment_exclusions marks the *outer*
(engulfing) detection of each pair as ``excluded_from_export=True`` so
it drops out of the export counts while leaving the tighter crop in.

Runs on the Export step, not at inference time — there is no point
deciding which duplicate to keep before the reviewer has filtered out
rejected detections in Review. Only accepted (confirmed or corrected)
detections are considered, in both the outer and inner positions: a
rejected inner bbox must not cause us to drop a real outer bbox.

Sticky per row: once a reviewer has explicitly toggled
excluded_from_export from the Export page, ``export_exclusion_user_set``
flips to True on that row and engulfment will never re-flag it.
"""

from __future__ import annotations

from .models import Detection, DetectionStatus


def apply_engulfment_exclusions(run_id: int) -> int:
    """Mark engulfing bboxes as excluded_from_export for the given run.

    Per source image, for each ordered pair (outer, inner): if outer
    strictly contains inner and is strictly larger, outer is flagged.
    Returns the number of rows newly excluded.
    """
    rows = list(
        Detection.objects.filter(
            inference_run_id=run_id,
            status=DetectionStatus.ACCEPTED,
            excluded_from_export=False,
        ).values('id', 'image_id', 'bbox', 'export_exclusion_user_set')
    )
    by_image: dict[int, list[dict]] = {}
    for row in rows:
        if not row['bbox']:
            continue
        by_image.setdefault(row['image_id'], []).append(row)

    to_exclude: set[int] = set()
    for items in by_image.values():
        if len(items) < 2:
            continue
        for outer in items:
            if outer['export_exclusion_user_set']:
                continue
            ob = outer['bbox']
            outer_area = (ob['x2'] - ob['x1']) * (ob['y2'] - ob['y1'])
            for inner in items:
                if inner['id'] == outer['id']:
                    continue
                ib = inner['bbox']
                inner_area = (ib['x2'] - ib['x1']) * (ib['y2'] - ib['y1'])
                if inner_area >= outer_area:
                    continue
                if (
                    ob['x1'] <= ib['x1']
                    and ob['y1'] <= ib['y1']
                    and ob['x2'] >= ib['x2']
                    and ob['y2'] >= ib['y2']
                ):
                    to_exclude.add(outer['id'])
                    break

    if not to_exclude:
        return 0
    return Detection.objects.filter(pk__in=to_exclude).update(
        excluded_from_export=True,
    )
