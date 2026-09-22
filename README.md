# MPPT24 CORE

MPPT24 CORE é uma plataforma modular para observar sistemas Linux, validar os dados recolhidos e produzir decisões técnicas justificáveis.

O sistema separa rigorosamente observação, validação, histórico e decisão. Quando os dados são insuficientes ou incoerentes, o resultado é `UNKNOWN`, em vez de uma conclusão inventada.

## Princípios

1. Observar o sistema operativo.
2. Preservar os factos recolhidos.
3. Validar antes de interpretar.
4. Separar factos, análise e conclusões.
5. Explicar todas as decisões.
6. Não executar ações administrativas automaticamente.
7. Tratar ausência ou incoerência de dados como informação relevante.

## Estado atual

A implementação incluída neste repositório corresponde a uma base operacional validada:

- sete observers oficiais;
- Observer Runner 2.0.0;
- Historian 2.0.0;
- Decision Engine 3.0.0;
- pipeline operacional através de systemd;
- contratos e schemas versionados;
- geração e promoção atómicas;
- validação estrutural e semântica;
- relatórios JSON determinísticos;
- testes de contrato e regressão.

Os sete observers oficiais são:

- `observer-cpu`;
- `observer-memory`;
- `observer-network`;
- `observer-services`;
- `observer-ssh`;
- `observer-storage`;
- `observer-system`.

## Fluxo operacional

1. Os observers recolhem factos.
2. A fronteira de captura valida cada relatório.
3. O Observer Runner cria uma geração isolada.
4. O manifesto descreve integralmente a geração.
5. O validador produz um snapshot validado.
6. O Historian preserva o resultado.
7. O Decision Engine produz o relatório final.

Uma geração só pode ser promovida depois de cumprir os contratos de estrutura, identidade, permissões e coerência semântica.

## Decision Engine 3.0.0

O Decision Engine recebe exclusivamente um snapshot validado e produz os seguintes domínios de saúde:

- `overall`;
- `system`;
- `security`;
- `resources`;
- `connectivity`;
- `services`.

Os estados possíveis são:

- `OK`;
- `WARNING`;
- `ERROR`;
- `UNKNOWN`.

O relatório final separa factos, análise, conclusões, resumo, recomendações, avisos e erros.

## Segurança

A implementação aplica, entre outras, as seguintes fronteiras:

- rejeição de ligações simbólicas em caminhos determinantes;
- leitura limitada e validação estrita de UTF-8;
- limites de tamanho e profundidade de JSON;
- rejeição de chaves JSON duplicadas;
- rejeição de números não finitos;
- schemas locais sem resolução através da rede;
- execução isolada do validador;
- ambiente mínimo para subprocessos;
- limites independentes para `stdout` e `stderr`;
- timeout e terminação do grupo de processos;
- publicação atómica de gerações;
- permissões finais restritivas;
- validação da correspondência entre manifesto e relatórios.

A edição pública não inclui palavras-passe, tokens, chaves privadas nem relatórios operacionais reais.

## Estrutura do repositório

- `config/` — configuração e registo autorizado de observers;
- `core/` — captura, validação de contratos e pipeline;
- `decision/` — contratos e motores de decisão;
- `historian/` — persistência do histórico operacional;
- `observer/` — módulos de observação;
- `runner/` — execução isolada e construção de gerações;
- `schemas/` — schemas JSON versionados;
- `systemd/` — unidades do pipeline;
- `tests/` — testes de contrato, regressão e fixtures sintéticas.

Os dados produzidos durante a execução não fazem parte do código-fonte publicado.

## Requisitos

A base foi desenvolvida e validada em Ubuntu Server 24.04 LTS.

Principais requisitos:

- Linux;
- Python 3;
- Bash;
- `jq`;
- `jsonschema` para Python;
- systemd para a integração operacional.

## Validação

A regressão oficial abrange captura, manifesto, registo, Runner, Decision Engine, serialização, snapshot e contratos de relatório e saúde.

A validação deve ser executada antes de qualquer instalação ou promoção.

Exemplo:

```bash
python3 -I tests/decision-engine-3-contract-test.py
```

A integração operacional deve ser validada num ambiente isolado antes de ser utilizada num servidor de produção.

## Instalação

A instalação automatizada e o empacotamento ainda estão em preparação.

Até existir um instalador público validado, este repositório deve ser tratado como código-fonte técnico e não como um comando de instalação direta em produção.

## Privacidade

As fixtures incluídas nos testes são sintéticas. Relatórios reais produzidos por um servidor nunca devem ser adicionados ao Git.

As regras de exclusão abrangem artefactos de execução em:

- `data/observer/`;
- `data/history/`;
- `__pycache__/`.

## Autor

Marco Paulo Peixoto Teixeira — MPPT24.

## Licença

Este projeto é disponibilizado sob a GNU Affero General Public License, versão 3. Consulte [LICENSE](LICENSE).
