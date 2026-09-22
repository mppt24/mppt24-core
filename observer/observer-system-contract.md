# Contrato — observer-system

## Identificação

- Módulo: `observer-system`
- Versão atual: `1.0.0`
- Tipo: Observer

## Missão

Observar factos atuais do sistema Linux sem interpretar gravidade, diagnosticar causas ou alterar o servidor.

## Fontes

- `hostnamectl`
- `uname -m`
- `/proc/uptime`
- `/proc/loadavg`
- `/proc/meminfo`
- `lscpu`
- `/sys/class/thermal`
- `timedatectl`

As recolhas devem usar formatos estáveis e, quando necessário, `LC_ALL=C`.

## Factos de disponibilidade das fontes

- `hostnamectl_available`
- `architecture_available`
- `proc_available`
- `cpu_available`
- `memory_available`
- `thermal_available`
- `time_available`

Quando um indicador é `false`, os factos dependentes dessa fonte são `null` e o motivo surge em `warnings` ou `errors`.

## Factos de identificação

- `hostname`
- `operating_system`
- `kernel`
- `architecture`
- `chassis`
- `hardware_vendor`
- `hardware_model`
- `firmware_version`
- `firmware_date`
- `boot_id`

## Factos de execução e CPU

- `uptime_seconds`
- `load_average_1m`
- `load_average_5m`
- `load_average_15m`
- `runnable_tasks`
- `total_tasks`
- `cpu_model`
- `cpu_logical`
- `cpu_sockets`
- `cpu_cores_per_socket`
- `cpu_threads_per_core`

## Factos de memória, temperatura e tempo

- `memory_total_kb`
- `memory_available_kb`
- `swap_total_kb`
- `swap_free_kb`
- `thermal_zones`
- `timezone`
- `ntp_enabled`
- `ntp_synchronized`
- `local_rtc`

Quando disponível, `thermal_zones` é uma lista de objetos com `name` e `temperature_millicelsius`; quando indisponível, é `null`.

## Estados técnicos

- `OK`: todas as fontes foram consultadas.
- `WARNING`: uma fonte secundária — CPU, temperatura ou tempo/NTP — não está disponível.
- `ERROR`: uma fonte essencial impede a observação do sistema.
- Dados não observados são `null`, nunca zero.

## Regras de confiança

- `100`: todas as fontes foram consultadas.
- `90`: temperatura ou tempo/NTP indisponível.
- `85`: topologia da CPU indisponível.
- `40`: uma fonte essencial — identificação, execução/carga ou memória — indisponível.

Quando existem várias limitações, prevalece a menor confiança.

## Limites

O módulo não decide se carga, memória ou temperatura são normais. Não verifica serviços, rede, discos ou segurança; esses factos pertencem a outros Observers.

## Saída e persistência

O módulo escreve JSON em `stdout`.

A captura será feita por `core/capture-observer.sh` para:

`data/observer/observer-system.json`
