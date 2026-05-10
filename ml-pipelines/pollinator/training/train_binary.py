"""
training/train_binary.py
=========================
Train binary classifier: insect vs background.

Two architectures available:
    efficientnet: EfficientNet-B2, ImageNet-pretrained, all layers trainable.
    insectnet:    RegNet-Y-32GF, pretrained on 2526 insect classes, frozen backbone.
EfficientNet-B2 currently performs best for insect-vs-background.

Background crops are sampled evenly across camera plots so no single plot
dominates the training data. See pollinator.training.sampling for details.

Usage (CLI):
    python -m pollinator.training.train_binary \
        --data_dirs path/to/labeled_a path/to/labeled_b \
        --model     efficientnet \
        --output    path/to/models \
        --epochs    20

Usage (as module):
    from pollinator.training.train_binary import train_binary
    train_binary(data_dirs=["path/to/labeled_a", "path/to/labeled_b"])
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as T
from torch.utils.data import DataLoader, WeightedRandomSampler

from .datasets import CropDataset, letterbox
from .models import build_efficientnet_b2, build_insectnet
from .sampling import sample_background_balanced

logger = logging.getLogger(__name__)

CLASSES = ['background', 'insect']
INSECT_FOLDERS = ['bumblebee', 'fly', 'butterfly', 'other']
DEFAULT_BG_RATIO = 3


def load_and_split(
    labeled_dir: Path,
    val_frac: float = 0.2,
    test_frac: float = 0.1,
    bg_ratio: int = DEFAULT_BG_RATIO,
    seed: int = 42,
) -> tuple:
    """
    Collect insect + background samples from a labeled directory.
    Background is sampled evenly across camera plots (per-plot quota).
    Returns stratified train/val/test split.
    """
    insect_paths = []
    for folder in INSECT_FOLDERS:
        d = labeled_dir / folder
        if not d.exists():
            continue
        for ext in ('*.jpg', '*.jpeg', '*.png'):
            insect_paths.extend(d.glob(ext))

    n_insect = len(insect_paths)
    n_bg_target = n_insect * bg_ratio

    bg_dir = labeled_dir / 'background'
    bg_paths = sample_background_balanced(bg_dir, n_bg_target, seed)

    all_samples = [(p, 0) for p in bg_paths] + [(p, 1) for p in insect_paths]

    if n_insect < 150:
        logger.warning(f'Only {n_insect} insect crops. Annotate more before training.')

    rng = np.random.default_rng(seed)
    by_class = {0: [], 1: []}
    for i, (_, lbl) in enumerate(all_samples):
        by_class[lbl].append(i)

    train_idx, val_idx, test_idx = [], [], []
    for lbl, idxs in by_class.items():
        idxs = list(idxs)
        rng.shuffle(idxs)
        n_test = max(1, int(len(idxs) * test_frac))
        n_val = max(1, int(len(idxs) * val_frac))
        test_idx.extend(idxs[:n_test])
        val_idx.extend(idxs[n_test : n_test + n_val])
        train_idx.extend(idxs[n_test + n_val :])

    counts = {0: len(by_class[0]), 1: len(by_class[1])}

    def split_counts(idx):
        bg = sum(1 for i in idx if all_samples[i][1] == 0)
        ins = sum(1 for i in idx if all_samples[i][1] == 1)
        return bg, ins

    tr_bg, tr_ins = split_counts(train_idx)
    va_bg, va_ins = split_counts(val_idx)
    te_bg, te_ins = split_counts(test_idx)

    logger.info(f'\nDataset split ({labeled_dir.name}):')
    logger.info(f'  strategy: stratified, test={test_frac:.0%}, val={val_frac:.0%}')
    logger.info(f'  {"split":8}  {"background":>12}  {"insect":>8}  {"total":>8}')
    logger.info(f'  {"train":8}  {tr_bg:>12}  {tr_ins:>8}  {len(train_idx):>8}')
    logger.info(f'  {"val":8}  {va_bg:>12}  {va_ins:>8}  {len(val_idx):>8}')
    logger.info(f'  {"test":8}  {te_bg:>12}  {te_ins:>8}  {len(test_idx):>8}')
    logger.info(f'  background:insect ratio = {counts[0] / max(1, counts[1]):.1f}:1')

    return all_samples, train_idx, val_idx, test_idx, counts


def make_loaders(
    all_samples, train_idx, val_idx, test_idx, counts, img_size, batch
) -> tuple:
    train_tf = T.Compose(
        [
            T.Lambda(lambda img: letterbox(img, img_size)),
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.RandomRotation(30),
            T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
            T.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    val_tf = T.Compose(
        [
            T.Lambda(lambda img: letterbox(img, img_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    train_samples = [all_samples[i] for i in train_idx]
    val_samples = [all_samples[i] for i in val_idx]
    test_samples = [all_samples[i] for i in test_idx]

    labels = [s[1] for s in train_samples]
    cls_w = 1.0 / np.maximum(np.bincount(labels, minlength=2), 1)
    sample_w = [cls_w[l] for l in labels]
    sampler = WeightedRandomSampler(sample_w, len(sample_w))

    w = torch.tensor([1.0 / max(1, counts[i]) for i in range(2)])
    criterion = nn.CrossEntropyLoss(weight=w / w.sum())

    train_loader = DataLoader(
        CropDataset(train_samples, train_tf),
        batch_size=batch,
        sampler=sampler,
        num_workers=0,
    )
    val_loader = DataLoader(
        CropDataset(val_samples, val_tf), batch_size=batch, shuffle=False, num_workers=0
    )
    test_loader = DataLoader(
        CropDataset(test_samples, val_tf),
        batch_size=batch,
        shuffle=False,
        num_workers=0,
    )
    return train_loader, val_loader, test_loader, criterion


@torch.no_grad()
def eval_epoch(model, loader, criterion, device) -> dict:
    model.eval()
    loss_sum = correct = total = 0
    tp = fp = fn = tn = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        out = model(imgs)
        preds = out.argmax(1)
        loss_sum += criterion(out, labels).item() * labels.size(0)
        correct += (preds == labels).sum().item()
        total += labels.size(0)
        tp += ((preds == 1) & (labels == 1)).sum().item()
        fp += ((preds == 1) & (labels == 0)).sum().item()
        fn += ((preds == 0) & (labels == 1)).sum().item()
        tn += ((preds == 0) & (labels == 0)).sum().item()
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-8, prec + rec)
    return {
        'loss': loss_sum / max(1, total),
        'acc': correct / max(1, total),
        'precision': prec,
        'recall': rec,
        'f1': f1,
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
    }


def train_binary(
    data_dirs: list,
    model_type: str = 'efficientnet',
    insectnet_weights: Optional[str] = None,
    output_dir: str = 'models',
    epochs: int = 20,
    batch: int = 32,
    lr: float = 1e-3,
    val_frac: float = 0.2,
    test_frac: float = 0.1,
    bg_ratio: int = DEFAULT_BG_RATIO,
    seed: int = 42,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
) -> dict:
    """
    Train binary insect/background classifier.

    Background crops are sampled evenly across camera plots to avoid any
    single plot dominating the training data.

    Args:
        data_dirs:         One or more labeled-data root folders. Each folder
                           contains insect class subdirs (bumblebee, fly,
                           butterfly, other) plus a background/ subdir.
        model_type:        "efficientnet" or "insectnet".
        insectnet_weights: Path to InsectNet model.pth (required for insectnet).
        output_dir:        Where to save checkpoints and results.
        epochs, batch, lr, val_frac, test_frac, bg_ratio, seed: training params.
        progress_callback: Optional callback invoked once per epoch.
                           Signature: (processed, total, message, level)
                           where level is one of 'info', 'warn', 'error'.
                           Exceptions raised by the callback are swallowed
                           so they cannot break the run.

    Returns:
        dict with val and test metrics of the best checkpoint.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if not data_dirs:
        raise ValueError('data_dirs must contain at least one path')
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f'Device: {device}')

    def _emit(
        processed: int, total: int, message: str = '', level: str = 'info'
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(processed, total, message, level)
        except Exception:
            logger.exception('progress_callback raised; ignoring')

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(seed)
    np.random.seed(seed)

    all_samples = []
    train_idx, val_idx, test_idx = [], [], []
    counts = {0: 0, 1: 0}
    offset = 0
    for d in data_dirs:
        s, t, v, te, c = load_and_split(Path(d), val_frac, test_frac, bg_ratio, seed)
        all_samples.extend(s)
        train_idx.extend(i + offset for i in t)
        val_idx.extend(i + offset for i in v)
        test_idx.extend(i + offset for i in te)
        counts[0] += c[0]
        counts[1] += c[1]
        offset += len(s)
    logger.info(
        f'\nCombined {len(data_dirs)} dataset(s). Background: {counts[0]}  Insect: {counts[1]}'
    )

    if model_type == 'insectnet':
        if not insectnet_weights:
            raise ValueError('insectnet_weights required for insectnet model')
        model, img_size = build_insectnet(insectnet_weights, num_classes=2)
    else:
        model, img_size = build_efficientnet_b2(num_classes=2, img_size=256)
    model = model.to(device)

    train_loader, val_loader, test_loader, criterion = make_loaders(
        all_samples, train_idx, val_idx, test_idx, counts, img_size, batch
    )
    criterion = criterion.to(device)

    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()), lr=lr
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    ckpt_path = out_dir / f'{model_type}_binary_best.pth'
    best_f1 = 0.0

    logger.info(f'\n{"=" * 60}')
    logger.info(f'{model_type}  |  img={img_size}px  |  epochs={epochs}  |  lr={lr}')
    logger.info(f'{"=" * 60}')
    logger.info(
        f'{"Ep":>3}  {"TrLoss":>7}  {"VaLoss":>7}  {"Prec":>6}  '
        f'{"Recall":>6}  {"F1":>6}  {"Acc":>6}'
    )

    t0 = time.time()
    for ep in range(1, epochs + 1):
        model.train()
        tr_loss = 0.0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(imgs), labels)
            loss.backward()
            optimizer.step()
            tr_loss += loss.item() * labels.size(0)
        tr_loss /= len(train_loader.dataset)
        scheduler.step()

        v = eval_epoch(model, val_loader, criterion, device)
        star = ''
        if v['f1'] > best_f1:
            best_f1 = v['f1']
            torch.save(
                {
                    'epoch': ep,
                    'model_name': model_type,
                    'img_size': img_size,
                    'state_dict': model.state_dict(),
                    'val_f1': v['f1'],
                    'val_recall': v['recall'],
                    'val_precision': v['precision'],
                },
                ckpt_path,
            )
            star = ' *'

        logger.info(
            f'{ep:>3}  {tr_loss:>7.4f}  {v["loss"]:>7.4f}  '
            f'{v["precision"]:>6.3f}  {v["recall"]:>6.3f}  '
            f'{v["f1"]:>6.3f}  {v["acc"]:>6.3f}{star}'
        )
        _emit(
            ep,
            epochs,
            f'Epoch {ep}/{epochs}: tr_loss={tr_loss:.4f} val_f1={v["f1"]:.3f} '
            f'val_recall={v["recall"]:.3f} val_precision={v["precision"]:.3f}',
        )

    logger.info(
        f'\nDone in {(time.time() - t0) / 60:.1f} min  |  Best val F1: {best_f1:.3f}'
    )

    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt['state_dict'])
    test = eval_epoch(model, test_loader, criterion, device)

    logger.info(f'\nTest set (best checkpoint epoch {ckpt["epoch"]}):')
    logger.info(
        f'  F1={test["f1"]:.3f}  Recall={test["recall"]:.3f}  '
        f'Precision={test["precision"]:.3f}  Acc={test["acc"]:.3f}'
    )
    logger.info(f'  TP={test["tp"]}  FP={test["fp"]}  FN={test["fn"]}  TN={test["tn"]}')

    results = {
        'model': model_type,
        'data_dirs': [str(d) for d in data_dirs],
        'img_size': img_size,
        'best_epoch': ckpt['epoch'],
        'best_val_f1': best_f1,
        'test_f1': test['f1'],
        'test_recall': test['recall'],
        'test_precision': test['precision'],
        'test_acc': test['acc'],
        'test_tp': test['tp'],
        'test_fp': test['fp'],
        'test_fn': test['fn'],
        'test_tn': test['tn'],
    }
    (out_dir / f'{model_type}_binary_results.json').write_text(
        json.dumps(results, indent=2)
    )
    logger.info(f'Checkpoint: {ckpt_path}')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--data_dirs',
        nargs='+',
        required=True,
        help='One or more labeled-data root folders',
    )
    parser.add_argument(
        '--model', default='efficientnet', choices=['efficientnet', 'insectnet']
    )
    parser.add_argument('--insectnet_weights', help='Path to InsectNet model.pth')
    parser.add_argument('--output', default='models')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument(
        '--bg_ratio',
        type=int,
        default=DEFAULT_BG_RATIO,
        help='Background:insect sampling ratio (default 3)',
    )
    parser.add_argument(
        '--no_progress',
        action='store_true',
        help='Disable per-epoch progress lines on stdout',
    )
    args = parser.parse_args()

    def _print_progress(processed: int, total: int, message: str, level: str) -> None:
        print(f'[{processed}/{total}] {message}', flush=True)

    train_binary(
        data_dirs=args.data_dirs,
        model_type=args.model,
        insectnet_weights=args.insectnet_weights,
        output_dir=args.output,
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        bg_ratio=args.bg_ratio,
        progress_callback=None if args.no_progress else _print_progress,
    )
