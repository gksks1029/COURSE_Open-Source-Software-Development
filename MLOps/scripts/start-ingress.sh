#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
if systemctl --user is-active --quiet kserve-lab2-ingress.service; then
  echo "kserve-lab2-ingress.service is already running."
  exit 0
fi
systemd-run --user --unit=kserve-lab2-ingress --collect \
  --property=Restart=on-failure --property=RestartSec=3 \
  /usr/bin/bash "${LAB2_ROOT}/scripts/port-forward.sh"
