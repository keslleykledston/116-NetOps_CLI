#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-up}"
mkdir -p /var/run/xl2tpd
case "$ACTION" in
  up)
    ipsec up netops-l2tp
    echo 'c netops-l2tp' > /var/run/xl2tpd/l2tp-control
    ;;
  down)
    echo 'd netops-l2tp' > /var/run/xl2tpd/l2tp-control || true
    ipsec down netops-l2tp || true
    ;;
  *) echo "usage: $0 up|down" >&2; exit 2 ;;
esac
