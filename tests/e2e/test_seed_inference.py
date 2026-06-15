"""End-to-end seed-detector inference smoke test.

Marked e2e (auto, by directory) and skipped unless AEA_E2E_SEED_WEIGHTS points
at a real checkpoint. Run with:

    AEA_E2E_SEED_WEIGHTS=/path/to/seed.pt pytest -m e2e tests/e2e

The model is built directly with device='cpu' rather than via helpers.load_model,
which pins device=0 (GPU). run_inference is the real SAHI sliced-prediction path.
"""


def test_seed_detector_runs_inference(seed_weights, sample_image):
    # Lazy imports so sahi/ultralytics only load when this test actually runs.
    from sahi import AutoDetectionModel

    from ml_pipelines.seed_src.inference.inference import run_inference

    model = AutoDetectionModel.from_pretrained(
        model_type='ultralytics',
        model_path=str(seed_weights),
        confidence_threshold=0.3,
        device='cpu',
    )
    result = run_inference(str(sample_image), model)

    assert hasattr(result, 'object_prediction_list')
    assert isinstance(result.object_prediction_list, list)
