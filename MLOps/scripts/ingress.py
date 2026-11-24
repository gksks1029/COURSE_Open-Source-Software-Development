"""Bounded startup GET probes; never retry model POST requests."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


def wait_ingress(url, hostname, expected, output, timeout=180, interval=2):
    if timeout <= 0 or interval <= 0:
        raise ValueError("Probe timeout and interval must be positive")
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    attempts = []
    while time.monotonic() < deadline:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                  "status": 0, "body": "", "headers": {}, "error": ""}
        request = urllib.request.Request(url, headers={"Host": hostname, "Connection": "close"})
        remaining = max(.001, deadline - time.monotonic())
        try:
            with opener.open(request, timeout=min(5, remaining)) as response:
                record.update(status=response.status, body=response.read().decode(errors="replace"),
                              headers=dict(response.headers))
        except urllib.error.HTTPError as exc:
            with exc:
                record.update(status=exc.code, body=exc.read().decode(errors="replace"), headers=dict(exc.headers))
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            record["error"] = str(exc)
        attempts.append(record)
        output.write_text(json.dumps({"url": url, "hostname": hostname, "attempts": attempts}, indent=2) + "\n")
        if record["status"] == 200:
            if record["body"].strip() != expected:
                raise RuntimeError(f"HTTP 200 with unexpected body; see {output}")
            return record["body"].strip()
        if record["status"] not in (0, 404, 502, 503, 504):
            raise RuntimeError(f"Non-transient HTTP {record['status']}; see {output}")
        print(f"Ingress not ready: attempt={len(attempts)} HTTP={record['status']}; waiting for routing convergence", flush=True)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise RuntimeError(f"Ingress did not become ready within {timeout}s; see {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    response = wait_ingress(args.url, args.host, args.expected, args.output, args.timeout)
    print(f"PASS: KServe -> Knative -> Istio -> localhost:8080: {response}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
