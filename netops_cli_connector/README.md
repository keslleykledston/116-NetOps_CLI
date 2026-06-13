# netops_cli_connector

Conector/bastiao NetOps para rodar como container no host do cliente. O MVP permite que o servidor central NetOps acesse, de forma controlada, recursos da rede local para testes e preparacao de coleta via SSH, SNMP, ICMP e, futuramente, NETCONF.

O projeto entrega:

- Interface web FastAPI/Jinja2 com login.
- Configuracao de WireGuard.
- Configuracao de L2TP/IPsec com strongSwan e xl2tpd.
- Cadastro de rotas estaticas.
- NAT/masquerade.
- Diagnosticos de ping, traceroute, TCP, UDP, SNMP, rotas, interfaces e firewall.
- Heartbeat para servidor NetOps central.
- CLI interno `netops-cli`.

## Arquitetura

```text
NetOps Server
    |
    | WireGuard VPN
    |
Host do Cliente
    |
    | Container netops_cli_connector
    |
Rede Local do Cliente
    |
Roteadores / Switches / OLTs
```

## Requisitos do Host

- Linux com Docker Engine e Docker Compose Plugin.
- Kernel com suporte a WireGuard, IPsec, PPP/L2TP, iptables/nftables e forwarding.
- Acesso root ou usuario com permissao para Docker.
- Portas de VPN liberadas conforme uso:
  - WireGuard: UDP 51820 ou porta configurada.
  - L2TP/IPsec: UDP 500, 4500 e 1701.
- Porta web local livre. O exemplo usa `8091` para evitar conflito com outros servicos.

Verificacao basica:

```bash
docker --version
docker compose version
uname -r
```

## Por Que o Container e Privilegiado

O `docker-compose.yml` usa:

```yaml
network_mode: host
privileged: true
cap_add:
  - NET_ADMIN
  - SYS_MODULE
```

Isso e necessario porque o conector manipula rede do host:

- Criacao de interfaces VPN.
- WireGuard via `wg-quick`.
- IPsec/L2TP com strongSwan, xl2tpd e PPP.
- Rotas estaticas com `ip route`.
- NAT/masquerade com iptables/nftables.
- `sysctl net.ipv4.ip_forward`.
- Modulos de kernel em ambientes que exigem `SYS_MODULE`.

Sem essas permissoes, VPN, rotas e firewall tendem a falhar dentro do container.

## Estrutura

```text
netops_cli_connector/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   ├── services/
│   ├── templates/
│   └── static/
├── scripts/
├── config/
│   ├── wireguard/
│   ├── ipsec/
│   └── runtime/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

Arquivos sensiveis de runtime ficam em `config/` e sao ignorados pelo Git, exceto `.gitkeep`.

## Instalacao Rapida

Clone o repositorio:

```bash
git clone https://github.com/keslleykledston/116-NetOps_CLI.git
cd 116-NetOps_CLI/netops_cli_connector
```

Crie o `.env`:

```bash
cp .env.example .env
```

Edite as variaveis:

```bash
nano .env
```

Suba o container:

```bash
docker compose up -d --build
```

Acesse:

```text
http://IP_DO_HOST:8091
```

Credenciais iniciais dependem do `.env`:

```text
WEB_USERNAME=admin
WEB_PASSWORD=change-me
```

Troque `WEB_PASSWORD`, `SESSION_SECRET` e `CONNECTOR_TOKEN` antes de usar em ambiente real.

## Variaveis de Ambiente

Arquivo: `.env`

```env
NETOPS_CONNECTOR_NAME=cliente-a
WEB_USERNAME=admin
WEB_PASSWORD=change-me
NETOPS_SERVER_URL=https://netops.example.com
CONNECTOR_TOKEN=change-me
NETOPS_WG_PROVISION_PATH=/api/connectors/wireguard/provision
WG_INTERFACE=wg-netops
LAN_INTERFACE=eth0
WAN_INTERFACE=eth0
WEB_HOST=0.0.0.0
WEB_PORT=8091
HEARTBEAT_INTERVAL_SECONDS=60
SESSION_SECRET=change-this-random-secret
CONFIG_ROOT=/etc/netops-cli
```

Notas:

- `WEB_PORT`: porta HTTP exposta pelo FastAPI em `network_mode: host`.
- `LAN_INTERFACE`: interface voltada para a rede local do cliente.
- `WAN_INTERFACE`: interface de saida/default route.
- `WG_INTERFACE`: nome esperado para interface WireGuard.
- `NETOPS_SERVER_URL`: URL do servidor central que recebe heartbeat.
- `CONNECTOR_TOKEN`: token Bearer para heartbeat.
- `NETOPS_WG_PROVISION_PATH`: endpoint do servidor central usado para provisionar WireGuard via token.

## Construcao Manual

Build da imagem:

```bash
docker compose build
```

Subir em background:

```bash
docker compose up -d
```

Rebuild apos alterar codigo:

```bash
docker compose up -d --build
```

Ver logs:

```bash
docker logs -f netops_cli_connector
```

Ver status:

```bash
docker compose ps
docker exec -it netops_cli_connector netops-cli status
```

Parar:

```bash
docker compose down
```

## Publicacao com Nginx

Opcionalmente publique a interface atras de Nginx com HTTPS.

Exemplo para `netopscli.devops.k3gsolutions.com.br` apontando para `127.0.0.1:8091`:

```nginx
upstream netopscli_connector {
    server 127.0.0.1:8091;
    keepalive 32;
}

