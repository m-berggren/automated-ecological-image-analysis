"""Unit tests for LabelExtractor.clean_label_text.

The module imports easyocr and __init__ builds an easyocr.Reader (downloads
model weights). easyocr.Reader is stubbed so __init__ runs against the real
species/type maps without the download, and only the pure OCR-cleaning regex
logic is exercised.
"""

import pytest


@pytest.fixture
def extractor(load_leaf, monkeypatch):
    module = load_leaf('seed_src/utils/label_extractor.py')
    monkeypatch.setattr(module.easyocr, 'Reader', lambda *args, **kwargs: None)
    return module.LabelExtractor(gpu=False)


class TestCleanLabelText:
    def test_canonical_species_and_dashed_number(self, extractor):
        assert extractor.clean_label_text('PHYCA 12-34') == 'PHYCA 12-34'

    def test_alias_maps_to_canonical_species(self, extractor):
        # 'VAV' is an OCR alias for 'VAU'; dot separator normalises to a dash.
        assert extractor.clean_label_text('VAV 10.20') == 'VAU 10-20'

    def test_spaces_inside_number_are_stripped(self, extractor):
        assert extractor.clean_label_text('phy 5 6') == 'PHYCA 56'

    def test_species_without_number_returns_species(self, extractor):
        assert extractor.clean_label_text('CAT') == 'CAT'

    def test_unrecognized_text_passed_through(self, extractor):
        assert extractor.clean_label_text('zzz') == 'ZZZ'
