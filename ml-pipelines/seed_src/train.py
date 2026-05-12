import os

from ultralytics import YOLO

"""
Includes all 4 variations of the YOLO26-OBB model:
- YOLO26s-OBB model without augmentations
- YOLO26s-OBB model with augmentations
- YOLO26n-OBB model without augmentations
- YOLO26n-OBB model with augmentations
The results are quite similar, so kept them all in for now.
We can later remove the ones that are not being used.
"""

"""
# YOLO26s-OBB model without augmentations
def train_species_model(species_name, data_yaml_path, epochs=90):
    model = YOLO('yolo26s-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=species_name,  # This creates unique folders per species
        exist_ok=True,
        batch=-1, # Allow YOLO to decide the best batch size
        mosaic=0.0,
        close_mosaic=0,
        plots=True,
        patience=20, # Early stopping if the model doesn't improve for 20 epochs
    )

    return os.path.join('runs', 'obb', species_name, 'weights', 'best.pt')
"""
"""
# YOLO26s-OBB model with augmentations
def train_species_model(species_name, data_yaml_path, epochs=90):
    model = YOLO('yolo26s-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=species_name,  # This creates unique folders per species
        exist_ok=True,
        batch=-1, # Allow YOLO to decide the best batch size
        mosaic=1.0,
        close_mosaic=0,
        plots=True,
        mixup=0.2,
        degrees=45.0,
        flipud=0.5,
        fliplr=0.5,
        patience=20, # Early stopping if the model doesn't improve for 20 epochs'
    )

    return os.path.join('runs', 'obb', species_name, 'weights', 'best.pt')
"""

"""
# YOLO26n-OBB model without augmentations
def train_species_model(species_name, data_yaml_path, epochs=90):
    model = YOLO('yolo26n-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=species_name,  # This creates unique folders per species
        exist_ok=True,
        batch=-1, # Allow YOLO to decide the best batch size
        mosaic=0.0,
        close_mosaic=0,
        plots=True,
        patience=20, # Early stopping if the model doesn't improve for 20 epochs
    )

    return os.path.join('runs', 'obb', species_name, 'weights', 'best.pt')
"""

"""
# YOLO26n-OBB model with augmentations
def train_species_model(species_name, data_yaml_path, epochs=90):
    model = YOLO('yolo26n-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=species_name,  # This creates unique folders per species
        exist_ok=True,
        batch=-1, # Allow YOLO to decide the best batch size
        mosaic=1.0,
        close_mosaic=0,
        plots=True,
        mixup=0.2,
        degrees=45.0,
        flipud=0.5,
        fliplr=0.5,
        patience=20, # Early stopping if the model doesn't improve for 20 epochs
        # project='runs/obb'
    )

    return os.path.join('runs', 'obb', species_name, 'weights', 'best.pt')
"""

# Includes more parameters so that there is an option for incremental training
def train_species_model(
    species_name,
    data_yaml_path,
    *,
    epochs=90,
    pretrained_weights_path='yolo26n-obb.pt', # Pretrained checkpoint
    finetune_from: str | None = None, # For retraining, we should set this parameter to a path to best.pt or last.pt from a previous run. If set, it overrides pretrained_weights_path
    run_name: str | None = None, # New run folder name under runs/obb/ (use e.g. f"{species_name}_ft1" to avoid overwriting)
    lr0: float | None = None, # Learning rate for the new run
    lrf: float | None = None, # Also learning rate for the new run
):
    run_name = run_name or species_name
    weights = finetune_from if finetune_from else pretrained_weights_path
    model = YOLO(weights)
    train_kwargs = dict(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=run_name,
        exist_ok=True,
        batch=-1,
        mosaic=0.0,
        close_mosaic=0,
        plots=True,
        patience=20,
        resume=False,  # This makes it explicit that this is a new run, not a crash-resume
    )
    if lr0 is not None:
        train_kwargs['lr0'] = lr0
    if lrf is not None:
        train_kwargs['lrf'] = lrf
    model.train(**train_kwargs)
    return os.path.join('runs', 'obb', run_name, 'weights', 'best.pt')
