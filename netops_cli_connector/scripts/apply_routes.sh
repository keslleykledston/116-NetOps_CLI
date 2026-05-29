#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from app.services.routing import apply_all
for result in apply_all():
    print(f"{result.command}: rc={result.returncode}")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
PY