server {
    listen 80;
    server_name netopscli.devops.k3gsolutions.com.br;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name netopscli.devops.k3gsolutions.com.br;

    ssl_certificate /etc/letsencrypt/live/netopscli.devops.k3gsolutions.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/netopscli.devops.k3gsolutions.com.br/privkey.pem;

    location / {
        proxy_pass http://netopscli_connector;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

Validar e recarregar:

```bash
nginx -t
systemctl reload nginx
```

Emitir certificado com Certbot:

```bash
certbot --nginx -d netopscli.devops.k3gsolutions.com.br
```

## WireGuard

Acesse `WAN / WireGuard` na interface web.

### Autenticacao e Provisionamento

WireGuard nao autentica o tunel com token. WireGuard autentica peers com chaves:

- Private key do client: fica somente no conector.
- Public key do client: enviada ao servidor.
- Private key do servidor: fica somente no servidor.
- Public key do servidor: recebida pelo client.

O `CONNECTOR_TOKEN` e usado para autenticar o provisionamento/API com o NetOps Server. O fluxo recomendado e:

1. O conector gera a private key localmente.
2. O conector deriva a public key local.
3. O conector envia a public key ao NetOps Server usando `Authorization: Bearer <CONNECTOR_TOKEN>`.
4. O NetOps Server cadastra o peer e devolve endpoint, public key do servidor, IP do tunel e Allowed IPs.
5. O conector salva `/etc/wireguard/netops.conf`.

Endpoint esperado no servidor central:

```http
POST /api/connectors/wireguard/provision
Authorization: Bearer <CONNECTOR_TOKEN>
```

Payload enviado:

```json
{
  "connector_name": "cliente-a",
  "public_key": "<CLIENT_PUBLIC_KEY>",
  "wireguard_interface": "wg-netops",
  "lan_interface": "eth0",
  "wan_interface": "eth0"
}
```

Resposta esperada:

```json
{
  "endpoint": "vpn.netops.example.com",
  "port": 51820,
  "server_public_key": "<SERVER_PUBLIC_KEY>",
  "allowed_ips": "10.255.0.1/32, 10.200.0.0/16",
  "tunnel_ip": "10.255.0.2/30",
  "keepalive": 25
}
```

Tambem e aceito responder dentro de `wireguard`:

```json
{
  "wireguard": {
    "server_endpoint": "vpn.netops.example.com:51820",
    "server_public_key": "<SERVER_PUBLIC_KEY>",
    "allowed_ips": "10.255.0.1/32, 10.200.0.0/16",
    "client_tunnel_ip": "10.255.0.2/30",
    "persistent_keepalive": 25
  }
}
```

Na interface, use o botao `Provisionar via token`. No CLI:

```bash
docker exec -it netops_cli_connector netops-cli wg provision
```

O modo manual continua disponivel na mesma tela.

Campos principais:

- Endpoint do NetOps Server.
- Porta.
- Private Key local.
- Public Key do servidor.
- Allowed IPs.
- IP local do tunel.
- Keepalive.

A configuracao gerada fica em:

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

CLI:

```bash
docker exec -it netops_cli_connector netops-cli wg up
docker exec -it netops_cli_connector netops-cli wg down
```

Verificar no host/container:

```bash
docker exec -it netops_cli_connector wg show
docker exec -it netops_cli_connector ip addr show
```

## L2TP/IPsec

Acesse `LAN / L2TP IPsec` na interface web.

Campos principais:

- Servidor VPN remoto.
- IP local IPsec, quando o host tiver IP privado e IP publico na mesma interface. No ambiente validado: `131.108.136.133`.
- ID local IPsec, deixe vazio para o Mikrotik L2TP/IPsec dinamico, a menos que o concentrador exija ID especifico.
- Propostas IKE/ESP, opcionais. Use para casar phase1/phase2 com o profile/proposal do concentrador.
- Usuario.
- Senha.
- PSK.
- Interface criada, normalmente `ppp0`.
- Rede remota.
- Rotas que devem passar pela VPN.

Arquivos gerados:

```text
/etc/netops-cli/ipsec/ipsec.conf
/etc/netops-cli/ipsec/ipsec.secrets
/etc/netops-cli/ipsec/xl2tpd.conf
/etc/netops-cli/ipsec/options.xl2tpd
```

O entrypoint regenera e copia a configuracao ativa para:

```text
/etc/ipsec.conf
/etc/ipsec.secrets
/etc/xl2tpd/xl2tpd.conf
```

Padrao validado com Mikrotik L2TP/IPsec:

```ini
# /etc/ipsec.conf
conn netops-l2tp
    keyexchange=ikev1
    authby=secret
    type=transport
    forceencaps=yes
    left=131.108.136.133
    leftprotoport=17/1701
    right=45.169.161.132
    rightid=%any
    rightprotoport=17/1701
    ikelifetime=1d
    lifetime=30m
    ike=aes128-sha1-modp2048,aes128-sha1-modp1024,3des-sha1-modp2048,3des-sha1-modp1024
    esp=aes128-sha1-modp1024,aes192-sha1-modp1024,aes256-sha1-modp1024,3des-sha1-modp1024
```

```ini
# /etc/xl2tpd/xl2tpd.conf
[global]
access control = no
listen-addr = 131.108.136.133

[lac netops-l2tp]
lns = 45.169.161.132
pppoptfile = /etc/netops-cli/ipsec/options.xl2tpd
length bit = yes
redial = no
autodial = no
```

Notas importantes:

- Nao usar `require ipsec = yes` no `xl2tpd.conf`; o `xl2tpd` 1.3.18 rejeita essa diretiva.
- Usar `listen-addr` igual ao `left` do IPsec quando o host tiver mais de um IP. Sem isso, o L2TP pode sair pela origem errada e expirar em `Maximum retries exceeded`.
- O arquivo `/etc/ipsec.secrets` usa PSK catch-all (`: PSK "..."`) para casar com peer dinamico do Mikrotik.
- No Mikrotik, a identity do IPsec precisa usar `auth-method=pre-shared-key`.

Comportamento de conexao:

- O app limpa tentativa anterior antes de conectar.
- O app garante que o `xl2tpd` esteja rodando.
- O app executa `ipsec up netops-l2tp`.
- O L2TP so e iniciado se o IPsec estabelecer com sucesso.
- Quando `ppp0` sobe, o app reaplica as rotas estaticas salvas.
- Se o IPsec falhar ou ficar preso em `CONNECTING`, a tentativa e limpa e o erro aparece na tela.

Validacao:

```bash
docker exec -it netops_cli_connector ipsec status
docker exec -it netops_cli_connector ipsec statusall
docker exec -it netops_cli_connector ip -br addr show ppp0
docker exec -it netops_cli_connector ip route
```

Estado esperado:

```text
Security Associations (1 up, 0 connecting)
netops-l2tp: ESTABLISHED
netops-l2tp: INSTALLED, TRANSPORT
ppp0 ativo
```

## Rotas Estaticas

Acesse `Rotas` na interface web.

Campos:

- Destino CIDR.
- Gateway.
- Interface.
- Metrica.
- Descricao.

Exemplos:

```text
10.10.0.0/16 via 192.168.88.1 dev eth0
172.16.0.0/12 dev wg-netops
10.200.0.0/16 via 10.164.172.1 dev ppp0
10.0.0.0/8 via 10.164.172.1 dev ppp0
```

Para redes remotas via L2TP, a rota so funciona depois que `ppp0` existe. O conector reaplica as rotas salvas ao conectar o L2TP. Validacao:

```bash
docker exec -it netops_cli_connector ip route get 10.200.3.1
docker exec -it netops_cli_connector ping -c 3 10.200.3.1
```

Estado esperado:

```text
10.200.3.1 via 10.164.172.1 dev ppp0 src 10.199.99.232
3 packets transmitted, 3 received, 0% packet loss
```

CLI:

```bash
docker exec -it netops_cli_connector netops-cli routes list
```

Ver rotas reais:

```bash
docker exec -it netops_cli_connector ip route show
```

## NAT / Masquerade

Acesse `NAT` na interface web.

Campos:

- Interface origem/LAN.
- Interface saida/WAN/WireGuard/L2TP.
- Rede origem.
- Ativar forwarding IPv4.

Exemplo aplicado:

```bash
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -s 10.10.0.0/16 -o wg-netops -j MASQUERADE
```

O app usa `iptables -C` antes de adicionar regra, evitando duplicidade.

CLI:

```bash
docker exec -it netops_cli_connector netops-cli nat enable
docker exec -it netops_cli_connector netops-cli nat disable
```

Ver regras:

```bash
docker exec -it netops_cli_connector iptables -t nat -S
docker exec -it netops_cli_connector nft list ruleset
```

## Diagnosticos

Acesse `Diagnosticos` na interface web.

Testes disponiveis:

- Ping ICMP.
- Traceroute.
- TCP check, por exemplo porta 22.
- UDP check, por exemplo porta 161.
- SNMP walk.
- Interfaces.
- Rotas.
- Firewall iptables/nftables.
- Logs de WireGuard e L2TP/IPsec.

CLI:

```bash
docker exec -it netops_cli_connector netops-cli test ping 10.0.0.1
docker exec -it netops_cli_connector netops-cli test udp 10.0.0.1 161
docker exec -it netops_cli_connector netops-cli test snmp 10.0.0.1 public
```

Observacao sobre UDP:

- O teste UDP confirma que o pacote foi enviado.
- UDP nao garante resposta.
- Para validar SNMP de verdade, use `snmpwalk` com community correta e ACL liberada no equipamento.

API com sessao autenticada:

```bash
curl -b cookies.txt -c cookies.txt -X POST http://IP_DO_HOST:8091/login \
  -d 'username=admin' \
  -d 'password=change-me'

curl -b cookies.txt http://IP_DO_HOST:8091/api/status

curl -b cookies.txt -X POST http://IP_DO_HOST:8091/api/diagnostics/ping \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","count":4}'

curl -b cookies.txt -X POST http://IP_DO_HOST:8091/api/diagnostics/tcp-check \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","port":22}'

curl -b cookies.txt -X POST http://IP_DO_HOST:8091/api/diagnostics/udp-check \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","port":161}'

curl -b cookies.txt -X POST http://IP_DO_HOST:8091/api/diagnostics/snmpwalk \
  -H 'Content-Type: application/json' \
  -d '{"host":"10.0.0.1","community":"public"}'

curl -b cookies.txt http://IP_DO_HOST:8091/api/routes
curl -b cookies.txt http://IP_DO_HOST:8091/api/interfaces
curl -b cookies.txt http://IP_DO_HOST:8091/api/firewall
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

O ultimo resultado fica em:

```text
/etc/netops-cli/runtime/heartbeat.json
```

## Fila de jobs NetOps (coletas automaticas)

Alem do heartbeat, o conector executa jobs enfileirados pelo NetOps Server:

```text
GET  /api/connectors/jobs/pending
POST /api/connectors/jobs/:id/result
```

Tipos suportados: `PING`, `TRACEROUTE`, `TCP_CHECK`, `ROUTE_CHECK`, `SNMP_GET`, `SNMP_WALK`, `SSH_COMMAND`, `SSH_CONFIG_BUNDLE`, `WG_STATUS`.

O loop roda automaticamente quando `JOB_POLL_ENABLED=true` (default). Estado em `/etc/netops-cli/runtime/jobs_poll.json`.

Poll manual:

```bash
docker exec -it netops_cli_connector netops-cli jobs-poll
```

No dashboard, os paineis **Fila NetOps** e **Ultimo job** mostram a ultima execucao.

## CLI Interno

Comandos disponiveis:

```bash
docker exec -it netops_cli_connector netops-cli status
docker exec -it netops_cli_connector netops-cli heartbeat
docker exec -it netops_cli_connector netops-cli wg up
docker exec -it netops_cli_connector netops-cli wg down
docker exec -it netops_cli_connector netops-cli routes list
docker exec -it netops_cli_connector netops-cli nat enable
docker exec -it netops_cli_connector netops-cli nat disable
docker exec -it netops_cli_connector netops-cli test ping 10.0.0.1
docker exec -it netops_cli_connector netops-cli test udp 10.0.0.1 161
docker exec -it netops_cli_connector netops-cli test snmp 10.0.0.1 public
```

## Validacao Pos-Instalacao

Execute:

```bash
docker compose ps
docker logs --tail=100 netops_cli_connector
curl -I http://127.0.0.1:8091/login
```

Na interface web:

- Login abre.
- Dashboard mostra interfaces e rotas.
- WireGuard salva configuracao e gera `/etc/wireguard/netops.conf`.
- L2TP/IPsec mostra status, logs e ultimo resultado de conexao.
- Rotas podem ser adicionadas/removidas.
- NAT pode ser ativado/desativado.
- Diagnostico de ping funciona.
- Heartbeat manual retorna sucesso ou erro claro de conectividade/token.

Validacao de rede por dentro do container:

```bash
docker exec -it netops_cli_connector ip route get 10.200.1.1
docker exec -it netops_cli_connector ping -c 4 10.200.1.1
docker exec -it netops_cli_connector snmpwalk -v2c -c <community> 10.200.1.1 1.3.6.1.2.1.1
```

## Troubleshooting

Container nao sobe:

```bash
docker logs netops_cli_connector
docker compose config
```

Porta web ocupada:

```bash
ss -ltnp | grep 8091
```

Altere `WEB_PORT` no `.env` e reinicie:

```bash
docker compose up -d
```

WireGuard nao sobe:

```bash
docker exec -it netops_cli_connector wg show
docker exec -it netops_cli_connector wg-quick up netops
docker exec -it netops_cli_connector ip route
```

L2TP/IPsec nao estabelece:

```bash
docker exec -it netops_cli_connector ipsec statusall
docker exec -it netops_cli_connector ip xfrm state
docker exec -it netops_cli_connector ip xfrm policy
docker exec -it netops_cli_connector ip -br addr show ppp0
```

Pontos comuns:

- PSK incorreta (deve ser igual ao `ipsec-secret` do `/interface l2tp-server server` no Mikrotik).
- Usuario/senha PPP incorretos.
- Propostas IKE/ESP incompatíveis com o `/ip ipsec profile` default do Mikrotik.
- Servidor exige ID especifico (`leftid` = IP publico do cliente).
- UDP 500/4500/1701 bloqueado.
- NAT intermediario sem NAT-T.
- Rota remota ausente.

Mikrotik ROS 6 — alinhar propostas ao `/ip ipsec profile` + `/ip ipsec proposal` default:

| Mikrotik | NetOps CLI (strongSwan) |
|----------|-------------------------|
| profile enc `aes-128,3des` + hash `sha1` + dh `modp2048,modp1024` | IKE: `aes128-sha1-modp2048,3des-sha1-modp2048` |
| proposal enc `aes-256-cbc,...` + auth `sha1` + pfs `modp1024` | ESP: `aes128-sha1-modp1024,aes256-sha1-modp1024` |

**Nao** oferecer `aes256` na fase 1 se o profile Mikrotik so tem `aes-128,3des`.

Confirme tambem no Mikrotik:

```bash
/interface l2tp-server server print
/ip ipsec peer print detail where dynamic
/ppp secret print where service=l2tp
```

O L2TP server precisa de `use-ipsec=yes` e `ipsec-secret` igual a PSK do NetOps CLI. Sem isso o peer dinamico nao nasce e aparece `no auth method defined for peer`.

SNMP nao responde mas ping responde:

- Verifique ACL SNMP no equipamento.
- Verifique community.
- Verifique se o equipamento aceita origem do tunel, por exemplo IP `ppp0`.
- Verifique firewall para UDP 161.

## Seguranca

- A interface exige login com usuario e senha via `.env`.
- Secrets nao sao exibidos completos na interface.
- Private key, PSK, senha VPN, token e community SNMP sao mascarados em telas e logs de comandos.
- Arquivos sensiveis sao gravados com permissao `0600`.
- Diretorios de configuracao sao mantidos com permissao `0700`.
- `.env` e configs reais em `config/` sao ignorados pelo Git.
- Acoes destrutivas de rotas e NAT exigem confirmacao textual.
- O MVP nao implementa coleta avancada de dispositivos; ele apenas prepara conectividade e diagnosticos.

Recomendacoes para producao:

- Trocar `WEB_PASSWORD`.
- Gerar `SESSION_SECRET` forte.
- Rotacionar `CONNECTOR_TOKEN`.
- Restringir acesso ao painel por firewall/VPN administrativa.
- Publicar com HTTPS via Nginx quando exposto fora do host.
- Auditar rotas e NAT antes de ativar em ambiente do cliente.

## Atualizacao

Atualizar codigo:

```bash
git pull
docker compose up -d --build
```

Preservacao de dados:

- Arquivos em `config/` ficam no host e sobrevivem ao rebuild.
- `.env` fica no host e nao e versionado.

Backup simples:

```bash
tar czf netops-cli-backup.tgz .env config/
```
