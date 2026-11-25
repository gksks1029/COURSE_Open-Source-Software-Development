"""Admission startup retry tests; kubectl is mocked and never executed."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from admission import wait_admission

UNAVAILABLE = 'failed calling webhook "inferenceservice.defaulter": dial tcp 10.96.0.1:443: connect: connection refused'


class AdmissionTests(unittest.TestCase):
    def test_connection_refused_then_dry_run_succeeds(self):
        responses = [subprocess.CompletedProcess([], 1, "", UNAVAILABLE),
                     subprocess.CompletedProcess([], 0, "configured (server dry run)", "")]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempts.json"
            with patch("admission.subprocess.run", side_effect=responses) as run:
                wait_admission(Path("smoke.yaml"), output, timeout=1, interval=.001)
            self.assertEqual([item["returncode"] for item in json.loads(output.read_text())["attempts"]], [1, 0])
            for call in run.call_args_list:
                self.assertIn("--dry-run=server", call.args[0])
                self.assertIn("kind-kserve", call.args[0])

    def test_invalid_manifest_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempts.json"
            with patch("admission.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "Invalid value: malformed manifest")) as run:
                with self.assertRaisesRegex(RuntimeError, "malformed manifest"):
                    wait_admission(Path("smoke.yaml"), output, timeout=1, interval=.001)
            run.assert_called_once()

    def test_persistent_refusal_is_bounded_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempts.json"
            with patch("admission.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", UNAVAILABLE)):
                with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                    wait_admission(Path("smoke.yaml"), output, timeout=.025, interval=.005)
            self.assertTrue(json.loads(output.read_text())["attempts"])


if __name__ == "__main__":
    unittest.main()
