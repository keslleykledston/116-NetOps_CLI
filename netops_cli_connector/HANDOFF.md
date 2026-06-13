# NetOps CLI Connector - Handoff

Data de referencia: 2026-06-13

## 1. Resumo executivo

O `netops_cli_connector` e um bastiao/container privilegiado que roda no host do cliente para expor um painel web e um CLI local para operacoes de rede controladas.

O objetivo do sistema e:

- manter conectividade com o NetOps central via WireGuard;
- manter conectividade legada via L2TP/IPsec;
- publicar rotas estaticas e NAT no host;
- executar diagnosticos de rede a partir do host do cliente;
- enviar heartbeat para o servidor central;
- buscar e processar jobs remotos do NetOps central.

O container roda com `network_mode: host`, `privileged: true` e `cap_add` de rede, porque a aplicacao nao apenas consulta estado: ela altera rotas, interfaces, IPsec, WireGuard e regras de firewall do host.

## 2. Estrutura mental do sistema

O codigo esta separado em quatro camadas:

1. `app/main.py`
   - sobe o FastAPI;
   - instala middleware de sessao;
   - inicia tarefas de bootstrap e background.

2. `app/routes/*`
   - expoe a interface web e a API JSON;
   - faz apenas validacao de formulario, chamada de service e redirect/render.

3. `app/services/*`
   - contem a logica real de rede, persistencia, heartbeat, jobs remotos e execucao de comandos.

4. `config/` e `runtime/`
   - armazenam configuracoes persistidas e artefatos de execucao.

## 3. Fluxo de inicializacao

### 3.1 Entry point do container

O fluxo comeca em `scripts/entrypoint.sh`:

1. cria os diretorios esperados em `/etc/netops-cli`, `/etc/wireguard` e `/var/run/xl2tpd`;
2. tenta reescrever os arquivos de IPsec/L2TP a partir da configuracao salva;
3. reaplica rotas persistidas;
4. sobe `ipsec` e `xl2tpd` se possivel;
5. executa o `uvicorn app.main:app`.

Esse entrypoint assume que o container tem acesso ao host network stack e aos binarios de sistema instalados na imagem.

### 3.2 Bootstrap da aplicacao

Em `app/main.py`, o startup dispara tres rotinas background:

- `_bootstrap_network()`
  - espera 2 segundos;
  - se existir configuracao L2TP/IPsec salva, chama `l2tp_ipsec.up()`;
  - espera 8 segundos;
  - aplica todas as rotas salvas com `routing.apply_all()`.

- `heartbeat.loop()`
  - envia heartbeat periodico para o NetOps central.

- `job_poll.loop()`
  - se habilitado por `JOB_POLL_ENABLED`, busca jobs pendentes do servidor central e devolve os resultados.

Essa ordem importa: o bootstrap tenta restaurar conectividade antes do heartbeat e da fila de jobs entrarem em ciclo.

## 4. Autenticacao e sessao

O acesso web e protegido por login simples em `app/main.py`:

- usuario e senha vem de `WEB_USERNAME` e `WEB_PASSWORD`;
- a sessao e armazenada via `SessionMiddleware` usando `SESSION_SECRET`;
- ao logar, `request.session["user"]` e setado;
- ao sair, a sessao e limpa.

`app/security.py` centraliza a protecao:

- HTML sem login recebe redirect para `/login`;
- endpoints JSON em `/api/*` recebem `401`.

Isso significa que a interface e a API compartilham o mesmo mecanismo de autenticacao, mas o comportamento de erro e diferente conforme o tipo de rota.

## 5. Persistencia

O estado de runtime e salvo em JSON dentro de `settings.runtime_dir`, que por padrao aponta para `/etc/netops-cli/runtime`.

Arquivos principais:

- `wireguard.json`
  - configuracao atual do WireGuard;
- `wireguard_provision.json`
  - parametros usados no provisionamento via token;
