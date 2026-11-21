<div lang="pt-PT">

# MPPT24 CORE

O CORE recolhe dados de um sistema Linux, como utilização de CPU, espaço em disco e estado dos serviços. Verifica a qualidade desses dados e produz um relatório que explica os resultados.

## Primeiros passos

- **Perceber um resultado sem instalar.** Se faltarem dados de rede, o CORE pode devolver `UNKNOWN`. Nesse caso, começa por perceber por que falhou a recolha. [Guia de leitura, infográfico e cuidados](GUIA.md)
- **Correr os testes.** Começa pelos requisitos e segue os comandos de validação. A base foi validada em Ubuntu Server 24.04 LTS. [Requisitos](#requisitos) · [Como correr os testes](#valida%C3%A7%C3%A3o)
- **Entender o código.** Segue o percurso desde a recolha até ao relatório final. [Fluxo operacional](#fluxo-operacional)
- **Reportar um problema de segurança.** Consulta o canal e a informação a incluir. [Política de segurança](SECURITY.md)

O código e os testes já estão publicados. O empacotamento e o instalador público continuam em preparação.

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

## Relatórios e documentação técnica

- **O que ficou validado em cada etapa.** Os relatórios de encerramento descrevem o que foi testado nas primeiras versões dos observadores. [Observador do sistema](reports/observer-system-1.0.0.md) · [Observador de SSH](reports/observer-ssh-1.0.0.md)
- **Como ler um relatório JSON.** A especificação explica os campos, os possíveis estados e o grau de confiança. [Especificação comum](SPECIFICATION.md#estrutura-do-relatório)
- **Como as peças trabalham em conjunto.** A arquitetura descreve a sequência completa e as responsabilidades dos componentes. [Arquitetura do pipeline](ARCHITECTURE.md)

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
- Git para descarregar o código;
- Python 3;
- Bash;
- `jq` e `ip` (pacote `iproute2`);
- `jsonschema` para Python;
- systemd para a integração operacional.

## Validação

A regressão oficial abrange captura, manifesto, registo, Runner, Decision Engine, serialização, snapshot e contratos de relatório e saúde.

Podes consultar os resultados no GitHub sem instalar nada. Para repetir a verificação, usa um ambiente Linux de teste. Os comandos abaixo instalam apenas as dependências e executam os testes a partir da pasta do código. [Ver a execução dos testes do CORE](https://github.com/mppt24/mppt24-core/actions/runs/44919951511)

Em Ubuntu Server 24.04 LTS, instala as dependências com:

```bash
sudo apt-get install iproute2 jq python3-jsonschema
```

Se ainda não tens o código, descarrega-o com `git clone https://github.com/mppt24/mppt24-core.git` e entra na pasta com `cd mppt24-core`. Aí, executa os conjuntos de testes:

```bash
bash tests/run-contract-tests.sh
```

No fim, procura a linha que começa por `Suites:`. Se indicar `falhas: 0`, os conjuntos de testes passaram. Se houver falhas, procura acima o nome do primeiro teste que falhou e guarda a mensagem de erro com a versão em uso.

O mesmo comando corre no [GitHub Actions](https://github.com/mppt24/mppt24-core/actions/workflows/contracts.yml). As suites usam ficheiros temporários e fixtures sintéticas. Os testes de integração dos observadores fazem leituras locais do sistema.

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

</div>
