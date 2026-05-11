"""End-to-end binary classifier training workflow.

Currently a thin pass-through to pollinator.training.train_binary; the file
exists so all training entry points live in pollinator.workflows, mirroring
the layered structure used for inference and YOLO training.
"""

from ..training.train_binary import train_binary as retrain_binary

__all__ = ['retrain_binary']
