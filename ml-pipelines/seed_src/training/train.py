import os

from ultralytics import YOLO


# YOLO26n-OBB model without data augmentations
# Includes more parameters so that there is an option for incremental training
def train_species_model(
    species_name,
    data_yaml_path,
    *,
    epochs=90,
    pretrained_weights_path='yolo26n-obb.pt',
    finetune_from: str | None = None,
    run_name: str | None = None,
    lr0: float | None = None,
    lrf: float | None = None,
):
    run_name = run_name or species_name
    weights = finetune_from if finetune_from else pretrained_weights_path
    model = YOLO(weights)
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
