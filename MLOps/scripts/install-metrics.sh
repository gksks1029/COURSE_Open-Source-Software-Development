#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
source "${LAB2_ROOT}/environment/versions.env"
[[ "$(kubectl config current-context)" == kind-kserve ]] || {
  echo "Expected the isolated kind-kserve context." >&2
  exit 1
}
mkdir -p "${LAB2_ROOT}/.tools/upstream"
manifest="${LAB2_ROOT}/.tools/upstream/metrics-server-components.yaml"
curl --fail --location --retry 3 --connect-timeout 20 \
  "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER_VERSION}/components.yaml" \
  -o "${manifest}"
printf '%s  %s\n' "${METRICS_SERVER_SHA256}" "${manifest}" | sha256sum --check
# kind kubelet certificates do not have an IP SAN. This exception is lab-only.
python3 - "${manifest}" "${manifest%.yaml}-kind.yaml" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
anchor = '        - --kubelet-use-node-status-port\n'
if source.count(anchor) != 1:
    raise SystemExit('Unexpected metrics-server manifest arguments')
Path(sys.argv[2]).write_text(source.replace(anchor, anchor + '        - --kubelet-insecure-tls\n'))
PY
kubectl apply -f "${manifest%.yaml}-kind.yaml"
kubectl rollout status deployment/metrics-server -n kube-system --timeout=300s
kubectl wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s
kubectl top nodes
