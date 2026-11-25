"""Wait for KServe admission using a server-side dry run, without storing changes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


def transient_webhook_error(message):
    message = message.lower()
    return ("failed calling webhook" in message or "failed to call webhook" in message) and any(
        reason in message for reason in (
            "connection refused", "no endpoints available", "context deadline exceeded",
            "i/o timeout", "tls handshake timeout",
        )
    )


def wait_admission(manifest, output, timeout=180, interval=2):
    if timeout <= 0 or interval <= 0:
        raise ValueError("Probe timeout and interval must be positive")
    deadline = time.monotonic() + timeout
    attempts = []
    command = ["kubectl", "--context", "kind-kserve", "--request-timeout=10s", "-n", "lab2",
               "apply", "--dry-run=server", "-f", str(manifest)]
    while time.monotonic() < deadline:
        record = {"timestamp": datetime.now(timezone.utc).isoformat()}
        try:
            result = subprocess.run(command, text=True, capture_output=True,
                                    timeout=min(15, max(.001, deadline - time.monotonic())))
            record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            retry = transient_webhook_error(result.stderr)
        except subprocess.TimeoutExpired:
            record.update(returncode=None, stdout="", stderr="Admission dry-run command timed out")
            retry = True
        attempts.append(record)
        output.write_text(json.dumps({"manifest": str(manifest), "attempts": attempts}, indent=2) + "\n")
        if record["returncode"] == 0:
            print("PASS: KServe admission webhook accepted server-side dry run", flush=True)
            return
        if not retry:
            raise RuntimeError(f"Admission dry run failed: {record['stderr'].strip()}; see {output}")
        print(f"KServe admission not ready: attempt={len(attempts)}; waiting for webhook connectivity", flush=True)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise RuntimeError(f"KServe admission did not become ready within {timeout}s; see {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    wait_admission(args.manifest, args.output, args.timeout)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