- `wireguard_last_provision.json`
  - ultimo resultado do provisionamento;
- `l2tp_ipsec.json`
  - configuracao persistida de L2TP/IPsec;
- `l2tp_ipsec_last_action.json`
  - ultimo up/down de L2TP/IPsec;
- `routes.json`
  - rotas estaticas definidas na UI;
- `nat.json`
  - estado do NAT e seus parametros;
- `heartbeat.json`
  - ultimo envio de heartbeat;
- `jobs_poll.json`
  - ultimo ciclo do poll de jobs.

`app/storage.py` faz escrita segura com arquivo temporario + `os.replace`, e sanitiza dados sensiveis quando o contexto pede.

## 6. WireGuard

### 6.1 Configuracao

`app/services/wireguard.py` faz tres coisas:

1. guarda a configuracao local em JSON;
2. gera o arquivo `/etc/wireguard/netops.conf`;
3. provisiona o tunnel via servidor NetOps quando o token esta configurado.

Os campos principais da configuracao sao:

- `endpoint`
- `port`
- `private_key`
- `server_public_key`
- `allowed_ips`
- `tunnel_ip`
- `keepalive`

### 6.2 Provisionamento via token

`provision_with_token()` segue esta ordem:

1. resolve URL do servidor e token a partir do runtime ou do `.env`;
2. bloqueia uso de placeholders como `https://netops.example.com` e `change-me`;
3. reaproveita a private key local se ela existir, ou gera novo par de chaves com `wg genkey` e `wg pubkey`;
4. faz `POST` para `/api/connectors/wireguard/provision` no servidor central;
5. valida a resposta JSON;
6. normaliza campos como endpoint, porta, server public key, allowed IPs, tunnel IP e keepalive;
7. salva a configuracao final e marca `provisioned: True`.

O payload enviado ao servidor inclui:

- `connector_name`
- `public_key`
- `wireguard_interface`
- `lan_interface`
- `wan_interface`

### 6.3 Subida e queda do tunnel

`up()` e `down()` usam `wg-quick up netops` e `wg-quick down netops`.

`status()` tenta identificar se a interface configurada existe, ou se a interface `netops` esta viva.

`stats()` coleta:

- interfaces WireGuard ativas;
- peers;
- latest handshake;
- RX/TX;
- endpoint e allowed IPs.

Isso alimenta tanto a tela web quanto o dashboard.

## 7. L2TP/IPsec

### 7.1 Objetivo do modulo

`app/services/l2tp_ipsec.py` implementa a conexao legada com um servidor remoto de VPN via strongSwan + xl2tpd + PPP.

Ele grava quatro arquivos principais:

- `/etc/netops-cli/ipsec/ipsec.conf`
- `/etc/netops-cli/ipsec/ipsec.secrets`
- `/etc/netops-cli/ipsec/xl2tpd.conf`
- `/etc/netops-cli/ipsec/options.xl2tpd`

e depois replica isso para os caminhos do sistema:

- `/etc/ipsec.conf`
- `/etc/ipsec.secrets`
- `/etc/xl2tpd/xl2tpd.conf`

### 7.2 Regras e convencoes

O codigo esta claramente otimizado para Mikrotik ROS 6:

- usa `keyexchange=ikev1`;
- usa `authby=secret`;
- usa `type=transport`;
- aplica `forceencaps=yes`;
- inclui proposal defaults compativeis com Mikrotik;
- deixa `leftid` opcional porque o comentario do codigo diz que um `leftid` explicito pode quebrar o phase1;
- `psk` e tratado como catch-all;
- `local_address` defaulta para `%defaultroute`.

### 7.3 Sequencia de conexao

`up()` executa uma cadeia de verificacoes e comandos:

