#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
source "${LAB2_ROOT}/environment/versions.env"

[[ "$(uname -s)-$(uname -m)" == Linux-x86_64 ]] || {
  echo "This installer requires Linux x86_64." >&2
  exit 1
}
mkdir -p "${LAB2_ROOT}/.tools/bin" "${LAB2_ROOT}/.tools/downloads"
cd "${LAB2_ROOT}/.tools/downloads"
fetch() { curl --fail --location --retry 3 --connect-timeout 20 -o "$2" "$1"; }

fetch "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64" kind-linux-amd64
fetch "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64.sha256sum" kind-linux-amd64.sha256sum
sha256sum --check kind-linux-amd64.sha256sum
install -m 755 kind-linux-amd64 ../bin/kind

fetch "https://dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/amd64/kubectl" kubectl
fetch "https://dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/amd64/kubectl.sha256" kubectl.sha256
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check
install -m 755 kubectl ../bin/kubectl

archive="helm-${HELM_VERSION}-linux-amd64.tar.gz"
fetch "https://get.helm.sh/${archive}" "${archive}"
fetch "https://get.helm.sh/${archive}.sha256sum" "${archive}.sha256sum"
sha256sum --check "${archive}.sha256sum"
tar -xzf "${archive}" linux-amd64/helm
install -m 755 linux-amd64/helm ../bin/helm

kind version
kubectl version --client
helm version --short
