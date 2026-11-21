# Guia de MPPT24 CORE

**Estado:** Base pública validada.

Pipeline Linux de observação, validação e decisão.

[![MPPT24 CORE. README e arquitetura. 9 suites de contrato. Usar dados de teste.](docs/guia-visual.png)](docs/guia-visual.png)

## Onde começar

Lê [a arquitetura](ARCHITECTURE.md) e os [requisitos do README](README.md#requisitos).

## Como confirmar

Num ambiente Linux de teste, executa `bash tests/run-contract-tests.sh` depois de instalar os requisitos do README.

## Como ler os registos

Em **Actions**, abre «Contratos MPPT24 CORE». Procura a linha final `Suites: 9; falhas: 0`. `UNKNOWN` num relatório significa que faltam dados para concluir.

### Exemplo fictício

```text
OK · Suites: 9 · Falhas: 0
```

Lê pela ordem **resultado**, **etapa** e **detalhe**. Para investigar uma falha, confirma primeiro a data e a versão, depois abre o primeiro passo que falhou.

## Cuidados

A suite usa fixtures sintéticas, mas alguns observadores fazem leituras locais. Não publiques relatórios operacionais. O instalador público ainda está em evolução.
