# Disclaimer: This file was converted from a Jupyter notebook file. During the conversion process,
# Gemini Pro 3.1 LLM was used for debugging issues.

import argparse
import os
import re

import cv2
import easyocr
import pandas as pd


class LabelExtractor:
    def __init__(self, gpu=False):
        self.reader = easyocr.Reader(['en'], gpu=gpu)
        self.species_list = ['PHYCA', 'VAU', 'PEH', 'CAT']
        self.type_map = {
            'PHYCA': 'PHYCA',
            'PHY': 'PHYCA',
            'PHICA': 'PHYCA',
            'VAU': 'VAU',
            'VAV': 'VAU',
            'VAVU': 'VAU',
            'VAY': 'VAU',
            'PEH': 'PEH',
            'PEM': 'PEH',
            'REH': 'PEH',
            'PED': 'PEH',
            'CAT': 'CAT',
        }

    def clean_label_text(self, raw_text):
        """Standardizes OCR output to match: <TYPE Number-Number>"""
        raw_text = raw_text.upper()

        # Identify species type
        matched_type = 'UNKNOWN'
        for key, val in self.type_map.items():
            if key in raw_text:
                matched_type = val
                break

        # Extract numeric pattern
        pattern = r'(\d+[\s\.\-\_]*\d+\s*[A-Z]?)'
        match = re.search(pattern, raw_text)

        if match:
            nums = (
                match.group(1)
                .replace(' ', '')
                .replace('.', '-')
                .replace('_', '-')
                .replace('--', '-')
            )
            nums = re.sub(r'-+', '-', nums)
            return f'{matched_type} {nums}'

        return matched_type if matched_type != 'UNKNOWN' else raw_text

    def extract_from_image(self, image_path):  # pragma: no cover
        """Crops image into zones and runs OCR."""
        img = cv2.imread(image_path)
        if img is None:
            return 'File not found or corrupt'

        h, w, _ = img.shape

        # Define crop zones
        zones = {
            'top': img[0 : int(h * 0.15), int(w * 0.05) : int(w * 0.95)],
            'bottom': img[int(h * 0.85) : h, int(w * 0.05) : int(w * 0.95)],
            'left': img[int(h * 0.05) : int(h * 0.95), 0 : int(w * 0.15)],
            'right': img[int(h * 0.05) : int(h * 0.95), int(w * 0.85) : w],
        }

        final_results = []
        for zone_name, crop in zones.items():
            # Rotate side labels to be horizontal for OCR
            if zone_name == 'left':
                crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
            elif zone_name == 'right':
                crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif zone_name == 'bottom':
                crop = cv2.rotate(crop, cv2.ROTATE_180)

            results = self.reader.readtext(crop, detail=0, paragraph=True)

            if results:
                for raw_string in results:
                    cleaned = self.clean_label_text(raw_string)
                    if any(s in cleaned for s in self.species_list):
                        if cleaned not in final_results:
                            final_results.append(cleaned)

        return ' | '.join(final_results) if final_results else 'No text detected'


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description='Extract species labels from seed images.'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='data/seed/images/val/',
        help='Path to image directory',
    )
    parser.add_argument(
        '--output',
        type=str,
        default='extracted_labels.csv',
        help='Path to save results',
    )
    parser.add_argument('--gpu', action='store_true', help='Use GPU for OCR')
    args = parser.parse_args()

    extractor = LabelExtractor(gpu=args.gpu)

    if not os.path.exists(args.input):
        print(f'Error: Path {args.input} does not exist.')
        return

    val_images = [
        f
        for f in os.listdir(args.input)
        if f.lower().endswith(('.jpg', '.png', '.jpeg'))
    ]
    all_labels = []

    print(f'Processing {len(val_images)} images...')

    for img_name in val_images:
        full_path = os.path.join(args.input, img_name)
        extracted = extractor.extract_from_image(full_path)

        all_labels.append({'image_name': img_name, 'extracted_text': extracted})
        print(f'Done: {img_name} -> {extracted}')

    # Export results
    df = pd.DataFrame(all_labels)
    df.to_csv(args.output, index=False)
    print(f'\nResults saved to {args.output}')


if __name__ == '__main__':
    main()
