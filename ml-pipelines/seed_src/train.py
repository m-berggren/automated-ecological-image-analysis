from ultralytics import YOLO

def train_model():
    model = YOLO("yolo26n-obb.pt")

    results = model.train(
       data="../data/seed/data.yaml",
        epochs=100,
        imgsz=768,
        batch=2,
        crop_fraction=0.2,
        mosaic=0.0,
        close_mosaic=0,
        plots=True
    )

    return results