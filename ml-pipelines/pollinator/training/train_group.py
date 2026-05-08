"""
training/train_group.py
========================
Train group classifier: bumblebee / fly / butterfly_moth / other.

Uses two model architectures:
    - EfficientNet-B2: standard image classifier, all layers trainable, ImageNet pretrained weights.
    - InsectNet:      custom insect classifier, last block + fc trainable, pretrained on 2526 insect classes.

Result shows that insectnet is performing better than efficientnet, and stage 2 fine-tuning on Arctic crops is not necessary for insectnet (and can even cause overfitting) since it's already well-trained on insect features from stage 1.

Two-stage training:
  Stage 1 (optional): web images + Arctic crops(images from collaborator) combined
  Stage 2:            Arctic crops only (fine-tune)
  Set epochs_s2=0 to skip Stage 2 (recommended for InsectNet since it's already well-trained after Stage 1).

Data split:
  - Val:        Arctic + web mixed (balanced per-class evaluation)
  - Test Arctic: Arctic crops only, never seen during training
  - Test Web:    web images only, capped to same size as Test Arctic

Usage (CLI):
    python -m pollinator.training.train_group \
        --data_ls   path/to/labeled_ls \
        --data_mb   path/to/labeled_mb \
        --web_dir   path/to/web_images \
        --mode      combined \
        --model     insectnet \
        --insectnet_weights path/to/InsectNet/model.pth \
        --output    path/to/models \
        --epochs_s1 20 \
        --epochs_s2 0

Usage (as module):
    from pollinator.training.train_group import train_group
    train_group(data_ls="...", data_mb="...", web_dir="...", mode="combined",
                model_type="insectnet", epochs_s2=0)
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

CLASSES = ["bumblebee", "fly", "butterfly_moth", "other"]

ARCTIC_ALIAS = {
    "bumblebee":  "bumblebee",
    "fly":        "fly",
    "butterfly":  "butterfly_moth",
    "other":      "other",
}

WEB_ALIAS = {
    "bumblebee":      "bumblebee",
    "fly":            "fly",
    "butterfly":      "butterfly_moth",
    "butterfly_moth": "butterfly_moth",
    "other":          "other",
}


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


def collect_samples(arctic_dir: Optional[Path], web_dir: Optional[Path],
                    classes: list) -> tuple:
    cls_to_idx = {c: i for i, c in enumerate(classes)}

    arctic_samples = []
    if arctic_dir is not None:
        for folder, cls in ARCTIC_ALIAS.items():
            if cls not in cls_to_idx:
                continue
            d = arctic_dir / folder
            if not d.exists():
                continue
            idx = cls_to_idx[cls]
            for ext in ("*.jpg", "*.jpeg", "*.png"):
                for p in d.glob(ext):
                    arctic_samples.append((p, idx))

    web_samples = []
    if web_dir is not None and web_dir.exists():
        for folder, cls in WEB_ALIAS.items():
            if cls not in cls_to_idx:
                continue
            d = web_dir / folder
            if not d.exists():
                continue
            idx = cls_to_idx[cls]
            for ext in ("*.jpg", "*.jpeg", "*.png"):
                for p in d.glob(ext):
                    web_samples.append((p, idx))

    def count_by_class(samples):
        c = {i: 0 for i in range(len(classes))}
        for _, lbl in samples:
            c[lbl] += 1
        return c

    return arctic_samples, web_samples, count_by_class(arctic_samples), count_by_class(web_samples)


def stratified_split(samples: list, n_classes: int, val_frac: float,
                     seed: int, test_frac: float = 0.1) -> tuple:
    """Stratified train/val/test split by class."""
    rng      = np.random.default_rng(seed)
    by_class = {i: [] for i in range(n_classes)}
    for i, (_, lbl) in enumerate(samples):
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
    return train_idx, val_idx, test_idx


def make_loader(samples: list, indices: list, img_size: int, batch: int,
                augment: bool = True) -> DataLoader:
    lb = T.Lambda(lambda img: letterbox(img, img_size))
    if augment:
        tf = T.Compose([
            lb,
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.RandomRotation(30),
            T.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.3, hue=0.05),
            T.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    else:
        tf = T.Compose([
            lb, T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    subset = [samples[i] for i in indices]
    ds     = CropDataset(subset, tf)
    if augment:
        labels   = [s[1] for s in subset]
        cls_w    = 1.0 / np.maximum(np.bincount(labels, minlength=len(CLASSES)), 1)
        sample_w = [cls_w[l] for l in labels]
        sampler  = WeightedRandomSampler(sample_w, len(sample_w))
        return DataLoader(ds, batch_size=batch, sampler=sampler, num_workers=0)
    return DataLoader(ds, batch_size=batch, shuffle=False, num_workers=0)


# ── Model builders ─────────────────────────────────────────────────────────
def build_efficientnet_b2(num_classes: int) -> tuple:
    logger.info(f"Building EfficientNet-B2 (ImageNet, all layers trainable, {num_classes} classes)")
    model = torchvision.models.efficientnet_b2(weights="IMAGENET1K_V1")
    in_f  = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_f, num_classes)
    return model, 224


def build_insectnet(weights_path: str, num_classes: int,
                    unfreeze_last_block: bool = True) -> tuple:
    logger.info(f"Building InsectNet group classifier (RegNet-Y-32GF, {num_classes} classes)")
    model    = torchvision.models.regnet_y_32gf()
    model.fc = nn.Linear(3712, 2526)
    state    = torch.load(weights_path, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"] if "model" in state else state, strict=True)
    model.fc = nn.Linear(3712, num_classes)
    nn.init.xavier_uniform_(model.fc.weight)
    nn.init.zeros_(model.fc.bias)
    for name, p in model.named_parameters():
        p.requires_grad = name.startswith("fc.")
    if unfreeze_last_block:
        for name, p in model.named_parameters():
            if "trunk_output.block4" in name or name.startswith("fc."):
                p.requires_grad = True
        logger.info("Unfreezing last backbone block (trunk_output.block4) + fc")
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    logger.info(f"Trainable: {n_train:,} / {n_total:,} params")
    return model, 224


def weighted_criterion(counts: dict, n_classes: int, device) -> nn.Module:
    w = torch.tensor(
        [1.0 / max(1, counts[i]) for i in range(n_classes)],
        dtype=torch.float, device=device
    )
    return nn.CrossEntropyLoss(weight=w / w.sum())


# ── Eval ───────────────────────────────────────────────────────────────────
@torch.no_grad()
def eval_epoch(model, loader, criterion, device, classes) -> dict:
    model.eval()
    loss_sum = correct = total = 0
    all_preds, all_labels = [], []
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        out   = model(imgs)
        preds = out.argmax(1)
        loss_sum += criterion(out, labels).item() * labels.size(0)
        correct  += (preds == labels).sum().item()
        total    += labels.size(0)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())

    per_class_f1 = {}
    for i, cls in enumerate(classes):
        tp   = sum(1 for p, l in zip(all_preds, all_labels) if p == i and l == i)
        fp   = sum(1 for p, l in zip(all_preds, all_labels) if p == i and l != i)
        fn   = sum(1 for p, l in zip(all_preds, all_labels) if p != i and l == i)
        prec = tp / max(1, tp + fp)
        rec  = tp / max(1, tp + fn)
        per_class_f1[cls] = 2 * prec * rec / max(1e-8, prec + rec)

    return {
        "loss":         loss_sum / max(1, total),
        "acc":          correct / max(1, total),
        "macro_f1":     sum(per_class_f1.values()) / len(classes),
        "per_class_f1": per_class_f1,
        "preds":        all_preds,
        "labels":       all_labels,
    }


# ── Training stage ─────────────────────────────────────────────────────────
def run_stage(model, name, train_loader, val_loader, epochs, lr,
              counts, ckpt_path, device, classes) -> tuple:
    criterion = weighted_criterion(counts, len(classes), device)
    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()), lr=lr
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_f1 = 0.0
    history = {"tr_loss": [], "val_loss": [], "macro_f1": []}

    logger.info(f"\n{'='*65}")
    logger.info(f"{name}  |  epochs={epochs}  |  lr={lr}")
    logger.info(f"{'='*65}")
    logger.info(f"{'Ep':>3}  {'TrLoss':>7}  {'VaLoss':>7}  {'MacroF1':>8}  {'Acc':>6}")

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

        v = eval_epoch(model, val_loader, criterion, device, classes)
        history["tr_loss"].append(tr_loss)
        history["val_loss"].append(v["loss"])
        history["macro_f1"].append(v["macro_f1"])

        star = ""
        if v["macro_f1"] > best_f1:
            best_f1 = v["macro_f1"]
            torch.save({
                "epoch": ep, "stage": name, "classes": classes,
                "state_dict": model.state_dict(),
                "macro_f1": v["macro_f1"], "acc": v["acc"],
            }, ckpt_path)
            star = " *"

        logger.info(f"{ep:>3}  {tr_loss:>7.4f}  {v['loss']:>7.4f}  "
                    f"{v['macro_f1']:>8.3f}  {v['acc']:>6.3f}{star}")

    return model, history


# ── Main training function ─────────────────────────────────────────────────
def train_group(
    data_ls:            Optional[str] = None,
    data_mb:            Optional[str] = None,
    web_dir:            Optional[str] = None,
    mode:               str   = "combined",
    model_type:         str   = "insectnet",
    insectnet_weights:  Optional[str] = None,
    unfreeze_last_block: bool = True,
    output_dir:         str   = "models",
    epochs_s1:          int   = 20,
    epochs_s2:          int   = 0,    # 0 = skip Stage 2 (recommended for InsectNet)
    batch:              int   = 32,
    lr_s1:              float = 1e-3,
    lr_s2:              float = 1e-4,
    val_frac:           float = 0.2,
    test_frac:          float = 0.1,
    seed:               int   = 42,
) -> dict:
    """
    Train group classifier (bumblebee / fly / butterfly_moth / other).

    Val set:        Arctic + web mixed for balanced per-class evaluation.
    Test Arctic:    Arctic crops only — reflects real field performance.
    Test Web:       web images only — reflects generalisation.

    epochs_s2=0 skips Stage 2 and uses Stage 1 checkpoint as final model.
    This is recommended for InsectNet as Stage 2 overfits on small Arctic data.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(seed)
    np.random.seed(seed)

    # ── Collect samples ────────────────────────────────────────────────────
    arctic_dirs = []
    if mode in ("ls", "combined") and data_ls:
        arctic_dirs.append(Path(data_ls))
    if mode in ("mb", "combined") and data_mb:
        arctic_dirs.append(Path(data_mb))

    arctic_samples = []
    counts_arctic  = {i: 0 for i in range(len(CLASSES))}

    for d in arctic_dirs:
        s, _, ca, _ = collect_samples(d, None, CLASSES)
        arctic_samples += s
        for i in range(len(CLASSES)):
            counts_arctic[i] += ca[i]

    web_samples, counts_web = [], {i: 0 for i in range(len(CLASSES))}
    if web_dir:
        _, web_samples, _, counts_web = collect_samples(None, Path(web_dir), CLASSES)

    logger.info("\nArctic crops per class:")
    for i, cls in enumerate(CLASSES):
        flag = "  ← low" if counts_arctic[i] < 50 else ""
        logger.info(f"  {cls:20}: {counts_arctic[i]:>5}{flag}")
    if web_samples:
        logger.info("\nWeb images per class:")
        for i, cls in enumerate(CLASSES):
            logger.info(f"  {cls:20}: {counts_web[i]:>5}")

    # ── Split ──────────────────────────────────────────────────────────────
    n_arctic = len(arctic_samples)
    all_samples_for_split = arctic_samples + web_samples

    all_train_idx, all_val_idx, _ = stratified_split(
        all_samples_for_split, len(CLASSES), val_frac, seed, test_frac
    )

    # Separate arctic and web train indices
    arctic_train_idx = [i for i in all_train_idx if i < n_arctic]
    web_train_idx    = [i - n_arctic for i in all_train_idx if i >= n_arctic]
    arctic_val_idx   = all_val_idx   # mixed val: arctic + web

    # Test Arctic: Arctic samples NOT in train or val
    used_arctic     = set(arctic_train_idx) | {i for i in all_val_idx if i < n_arctic}
    arctic_test_idx = [i for i in range(n_arctic) if i not in used_arctic]

    # Test Web: web samples NOT in train or val, capped to arctic test size
    used_web_train = set(web_train_idx)
    used_web_val   = {i - n_arctic for i in all_val_idx if i >= n_arctic}
    used_web       = used_web_train | used_web_val
    web_test_pool  = [i for i in range(len(web_samples)) if i not in used_web]
    rng_test       = np.random.default_rng(seed)
    rng_test.shuffle(web_test_pool)
    web_test_idx   = web_test_pool[:len(arctic_test_idx)]

    logger.info(f"\nTrain:        {len(arctic_train_idx)} arctic + {len(web_train_idx)} web")
    logger.info(f"Val:          {len(arctic_val_idx)} (arctic + web mixed)")
    logger.info(f"Test Arctic:  {len(arctic_test_idx)} (Arctic only — real field performance)")
    logger.info(f"Test Web:     {len(web_test_idx)} (web only — generalisation)")

    # ── Build model ────────────────────────────────────────────────────────
    if model_type == "insectnet":
        if not insectnet_weights:
            raise ValueError("insectnet_weights required for insectnet model")
        model, img_size = build_insectnet(
            insectnet_weights, len(CLASSES), unfreeze_last_block
        )
    else:
        model, img_size = build_efficientnet_b2(len(CLASSES))
    model = model.to(device)

    # ── Loaders ────────────────────────────────────────────────────────────
    val_loader         = make_loader(all_samples_for_split, arctic_val_idx,  img_size, batch, augment=False)
    test_loader_arctic = make_loader(arctic_samples,         arctic_test_idx, img_size, batch, augment=False)
    test_loader_web    = make_loader(web_samples,             web_test_idx,   img_size, batch, augment=False)

    # ── Stage 1: web + arctic combined ────────────────────────────────────
    stage1_ckpt = out_dir / f"group_{model_type}_stage1.pth"
    if web_samples and epochs_s1 > 0:
        combined_samples   = arctic_samples + web_samples
        combined_train_idx = (
            arctic_train_idx +
            [n_arctic + i for i in web_train_idx]
        )
        combined_counts = {i: counts_arctic[i] + counts_web[i] for i in range(len(CLASSES))}
        train_loader_s1 = make_loader(combined_samples, combined_train_idx, img_size, batch)
        model, _ = run_stage(
            model, f"{model_type}_stage1_combined",
            train_loader_s1, val_loader,
            epochs_s1, lr_s1, combined_counts, stage1_ckpt, device, CLASSES
        )
        ckpt = torch.load(stage1_ckpt, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["state_dict"])
        logger.info("Stage 1 done. Loading best checkpoint.")
    else:
        logger.info("No web images or epochs_s1=0 — skipping Stage 1.")

    # ── Stage 2: Arctic fine-tune (optional) ──────────────────────────────
    stage2_ckpt = out_dir / f"group_{model_type}_best.pth"
    if epochs_s2 == 0:
        logger.info(f"[{model_type}] Skipping Stage 2 (epochs_s2=0). Using Stage 1 checkpoint as final.")
        import shutil
        shutil.copy(stage1_ckpt, stage2_ckpt)
    else:
        train_loader_s2 = make_loader(arctic_samples, arctic_train_idx, img_size, batch)
        model, _ = run_stage(
            model, f"{model_type}_stage2_arctic",
            train_loader_s2, val_loader,
            epochs_s2, lr_s2, counts_arctic, stage2_ckpt, device, CLASSES
        )

    # ── Final evaluation ───────────────────────────────────────────────────
    ckpt = torch.load(stage2_ckpt, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["state_dict"])
    criterion_final = weighted_criterion(counts_arctic, len(CLASSES), device)

    final              = eval_epoch(model, val_loader,         criterion_final, device, CLASSES)
    final_test_arctic  = eval_epoch(model, test_loader_arctic, criterion_final, device, CLASSES)
    final_test_web     = eval_epoch(model, test_loader_web,    criterion_final, device, CLASSES)

    logger.info(f"\n--- {model_type} final report (best checkpoint epoch {ckpt['epoch']}) ---")
    logger.info(f"Val         MacroF1={final['macro_f1']:.3f}  Acc={final['acc']:.3f}")
    logger.info(f"Test Arctic MacroF1={final_test_arctic['macro_f1']:.3f}  Acc={final_test_arctic['acc']:.3f}  (real field performance)")
    logger.info(f"Test Web    MacroF1={final_test_web['macro_f1']:.3f}  Acc={final_test_web['acc']:.3f}  (generalisation)")
    logger.info("Per-class F1 (val):")
    for cls, f1 in final["per_class_f1"].items():
        logger.info(f"  {cls:20}: {f1:.3f}")

    # ── Save results ───────────────────────────────────────────────────────
    results = {
        "model":                   model_type,
        "mode":                    mode,
        "img_size":                img_size,
        "classes":                 CLASSES,
        "best_epoch":              ckpt["epoch"],
        "val_macro_f1":            final["macro_f1"],
        "val_acc":                 final["acc"],
        "val_per_class_f1":        final["per_class_f1"],
        "test_arctic_macro_f1":    final_test_arctic["macro_f1"],
        "test_arctic_acc":         final_test_arctic["acc"],
        "test_arctic_per_class":   final_test_arctic["per_class_f1"],
        "test_web_macro_f1":       final_test_web["macro_f1"],
        "test_web_acc":            final_test_web["acc"],
        "test_web_per_class":      final_test_web["per_class_f1"],
    }
    (out_dir / f"group_{model_type}_results.json").write_text(
        json.dumps(results, indent=2)
    )
    logger.info(f"Checkpoint: {stage2_ckpt}")
    return results


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_ls",            help="Path to labeled_ls")
    parser.add_argument("--data_mb",            help="Path to labeled_mb")
    parser.add_argument("--web_dir",            help="Path to web_images (optional)")
    parser.add_argument("--mode",               default="combined", choices=["ls", "mb", "combined"])
    parser.add_argument("--model",              default="insectnet", choices=["efficientnet", "insectnet"])
    parser.add_argument("--insectnet_weights",  help="Path to InsectNet model.pth")
    parser.add_argument("--no_unfreeze",        action="store_true", help="Keep InsectNet backbone fully frozen")
    parser.add_argument("--output",             default="models")
    parser.add_argument("--epochs_s1",          type=int,   default=20)
    parser.add_argument("--epochs_s2",          type=int,   default=0,
                        help="Stage 2 epochs (0=skip, recommended for InsectNet)")
    parser.add_argument("--batch",              type=int,   default=32)
    parser.add_argument("--lr_s1",              type=float, default=1e-3)
    parser.add_argument("--lr_s2",              type=float, default=1e-4)
    args = parser.parse_args()

    train_group(
        data_ls             = args.data_ls,
        data_mb             = args.data_mb,
        web_dir             = args.web_dir,
        mode                = args.mode,
        model_type          = args.model,
        insectnet_weights   = args.insectnet_weights,
        unfreeze_last_block = not args.no_unfreeze,
        output_dir          = args.output,
        epochs_s1           = args.epochs_s1,
        epochs_s2           = args.epochs_s2,
        batch               = args.batch,
        lr_s1               = args.lr_s1,
        lr_s2               = args.lr_s2,
    )