#!/usr/bin/env bash
# Source this file to select the isolated Lab 2 tools and kubeconfig.
LAB2_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export LAB2_ROOT
export PATH="${LAB2_ROOT}/.tools/bin:${PATH}"
export KUBECONFIG="${LAB2_ROOT}/.state/kubeconfig"
export HELM_CONFIG_HOME="${LAB2_ROOT}/.state/helm/config"
export HELM_CACHE_HOME="${LAB2_ROOT}/.state/helm/cache"
export HELM_DATA_HOME="${LAB2_ROOT}/.state/helm/data"
export KIND_EXPERIMENTAL_PROVIDER=podman
export CONTAINERS_CONF_OVERRIDE="${LAB2_ROOT}/environment/containers.conf"
export INGRESS_HOST=localhost
export INGRESS_PORT=8080
export URL="http://${INGRESS_HOST}:${INGRESS_PORT}"
