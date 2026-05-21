"""
Train YOLO pollinator detector (two-stage: frozen backbone -> full fine-tune).

Classes: bumblebee / fly / butterfly / other.
CVAT export expected in YOLO 1.1 format.

Small-object strategy:
    Train at 640px (fast, fits GPU). Inference uses SAHI tiling (see
    detection/yolo_detector.py) so a 30px insect in a 3008x1692 source
    image appears at natural size inside its 640x640 tile.

Imbalanced-data strategy:
    fly is dominant; others are rare. We use:
        - copy_paste augmentation: copies rare-class objects into other images
        - mixup augmentation: blends images to expose rare classes more
        - two-stage training: freeze backbone first, then unfreeze all

Expected dataset layout (already split):
    dataset_root/
        images/{train,val,test}/*.jpg
        labels/{train,val,test}/*.txt

Usage (CLI):
    python -m pollinator.training.train_yolo \
        --dataset_root path/to/dataset \
        --output_dir   runs/pollinator \
        --epochs_stage1 30 --epochs_stage2 70

Usage (as module):
    from pollinator.training.train_yolo import train_yolo
    train_yolo(dataset_root="dataset", output_dir="runs/pollinator")
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import yaml
from ultralytics import YOLO

logger = logging.getLogger(__name__)

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']


# ── Dataset config ────────────────────────────────────────────────────────
def write_data_yaml(dataset_root: Path, classes: list) -> Path:
    """Write the data.yaml that ultralytics reads. The test split is
    optional and only included when images/test/ exists on disk."""
    yaml_path = dataset_root / 'data.yaml'
    cfg = {
        'path': str(dataset_root.resolve()),
        'train': 'images/train',
        'val': 'images/val',
        'nc': len(classes),
        'names': classes,
    }
    if (dataset_root / 'images' / 'test').exists():
        cfg['test'] = 'images/test'
    yaml_path.write_text(yaml.dump(cfg, default_flow_style=False))
    logger.info(f'data.yaml written to {yaml_path}')
    return yaml_path


def count_bboxes(labels_dir: Path, classes: list) -> dict:
    counts = {i: 0 for i in range(len(classes))}
    for txt in labels_dir.glob('*.txt'):
        for line in txt.read_text().strip().splitlines():
            parts = line.strip().split()
            if parts:
                cls = int(parts[0])
                if cls < len(classes):
                    counts[cls] += 1
    return counts


def log_dataset_stats(dataset_root: Path, classes: list):
    for split in ('train', 'val', 'test'):
        ldir = dataset_root / 'labels' / split
        idir = dataset_root / 'images' / split
        if not ldir.exists():
            logger.warning(f'{ldir} not found')
            continue
        n_imgs = (
            len(list(idir.glob('*.JPG')))
            + len(list(idir.glob('*.jpg')))
            + len(list(idir.glob('*.png')))
        )
        counts = count_bboxes(ldir, classes)
        logger.info(f'{split}: {n_imgs} images')
        for i, cls in enumerate(classes):
            flag = '  ← low, consider Roboflow data' if counts[i] < 200 else ''
            logger.info(f'  {cls:15}: {counts[i]:>5} bbox{flag}')


# ── Eval helpers ───────────────────────────────────────────────────────────
def _per_class_rows(box, classes: list) -> dict:
    """Map each class name to its metrics, or None if it had no val instances.

    Ultralytics packs box.p / box.r / box.ap50 only with the classes that
    appeared in the validation set, in the order given by box.ap_class_index
    (which holds the real class ids). Indexing those arrays by the global
    class position is wrong: a fly-only set has box.ap50[0]=fly, so position 0
    would be mislabelled as classes[0] (bumblebee). Map through ap_class_index.
    """
    out: dict = {cls: None for cls in classes}
    try:
        ap_class_index = [int(c) for c in box.ap_class_index]
    except (AttributeError, TypeError):
        # Fallback: assume positional alignment (older ultralytics / no data).
        ap_class_index = list(range(len(classes)))
    for pos, class_id in enumerate(ap_class_index):
        if not 0 <= class_id < len(classes):
            continue
        try:
            p = float(box.p[pos])
            r = float(box.r[pos])
            f1 = 2 * p * r / max(1e-8, p + r)
            ap = float(box.ap50[pos])
        except (IndexError, AttributeError):
            continue
        out[classes[class_id]] = {'precision': p, 'recall': r, 'f1': f1, 'ap50': ap}
    return out


def per_class_metrics(box, classes: list) -> dict:
    return _per_class_rows(box, classes)


def log_split_metrics(metrics, split_name: str, classes: list) -> dict:
    logger.info(f'\n--- {split_name.upper()} per-class results ---')
    box = metrics.box
    rows = _per_class_rows(box, classes)
    for cls in classes:
        row = rows.get(cls)
        if row is None:
            logger.info(f'{cls:15}  (no detections)')
        else:
            logger.info(
                f'{cls:15}  P={row["precision"]:.3f}  R={row["recall"]:.3f}  '
                f'F1={row["f1"]:.3f}  AP50={row["ap50"]:.3f}'
            )
    logger.info(f'\n{split_name.upper()} mAP50:    {float(box.map50):.3f}')
    logger.info(f'{split_name.upper()} mAP50-95: {float(box.map):.3f}')
    return {
        'mAP50': float(box.map50),
        'mAP50_95': float(box.map),
        'per_class': rows,
    }


# ── Training ───────────────────────────────────────────────────────────────
def train_yolo(
    dataset_root: str,
    output_dir: str,
    model_size: str = 'yolo26n.pt',
    img_size: int = 640,
    batch: int = 16,
    seed: int = 42,
    epochs_stage1: int = 30,
    lr_stage1: float = 1e-3,
    freeze_layers: int = 10,
    patience_s1: int = 15,
    epochs_stage2: int = 70,
    lr_stage2: float = 1e-4,
    patience_s2: int = 20,
    copy_paste: float = 0.3,
    mixup: float = 0.1,
    mosaic: float = 1.0,
    classes: Optional[list] = None,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
) -> dict:
    """
    Two-stage YOLO training: frozen backbone -> full fine-tune.

    Args:
        dataset_root:   Folder with images/{train,val,test} and labels/{train,val,test}.
        output_dir:     Where ultralytics writes runs (e.g. runs/pollinator).
        model_size:     Pretrained weights to start from (e.g. yolo26n.pt).
        img_size:       Training image size in pixels.
        batch:          Batch size.
        seed:           Random seed.
        epochs_stage1:  Stage 1 (frozen backbone) epochs.
        lr_stage1:      Stage 1 learning rate.
        freeze_layers:  Number of backbone layers to freeze in stage 1.
        patience_s1:    Stage 1 early-stop patience.
        epochs_stage2:  Stage 2 (full fine-tune) epochs.
        lr_stage2:      Stage 2 learning rate.
        patience_s2:    Stage 2 early-stop patience.
        copy_paste:     copy_paste augmentation strength (rare-class boost).
        mixup:          mixup augmentation strength.
        mosaic:         mosaic augmentation strength.
        classes:        Class names list (default: bumblebee/fly/butterfly/other).
        progress_callback: Optional callback invoked once per epoch across both
                           stages. Signature: (processed, total, message, level)
                           where total is epochs_stage1 + epochs_stage2 and
                           processed is monotonic across stages. Exceptions
                           raised by the callback are swallowed.

    Returns:
        dict with stage1 / stage2 weights paths and val + test metrics.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    classes = classes or CLASSES

    total_epochs = epochs_stage1 + epochs_stage2

    def _emit(
        processed: int, total: int, message: str = '', level: str = 'info'
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(processed, total, message, level)
        except Exception:
            logger.exception('progress_callback raised; ignoring')

    def _make_epoch_hook(stage_name: str, stage_epochs: int, offset: int):
        def _hook(trainer):
            try:
                ep = int(getattr(trainer, 'epoch', 0)) + 1
            except Exception:
                ep = 0
            _emit(
                offset + ep,
                total_epochs,
                f'{stage_name} epoch {ep}/{stage_epochs}',
            )

        return _hook

    dataset_root = Path(dataset_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (dataset_root / 'images' / 'train').is_dir():
        raise RuntimeError(
            f'No pre-split dataset at {dataset_root}. Expected layout: '
            f'{dataset_root}/{{images,labels}}/{{train,val,test}}/.'
        )

    yaml_path = write_data_yaml(dataset_root, classes)
    log_dataset_stats(dataset_root, classes)

    # ── Stage 1: frozen backbone ──────────────────────────────────────────
    # epochs_stage1=0 skips stage 1 entirely (incremental retrain from input
    # weights). Stage 2 then starts directly from model_size.
    if epochs_stage1 > 0:
        logger.info(f'\n{"=" * 60}')
        logger.info(
            f'Stage 1 (frozen backbone) | epochs={epochs_stage1} lr={lr_stage1}'
        )
        logger.info(f'{"=" * 60}')

        model = YOLO(model_size)
        if progress_callback is not None:
            model.add_callback(
                'on_train_epoch_end', _make_epoch_hook('stage1', epochs_stage1, 0)
            )
        results_s1 = model.train(
            data=str(yaml_path),
            epochs=epochs_stage1,
            imgsz=img_size,
            batch=batch,
            lr0=lr_stage1,
            # Force AdamW so ultralytics respects lr0. With the default
            # optimizer='auto' it ignores lr0 and silently picks ~0.00125,
            # which is far too high for stage-2 fine-tuning and prevents
            # convergence below stage 1.
            optimizer='AdamW',
            freeze=freeze_layers,
            patience=patience_s1,
            copy_paste=copy_paste,
            mixup=mixup,
            mosaic=mosaic,
            cache='disk',
            seed=seed,
            project=str(output_dir),
            name='stage1_frozen',
            exist_ok=True,
            verbose=True,
        )
        stage1_best = output_dir / 'stage1_frozen' / 'weights' / 'best.pt'
        s1_map50 = float(results_s1.results_dict.get('metrics/mAP50(B)', 0.0))
        logger.info(f'Stage 1 done. Best weights: {stage1_best} | mAP50={s1_map50:.3f}')
    else:
        logger.info('Skipping stage 1 (epochs_stage1=0). Stage 2 resumes from input.')
        stage1_best = Path(model_size)
        s1_map50 = None

    # ── Stage 2: full fine-tune ───────────────────────────────────────────
    logger.info(f'\n{"=" * 60}')
    logger.info(f'Stage 2 (full fine-tune) | epochs={epochs_stage2} lr={lr_stage2}')
    logger.info(f'{"=" * 60}')

    model_s2 = YOLO(str(stage1_best))
    if progress_callback is not None:
        model_s2.add_callback(
            'on_train_epoch_end',
            _make_epoch_hook('stage2', epochs_stage2, epochs_stage1),
        )
    results_s2 = model_s2.train(
        data=str(yaml_path),
        epochs=epochs_stage2,
        imgsz=img_size,
        batch=batch,
        lr0=lr_stage2,
        # See stage 1 for why optimizer='AdamW' is explicit.
        optimizer='AdamW',
        freeze=0,
        patience=patience_s2,
        copy_paste=copy_paste,
        mixup=mixup,
        mosaic=mosaic,
        cache='disk',
        seed=seed,
        project=str(output_dir),
        name='stage2_finetune',
        exist_ok=True,
        verbose=True,
    )
    stage2_best = output_dir / 'stage2_finetune' / 'weights' / 'best.pt'
    s2_map50 = float(results_s2.results_dict.get('metrics/mAP50(B)', 0.0))
    logger.info(f'Stage 2 done. Best weights: {stage2_best} | mAP50={s2_map50:.3f}')

    # ── Evaluation on val (and test if present) ───────────────────────────
    model_eval = YOLO(str(stage2_best))
    val_metrics = log_split_metrics(
        model_eval.val(data=str(yaml_path), split='val', imgsz=img_size, batch=batch),
        'val',
        classes,
    )
    test_metrics: dict = {}
    if (Path(dataset_root) / 'images' / 'test').exists():
        test_metrics = log_split_metrics(
            model_eval.val(
                data=str(yaml_path), split='test', imgsz=img_size, batch=batch
            ),
            'test',
            classes,
        )
    else:
        logger.info('No test split found; skipping test evaluation')

    summary = {
        'model': str(stage2_best),
        'classes': classes,
        'stage1_best': str(stage1_best),
        'stage1_mAP50': s1_map50,
        'stage2_mAP50': s2_map50,
        'val': val_metrics,
        'test': test_metrics,
    }
    (output_dir / 'results.json').write_text(json.dumps(summary, indent=2))
    logger.info(f'\nSaved summary to {output_dir / "results.json"}')
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train YOLO pollinator detector')
    parser.add_argument(
        '--dataset_root',
        required=True,
        help='Folder with images/{train,val,test} and labels/{train,val,test}',
    )
    parser.add_argument(
        '--output_dir',
        required=True,
        help='Where ultralytics writes runs (e.g. runs/pollinator)',
    )
    parser.add_argument('--model_size', default='yolo26n.pt')
    parser.add_argument('--img_size', type=int, default=640)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--epochs_stage1', type=int, default=30)
    parser.add_argument('--lr_stage1', type=float, default=1e-3)
    parser.add_argument('--freeze_layers', type=int, default=10)
    parser.add_argument('--patience_s1', type=int, default=15)
    parser.add_argument('--epochs_stage2', type=int, default=70)
    parser.add_argument('--lr_stage2', type=float, default=1e-4)
    parser.add_argument('--patience_s2', type=int, default=20)
    parser.add_argument('--copy_paste', type=float, default=0.3)
    parser.add_argument('--mixup', type=float, default=0.1)
    parser.add_argument('--mosaic', type=float, default=1.0)
    parser.add_argument(
        '--no_progress',
        action='store_true',
        help='Disable per-epoch progress lines on stdout',
    )
    args = parser.parse_args()

    def _print_progress(processed: int, total: int, message: str, level: str) -> None:
        print(f'[{processed}/{total}] {message}', flush=True)

    train_yolo(
        dataset_root=args.dataset_root,
        output_dir=args.output_dir,
        model_size=args.model_size,
        img_size=args.img_size,
        batch=args.batch,
        seed=args.seed,
        epochs_stage1=args.epochs_stage1,
        lr_stage1=args.lr_stage1,
        freeze_layers=args.freeze_layers,
        patience_s1=args.patience_s1,
        epochs_stage2=args.epochs_stage2,
        lr_stage2=args.lr_stage2,
        patience_s2=args.patience_s2,
        copy_paste=args.copy_paste,
        mixup=args.mixup,
        mosaic=args.mosaic,
        progress_callback=None if args.no_progress else _print_progress,
    )
