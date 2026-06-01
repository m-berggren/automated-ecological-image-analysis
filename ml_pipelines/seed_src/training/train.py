import multiprocessing
import os
import sys

# Enable Windows to run and not just Unix systems
if sys.platform == 'win32':
    multiprocessing.set_start_method('spawn', force=True)
else:
    multiprocessing.set_start_method('fork', force=True)

from ultralytics import YOLO


def train_species_model(
    species_name,
    data_yaml_path,
    *,
    epochs=1,
    pretrained_weights_path='yolo26n-obb.pt',
    finetune_from: str | None = None,
    run_name: str | None = None,
    progress_callback=None,
    lr0: float | None = None,
    lrf: float | None = None,
    project: str | None = None,
):

    print(
        f'train_species_model called! species={species_name} callback={progress_callback is not None}'
    )
    import sys

    sys.stdout.flush()
    run_name = run_name or species_name
    weights = finetune_from if finetune_from else pretrained_weights_path
    model = YOLO(weights)

    if progress_callback:

        def on_fit_epoch_end(trainer):
            progress_callback(
                processed=trainer.epoch + 1,
                total=trainer.epochs,
                message=f'Epoch {trainer.epoch + 1}/{trainer.epochs}',
                level='info',
            )

        model.add_callback('on_fit_epoch_end', on_fit_epoch_end)

    train_kwargs = dict(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=run_name,
        exist_ok=False,
        batch=-1,
        mosaic=0.0,
        close_mosaic=0,
        plots=True,
        patience=20,
        resume=False,
    )
    if lr0 is not None:
        train_kwargs['lr0'] = lr0
    if lrf is not None:
        train_kwargs['lrf'] = lrf
    # `project` redirects YOLO's run output from the CWD-relative
    # runs/obb/ default to a caller-chosen dir. The Django training job
    # uses this to write weights straight into MEDIA_ROOT/training/<job_pk>/
    # so nothing ever lands outside MEDIA_ROOT.
    if project is not None:
        train_kwargs['project'] = project

    model.train(**train_kwargs)
    base = project if project is not None else os.path.join('runs', 'obb')
    return os.path.join(base, run_name, 'weights', 'best.pt')
