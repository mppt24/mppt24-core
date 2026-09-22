# MPPT24 CORE
# Decision Engine Contract
# Version: 2.3.0

## Objetivo

O Decision Engine interpreta os relatórios produzidos pelos Observers e
constrói uma visão consolidada do estado do sistema.

O Decision Engine:

- não observa diretamente o sistema operativo;
- não executa comandos de diagnóstico no sistema;
- não altera configurações, serviços ou dados operacionais;
- não toma decisões pelo administrador;
- não inventa factos ausentes.

A decisão final pertence sempre ao administrador humano.

## Entrada

A entrada operacional é constituída pelos ficheiros:

`data/observer/observer-*.json`

Cada relatório deve fornecer, no mínimo:

- `module`;
- `status`;
- `facts`.

O nome de cada módulo deve ser uma string não vazia e única no conjunto
de relatórios.

Os estados técnicos reconhecidos são:

- `OK`;
- `WARNING`;
- `ERROR`;
- `UNKNOWN`.

Quando nenhum relatório de Observer é encontrado, o processamento falha
explicitamente.

## Agregação de estados

O estado global é determinado pela seguinte prioridade:

1. `ERROR`, quando existe pelo menos um Observer em `ERROR`;
2. `WARNING`, quando não existe `ERROR` e existe pelo menos um `WARNING`;
3. `UNKNOWN`, quando não existe `ERROR` nem `WARNING` e existe um estado
   ausente ou desconhecido;
4. `OK`, quando todos os Observers estão em `OK`.

## Saída

O Decision Engine escreve em `stdout` um relatório JSON normalizado.

A saída contém os campos:

- `module`;
- `version`;
- `timestamp`;
- `status`;
- `confidence`;
- `facts`;
- `analysis`;
- `conclusions`;
- `health`;
- `summary`;
- `recommendations`;
- `warnings`;
- `errors`.

`module` deve ser `decision-engine`.

`version` deve corresponder à versão declarada pelo módulo.

`status` só pode ser `OK`, `WARNING`, `ERROR` ou `UNKNOWN`.

`confidence` é um inteiro entre `0` e `100`.

`facts` e `health` são objetos JSON.

`analysis`, `conclusions`, `summary`, `recommendations`, `warnings` e
`errors` são listas de texto.

## Contrato de health

O objeto `health` do Decision Engine deve conter, no mínimo, os domínios:

- `overall`;
- `system`;
- `security`;
- `resources`;
- `connectivity`;
- `services`.

Cada domínio é um objeto com um campo `status`.

O valor de `status` só pode ser:

- `OK`;
- `WARNING`;
- `ERROR`;
- `UNKNOWN`.

Os nomes dos domínios não podem ser vazios e um domínio não pode ser
definido mais de uma vez.

O estado de `health.overall.status` deve ser igual ao campo `status` do
relatório.

O domínio `overall` representa a agregação dos estados técnicos dos
Observers. Os restantes domínios representam interpretações específicas
dos factos recolhidos e podem indicar atenção adicional.

## Domínio system

O domínio `system` utiliza o estado do `observer-system` e os factos:

- `time_available`;
- `ntp_enabled`;
- `ntp_synchronized`.

Regras:

1. `observer-system = ERROR` produz `system = ERROR`;
2. `observer-system = WARNING` produz `system = WARNING`;
3. estado ausente ou desconhecido produz `system = UNKNOWN`;
4. `observer-system = OK` com factos temporais ausentes, inválidos ou
   incoerentes produz `system = UNKNOWN`;
5. `observer-system = OK` com NTP desativado ou não sincronizado produz
   `system = WARNING`;
6. `observer-system = OK` com fonte temporal disponível, NTP ativado e
   sincronizado produz `system = OK`.

Valores booleanos `false` são factos válidos e não podem ser confundidos
com valores ausentes.

## Restantes domínios

- `security` interpreta disponibilidade do journal e eventos SSH;
- `resources` interpreta carga, memória e swap;
- `connectivity` interpreta LAN, gateway predefinido e VPNs esperadas;
- `services` interpreta os serviços essenciais monitorizados.

Quando os factos necessários são insuficientes ou inválidos, o domínio
correspondente deve devolver `UNKNOWN`.

## Regras de integridade

1. Nunca inventar factos.
2. Nunca ocultar erros de entrada ou validação.
3. Distinguir factos, análise, conclusões e recomendações.
4. Preservar valores booleanos `true` e `false`.
5. Rejeitar módulos duplicados.
6. Rejeitar domínios de health duplicados.
7. Rejeitar estados de health inválidos.
8. Não executar alterações no sistema.
9. A decisão final pertence sempre ao administrador humano.

## Fluxo

Observers
    ↓
Decision Engine
    ↓
Human
