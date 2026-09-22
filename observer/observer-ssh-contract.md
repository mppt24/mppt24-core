# Contrato — observer-ssh

## Identificação

- Módulo: `observer-ssh`
- Versão atual: `1.0.0`
- Tipo: Observer
- Janela temporal: 24 horas móveis

## Missão

Observar factos atuais e eventos SSH sem interpretar intenção, atribuir gravidade operacional, bloquear endereços ou alterar o sistema.

## Fontes sem privilégios

- `systemctl`
- `journalctl`
- `ssh.service`
- `ssh.socket`

## Factos produzidos

- `systemctl_available`
- `ssh_service_active`
- `ssh_service_enabled`
- `ssh_socket_active`
- `ssh_socket_enabled`
- `ssh_listen_endpoints`
- `journal_available`
- `observation_window_hours`
- `invalid_user_events_24h`
- `invalid_user_closed_events_24h`
- `root_closed_preauth_events_24h`
- `failed_password_events_24h`
- `accepted_publickey_events_24h`
- `banner_exchange_events_24h`
- `invalid_user_unique_ips_24h`
- `root_closed_preauth_unique_ips_24h`
- `accepted_publickey_unique_ips_24h`
- `banner_exchange_unique_ips_24h`

## Estados técnicos

- `OK`: todas as fontes foram consultadas.
- `WARNING`: o `systemctl` não pôde ser consultado completamente.
- `ERROR`: o journal SSH não pôde ser consultado.
- Dados não observados são `null`; nunca são convertidos em zero.

## Limites atuais

Não recolhe configuração efetiva através de `sshd -T`, porque o utilizador normal não pode ler todos os ficheiros incluídos.

Não recolhe estado do Fail2Ban, porque o socket administrativo exige privilégios de root.

Estas permissões não serão enfraquecidas para facilitar o Observer.

## Saída e persistência

O módulo escreve JSON em `stdout`.

A captura é responsabilidade de:

`core/capture-observer.sh`

Destino atual:

`data/observer/observer-ssh.json`

A gravação usa ficheiro temporário, validação JSON, permissões `640` e promoção atómica.

## Proibições

O módulo não interpreta os IPs, não chama eventos de ataques, não soma categorias diferentes como “falhas SSH”, não decide e não modifica o servidor.
