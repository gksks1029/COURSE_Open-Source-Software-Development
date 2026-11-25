#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
ingress_script="${LAB2_ROOT}/scripts/port-forward.sh"
configured_command="$(systemctl --user show kserve-lab2-ingress.service --property=ExecStart --value 2>/dev/null || true)"
if systemctl --user is-active --quiet kserve-lab2-ingress.service \
  && [[ "${configured_command}" == *"${ingress_script}"* ]]; then
  echo "kserve-lab2-ingress.service is already running."
  exit 0
fi
if [[ -n "${configured_command}" ]]; then
  echo "Replacing the existing ingress service with the current lab path."
  systemctl --user stop kserve-lab2-ingress.service
fi
systemd-run --user --unit=kserve-lab2-ingress --collect \
  --property=Restart=on-failure --property=RestartSec=3 \
  /usr/bin/bash "${ingress_script}"
