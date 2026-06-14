"""Unit tests for ml_pipelines.seed_src.inference.confidence_analyzer."""

import pytest


@pytest.fixture(scope='session')
def analyzer(load_leaf):
    return load_leaf('seed_src/inference/confidence_analyzer.py')


def test_no_predictions_returns_zeroed_result(analyzer):
    result = analyzer.analyze_seed_confidence([])
    assert result['total_count'] == 0
    assert result['overall_confidence'] == 0.0
    assert result['estimated_range'] == (0, 0)
    assert result['high_risk_flag'] is False
    assert 'reason' in result


def test_high_confidence_is_not_flagged(analyzer):
    preds = [{'conf': 1.0}, {'conf': 1.0}]
    result = analyzer.analyze_seed_confidence(preds, risk_threshold=0.20)
    assert result['total_count'] == 2
    assert result['overall_confidence'] == 1.0
    assert result['estimated_range'] == (2, 2)
    assert result['high_risk_flag'] is False


def test_low_confidence_widens_range_and_flags_risk(analyzer):
    preds = [{'conf': 0.5}, {'conf': 0.5}]
    result = analyzer.analyze_seed_confidence(preds, risk_threshold=0.20)
    # uncertainty 0.5 -> error_margin 1.0 -> range [1, 3].
    assert result['estimated_range'] == (1, 3)
    assert result['high_risk_flag'] is True


def test_missing_conf_defaults_to_zero(analyzer):
    result = analyzer.analyze_seed_confidence([{}])
    assert result['overall_confidence'] == 0.0
    assert result['estimated_range'] == (0, 2)
    assert result['high_risk_flag'] is True
