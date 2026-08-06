"""Keep the seeds unit tests free of the torch/ultralytics training stack.

apps.seeds.training imports train_species_model at module top from
ml_pipelines.seed_src.training.train, which pulls ultralytics (slow, networked
first-import). The pure split/validation helpers under test never call it, so a
lightweight stand-in is installed before that module is imported. The guard
leaves a real import untouched if something already loaded it.
"""

import sys
import types

_TRAIN_MODULE = 'ml_pipelines.seed_src.training.train'

if _TRAIN_MODULE not in sys.modules:
    _stub = types.ModuleType(_TRAIN_MODULE)
    _stub.train_species_model = lambda *args, **kwargs: None
    sys.modules[_TRAIN_MODULE] = _stub
