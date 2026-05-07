from ultralytics import YOLO
import os

def train_model():
    model = YOLO("yolo26n-obb.pt")

    model.train(
        data="../data/seed/data.yaml",
        epochs=200,
        imgsz=768,
        batch=2,
        mosaic=0.0,
        close_mosaic=0,
        plots=True,
        augment=True #Augmentation
    )

    save_dir = model.trainer.save_dir
    best_path = os.path.join(save_dir, "weights", "best.pt")

    return best_path