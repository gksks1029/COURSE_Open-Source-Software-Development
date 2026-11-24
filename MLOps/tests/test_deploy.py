"""Regression fixture uses real Knative Service status field names."""
import json
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lab


class DeployTests(unittest.TestCase):
    def test_promotion_waits_for_inferenceservice_traffic_to_catch_up(self):
        revision = "iris-predictor-00002"
        stale = {"status": {"conditions": [{"type": "Ready", "status": "True"}],
                            "components": {"predictor": {
                                "latestReadyRevision": revision,
                                "traffic": [{"revisionName": "iris-predictor-00001", "percent": 80},
                                            {"revisionName": revision, "percent": 20}],
                            }}}}
        current = copy.deepcopy(stale)
        current["status"]["components"]["predictor"]["traffic"] = [{"revisionName": revision, "percent": 100}]
        child = {"metadata": {"generation": 2}, "status": {
            "observedGeneration": 2, "latestReadyRevisionName": revision,
            "latestCreatedRevisionName": revision,
            "traffic": [{"revisionName": revision, "percent": 100}],
        }}
        desired = {"spec": {"predictor": {}}}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(lab, "get", side_effect=[None, stale, child, current, child, child]), \
                 patch.object(lab, "k", side_effect=[json.dumps(desired), None, None]), \
                 patch.object(lab.time, "sleep") as sleep:
                result = lab.deploy("fixture.yaml", "iris", Path(directory))
            self.assertEqual(result, current)
            sleep.assert_called_once_with(2)

    def test_ready_knative_service_uses_revision_name_fields(self):
        revision = "iris-predictor-00001"
        isvc = {"status": {"conditions": [{"type": "Ready", "status": "True"}],
                           "components": {"predictor": {"latestReadyRevision": revision,
                                "traffic": [{"revisionName": revision, "percent": 100}]}}}}
        ksvc = {"metadata": {"generation": 1}, "status": {
            "observedGeneration": 1,
            "latestReadyRevisionName": revision,
            "latestCreatedRevisionName": revision,
            "traffic": [{"revisionName": revision, "percent": 100}],
        }}
        desired = {"spec": {"predictor": {}}}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(lab, "get", side_effect=[None, isvc, ksvc, ksvc]), \
                 patch.object(lab, "k", side_effect=[json.dumps(desired), None, None]):
                result = lab.deploy("fixture.yaml", "iris", Path(directory))
            self.assertEqual(result, isvc)
            saved = json.loads((Path(directory) / "iris-knative.json").read_text())
            self.assertEqual(saved["status"]["latestReadyRevisionName"], revision)


if __name__ == "__main__":
    unittest.main()
