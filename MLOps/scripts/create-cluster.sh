#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
source "${LAB2_ROOT}/environment/versions.env"
umask 077
mkdir -p "${LAB2_ROOT}/.state"
if kind get clusters | rg -qx kserve; then
  kind export kubeconfig --name kserve --kubeconfig "${KUBECONFIG}"
else
  systemd-run --scope --user -p Delegate=yes \
    kind create cluster --name kserve \
    --image "${KIND_NODE_IMAGE}" \
    --config "${LAB2_ROOT}/environment/kind-config.yaml" \
    --kubeconfig "${KUBECONFIG}" --wait 180s --retain
fi
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl get nodes -o wide
