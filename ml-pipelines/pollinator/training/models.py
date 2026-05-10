"""
training/models.py
===================
Shared model builders for the InsectNet (RegNet-Y-32GF backbone, pretrained
on 2526 insect classes) and EfficientNet-B2 (ImageNet-pretrained) heads used
by both binary and group classifier training.
"""

import logging

import torch
import torch.nn as nn
import torchvision

logger = logging.getLogger(__name__)

INSECTNET_PRETRAIN_CLASSES = 2526
INSECTNET_FC_IN = 3712


def build_efficientnet_b2(num_classes: int, img_size: int = 224) -> tuple:
    """
    EfficientNet-B2 with an ImageNet-pretrained backbone and a fresh
    classification head sized to num_classes. All layers trainable.
    Returns (model, img_size).
    """
    logger.info(
        f'Building EfficientNet-B2 (ImageNet, {num_classes} classes, {img_size}px, all layers trainable)'
    )
    model = torchvision.models.efficientnet_b2(weights='IMAGENET1K_V1')
    in_f = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_f, num_classes)
    return model, img_size


def build_insectnet(
    weights_path: str,
    num_classes: int,
    unfreeze_last_block: bool = False,
) -> tuple:
    """
    InsectNet RegNet-Y-32GF with the pretrained 2526-class head replaced by
    a fresh head sized to num_classes. By default the entire backbone is
    frozen and only the new fc is trainable. Set unfreeze_last_block=True
    to also train trunk_output.block4 (used for the group classifier where
    fine-tuning helps with the small Arctic dataset).
    Returns (model, img_size).
    """
    logger.info(f'Building InsectNet (RegNet-Y-32GF, {num_classes} classes)')
    model = torchvision.models.regnet_y_32gf()
    model.fc = nn.Linear(INSECTNET_FC_IN, INSECTNET_PRETRAIN_CLASSES)
    state = torch.load(weights_path, map_location='cpu', weights_only=False)
    model.load_state_dict(state['model'] if 'model' in state else state, strict=True)

    model.fc = nn.Linear(INSECTNET_FC_IN, num_classes)
    nn.init.xavier_uniform_(model.fc.weight)
    nn.init.zeros_(model.fc.bias)

    for name, p in model.named_parameters():
        p.requires_grad = name.startswith('fc.')

    if unfreeze_last_block:
        for name, p in model.named_parameters():
            if 'trunk_output.block4' in name or name.startswith('fc.'):
                p.requires_grad = True
        logger.info('Unfreezing last backbone block (trunk_output.block4) + fc')
    else:
        logger.info('Backbone: FROZEN (only fc layer trainable)')

    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    logger.info(f'Trainable: {n_train:,} / {n_total:,} params')
    return model, 224
