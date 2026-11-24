#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
exec kubectl --context kind-kserve -n istio-system port-forward \
  --address 127.0.0.1 svc/istio-ingressgateway 8080:80
