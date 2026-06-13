#!/bin/bash
set -e

CONTAINER="netops_cli_connector"

echo "=== NetOps VPN Status Check ==="
echo ""

# WireGuard Status
echo "📡 WireGuard:"
WG_STATUS=$(docker exec -it "$CONTAINER" ip link show wg-netops 2>/dev/null || echo "not found")
if echo "$WG_STATUS" | grep -q "UP"; then
    echo "  ✓ Status: UP"
    docker exec -it "$CONTAINER" wg show wg-netops 2>/dev/null || echo "  (wg show not available)"
    docker exec -it "$CONTAINER" ip addr show wg-netops 2>/dev/null || true
else
    echo "  ✗ Status: DOWN"
    docker exec -it "$CONTAINER" ip link show wg-netops 2>/dev/null || echo "  (interface not found)"
fi

echo ""
echo "📡 L2TP/IPsec:"
# L2TP Status
L2TP_STATUS=$(docker exec -it "$CONTAINER" ip link show ppp0 2>/dev/null || echo "not found")
if echo "$L2TP_STATUS" | grep -q "UP"; then
    echo "  ✓ Status: UP"
    docker exec -it "$CONTAINER" ip addr show ppp0 2>/dev/null || true
else
    echo "  ✗ Status: DOWN"
    docker exec -it "$CONTAINER" ip link show ppp0 2>/dev/null || echo "  (interface not found)"
fi

echo ""
echo "=== Diagnostics ==="
echo ""

# Routes
echo "📍 Routes:"
docker exec -it "$CONTAINER" ip route show 2>/dev/null | head -10

echo ""
echo "🔌 Interfaces:"
docker exec -it "$CONTAINER" ip -br addr show 2>/dev/null | grep -E "wg-netops|ppp0|eth0"

echo ""
echo "=== Test Ping to 10.200.x.x ==="
echo ""

if docker exec -it "$CONTAINER" ping -c 2 10.200.1.1 2>/dev/null; then
    echo "✓ Ping 10.200.1.1: SUCCESS"
else
    echo "✗ Ping 10.200.1.1: FAILED"
fi

if docker exec -it "$CONTAINER" ping -c 2 10.200.3.1 2>/dev/null; then
    echo "✓ Ping 10.200.3.1: SUCCESS"
else
    echo "✗ Ping 10.200.3.1: FAILED"
fi

echo ""
echo "Done."
