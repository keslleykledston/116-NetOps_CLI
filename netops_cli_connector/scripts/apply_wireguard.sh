#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-up}"
case "$ACTION" in
  up) wg-quick up netops ;;
  down) wg-quick down netops ;;
  restart) wg-quick down netops || true; wg-quick up netops ;;
  *) echo "usage: $0 up|down|restart" >&2; exit 2 ;;
esac
