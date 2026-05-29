#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-enable}"
python - "$ACTION" <<'PY'
import sys
from app.services import firewall

action = sys.argv[1]
if action == "enable":
    result = firewall.enable_nat(firewall.get_nat())
elif action == "disable":
    result = firewall.disable_nat()
else:
    raise SystemExit("usage: apply_nat.sh enable|disable")
print(f"{result.command}: rc={result.returncode}")
print(result.stdout)
print(result.stderr)
PY
