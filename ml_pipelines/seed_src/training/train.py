import os
import multiprocessing
multiprocessing.set_start_method('fork', force=True)

from ultralytics import YOLO


def train_species_model(
    species_name,
    data_yaml_path,
    *,
    epochs=90,
    pretrained_weights_path='yolo26n-obb.pt',
    finetune_from: str | None = None,
    run_name: str | None = None,
    progress_callback=None,
    lr0: float | None = None,
    lrf: float | None = None,
):
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

    model.train(**train_kwargs)
    return os.path.join('runs', 'obb', run_name, 'weights', 'best.pt')