1. espera `ipsec status` mostrar que o strongSwan esta pronto;
2. garante que `xl2tpd` esta rodando;
3. manda desligar qualquer sessao antiga em `l2tp-control`;
4. chama `ipsec down netops-l2tp`;
5. chama `ipsec up netops-l2tp`;
6. valida o output de `ipsec statusall`;
7. se o IPsec ficou `ESTABLISHED`/`INSTALLED`, envia `c netops-l2tp` para o `xl2tpd`;
8. espera a interface PPP escolhida subir;
9. aplica as rotas estaticas salvas;
10. grava o resultado completo em `l2tp_ipsec_last_action.json`.

Se alguma fase falha, o resultado e normalizado com `CommandResult` e mensagens explicitas para facilitar diagnostico.

### 7.4 Falhas tratadas

O modulo tenta detectar falhas reais mesmo quando o comando retorna `rc=0`, por exemplo:

- `establishing connection 'netops-l2tp' failed`
- `destroying ike_sa`
- `no proposal chosen`
- `authentication failed`

Se isso aparece no stdout/stderr, o retorno e reclassificado como erro.

### 7.5 Desligamento

`down()` envia:

- `echo 'd netops-l2tp' > /var/run/xl2tpd/l2tp-control`
- `ipsec down netops-l2tp`

e grava a acao como `disconnect`.

### 7.6 Diagnostico

`diagnostics()` consolida:

- `ipsec statusall`
- `ip -d addr show <iface>`
- `ip route show`
- `ip route get <server>`
- checagem UDP de `500`, `4500` e `1701`
- `ip xfrm state`
- `ip xfrm policy`
- processos `charon`, `starter`, `xl2tpd`, `pppd`
- logs recentes via `journalctl` e `tail`

Isso e exposto na pagina `/l2tp-ipsec` e na rota `GET /diagnostics/system`.

## 8. Rotas estaticas

`app/services/routing.py` persiste uma lista de rotas em `routes.json`.

Fluxo:

- `configured_routes()` carrega o estado salvo;
- `add_route()` substitui rotas com mesmo destino e aplica a nova rota no sistema;
- `delete_route()` remove do estado e tenta deletar da tabela do host;
- `apply_route()` usa `ip route replace` com `via`, `dev` e `metric` opcionais;
- `apply_all()` reaplica todas as rotas salvas.

O bootstrap do container reaplica essas rotas depois de restaurar o L2TP, porque a interface PPP pode ser dependencia da rota.

## 9. NAT / masquerade

`app/services/firewall.py` salva a configuracao em `nat.json` e manipula a tabela NAT do `iptables`.

### 9.1 Ativacao

`enable_nat()`:

1. grava `enabled: True`;
2. se `enable_forwarding` estiver ligado, executa `sysctl -w net.ipv4.ip_forward=1`;
3. verifica se a regra NAT existe com `iptables -t nat -C POSTROUTING ... -j MASQUERADE`;
4. se nao existir, adiciona com `iptables -t nat -A POSTROUTING ... -j MASQUERADE`.

### 9.2 Desativacao

`disable_nat()`:

1. grava `enabled: False`;
2. verifica se a regra existe;
3. se existir, remove com `iptables -t nat -D POSTROUTING ... -j MASQUERADE`.

### 9.3 Observacao de modelagem

O objeto salvo em `nat.json` contem os campos de interface e source network usados tanto pela UI quanto pela execucao.

## 10. Diagnosticos gerais

`app/services/diagnostics.py` oferece checks simples e reutilizados em varias rotas:

- `ping(host, count)`
- `traceroute(host)`
- `tcp_check(host, port)`
- `udp_check(host, port)`
- `snmpwalk(host, community, oid)`
- `ssh_test(host, user, port)`
- `interfaces()`

Observacoes importantes:

- `tcp_check` e `udp_check` usam sockets, nao shell;
- `snmpwalk` e `ssh_test` usam `run()` para chamar binarios do sistema;
- `snmpwalk` redige a community string no resultado;
- `ssh_test` usa `StrictHostKeyChecking=no`.

