"""
training/train_binary.py
=========================
Train binary classifier: insect vs background.

Uses two model architectures:
    - EfficientNet-B2: standard image classifier, all layers trainable, ImageNet pretrained weights.
    - InsectNet:      custom insect classifier, last block + fc trainable, pretrained on 2526 insect classes.

Result shows EfficientNet-B2 performs better in identifying insects vs background

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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as T
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

logger = logging.getLogger(__name__)

CLASSES        = ["background", "insect"]
INSECT_FOLDERS = ["bumblebee", "fly", "butterfly", "other"]
DEFAULT_BG_RATIO = 3


# ── Dataset helpers ────────────────────────────────────────────────────────
def letterbox(img: Image.Image, size: int) -> Image.Image:
    w, h  = img.size
    max_s = max(w, h)
    sq    = Image.new("RGB", (max_s, max_s), (0, 0, 0))
    sq.paste(img, ((max_s - w) // 2, (max_s - h) // 2))
    return sq.resize((size, size), Image.BILINEAR)


class CropDataset(Dataset):
    def __init__(self, samples, transform):
        self.samples   = samples
        self.transform = transform

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


def _collect_samples(labeled_dir: Path, bg_ratio: int, rng, bg_counts_per_plot: dict):
    """Collect (path, label) pairs with per-plot background quota sampling."""
    samples = []

    # Insect crops (all subfolders except background and unsure)
    for folder in INSECT_FOLDERS:
        d = labeled_dir / folder
        if not d.exists():
            continue
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            for p in d.glob(ext):
                samples.append((p, 1))  # 1 = insect

    n_insect = sum(1 for _, l in samples if l == 1)
    quota    = n_insect * bg_ratio

    # Background crops — sample per plot
    bg_dir = labeled_dir / "background"
    if bg_dir.exists():
        # Group by plot (parent folder name encoded in filename)
        all_bg = list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png"))
        rng.shuffle(all_bg)
        # Simple random sample capped at quota
        sampled = all_bg[:quota]
        for p in sampled:
            samples.append((p, 0))  # 0 = background

    n_bg = sum(1 for _, l in samples if l == 0)
    logger.info(f"  {labeled_dir.name}: insect={n_insect} background={n_bg}")
    return samples


def load_and_split(
    labeled_dirs: list,
    val_frac:     float = 0.2,
    test_frac:    float = 0.1,
    bg_ratio:     int   = DEFAULT_BG_RATIO,
    seed:         int   = 42,
) -> tuple:
    rng = np.random.default_rng(seed)
    all_samples = []
    for d in labeled_dirs:
        all_samples += _collect_samples(Path(d), bg_ratio, rng, {})

    rng.shuffle(all_samples)

    # Stratified split
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

    counts = {0: sum(1 for _, l in all_samples if l == 0),
              1: sum(1 for _, l in all_samples if l == 1)}

    def split_counts(idx):
        bg  = sum(1 for i in idx if all_samples[i][1] == 0)
        ins = sum(1 for i in idx if all_samples[i][1] == 1)
        return bg, ins

    tr_bg, tr_ins = split_counts(train_idx)
    va_bg, va_ins = split_counts(val_idx)
    te_bg, te_ins = split_counts(test_idx)

    logger.info(f"\nDataset split summary:")
    logger.info(f"  Strategy: stratified by class, test={test_frac:.0%}, val={val_frac:.0%}")
    logger.info(f"  {'Split':8}  {'Background':>12}  {'Insect':>8}  {'Total':>8}")
    logger.info(f"  {'Train':8}  {tr_bg:>12}  {tr_ins:>8}  {len(train_idx):>8}")
    logger.info(f"  {'Val':8}  {va_bg:>12}  {va_ins:>8}  {len(val_idx):>8}")
    logger.info(f"  {'Test':8}  {te_bg:>12}  {te_ins:>8}  {len(test_idx):>8}")
    logger.info(f"  Background:insect ratio = {counts[0]/max(1,counts[1]):.1f}:1")

    return all_samples, train_idx, val_idx, test_idx, counts


def make_loaders(all_samples, train_idx, val_idx, test_idx, counts, img_size, batch):
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

    # Weighted sampler for training
    labels   = [s[1] for s in train_samples]
    cls_w    = 1.0 / np.maximum(np.bincount(labels, minlength=2), 1)
    sample_w = [cls_w[l] for l in labels]
    sampler  = WeightedRandomSampler(sample_w, len(sample_w))

    # Weighted loss
    w = torch.tensor([1.0 / max(1, counts[i]) for i in range(2)])
    w = w / w.sum()
    criterion = nn.CrossEntropyLoss(weight=w)

    train_loader = DataLoader(CropDataset(train_samples, train_tf),
                              batch_size=batch, sampler=sampler, num_workers=0)
    val_loader   = DataLoader(CropDataset(val_samples, val_tf),
                              batch_size=batch, shuffle=False, num_workers=0)
    test_loader  = DataLoader(CropDataset(test_samples, val_tf),
                              batch_size=batch, shuffle=False, num_workers=0)
    return train_loader, val_loader, test_loader, criterion


# ── Model builders ─────────────────────────────────────────────────────────
def build_efficientnet_b2():
    logger.info("Building EfficientNet-B2 (ImageNet, 256px, all layers trainable)")
    model = torchvision.models.efficientnet_b2(weights="IMAGENET1K_V1")
    in_f  = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_f, 2)
    return model, 256


def build_insectnet(weights_path: str, unfreeze_last: bool = False):
    logger.info(f"Building InsectNet binary (RegNet-Y-32GF, 224px)")
    model    = torchvision.models.regnet_y_32gf()
    model.fc = nn.Linear(3712, 2526)
    state    = torch.load(weights_path, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"] if "model" in state else state, strict=True)
    model.fc = nn.Linear(3712, 2)
    nn.init.xavier_uniform_(model.fc.weight)
    for name, p in model.named_parameters():
        p.requires_grad = name.startswith("fc.")
    if unfreeze_last:
        for name, p in model.named_parameters():
            if "trunk_output.block4" in name or name.startswith("fc."):
                p.requires_grad = True
        logger.info("Backbone: last block + fc unfrozen")
    else:
        logger.info("Backbone: FROZEN (only fc layer trainable)")
    return model, 224


# ── Training loop ──────────────────────────────────────────────────────────
@torch.no_grad()
def eval_epoch(model, loader, criterion, device):
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
    return {"loss": loss_sum / total, "acc": correct / total,
            "precision": prec, "recall": rec, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def train_binary(
    data_ls:         Optional[str] = None,
    data_mb:         Optional[str] = None,
    mode:            str   = "combined",
    model_type:      str   = "efficientnet",
    insectnet_weights: Optional[str] = None,
    output_dir:      str   = "models",
    epochs:          int   = 20,
    batch:           int   = 32,
    lr:              float = 1e-3,
    val_frac:        float = 0.2,
    test_frac:       float = 0.1,
    bg_ratio:        int   = DEFAULT_BG_RATIO,
    seed:            int   = 42,
) -> dict:
    """
    Train binary insect/background classifier.

    Args:
        data_ls:   Path to labeled_ls folder (Lian's data).
        data_mb:   Path to labeled_mb folder (Marcus's data).
        mode:      "ls", "mb", or "combined".
        model_type: "efficientnet" or "insectnet".
        insectnet_weights: Path to InsectNet model.pth (required for insectnet).
        output_dir: Where to save checkpoints and curves.
        epochs, batch, lr, val_frac, test_frac, bg_ratio, seed: training params.

    Returns:
        dict with val and test metrics of the best checkpoint.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect data dirs
    dirs = []
    if mode in ("ls", "combined") and data_ls:
        dirs.append(data_ls)
    if mode in ("mb", "combined") and data_mb:
        dirs.append(data_mb)
    if not dirs:
        raise ValueError("No data directories provided")

    torch.manual_seed(seed)
    np.random.seed(seed)

    all_samples, train_idx, val_idx, test_idx, counts = load_and_split(
        dirs, val_frac, test_frac, bg_ratio, seed
    )
    img_size = 256 if model_type == "efficientnet" else 224
    train_loader, val_loader, test_loader, criterion = make_loaders(
        all_samples, train_idx, val_idx, test_idx, counts, img_size, batch
    )

    # Build model
    if model_type == "insectnet":
        if not insectnet_weights:
            raise ValueError("insectnet_weights path required for insectnet model")
        model, img_size = build_insectnet(insectnet_weights)
    else:
        model, img_size = build_efficientnet_b2()
    model = model.to(device)

    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()), lr=lr
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = criterion.to(device)

    ckpt_path = out_dir / f"{model_type}_binary_best.pth"
    best_f1   = 0.0
    history   = {"tr_loss": [], "val_loss": [], "val_f1": [], "val_acc": []}

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

        v = eval_epoch(model, val_loader, criterion, device)
        history["tr_loss"].append(tr_loss)
        history["val_loss"].append(v["loss"])
        history["val_f1"].append(v["f1"])
        history["val_acc"].append(v["acc"])

        star = ""
        if v["f1"] > best_f1:
            best_f1 = v["f1"]
            torch.save({
                "epoch": ep, "model_name": model_type, "img_size": img_size,
                "state_dict": model.state_dict(),
                "val_f1": v["f1"], "val_acc": v["acc"],
            }, ckpt_path)
            star = " *"

        logger.info(f"{ep:>3}  {tr_loss:>7.4f}  {v['loss']:>7.4f}  "
                    f"{v['precision']:>6.3f}  {v['recall']:>6.3f}  "
                    f"{v['f1']:>6.3f}  {v['acc']:>6.3f}{star}")

    logger.info(f"\nDone in {(time.time()-t0)/60:.1f} min  |  Best val F1: {best_f1:.3f}")

    # Final test evaluation
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["state_dict"])
    test_metrics = eval_epoch(model, test_loader, criterion, device)

    logger.info(f"\n--- Test set results (best checkpoint epoch {ckpt['epoch']}) ---")
    logger.info(f"  F1={test_metrics['f1']:.3f}  "
                f"Recall={test_metrics['recall']:.3f}  "
                f"Precision={test_metrics['precision']:.3f}  "
                f"Acc={test_metrics['acc']:.3f}")
    logger.info(f"  TP={test_metrics['tp']}  FP={test_metrics['fp']}  "
                f"FN={test_metrics['fn']}  TN={test_metrics['tn']}")

    # Save training curves
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(history["tr_loss"], label="train")
    axes[0].plot(history["val_loss"], label="val")
    axes[0].set_title("Loss"); axes[0].legend()
    axes[1].plot(history["val_f1"],  label="F1")
    axes[1].plot(history["val_acc"], label="Accuracy")
    axes[1].set_title("Val F1 / Accuracy"); axes[1].legend()
    plt.tight_layout()
    plt.savefig(out_dir / f"{model_type}_binary_curves.png", dpi=100)
    plt.close()

    # Save results JSON
    results = {
        "model": model_type, "mode": mode, "img_size": img_size,
        "best_epoch": ckpt["epoch"], "best_val_f1": best_f1,
        "test_f1":        test_metrics["f1"],
        "test_recall":    test_metrics["recall"],
        "test_precision": test_metrics["precision"],
        "test_acc":       test_metrics["acc"],
    }
    (out_dir / f"{model_type}_binary_results.json").write_text(
        json.dumps(results, indent=2)
    )
    logger.info(f"Checkpoint: {ckpt_path}")
    return results


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_ls",   help="Path to labeled_ls")
    parser.add_argument("--data_mb",   help="Path to labeled_mb")
    parser.add_argument("--mode",      default="combined", choices=["ls", "mb", "combined"])
    parser.add_argument("--model",     default="efficientnet", choices=["efficientnet", "insectnet"])
    parser.add_argument("--insectnet_weights", help="Path to InsectNet model.pth")
    parser.add_argument("--output",    default="models")
    parser.add_argument("--epochs",    type=int,   default=20)
    parser.add_argument("--batch",     type=int,   default=32)
    parser.add_argument("--lr",        type=float, default=1e-3)
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
    )
