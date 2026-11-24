#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
exec python3 "${LAB2_ROOT}/scripts/lab.py" "$@"
