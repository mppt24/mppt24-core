# Guia de MPPT24 CORE

**Estado:** Base pública validada.

Pipeline Linux de observação, validação e decisão.

[![MPPT24 CORE. README e arquitetura. 9 suites de contrato. Usar dados de teste.](docs/guia-visual.png)](docs/guia-visual.png)

## Onde começar

Começa pelo exemplo abaixo para perceber um resultado. Para ver a sequência desde a recolha de dados até ao relatório, lê os [primeiros passos do CORE](README.md#primeiros-passos). Para aprofundar, abre a [arquitetura técnica](ARCHITECTURE.md).

## Como confirmar

Num ambiente Linux de teste, executa `bash tests/run-contract-tests.sh` depois de instalar os requisitos do README.

## Como ler os registos

Em **Actions**, abre «Contratos MPPT24 CORE». Procura a linha final `Suites: 9; falhas: 0`. `UNKNOWN` num relatório significa que faltam dados para concluir.

### Exemplo fictício

```text
OK · Suites: 9 · Falhas: 0
```

Uma suite é um conjunto de testes relacionados. «Falhas: 0» diz respeito aos testes dessa execução. Num relatório do sistema, `UNKNOWN` significa que falta informação. Por exemplo, sem dados fiáveis da ligação, começa por rever a recolha em vez de interpretar o resultado como uma falha da rede. [Ver a execução dos testes do CORE](https://github.com/mppt24/mppt24-core/actions/runs/44919951511)

## Cuidados

A suite usa fixtures sintéticas, mas alguns observadores fazem leituras locais. Não publiques relatórios operacionais. O instalador público ainda está em evolução.
