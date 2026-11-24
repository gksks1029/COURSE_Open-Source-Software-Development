#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
source "${LAB2_ROOT}/environment/versions.env"
[[ "$(kubectl config current-context)" == kind-kserve ]] || {
  echo "Expected the isolated kind-kserve context." >&2
  exit 1
}
mkdir -p "${LAB2_ROOT}/.tools/upstream" "${LAB2_ROOT}/results/environment"
installer="${LAB2_ROOT}/.tools/upstream/quick_install.sh"
curl --fail --location --retry 3 --connect-timeout 20 \
  "https://raw.githubusercontent.com/kserve/kserve/${KSERVE_VERSION}/hack/quick_install.sh" \
  -o "${installer}"
printf '%s  %s\n' "${QUICK_INSTALL_SHA256}" "${installer}" | sha256sum --check
bash "${installer}" -s 2>&1 | tee "${LAB2_ROOT}/results/environment/install-platform.log"

kubectl wait --for=condition=Ready -n knative-serving \
  knativeserving/knative-serving --timeout=600s
for namespace in cert-manager istio-system knative-serving kserve; do
  for deployment in $(kubectl get deployment -n "${namespace}" -o name); do
    kubectl rollout status "${deployment}" -n "${namespace}" --timeout=300s
  done
done
kubectl create namespace lab2 --dry-run=client -o yaml | kubectl apply -f -
kubectl get clusterservingruntimes
