from ultralytics import YOLO
import os


def train_species_model(species_name, data_yaml_path, epochs=200):
    model = YOLO("yolo26n-obb.pt")

    results = model.train(
        data=data_yaml_path,
        epochs=epochs,
        imgsz=768,
        batch=2,
        mosaic=0.0,
        close_mosaic=0,
        augment=True,
        plots=True
    )

    save_dir = model.trainer.save_dir
    best_path = os.path.join(save_dir, "weights", "best.pt")

    print(f"{species_name} model saved at: {best_path}")

    return best_path