## 11. Jobs remotos

Esse e um dos mecanismos mais importantes do codebase.

### 11.1 Credenciais

`app/services/netops_credentials.py` resolve:

- URL do NetOps central;
- token do connector.

Ele primeiro tenta a configuracao provisionada em runtime, depois cai para variaveis de ambiente.

Se URL ou token estiverem vazios, com `change-me` ou com o placeholder `netops.example.com`, o sistema considera as credenciais nao configuradas.

### 11.2 Polling

`app/services/job_poll.py` roda em loop quando `JOB_POLL_ENABLED=true`.

Passos:

1. valida credenciais;
2. faz `GET /api/connectors/jobs/pending`;
3. interpreta resposta como lista direta ou como `{"jobs": [...]}`;
4. executa cada job via `execute_job()`;
5. publica o resultado em `POST /api/connectors/jobs/{id}/result`;
6. grava resumo em `jobs_poll.json`.

### 11.3 Execucao dos jobs

`app/services/job_executor.py` traduz o job remoto em uma operacao local.

Tipos suportados:

- `PING`
- `TRACEROUTE`
- `TCP_CHECK`
- `ROUTE_CHECK`
- `SNMP_GET`
- `SNMP_WALK`
- `SSH_COMMAND`
- `SSH_CONFIG_BUNDLE`
- `WG_STATUS`

Regras de seguranca:

- comandos SSH passam por `validate_ssh_command()`;
- o policy e read-only;
- metacaracteres de shell sao bloqueados;
- comandos de configuracao/destruicao sao bloqueados;
- o comando precisa começar com prefixos permitidos como `display`, `show`, `ping`, `traceroute`.

Comportamentos especiais:

- `SSH_COMMAND` ajusta o comando para Huawei, injetando `screen-length 0 temporary` em alguns casos;
- `SSH_CONFIG_BUNDLE` executa uma sequencia de comandos, agrega saidas e produz metadados por comando;
- `SNMP_WALK` trunca saida acima de `SNMP_MAX_LINES`;
- `PING` e `TRACEROUTE` usam os helpers de diagnostico;
- `ROUTE_CHECK` usa `ip route get`.
- `WG_STATUS` devolve um snapshot estruturado do WireGuard para o servidor central.

## 12. API e paginas

### 12.1 Paginacao web

Principais rotas HTML:

- `/`
  - dashboard geral;
- `/wireguard`
  - configuracao e estado do WireGuard;
- `/l2tp-ipsec`
  - configuracao e diagnostico do IPsec/L2TP;
- `/routes`
  - rotas estaticas;
- `/nat`
  - NAT e firewall;
- `/diagnostics`
  - checks manuais.

### 12.2 API JSON

`app/routes/api.py` expoe:

- `GET /api/status`
- `POST /api/heartbeat`
- `POST /api/diagnostics/ping`
- `POST /api/diagnostics/tcp-check`
- `POST /api/diagnostics/udp-check`
- `POST /api/diagnostics/snmpwalk`
- `GET /api/routes`
- `GET /api/interfaces`
- `GET /api/firewall`

Todas exigem login via sessao.

## 13. CLI local

`netops-cli` e um wrapper para operacoes administrativas sem abrir a UI:

- `netops-cli status`
- `netops-cli heartbeat`
- `netops-cli jobs-poll`
- `netops-cli wg up|down|provision`
- `netops-cli routes list`
- `netops-cli nat enable|disable`
- `netops-cli test ping|snmp|udp`

Ele imprime JSON quando o retorno e dict e usa o mesmo codigo de servico da web.

## 14. Container e dependencias do host

### 14.1 Imagem

O `Dockerfile` instala os binarios usados pelo app:

- `iproute2`
- `iptables`
- `nftables`
- `ping`
- `traceroute`
- `netcat-openbsd`
- `openssh-client`
- `sshpass`
- `snmp`
- `wireguard-tools`
- `strongswan`
- `xl2tpd`
- `procps`
- `kmod`

