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
        --data_ls   path/to/labeled_ls \
        --data_mb   path/to/labeled_mb \
        --mode      combined \
        --model     efficientnet \
        --output    path/to/models \
        --epochs    20

Usage (as module):
    from pollinator.training.train_binary import train_binary
    train_binary(data_ls="...", data_mb="...", mode="combined")
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as T
from torch.utils.data import DataLoader, WeightedRandomSampler

from .datasets import letterbox, CropDataset
from .models   import build_efficientnet_b2, build_insectnet
from .sampling import sample_background_balanced

logger = logging.getLogger(__name__)

CLASSES          = ["background", "insect"]
INSECT_FOLDERS   = ["bumblebee", "fly", "butterfly", "other"]
DEFAULT_BG_RATIO = 3


def load_and_split(
    labeled_dir: Path,
    val_frac:    float = 0.2,
    test_frac:   float = 0.1,
    bg_ratio:    int   = DEFAULT_BG_RATIO,
    seed:        int   = 42,
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
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            insect_paths.extend(d.glob(ext))

    n_insect    = len(insect_paths)
    n_bg_target = n_insect * bg_ratio

    bg_dir   = labeled_dir / "background"
    bg_paths = sample_background_balanced(bg_dir, n_bg_target, seed)

    all_samples = [(p, 0) for p in bg_paths] + [(p, 1) for p in insect_paths]

    if n_insect < 150:
        logger.warning(f"Only {n_insect} insect crops. Annotate more before training.")

    rng      = np.random.default_rng(seed)
    by_class = {0: [], 1: []}
    for i, (_, lbl) in enumerate(all_samples):
        by_class[lbl].append(i)

    train_idx, val_idx, test_idx = [], [], []
    for lbl, idxs in by_class.items():
        idxs = list(idxs)
        rng.shuffle(idxs)
        n_test = max(1, int(len(idxs) * test_frac))
        n_val  = max(1, int(len(idxs) * val_frac))
        test_idx.extend(idxs[:n_test])
        val_idx.extend(idxs[n_test:n_test + n_val])
        train_idx.extend(idxs[n_test + n_val:])

    counts = {0: len(by_class[0]), 1: len(by_class[1])}

    def split_counts(idx):
        bg  = sum(1 for i in idx if all_samples[i][1] == 0)
        ins = sum(1 for i in idx if all_samples[i][1] == 1)
        return bg, ins

    tr_bg, tr_ins = split_counts(train_idx)
    va_bg, va_ins = split_counts(val_idx)
    te_bg, te_ins = split_counts(test_idx)

    logger.info(f"\nDataset split ({labeled_dir.name}):")
    logger.info(f"  strategy: stratified, test={test_frac:.0%}, val={val_frac:.0%}")
    logger.info(f"  {'split':8}  {'background':>12}  {'insect':>8}  {'total':>8}")
    logger.info(f"  {'train':8}  {tr_bg:>12}  {tr_ins:>8}  {len(train_idx):>8}")
    logger.info(f"  {'val':8}  {va_bg:>12}  {va_ins:>8}  {len(val_idx):>8}")
    logger.info(f"  {'test':8}  {te_bg:>12}  {te_ins:>8}  {len(test_idx):>8}")
    logger.info(f"  background:insect ratio = {counts[0]/max(1,counts[1]):.1f}:1")

    return all_samples, train_idx, val_idx, test_idx, counts


def make_loaders(all_samples, train_idx, val_idx, test_idx,
                 counts, img_size, batch) -> tuple:
    train_tf = T.Compose([
        T.Lambda(lambda img: letterbox(img, img_size)),
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.RandomRotation(30),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
        T.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = T.Compose([
        T.Lambda(lambda img: letterbox(img, img_size)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    train_samples = [all_samples[i] for i in train_idx]
    val_samples   = [all_samples[i] for i in val_idx]
    test_samples  = [all_samples[i] for i in test_idx]

    labels   = [s[1] for s in train_samples]
    cls_w    = 1.0 / np.maximum(np.bincount(labels, minlength=2), 1)
    sample_w = [cls_w[l] for l in labels]
    sampler  = WeightedRandomSampler(sample_w, len(sample_w))

    w         = torch.tensor([1.0 / max(1, counts[i]) for i in range(2)])
    criterion = nn.CrossEntropyLoss(weight=w / w.sum())

    train_loader = DataLoader(CropDataset(train_samples, train_tf),
                              batch_size=batch, sampler=sampler, num_workers=0)
    val_loader   = DataLoader(CropDataset(val_samples, val_tf),
                              batch_size=batch, shuffle=False, num_workers=0)
    test_loader  = DataLoader(CropDataset(test_samples, val_tf),
                              batch_size=batch, shuffle=False, num_workers=0)
    return train_loader, val_loader, test_loader, criterion


@torch.no_grad()
def eval_epoch(model, loader, criterion, device) -> dict:
    model.eval()
    loss_sum = correct = total = 0
    tp = fp = fn = tn = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        out   = model(imgs)
        preds = out.argmax(1)
        loss_sum += criterion(out, labels).item() * labels.size(0)
        correct  += (preds == labels).sum().item()
        total    += labels.size(0)
        tp += ((preds == 1) & (labels == 1)).sum().item()
        fp += ((preds == 1) & (labels == 0)).sum().item()
        fn += ((preds == 0) & (labels == 1)).sum().item()
        tn += ((preds == 0) & (labels == 0)).sum().item()
    prec = tp / max(1, tp + fp)
    rec  = tp / max(1, tp + fn)
    f1   = 2 * prec * rec / max(1e-8, prec + rec)
    return {
        "loss": loss_sum / max(1, total), "acc": correct / max(1, total),
        "precision": prec, "recall": rec, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def train_binary(
    data_ls:           Optional[str] = None,
    data_mb:           Optional[str] = None,
    mode:              str   = "combined",
    model_type:        str   = "efficientnet",
    insectnet_weights: Optional[str] = None,
    output_dir:        str   = "models",
    epochs:            int   = 20,
    batch:             int   = 32,
    lr:                float = 1e-3,
    val_frac:          float = 0.2,
    test_frac:         float = 0.1,
    bg_ratio:          int   = DEFAULT_BG_RATIO,
    seed:              int   = 42,
) -> dict:
    """
    Train binary insect/background classifier.

    Background crops are sampled evenly across camera plots to avoid any
    single plot dominating the training data.

    Args:
        data_ls:   Path to labeled_ls folder.
        data_mb:   Path to labeled_mb folder.
        mode:      "ls", "mb", or "combined".
        model_type: "efficientnet" or "insectnet".
        insectnet_weights: Path to InsectNet model.pth (required for insectnet).
        output_dir: Where to save checkpoints and results.
        epochs, batch, lr, val_frac, test_frac, bg_ratio, seed: training params.

    Returns:
        dict with val and test metrics of the best checkpoint.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(seed)
    np.random.seed(seed)

    if mode == "combined":
        if not data_ls or not data_mb:
            raise ValueError("combined mode requires both --data_ls and --data_mb")
        s1, t1, v1, te1, c1 = load_and_split(Path(data_ls), val_frac, test_frac, bg_ratio, seed)
        s2, t2, v2, te2, c2 = load_and_split(Path(data_mb), val_frac, test_frac, bg_ratio, seed)
        offset      = len(s1)
        all_samples = s1 + s2
        train_idx   = t1 + [i + offset for i in t2]
        val_idx     = v1 + [i + offset for i in v2]
        test_idx    = te1 + [i + offset for i in te2]
        counts      = {0: c1[0] + c2[0], 1: c1[1] + c2[1]}
        logger.info(f"\nCombined. Background: {counts[0]}  Insect: {counts[1]}")
    elif mode == "ls":
        if not data_ls:
            raise ValueError("ls mode requires --data_ls")
        all_samples, train_idx, val_idx, test_idx, counts = load_and_split(
            Path(data_ls), val_frac, test_frac, bg_ratio, seed
        )
    else:
        if not data_mb:
            raise ValueError("mb mode requires --data_mb")
        all_samples, train_idx, val_idx, test_idx, counts = load_and_split(
            Path(data_mb), val_frac, test_frac, bg_ratio, seed
        )

    if model_type == "insectnet":
        if not insectnet_weights:
            raise ValueError("insectnet_weights required for insectnet model")
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

    ckpt_path = out_dir / f"{model_type}_binary_best.pth"
    best_f1   = 0.0

    logger.info(f"\n{'='*60}")
    logger.info(f"{model_type}  |  img={img_size}px  |  epochs={epochs}  |  lr={lr}")
    logger.info(f"{'='*60}")
    logger.info(f"{'Ep':>3}  {'TrLoss':>7}  {'VaLoss':>7}  {'Prec':>6}  "
                f"{'Recall':>6}  {'F1':>6}  {'Acc':>6}")

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

        v    = eval_epoch(model, val_loader, criterion, device)
        star = ""
        if v["f1"] > best_f1:
            best_f1 = v["f1"]
            torch.save({
                "epoch":         ep,
                "model_name":    model_type,
                "img_size":      img_size,
                "state_dict":    model.state_dict(),
                "val_f1":        v["f1"],
                "val_recall":    v["recall"],
                "val_precision": v["precision"],
            }, ckpt_path)
            star = " *"

        logger.info(f"{ep:>3}  {tr_loss:>7.4f}  {v['loss']:>7.4f}  "
                    f"{v['precision']:>6.3f}  {v['recall']:>6.3f}  "
                    f"{v['f1']:>6.3f}  {v['acc']:>6.3f}{star}")

    logger.info(f"\nDone in {(time.time()-t0)/60:.1f} min  |  Best val F1: {best_f1:.3f}")

    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["state_dict"])
    test = eval_epoch(model, test_loader, criterion, device)

    logger.info(f"\nTest set (best checkpoint epoch {ckpt['epoch']}):")
    logger.info(f"  F1={test['f1']:.3f}  Recall={test['recall']:.3f}  "
                f"Precision={test['precision']:.3f}  Acc={test['acc']:.3f}")
    logger.info(f"  TP={test['tp']}  FP={test['fp']}  FN={test['fn']}  TN={test['tn']}")

    results = {
        "model":          model_type,
        "mode":           mode,
        "img_size":       img_size,
        "best_epoch":     ckpt["epoch"],
        "best_val_f1":    best_f1,
        "test_f1":        test["f1"],
        "test_recall":    test["recall"],
        "test_precision": test["precision"],
        "test_acc":       test["acc"],
        "test_tp":        test["tp"],
        "test_fp":        test["fp"],
        "test_fn":        test["fn"],
        "test_tn":        test["tn"],
    }
    (out_dir / f"{model_type}_binary_results.json").write_text(
        json.dumps(results, indent=2)
    )
    logger.info(f"Checkpoint: {ckpt_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_ls",           help="Path to labeled_ls")
    parser.add_argument("--data_mb",           help="Path to labeled_mb")
    parser.add_argument("--mode",              default="combined",
                        choices=["ls", "mb", "combined"])
    parser.add_argument("--model",             default="efficientnet",
                        choices=["efficientnet", "insectnet"])
    parser.add_argument("--insectnet_weights", help="Path to InsectNet model.pth")
    parser.add_argument("--output",            default="models")
    parser.add_argument("--epochs",            type=int,   default=20)
    parser.add_argument("--batch",             type=int,   default=32)
    parser.add_argument("--lr",                type=float, default=1e-3)
    parser.add_argument("--bg_ratio",          type=int,   default=DEFAULT_BG_RATIO,
                        help="Background:insect sampling ratio (default 3)")
    args = parser.parse_args()

    train_binary(
        data_ls           = args.data_ls,
        data_mb           = args.data_mb,
        mode              = args.mode,
        model_type        = args.model,
        insectnet_weights = args.insectnet_weights,
        output_dir        = args.output,
        epochs            = args.epochs,
        batch             = args.batch,
        lr                = args.lr,
        bg_ratio          = args.bg_ratio,
    )
