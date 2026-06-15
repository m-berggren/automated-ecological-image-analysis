"""End-to-end YOLO inference smoke test.

Marked e2e (auto, by directory) and skipped unless AEA_E2E_YOLO_WEIGHTS points
at a real checkpoint. Run with:

    AEA_E2E_YOLO_WEIGHTS=/path/to/yolo.pt pytest -m e2e tests/e2e
"""


def test_yolo_detector_runs_inference(yolo_weights, sample_image):
    # Imported lazily so the heavy ultralytics/sahi import only happens when
    # the weights are present and this test actually runs.
    from ml_pipelines.pollinator.detection.yolo_detector import YoloDetector

    detector = YoloDetector(
        checkpoint_path=str(yolo_weights), device='cpu', use_sahi=False
    )
    results = detector.predict(str(sample_image))

    assert isinstance(results, list)
    for det in results:
        assert {'x1', 'y1', 'x2', 'y2', 'class', 'confidence'} <= set(det)
