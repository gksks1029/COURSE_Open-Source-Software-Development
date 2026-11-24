"""Offline checks: local HTTP fixture only; never contact Kubernetes."""
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from traffic import check_predictions, post_json, revision_counts, run_traffic
from ingress import wait_ingress


class Handler(BaseHTTPRequestHandler):
    records = []

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/warming":
            self.server.warm_attempts = getattr(self.server, "warm_attempts", 0) + 1
        status = 200
        if self.path == "/unavailable" or (self.path == "/warming" and self.server.warm_attempts <= 2):
            status = 503
        elif self.path == "/forbidden":
            status = 403
        body = b"wrong service\n" if self.path == "/wrong" else b"lab2-environment-ok\n"
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.records.append((self.headers["Host"], self.headers["X-Lab2-Run"], self.headers["X-Lab2-Seq"], body))
        if self.path == "/slow":
            time.sleep(.15)
        response = b'not json' if self.path == "/malformed" else json.dumps({"predictions": [1] * len(body["instances"])}).encode()
        self.send_response(503 if self.path == "/error" else 200)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            pass


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_bounded_count_and_request_identity(self):
        Handler.records.clear()
        payload = {"instances": [[6.8, 2.8, 4.8, 1.4]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requests.csv"
            result = run_traffic(self.url, "iris.lab2.example.com", payload, "count-run", path, count=12, workers=3)
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["success_sequences"], list(range(1, 13)))
        self.assertEqual(len(rows), 12)
        self.assertEqual({record[2] for record in Handler.records}, {str(i) for i in range(1, 13)})
        self.assertTrue(all(record[0] == "iris.lab2.example.com" and record[1] == "count-run" and record[3] == payload for record in Handler.records))

    def test_http_failure_invalid_body_and_timeout_are_not_success(self):
        payload = {"instances": [[1, 2, 3, 4]]}
        failed = post_json(self.url + "/error", "iris", payload, "run", 1)
        malformed = check_predictions(post_json(self.url + "/malformed", "iris", payload, "run", 2), 1)
        timed_out = post_json(self.url + "/slow", "iris", payload, "run", 3, timeout=.03)
        self.assertEqual(failed["status"], 503)
        self.assertFalse(failed["ok"])
        self.assertFalse(malformed["ok"])
        self.assertFalse(timed_out["ok"])
        self.assertTrue(timed_out["error"])

    def test_duration_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            start = time.monotonic()
            result = run_traffic(self.url, "iris", {"instances": [[1, 2, 3, 4]]}, "duration-run",
                                 Path(directory) / "requests.csv", duration=.1, workers=2)
        self.assertGreater(result["successful"], 0)
        self.assertLess(time.monotonic() - start, 3)

    def test_opener_is_constructed_once_per_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("traffic.urllib.request.build_opener", wraps=urllib.request.build_opener) as build:
                result = run_traffic(self.url, "iris", {"instances": [[1, 2, 3, 4]]}, "reuse-run",
                                     Path(directory) / "requests.csv", count=24, workers=3)
        self.assertEqual(result["successful"], 24)
        self.assertEqual(build.call_count, 3)

    def test_ingress_waits_for_503_to_clear(self):
        self.server.warm_attempts = 0
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe.json"
            response = wait_ingress(self.url + "/warming", "iris", "lab2-environment-ok", output, timeout=1, interval=.01)
            statuses = [attempt["status"] for attempt in json.loads(output.read_text())["attempts"]]
        self.assertEqual(response, "lab2-environment-ok")
        self.assertEqual(statuses, [503, 503, 200])

    def test_ingress_persistent_503_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe.json"
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                wait_ingress(self.url + "/unavailable", "iris", "lab2-environment-ok", output, timeout=.06, interval=.01)
            self.assertLess(time.monotonic() - started, 1)
            self.assertTrue(json.loads(output.read_text())["attempts"])

    def test_ingress_wrong_body_and_403_fail_without_retry(self):
        for path in ("/wrong", "/forbidden"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "probe.json"
                with self.assertRaises(RuntimeError):
                    wait_ingress(self.url + path, "iris", "lab2-environment-ok", output, timeout=1, interval=.01)
                self.assertEqual(len(json.loads(output.read_text())["attempts"]), 1)


class AttributionTests(unittest.TestCase):
    def line(self, run="run", seq=1, revision="old", code=200):
        return json.dumps({"lab2_run": run, "seq": str(seq), "revision": revision, "code": code})

    def test_only_matching_successes_are_counted_by_revision(self):
        logs = "\n".join(["not JSON", self.line(run="other"), self.line(), self.line(seq=2, revision="new"), self.line(seq=3, code=503)])
        self.assertEqual(revision_counts(logs, "run", [1, 2], ["old", "new"]), {"old": 1, "new": 1})

    def test_missing_duplicate_and_unexpected_revision_fail(self):
        cases = [self.line(), self.line() + "\n" + self.line(), self.line(revision="unknown")]
        for logs in cases:
            with self.subTest(logs=logs), self.assertRaises(ValueError):
                revision_counts(logs, "run", [1, 2], ["old", "new"])


if __name__ == "__main__":
    unittest.main()
