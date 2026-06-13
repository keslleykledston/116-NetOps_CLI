#!/usr/bin/env bash
set -euo pipefail

mkdir -p /etc/netops-cli/wireguard /etc/netops-cli/ipsec /etc/netops-cli/runtime /etc/wireguard /var/run/xl2tpd
chmod 700 /etc/netops-cli /etc/netops-cli/wireguard /etc/netops-cli/ipsec /etc/netops-cli/runtime /etc/wireguard

python3 - <<'PY' || true
from app.services import l2tp_ipsec

cfg = l2tp_ipsec.get_config()
if cfg:
    l2tp_ipsec.write_files(cfg)
PY

if [ -f /etc/netops-cli/ipsec/ipsec.conf ]; then
  cp /etc/netops-cli/ipsec/ipsec.conf /etc/ipsec.conf
fi
if [ -f /etc/netops-cli/ipsec/ipsec.secrets ]; then
  cp /etc/netops-cli/ipsec/ipsec.secrets /etc/ipsec.secrets
  chmod 600 /etc/ipsec.secrets
fi
if [ -f /etc/netops-cli/ipsec/xl2tpd.conf ]; then
  cp /etc/netops-cli/ipsec/xl2tpd.conf /etc/xl2tpd/xl2tpd.conf
fi

# Rotas estaticas salvas na UI (ex.: 10.0.0.0/8 via ppp0)
if [ -f /etc/netops-cli/runtime/routes.json ]; then
  python3 - <<'PY' || true
from app.services.routing import apply_all
apply_all()
PY
fi

ipsec start || true
sleep 2
if [ ! -p /var/run/xl2tpd/l2tp-control ]; then
  rm -f /var/run/xl2tpd/l2tp-control
fi
xl2tpd || true

exec uvicorn app.main:app --host "${WEB_HOST:-0.0.0.0}" --port "${WEB_PORT:-8080}"
