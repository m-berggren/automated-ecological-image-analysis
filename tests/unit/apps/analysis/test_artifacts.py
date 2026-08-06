"""Unit tests for the pure parsers in apps.analysis.artifacts.

classify_artifact + the args.yaml / results.csv / results.json extractors are
all text-in, dict-out. The DB-writing ingest_run_dir is integration territory.
"""

from apps.analysis.artifacts import (
    classify_artifact,
    metrics_from_results_csv,
    metrics_from_results_json,
    params_from_args_yaml,
)
from apps.analysis.models import ModelArtifactKind


class TestClassifyArtifact:
    def test_known_name(self):
        assert classify_artifact('F1_curve.png') == (ModelArtifactKind.F1_CURVE, '')

    def test_normalized_confusion_matrix_gets_caption(self):
        kind, caption = classify_artifact('confusion_matrix_normalized.png')
        assert kind == ModelArtifactKind.CONFUSION_MATRIX
        assert caption == 'normalized'

    def test_sample_prediction_prefix(self):
        kind, caption = classify_artifact('val_batch0_pred.jpg')
        assert kind == ModelArtifactKind.SAMPLE_PREDICTIONS
        assert caption == 'val_batch0_pred.jpg'

    def test_unknown(self):
        assert classify_artifact('random.txt') == (None, '')


class TestParamsFromArgsYaml:
    def test_picks_prefixed_hyperparameters(self):
        text = 'epochs: 20\nimgsz: 640\nmodel: yolov8n.pt\nlr0: 0.01\n'
        params = params_from_args_yaml(text)
        assert params == {'yolo_epochs': 20, 'yolo_imgsz': 640, 'yolo_lr0': 0.01}

    def test_non_mapping_returns_empty(self):
        assert params_from_args_yaml('- a\n- b\n') == {}

    def test_malformed_returns_empty(self):
        assert params_from_args_yaml('a: : :\n  - broken') == {}


class TestMetricsFromResultsCsv:
    def test_extracts_final_epoch_box_metrics(self):
        text = (
            'epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n'
            '1,0.5,0.4,0.45,0.30\n'
            '2,0.8,0.7,0.75,0.60\n'
        )
        assert metrics_from_results_csv(text) == {
            'precision': 0.8,
            'recall': 0.7,
            'mAP50': 0.75,
            'mAP50-95': 0.60,
        }

    def test_empty_returns_empty(self):
        assert metrics_from_results_csv('') == {}


class TestMetricsFromResultsJson:
    def test_maps_classifier_keys(self):
        text = '{"test_acc": 0.92, "test_f1": 0.9, "test_recall": 0.88}'
        assert metrics_from_results_json(text) == {
            'accuracy': 0.92,
            'f1': 0.9,
            'recall': 0.88,
        }

    def test_bool_is_not_treated_as_number(self):
        # True is an int subclass; pick() must reject it.
        assert metrics_from_results_json('{"test_acc": true}') == {}

    def test_malformed_returns_empty(self):
        assert metrics_from_results_json('not json') == {}
