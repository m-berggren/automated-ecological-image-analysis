"""End-to-end group classifier training workflow.

Currently a thin pass-through to pollinator.training.train_group; the file
exists so all training entry points live in pollinator.workflows, mirroring
the layered structure used for inference and YOLO training.
"""

from ..training.train_group import train_group as retrain_group

__all__ = ['retrain_group']
