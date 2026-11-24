"""User-run Lab 2 steps. No sudo, package installation, or cluster deletion."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from traffic import post_json, revision_counts, run_traffic

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "sklearn-iris"
INGRESS = "http://127.0.0.1:8080"
LOG_TEMPLATE = ('{"lab2_run":"{{.Request.Header.Get "X-Lab2-Run"}}",'
                '"seq":"{{.Request.Header.Get "X-Lab2-Seq"}}",'
                '"revision":"{{.Revision.Name}}","code":{{.Response.Code}}}')


def command(*args, capture=False):
    result = subprocess.run([str(a) for a in args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def k(*args, namespace="lab2", capture=False):
    timeout = "0" if args[0] in ("wait", "rollout") else "30s"
    prefix = ["kubectl", "--context", "kind-kserve", "--request-timeout=" + timeout]
    if namespace:
        prefix += ["-n", namespace]
    return command(*prefix, *args, capture=capture)


def get(kind, name=None, namespace="lab2", selector=None):
    args = ["get", kind]
    if name:
        args += [name, "--ignore-not-found"]
    if selector:
        args += ["-l", selector]
    raw = k(*args, "-o", "json", namespace=namespace, capture=True)
    return json.loads(raw) if raw.strip() else None


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def results(stage):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ROOT / "results" / stage / f"{stamp}-{uuid4().hex[:8]}"
    path.mkdir(parents=True)
    print(f"Results: {path}", flush=True)
    return path


def wait_for(check, description, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(2)
    raise RuntimeError(f"Timed out: {description}")


def ready(obj):
    return any(c["type"] == "Ready" and c["status"] == "True"
               for c in obj.get("status", {}).get("conditions", []))


def predictor(obj):
    return obj.get("status", {}).get("components", {}).get("predictor", {})


def signature(spec):
    model = spec.get("model", {})
    return ([spec.get(key) for key in ("minReplicas", "maxReplicas", "scaleMetric", "scaleTarget", "containerConcurrency")]
            + [model.get(key) for key in ("storageUri", "protocolVersion", "runtime")])


def deploy(path, name, out, percentage=100):
    before = get("isvc", name)
    desired = json.loads(k("apply", "--dry-run=client", "-f", ROOT / path, "-o", "json", capture=True))
    old_revision = predictor(before or {}).get("latestReadyRevision")
    require_new = before is not None and signature(before["spec"]["predictor"]) != signature(desired["spec"]["predictor"])
    k("apply", "-f", ROOT / path)

    def reconciled():
        obj, child = get("isvc", name), get("ksvc", name + "-predictor")
        if not obj or not child or not ready(obj):
            return None
        status = child.get("status", {})
        latest = status.get("latestReadyRevisionName")
        if (not latest or latest != status.get("latestCreatedRevisionName")
                or status.get("observedGeneration", 0) < child["metadata"]["generation"]
                or (require_new and latest == old_revision)):
            return None
        traffic = status.get("traffic", [])
        total = sum(t.get("percent", 0) for t in traffic)
        latest_weight = sum(t.get("percent", 0) for t in traffic if t.get("revisionName") == latest)
        reported = predictor(obj).get("traffic", [])
        reported_total = sum(t.get("percent", 0) for t in reported)
        reported_weight = sum(t.get("percent", 0) for t in reported if t.get("revisionName") == latest)
        if (total != 100 or latest_weight != percentage
                or predictor(obj).get("latestReadyRevision") != latest
                or reported_total != 100 or reported_weight != percentage):
            return None
        return obj

    obj = wait_for(reconciled, f"{name}: Ready and latest revision traffic={percentage}%")
    save(out / f"{name}.json", obj)
    save(out / f"{name}-knative.json", get("ksvc", name + "-predictor"))
    k("get", "isvc", name)
    return obj


def endpoint(obj, protocol="v1"):
    hostname = urlsplit(obj["status"]["url"]).netloc
    name = obj["metadata"]["name"]
    suffix = f"/v1/models/{name}:predict" if protocol == "v1" else f"/v2/models/{name}/infer"
    return INGRESS + suffix, hostname


def resume():
    out = results("resume")
    limit = int(Path("/proc/sys/fs/inotify/max_user_instances").read_text())
    if limit < 512:
        raise RuntimeError(f"inotify instance limit is {limit}. Review README host settings first; this script never runs sudo.")
    running = command("podman", "inspect", "kserve-control-plane", "--format", "{{.State.Running}}", capture=True).strip()
    if running != "true":
        command("podman", "start", "kserve-control-plane")

    def api_ready():
        result = subprocess.run(["kubectl", "--context", "kind-kserve", "--request-timeout=3s", "get", "--raw=/readyz"],
                                text=True, capture_output=True)
        return result.returncode == 0 and result.stdout.strip() == "ok"

    wait_for(api_ready, "Kubernetes API ready after restart", 180)
    k("wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s", namespace="")
    release = json.loads(command("helm", "list", "--kube-context", "kind-kserve", "-n", "kserve", "--all", "-o", "json", capture=True))
    save(out / "helm.json", release)
    if not any(r["name"] == "kserve" and r["status"] == "deployed" for r in release):
        raise RuntimeError("KServe Helm release is not deployed. Use the targeted recovery instructions in README; do not reinstall the cluster.")
    k("rollout", "status", "deployment/istio-ingressgateway", "--timeout=180s", namespace="istio-system")
    command("bash", ROOT / "scripts/start-ingress.sh")
    # Give the asynchronous user service time to bind the socket.
    import socket

    def listening():
        try:
            with socket.create_connection(("127.0.0.1", 8080), timeout=1):
                return True
        except OSError:
            return False

    wait_for(listening, "localhost ingress listener", 30)
    command("bash", ROOT / "scripts/verify-environment.sh")
    (out / "status.txt").write_text("PASS: resumed cluster and environment smoke test\n")


def models():
    out = results("models")
    before = get("knativeserving", "knative-serving", "knative-serving")
    save(out / "knative-before.json", before)
    patch = {"spec": {"config": {"observability": {
        "logging.enable-request-log": "true", "logging.request-log-template": LOG_TEMPLATE}}}}
    k("patch", "knativeserving", "knative-serving", "--type=merge", "-p", json.dumps(patch), namespace="knative-serving")
    def logging_configured():
        data = (get("configmap", "config-observability", "knative-serving") or {}).get("data", {})
        return data.get("logging.request-log-template") == LOG_TEMPLATE and data.get("logging.enable-request-log") == "true"

    wait_for(logging_configured,
             "Knative request logging configuration", 120)
    source = (ROOT / "models/train.py").read_text()
    job = get("job", "lab2-build-iris")
    config = get("configmap", "lab2-model-builder")
    if job and (not config or config.get("data", {}).get("train.py") != source):
        raise RuntimeError("Existing model Job uses different source. Do not overwrite serving models; inspect the Job/PVC first.")
    k("apply", "-f", ROOT / "manifests/models/pvc.yaml")
    manifest = k("create", "configmap", "lab2-model-builder", "--from-file=" + str(ROOT / "models/train.py"), "--dry-run=client", "-o", "json", capture=True)
    path = out / "model-builder-configmap.json"
    path.write_text(manifest)
    k("apply", "-f", path)
    k("apply", "-f", ROOT / "manifests/models/job.yaml")
    k("wait", "--for=condition=Complete", "job/lab2-build-iris", "--timeout=600s")
    log = k("logs", "job/lab2-build-iris", capture=True)
    (out / "models.log").write_text(log)
    print(log)
    print("PASS: model Job completed; artifacts remain in PVC lab2-iris-models.")


def inference():
    out = results("inference")
    predictions = []
    for protocol, name in [("v1", SERVICE), ("v2", SERVICE + "-v2")]:
        obj = deploy(f"manifests/inference/iris-{protocol}.yaml", name, out)
        payload = json.loads((ROOT / f"inputs/iris-{protocol}.json").read_text())
        url, hostname = endpoint(obj, protocol)
        result = post_json(url, hostname, payload, uuid4().hex, 1, timeout=60)
        save(out / f"{protocol}-request.json", {"url": url, "host": hostname, "payload": payload})
        save(out / f"{protocol}-response.json", result)
        if not result["ok"]:
            raise RuntimeError(f"{protocol} request failed: {result}")
        response = json.loads(result["body"])
        if protocol == "v1":
            values = response["predictions"]
        else:
            if response.get("model_name") != name or len(response.get("outputs", [])) != 1:
                raise RuntimeError("Unexpected V2 response model/outputs")
            output = response["outputs"][0]
            if math.prod(output["shape"]) != 2:
                raise RuntimeError("Unexpected V2 output shape")
            values = output["data"]
            if values and isinstance(values[0], list):
                values = [value for row in values for value in row]
        if values != [1, 1]:
            raise RuntimeError(f"Unexpected {protocol} predictions: {values}")
        predictions.append(values)
        print(f"PASS: {protocol} HTTP 200\n{json.dumps(response, indent=2)}", flush=True)
    if predictions[0] != predictions[1]:
        raise RuntimeError("V1/V2 protocol predictions differ")


def collect_counts(out, run_id, successful, allowed):
    def collect():
        logs = []
        for revision in allowed:
            pods = get("pods", selector=f"serving.knative.dev/revision={revision}")["items"]
            for pod in pods:
                name = pod["metadata"]["name"]
                log = k("logs", name, "-c", "queue-proxy", capture=True)
                (out / f"{name}-queue.log").write_text(log)
                logs.append(log)
        try:
            return revision_counts("\n".join(logs), run_id, successful, allowed)
        except ValueError as exc:
            (out / "log-attribution-error.txt").write_text(str(exc))
            return None
    return wait_for(collect, "queue-proxy logs match all successful client request IDs", 45)


def canary(promote=False):
    out = results("promotion" if promote else "canary")
    before = get("isvc", SERVICE)
    if not before:
        raise RuntimeError("Run inference before canary")
    current = before["spec"]["predictor"]
    if promote:
        if current.get("canaryTrafficPercent") != 20:
            raise RuntimeError("Promotion requires the completed 20% canary stage")
    elif not (current["model"]["storageUri"] == "pvc://lab2-iris-models/v1" or
              (current["model"]["storageUri"] == "pvc://lab2-iris-models/v2" and current.get("canaryTrafficPercent") == 20)):
        raise RuntimeError("Canary requires baseline model v1 or an existing 20% canary; do not restart over promoted/autoscaling state")
    previous = predictor(before)["latestReadyRevision"]
    if not promote and current.get("canaryTrafficPercent") == 20:
        traffic = get("ksvc", SERVICE + "-predictor").get("status", {}).get("traffic", [])
        previous = next((t["revisionName"] for t in traffic if t.get("percent") == 80), None)
        if not previous:
            raise RuntimeError("Existing 20% canary has no stable 80% revision")
    obj = deploy("manifests/canary/promote.yaml" if promote else "manifests/canary/20-percent.yaml",
                 SERVICE, out, 100 if promote else 20)
    latest = predictor(obj)["latestReadyRevision"]
    allowed = [latest] if promote else [previous, latest]
    if not promote and previous == latest:
        raise RuntimeError("Canary did not create a distinct revision")
    payload = json.loads((ROOT / "inputs/iris-v1.json").read_text())
    url, hostname = endpoint(obj)
    run_id = uuid4().hex
    stats = run_traffic(url, hostname, payload, run_id, out / "requests.csv", count=100 if promote else 1000, workers=4)
    save(out / "client.json", stats)
    counts = collect_counts(out, run_id, stats["success_sequences"], allowed)
    total = sum(counts.values())
    share = counts[latest] / total if total else 0
    expected = 1 if promote else .2
    passed = stats["failed"] == 0 and total == stats["total"]
    if promote:
        passed = passed and share == 1
    else:
        tolerance = 4 * math.sqrt(.2 * .8 / max(total, 1))
        passed = passed and all(counts.values()) and abs(share - expected) <= tolerance
    summary = {"run_id": run_id, "expected_latest_percent": expected * 100,
               "counts_by_revision": counts, "latest_revision": latest,
               "measured_latest_percent": round(share * 100, 2),
               "total": stats["total"], "failed": stats["failed"], "passed": passed}
    save(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    if not passed:
        raise RuntimeError("Traffic attribution/split check failed; inspect saved results")
    print("PASS: promotion traffic" if promote else "PASS: actual canary request counts by revision")


def sample_scale(revision):
    deployments = get("deployments", selector=f"serving.knative.dev/revision={revision}")["items"]
    autoscaler = get("kpa", revision) or {}
    return {
        "desired": sum(d["spec"].get("replicas", 0) for d in deployments),
        "ready": sum(d.get("status", {}).get("readyReplicas", 0) for d in deployments),
        "kpa_desired": autoscaler.get("status", {}).get("desiredScale", 0),
        "kpa_actual": autoscaler.get("status", {}).get("actualScale", 0),
    }


def autoscale():
    out = results("autoscaling")
    before = get("isvc", SERVICE)
    if not before or before["spec"]["predictor"]["model"]["storageUri"] != "pvc://lab2-iris-models/v2" or before["spec"]["predictor"].get("canaryTrafficPercent") is not None:
        raise RuntimeError("Finish canary promotion to model v2 before autoscaling")
    obj = deploy("manifests/autoscaling/iris.yaml", SERVICE, out)
    revision = predictor(obj)["latestReadyRevision"]
    wait_for(lambda: sample_scale(revision)["ready"] == 1, "single replica baseline", 180)
    payload = {"instances": json.loads((ROOT / "inputs/iris-v1.json").read_text())["instances"] * 128}
    save(out / "load-input.json", payload)
    url, hostname = endpoint(obj)
    stop = threading.Event()
    peak = 1
    last = {}
    with (out / "replicas.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "phase", "revision", "desired", "ready", "kpa_desired", "kpa_actual"])
        writer.writeheader()

        def sample(phase):
            nonlocal peak, last
            last = sample_scale(revision)
            if phase == "load":
                peak = max(peak, last["ready"])
            writer.writerow({"timestamp": datetime.now(timezone.utc).isoformat(), "phase": phase, "revision": revision, **last})
            stream.flush()
            print(f"{phase:8} ready={last['ready']} desired={last['desired']} kpa={last['kpa_desired']}", flush=True)

        for _ in range(3):
            sample("baseline")
            time.sleep(5)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_traffic, url, hostname, payload, uuid4().hex,
                                     out / "requests.csv", duration=120, workers=16, stop_event=stop)
            try:
                while not future.done():
                    sample("load")
                    time.sleep(5)
                stats = future.result()
            finally:
                stop.set()
        save(out / "load-summary.json", {key: value for key, value in stats.items() if key != "success_sequences"})
        started = time.monotonic()
        while time.monotonic() - started < 180:
            sample("cooldown")
            if time.monotonic() - started >= 60 and last["ready"] == last["desired"] == last["kpa_desired"] == 1:
                break
            time.sleep(5)
    passed = peak >= 2 and last.get("ready") == last.get("desired") == last.get("kpa_desired") == 1 and stats["successful"] > 0 and stats["failed"] == 0
    summary = {"revision": revision, "peak_ready_during_load": peak,
               "final": last, "requests": stats["total"], "failed": stats["failed"], "passed": passed}
    save(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    if not passed:
        raise RuntimeError("Autoscaling check failed. Inspect requests.csv and replicas.csv; do not claim success from desired replicas alone.")
    print("PASS: ready replicas increased under load and returned to one")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["resume", "models", "inference", "canary", "promote", "autoscale"])
    args = parser.parse_args()
    if os.environ.get("KUBECONFIG") != str(ROOT / ".state/kubeconfig"):
        parser.error("Use bash scripts/lab.sh <step> to select the isolated environment")
    if command("kubectl", "config", "current-context", capture=True).strip() != "kind-kserve":
        parser.error("Expected kind-kserve context")
    functions = {"resume": resume, "models": models, "inference": inference,
                 "canary": canary, "promote": lambda: canary(promote=True), "autoscale": autoscale}
    functions[args.step]()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted: traffic workers stop after their current request; cluster is preserved.", file=sys.stderr)
        sys.exit(130)
