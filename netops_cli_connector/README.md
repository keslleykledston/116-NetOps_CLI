# netops_cli_connector

Conector/bastiao NetOps para rodar como container no host do cliente. O objetivo do MVP e permitir que o servidor central NetOps acesse, de forma controlada, recursos locais via WireGuard, L2TP/IPsec, rotas estaticas, NAT/masquerade e diagnosticos basicos para SSH, SNMP e ICMP.

## Arquitetura

```text
NetOps Server
    |
    | WireGuard VPN
    |
Host do Cliente
    |
    | Container netops_cli
    |
Rede Local do Cliente
    |
Roteadores / Switches / OLTs
```

## Requisitos no host

- Docker e Docker Compose.
- Kernel com suporte a WireGuard, iptables/nftables, rotas e forwarding.
- Permissao para executar container privilegiado.

O `docker-compose.yml` usa `network_mode: host`, `privileged: true`, `NET_ADMIN` e `SYS_MODULE`. Isso e necessario porque o conector manipula interfaces VPN, rotas do host, regras de firewall/NAT, sysctl de forwarding e, em alguns ambientes, modulos de kernel. Sem essas permissoes, WireGuard, L2TP/IPsec, rotas e masquerade nao funcionam corretamente dentro do container.

## Instalacao no cliente

```bash
cp .env.example .env
docker compose up -d --build
```

Acesse:

```text
http://IP_DO_HOST:8091
```

Neste host, o Nginx pode publicar o conector em `https://netopscli.devops.k3gsolutions.com.br` apontando para `127.0.0.1:8091`. Se a porta `8080` estiver livre no cliente, ela tambem pode ser usada ajustando `WEB_PORT`.

Credenciais padrao do exemplo:

```text
usuario: admin
senha: change-me
```

Altere `WEB_PASSWORD`, `SESSION_SECRET` e `CONNECTOR_TOKEN` antes de usar em producao.

## Variaveis principais

```env
NETOPS_CONNECTOR_NAME=cliente-a
WEB_USERNAME=admin
WEB_PASSWORD=change-me
NETOPS_SERVER_URL=https://netops.example.com
CONNECTOR_TOKEN=change-me
WG_INTERFACE=wg-netops
LAN_INTERFACE=eth0
WAN_INTERFACE=eth0
WEB_HOST=0.0.0.0
WEB_PORT=8080
HEARTBEAT_INTERVAL_SECONDS=60
SESSION_SECRET=change-this-random-secret
CONFIG_ROOT=/etc/netops-cli
```

## Funcionalidades do MVP

- Interface web FastAPI/Jinja2 com login simples.
- Dashboard com interfaces, rotas, status WireGuard, L2TP/IPsec, NAT e heartbeat.
- Geracao de `/etc/wireguard/netops.conf`.
- Conectar/desconectar/testar WireGuard.
- Configuracao basica de L2TP/IPsec com strongSwan e xl2tpd.
- Cadastro e remocao de rotas estaticas.
- NAT/masquerade com protecao contra duplicidade via `iptables -C`.
- Diagnosticos: ping, traceroute, TCP porta 22, SNMP walk, rotas, interfaces, firewall e logs.
- Heartbeat para o servidor NetOps.
- CLI interno `netops-cli`.

## WireGuard

A pagina `WAN / WireGuard` gera:

```text
/etc/wireguard/netops.conf
```

Exemplo:

```ini
[Interface]
Address = 10.255.0.2/30
PrivateKey = <CLIENT_PRIVATE_KEY>

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = <SERVER_IP>:51820
AllowedIPs = 10.255.0.1/32, 10.200.0.0/16
PersistentKeepalive = 25
```

Comandos equivalentes:

```bash
docker exec -it netops_cli_connector netops-cli wg up
docker exec -it netops_cli_connector netops-cli wg down
```

## L2TP/IPsec

A pagina `LAN / L2TP IPsec` salva arquivos em:

```text
/etc/netops-cli/ipsec/ipsec.conf
/etc/netops-cli/ipsec/ipsec.secrets
/etc/netops-cli/ipsec/xl2tpd.conf
/etc/netops-cli/ipsec/options.xl2tpd
```

