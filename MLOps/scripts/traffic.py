"""Bounded HTTP traffic generation using only the Python standard library."""
import csv
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone


def post_json(url, hostname, payload, run_id, sequence, timeout=15, opener=None):
    request = urllib.request.Request(
        url, data=payload if isinstance(payload, bytes) else json.dumps(payload).encode(), method="POST",
        headers={"Host": hostname, "Content-Type": "application/json",
                 "Connection": "close", "X-Lab2-Run": run_id,
                 "X-Lab2-Seq": str(sequence)},
    )
    started = time.monotonic()
    status, body, error = 0, "", ""
    try:
        # These requests always target the local ingress, never an HTTP proxy.
        if opener is None:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            status, body = response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        with exc:
            status, body, error = exc.code, exc.read().decode(errors="replace"), str(exc)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        error = str(exc)
    result = {"seq": sequence, "status": status, "body": body, "error": error,
              "latency_ms": round((time.monotonic() - started) * 1000, 3)}
    result["ok"] = status == 200 and not error
    return result


def check_predictions(result, expected_size):
    if result["ok"]:
        try:
            predictions = json.loads(result["body"])["predictions"]
            if len(predictions) != expected_size or any(p not in (0, 1, 2) for p in predictions):
                raise ValueError("Unexpected Iris predictions")
        except (KeyError, TypeError, ValueError) as exc:
            result["ok"], result["error"] = False, str(exc)
    return result


def run_traffic(url, hostname, payload, run_id, output, *, count=None,
                duration=None, workers=4, stop_event=None):
    """Use either a finite count or duration; never retry a failed POST."""
    if (count is None) == (duration is None):
        raise ValueError("Specify exactly one of count and duration")
    if not 1 <= workers <= 32 or (count is not None and count < 1) or (duration is not None and duration <= 0):
        raise ValueError("Invalid traffic limits")
    stop_event = stop_event or threading.Event()
    encoded_payload = json.dumps(payload).encode()
    deadline = time.monotonic() + duration if duration is not None else None
    lock = threading.Lock()
    next_seq = 0
    successes, errors, latencies = set(), [], []
    started_at = datetime.now(timezone.utc).isoformat()
    with open(output, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["seq", "status", "ok", "latency_ms", "error"])
        writer.writeheader()

        def worker():
            nonlocal next_seq
            # Opener construction creates a TLS context even for HTTP on some
            # Python versions. Pay this cost once per worker, not per request.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while not stop_event.is_set():
                with lock:
                    if (count is not None and next_seq >= count) or (deadline is not None and time.monotonic() >= deadline):
                        return
                    next_seq += 1
                    sequence = next_seq
                result = check_predictions(post_json(url, hostname, encoded_payload, run_id, sequence, opener=opener), len(payload["instances"]))
                with lock:
                    writer.writerow({key: result[key] for key in writer.fieldnames})
                    if result["ok"]:
                        successes.add(sequence)
                    else:
                        errors.append({key: result[key] for key in ("seq", "status", "error")})
                    latencies.append(result["latency_ms"])
                    stream.flush()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker) for _ in range(workers)]
            try:
                for future in futures:
                    future.result()
            except BaseException:
                stop_event.set()
                raise
    ordered = sorted(latencies)
    return {
        "run_id": run_id, "started_at": started_at, "total": next_seq,
        "successful": len(successes), "failed": len(errors), "errors": errors[:20],
        "latency_p50_ms": ordered[len(ordered) // 2] if ordered else None,
        "latency_p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * .95))] if ordered else None,
        "success_sequences": sorted(successes),
    }


def revision_counts(logs, run_id, successful_sequences, allowed_revisions):
    """Attribute successful requests using queue-proxy logs, not model outputs."""
    seen = {}
    for line in logs.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("lab2_run") != run_id or record.get("code") != 200:
            continue
        sequence, revision = int(record["seq"]), record["revision"]
        if revision not in allowed_revisions:
            raise ValueError(f"Unexpected revision: {revision}")
        if sequence in seen:
            raise ValueError(f"Duplicate successful request sequence: {sequence}")
        seen[sequence] = revision
    if set(seen) != set(successful_sequences):
        raise ValueError(f"Client/server request mismatch: client={len(successful_sequences)}, logs={len(seen)}")
    return {revision: list(seen.values()).count(revision) for revision in allowed_revisions}
