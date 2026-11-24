#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
[[ "$(kubectl config current-context)" == kind-kserve ]] || {
  echo "Expected the isolated kind-kserve context." >&2
  exit 1
}
kubectl wait --for=condition=Ready nodes --all --timeout=60s
for namespace in cert-manager istio-system knative-serving kserve; do
  for deployment in $(kubectl get deployment -n "${namespace}" -o name); do
    kubectl rollout status "${deployment}" -n "${namespace}" --timeout=120s
  done
done
kubectl wait --for=condition=Ready -n knative-serving \
  knativeserving/knative-serving --timeout=120s
kubectl wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s
kubectl top nodes
kubectl get clusterservingruntime kserve-sklearnserver kserve-mlserver kserve-huggingfaceserver
kubectl get namespace lab2
kubectl apply -f "${LAB2_ROOT}/environment/smoke-test.yaml"
kubectl wait --for=condition=Ready -n lab2 \
  inferenceservice/environment-smoke --timeout=300s
service_url="$(kubectl get isvc environment-smoke -n lab2 -o jsonpath='{.status.url}')"
service_hostname="${service_url#*://}"
service_hostname="${service_hostname%%/*}"
mkdir -p "${LAB2_ROOT}/results/environment"
probe_results="$(mktemp -d "${LAB2_ROOT}/results/environment/ingress-XXXXXXXX")"
printf 'Ingress probe results: %s\n' "${probe_results}"
# Ready conditions may predate a cluster restart. Probe the actual data path.
if ! python3 "${LAB2_ROOT}/scripts/ingress.py" \
  --url "${URL}/" --host "${service_hostname}" \
  --expected lab2-environment-ok --timeout 180 \
  --output "${probe_results}/attempts.json"; then
  kubectl get pods -n lab2 -o wide
  kubectl get endpoints -n lab2
  exit 1
fi
kubectl get nodes
kubectl get pods -A
kubectl get isvc -n lab2
