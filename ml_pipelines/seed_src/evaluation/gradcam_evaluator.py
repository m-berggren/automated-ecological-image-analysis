"""
Saliency Map Generation for the YOLO-OBB seed models using EigenCAM on a single slice.
"""

import os
import sys

import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
from pytorch_grad_cam import EigenCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from ultralytics import YOLO

ML_PIPELINES_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
os.chdir(ML_PIPELINES_DIR)
sys.path.append(ML_PIPELINES_DIR)


class YoloWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        res = self.model(x)
        if isinstance(res, tuple):
            return res[0]
        return res


def main():
    species = 'phyca'  # Species model to test, updated per species
    model_path = os.path.abspath(f'runs/obb/{species}/weights/best.pt')

    print(f'Loading Ultralytics YOLO model for {species.upper()}...')
    model = YOLO(model_path)

    # Load a slice from the center of the image (1536x1536 size)
    img_dir = f'../data/seed/{species}_model/val/images/'
    if not os.path.exists(img_dir):
        print(f'Directory not found: {img_dir}.')
        return

    img_name = os.listdir(img_dir)[0]
    img_path = os.path.join(img_dir, img_name)

    img = cv2.imread(img_path)
    h, w, _ = img.shape

    cy, cx = h // 2, w // 2
    crop = img[cy - 768 : cy + 768, cx - 768 : cx + 768]

    rgb_img = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    rgb_img_float = np.float32(rgb_img) / 255

    pytorch_model = model.model
    pytorch_model.eval()

    # Target the last feature layer of the model (the layer before the Detect head)
    target_layers = [pytorch_model.model[-2]]

    print('Generating EigenCAM heatmap...')

    # Wrap the model so the GradCAM library doesn't crash on tuple outputs
    wrapped_model = YoloWrapper(pytorch_model)

    cam = EigenCAM(model=wrapped_model, target_layers=target_layers)
    tensor = (
        torch.from_numpy(rgb_img_float).permute(2, 0, 1).unsqueeze(0).to(model.device)
    )
    grayscale_cam = cam(input_tensor=tensor)[0, :]

    # Resize cam to match slice size
    grayscale_cam = cv2.resize(grayscale_cam, (1536, 1536))
    cam_image = show_cam_on_image(rgb_img_float, grayscale_cam, use_rgb=True)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    axes[0].imshow(rgb_img)
    axes[0].set_title('Original 768x768 Crop')
    axes[0].axis('off')
    axes[1].imshow(cam_image)
    axes[1].set_title('EigenCAM Saliency Map')
    axes[1].axis('off')

    os.makedirs('evaluations/saliency_plots', exist_ok=True)
    out_path = f'evaluations/saliency_plots/{species}_saliency.png'
    plt.savefig(out_path)
    print(f'Saved saliency map to {out_path}')


if __name__ == '__main__':
    main()