### 14.2 Compose

O `docker-compose.yml` monta:

- `./config:/etc/netops-cli`
- `/etc/wireguard:/etc/wireguard`
- `/lib/modules:/lib/modules:ro`

e usa:

- `network_mode: host`
- `privileged: true`
- `cap_add: NET_ADMIN, SYS_MODULE`

Sem esses privilegios, o produto fica apenas parcialmente funcional.

## 15. Variaveis de ambiente relevantes

As principais variaveis estao em `.env.example`:

- `NETOPS_CONNECTOR_NAME`
- `WEB_USERNAME`
- `WEB_PASSWORD`
- `NETOPS_SERVER_URL`
- `CONNECTOR_TOKEN`
- `NETOPS_WG_PROVISION_PATH`
- `WG_INTERFACE`
- `LAN_INTERFACE`
- `WAN_INTERFACE`
- `WEB_HOST`
- `WEB_PORT`
- `HEARTBEAT_INTERVAL_SECONDS`
- `JOB_POLL_ENABLED`
- `JOB_POLL_INTERVAL_SECONDS`
- `JOB_TIMEOUT_SECONDS`
- `SSH_CONNECT_TIMEOUT`
- `SSH_COMMAND_TIMEOUT`
- `SNMP_MAX_LINES`
- `SESSION_SECRET`
- `CONFIG_ROOT`

## 16. Riscos e pontos de atencao

1. Credenciais default sao placeholders.
   - `WEB_PASSWORD`, `CONNECTOR_TOKEN` e `SESSION_SECRET` precisam ser trocados.

2. O container altera rede do host.
   - qualquer erro de configuracao pode derrubar conectividade ou regras de firewall.

3. L2TP/IPsec e sensivel a compatibilidade de proposals.
   - o codigo ja tem defaults voltados a Mikrotik ROS 6, mas isso continua dependente do lado remoto.

4. Jobs SSH sao rigidamente read-only.
   - se o servidor central tentar mandar comando fora da policy, o job falha por design.

5. Nao ha testes automatizados no repositorio.
   - a validacao hoje depende de execucao manual e observacao de logs/status.

6. O sistema assume acesso a utilitarios de sistema dentro do container.
   - se a imagem ou o host nao disponibilizarem um binario, o service correspondente falha.

## 17. Ordem operacional recomendada

Se for assumir/manter esse ambiente em producao, a sequencia mais segura e:

1. validar `.env`;
2. subir o container;
3. abrir o dashboard;
4. provisionar WireGuard;
5. salvar L2TP/IPsec;
6. subir L2TP/IPsec;
7. aplicar rotas;
8. ativar NAT se necessario;
9. conferir heartbeat e fila de jobs;
10. usar `diagnostics/system` para validar rota, interfaces, firewall e logs.

## 18. Onde olhar primeiro quando algo quebra

1. `app/services/wireguard.py`
   - provisioning, chave, config e `wg-quick`.

2. `app/services/l2tp_ipsec.py`
   - write_files, `up()`, `diagnostics()` e deteccao de falha.

3. `app/services/job_executor.py`
   - se jobs remotos nao estao sendo aceitos.

4. `app/services/heartbeat.py`
   - se o servidor central nao recebe status.

5. `scripts/entrypoint.sh`
   - se algo falha antes do uvicorn subir.

## 19. Resumo curto de funcionamento

O sistema salva a configuracao de rede em JSON seguro, reescreve arquivos de VPN no host, executa comandos privilegiados no namespace de rede do host e sincroniza status com o NetOps central por heartbeat e polling de jobs.

O desenho e pragmatico: a UI apenas direciona as acoes; a confiabilidade real esta nas services que persistem estado, validam saida dos comandos e tentam restaurar a rede apos restart.