Os secrets sao gravados com permissao `0600`. O entrypoint copia esses arquivos para os caminhos esperados pelos daemons quando o container inicia.

## Rotas estaticas

Exemplos aceitos na interface:

```text
10.10.0.0/16 via 192.168.88.1 dev eth0
172.16.0.0/12 dev wg-netops
```

Via CLI:

```bash
docker exec -it netops_cli_connector netops-cli routes list
```

## NAT / Masquerade

Exemplo aplicado:

```bash
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -s 10.10.0.0/16 -o wg-netops -j MASQUERADE
```

Antes de adicionar regra, o conector executa `iptables -C` para evitar duplicidade.

Via CLI:

```bash
docker exec -it netops_cli_connector netops-cli nat enable
docker exec -it netops_cli_connector netops-cli nat disable
```

## Diagnosticos

Interface web: `Diagnosticos`

API:

```bash
curl -b cookies.txt -c cookies.txt -X POST http://IP_DO_HOST:8080/login \
  -d 'username=admin' -d 'password=change-me'

curl -b cookies.txt http://IP_DO_HOST:8080/api/status

curl -b cookies.txt -X POST http://IP_DO_HOST:8080/api/diagnostics/ping \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","count":4}'

curl -b cookies.txt -X POST http://IP_DO_HOST:8080/api/diagnostics/tcp-check \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","port":22}'

curl -b cookies.txt -X POST http://IP_DO_HOST:8080/api/diagnostics/snmpwalk \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","community":"public"}'

curl -b cookies.txt http://IP_DO_HOST:8080/api/routes
curl -b cookies.txt http://IP_DO_HOST:8080/api/interfaces
curl -b cookies.txt http://IP_DO_HOST:8080/api/firewall
```

CLI:

```bash
docker exec -it netops_cli_connector netops-cli status
docker exec -it netops_cli_connector netops-cli test ping 10.0.0.1
docker exec -it netops_cli_connector netops-cli test snmp 10.0.0.1 public
```

## Heartbeat

O conector envia periodicamente:

```http
POST /api/connectors/heartbeat
Authorization: Bearer <CONNECTOR_TOKEN>
```

Payload:

```json
{
  "connector_name": "cliente-a",
  "status": "online",
  "wireguard_status": "up",
  "l2tp_ipsec_status": "down",
  "lan_interface": "eth0",
  "wan_interface": "eth0",
  "routes_count": 5,
  "nat_enabled": true
}
```

Envio manual:

```bash
docker exec -it netops_cli_connector netops-cli heartbeat
```

## Seguranca

- A interface exige login com usuario e senha via `.env`.
- Secrets nao sao exibidos completos na interface.
- Private key, PSK, senha VPN, token e community SNMP sao mascarados em telas e logs de comandos.
- Arquivos sensiveis sao gravados com permissao `0600`.
- Diretorios de configuracao sao mantidos com permissao `0700`.
- Acoes destrutivas de rotas e NAT exigem confirmacao textual.
- O MVP nao implementa coleta avancada de dispositivos; ele apenas prepara o bastiao para testes e conectividade controlada.

Recomendacoes para producao:

- Usar senha forte e `SESSION_SECRET` aleatorio.
- Restringir acesso ao `WEB_PORT` por firewall do host ou VPN administrativa.
- Rotacionar `CONNECTOR_TOKEN`.
- Auditar regras de NAT e rotas antes de ativar em ambiente do cliente.
- Considerar TLS/reverse proxy quando a interface for exposta fora do host.

## Teste rapido

```bash
docker compose config
docker compose up -d --build
docker logs -f netops_cli_connector
curl -I http://127.0.0.1:8080/login
```

Depois de logar em `http://IP_DO_HOST:8080`, valide:

- Dashboard mostra interfaces e rotas.
- `WAN / WireGuard` salva a configuracao e gera `/etc/wireguard/netops.conf`.
- `Rotas` adiciona/remove uma rota de teste.
- `NAT` ativa/desativa masquerade.
- `Diagnosticos` executa ping.
- `netops-cli heartbeat` tenta enviar status ao servidor central.
