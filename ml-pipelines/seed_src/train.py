import os

from ultralytics import YOLO

"""
def train_species_model(species_name, data_yaml_path, epochs=200):
    model = YOLO('yolo26s-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        batch=2,
        mosaic=1.0,
        close_mosaic=0,
        mixup=0.2,
        degrees=45.0,
        flipud=0.5,
        fliplr=0.5,
        augment=True,
        plots=True,
        exist_ok=True,
        patience=25
    )

    save_dir = model.trainer.save_dir
    best_path = os.path.join(save_dir, 'weights', 'best.pt')

    print(f'{species_name} model saved at: {best_path}')

    return best_path

"""


def train_species_model(species_name, data_yaml_path, epochs=90):
    model = YOLO('yolo26n-obb.pt')

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        name=species_name,  # This creates unique folders per species
        exist_ok=True,
        batch=2,
        mosaic=0.0,
        close_mosaic=0,
        augment=True,
        plots=True,
    )

    return os.path.join('runs', 'obb', species_name, 'weights', 'best.pt')
