FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_ROOT=/etc/netops-cli

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    iproute2 \
    iptables \
    nftables \
    iputils-ping \
    traceroute \
    netcat-openbsd \
    openssh-client \
    snmp \
    wireguard-tools \
    strongswan \
    strongswan-charon \
    strongswan-starter \
    xl2tpd \
    procps \
    kmod \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/netops-cli

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY netops-cli /usr/local/bin/netops-cli

RUN chmod +x /usr/local/bin/netops-cli /opt/netops-cli/scripts/*.sh \
    && mkdir -p /etc/netops-cli/wireguard /etc/netops-cli/ipsec /etc/netops-cli/runtime /etc/wireguard \
    && chmod 700 /etc/netops-cli /etc/netops-cli/wireguard /etc/netops-cli/ipsec /etc/netops-cli/runtime /etc/wireguard

EXPOSE 8080

ENTRYPOINT ["/opt/netops-cli/scripts/entrypoint.sh"]
