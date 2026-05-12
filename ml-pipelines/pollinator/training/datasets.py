"""
Shared dataset primitives for binary and group classifier training:
letterbox image normalization and a generic Dataset class over (path, label) pairs.
"""

from PIL import Image
from torch.utils.data import Dataset


def letterbox(img: Image.Image, size: int) -> Image.Image:
    w, h = img.size
    max_s = max(w, h)
    sq = Image.new('RGB', (max_s, max_s), (0, 0, 0))
    sq.paste(img, ((max_s - w) // 2, (max_s - h) // 2))
    return sq.resize((size, size), Image.BILINEAR)


class CropDataset(Dataset):
    def __init__(self, samples, transform):
        self.samples = samples
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert('RGB')
        return self.transform(img), label
