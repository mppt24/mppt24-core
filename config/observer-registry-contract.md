# MPPT24 CORE — Contrato do Registo de Observers

Estado do documento: APROVADO
Versão do documento: 1.0.0
Versão do registo: 1.0.0
Data: 16 de agosto de 2026

## 1. Objetivo

Este documento define o formato, a autoridade e as regras de validação do Registo
de Observers da MPPT24 CORE.

O registo declara explicitamente os únicos Observers autorizados a participar no
pipeline.

A presença de um executável no diretório `observer/` não concede autorização
para execução.

O registo:

- não executa Observers;
- não recolhe factos;
- não altera relatórios;
- não modifica o sistema observado;
- não persiste dados operacionais;
- não substitui o contrato de saída dos módulos.

## 2. Autoridade

A arquitetura do pipeline está definida em `ARCHITECTURE.md`, versão 1.0.0.

O contrato serializado de relatório suportado é o 2.1.0.

Os Observers preservados nesta fase declaram versão 1.0.0.

Quando existir divergência entre o registo, o schema, um executável ou os
contratos aprovados, o Observer não deve ser autorizado até o conflito ser
analisado e resolvido explicitamente.

## 3. Artefactos e localização

Os artefactos oficiais são:

- registo: `config/observer-registry.json`;
- schema: `schemas/observer-registry/1.0.0/observer-registry.schema.json`;
- contrato: `config/observer-registry-contract.md`;
- testes: `tests/observer-registry-contract-test.py`.

Todos os caminhos são relativos à raiz do projeto.

O caminho do registo e o caminho do schema são determinados pela instalação do
projeto. Não são substituídos por entrada arbitrária durante a execução
operacional.

O registo não pode exceder 65536 bytes.

## 4. Formato do documento

O registo é um único documento JSON codificado em UTF-8.

O objeto de topo contém exatamente:

- `registry_version`;
- `report_contract`;
- `limits`;
- `observers`.

Propriedades de topo desconhecidas são rejeitadas.

`registry_version` é exatamente `1.0.0`.

`report_contract` é exatamente `2.1.0`.

`limits` declara os limites operacionais comuns a todos os Observers registados.

`observers` é uma lista ordenada, não vazia e limitada ao número máximo
declarado em `limits`.

A ordem da lista é normativa e será a ordem de execução do futuro Runner 2.0.0.

## 5. Entrada de Observer

Cada entrada de `observers` contém exatamente:

- `module`;
- `executable`;
- `required`;
- `module_versions`;
- `output_contract`.

Propriedades desconhecidas são rejeitadas.

`module` é um nome normalizado segundo o contrato de relatório 2.1.0.

`executable` é o caminho relativo do executável autorizado.

`required` é um booleano e declara se a falha ou ausência do módulo impede uma
geração `COMPLETE`.

`module_versions` é uma lista não vazia de versões SemVer explicitamente
suportadas.

`output_contract` identifica a versão exata do contrato serializado produzido
pelo Observer.

Nesta versão, cada entrada declara:

- `required` igual a `true`;
- `module_versions` igual a `["1.0.0"]`;
- `output_contract` igual a `2.1.0`.

Os valores de `module` e `executable` são únicos no registo.


## 6. Regras de caminho

Cada `executable`:

- é uma string não vazia;
- usa separadores `/`;
- é relativo à raiz do projeto;
- não começa por `/`;
- não contém componentes vazios, `.` ou `..`;
- não contém barras consecutivas;
- não termina com `/`;
- segue exatamente o formato `observer/<module>.sh`.

O nome do ficheiro deve corresponder ao valor de `module`.

Durante a validação contra a instalação, o caminho deve identificar:

- um ficheiro regular;
- um ficheiro executável;
- um ficheiro que não seja link simbólico.

O registo não contém comandos de shell, argumentos, expansões, variáveis de
ambiente ou caminhos alternativos.

Um consumidor não procura substitutos quando o caminho registado está ausente ou
inválido.

## 7. Limites operacionais

`limits` contém exatamente:

- `observer_timeout_seconds`;
- `stdout_max_bytes`;
- `stderr_max_bytes`;
- `report_max_bytes`;
- `json_max_depth`;
- `max_observers`.

Os valores da versão 1.0.0 são:

- `observer_timeout_seconds`: `30`;
- `stdout_max_bytes`: `262144`;
- `stderr_max_bytes`: `65536`;
- `report_max_bytes`: `262144`;
- `json_max_depth`: `32`;
- `max_observers`: `32`.

Os limites são obrigatórios, positivos e expressos como inteiros JSON.

Nenhum consumidor pode aumentar estes valores silenciosamente.

Um limite excedido causa falha explícita. Saídas aceites não são truncadas.

O limite total do ciclo, o tamanho do manifesto, o espaço livre mínimo e as
regras de durabilidade pertencem ao futuro contrato do Runner 2.0.0.

## 8. Observers autorizados

A versão 1.0.0 contém exatamente, por esta ordem:

1. `observer-cpu` — `observer/observer-cpu.sh`;
2. `observer-memory` — `observer/observer-memory.sh`;
3. `observer-network` — `observer/observer-network.sh`;
4. `observer-services` — `observer/observer-services.sh`;
5. `observer-ssh` — `observer/observer-ssh.sh`;
6. `observer-storage` — `observer/observer-storage.sh`;
7. `observer-system` — `observer/observer-system.sh`.

Todos são obrigatórios, suportam exclusivamente a versão de módulo 1.0.0 e
produzem o contrato de relatório 2.1.0.

Adicionar, remover, substituir ou reordenar um Observer exige atualização
explícita do registo, validação do schema, testes e revisão de compatibilidade.

Ficheiros adicionais existentes no diretório `observer/` permanecem não
autorizados.

## 9. Entrada JSON estrita

Antes de aplicar o schema, a validação confirma:

1. que o registo é um ficheiro regular;
2. que o registo não é link simbólico;
3. que o tamanho não excede 65536 bytes;
4. que o conteúdo é UTF-8 válido;
5. que existe exatamente um documento JSON;
6. que não existem chaves duplicadas em nenhum objeto;
7. que não existem `NaN`, `Infinity` ou `-Infinity`.

O documento é rejeitado integralmente quando qualquer verificação falha.

A validação não remove campos, não converte tipos e não normaliza valores.

## 10. Schema

O schema declara exatamente:

- dialecto `https://json-schema.org/draft/2020-12/schema`;
- identificador `urn:mppt24:schema:observer-registry:1.0.0`.

O próprio schema é validado com `Draft202012Validator.check_schema`.

O schema utiliza apenas referências internas ao próprio documento.

Referências externas, incluindo referências de rede, são proibidas.

O schema estrutural não substitui as verificações de unicidade entre entradas,
correspondência entre módulo e caminho ou estado real dos executáveis.

## 11. Validação semântica

Depois da validação estrutural, são confirmadas:

- unicidade de `module`;
- unicidade de `executable`;
- correspondência exata entre `module` e o nome do executável;
- ordem normativa dos sete Observers;
- quantidade de entradas não superior a `max_observers`;
- compatibilidade explícita das versões;
- igualdade entre o contrato de saída da entrada e `report_contract`;
- presença exata dos limites da versão 1.0.0.

Uma versão desconhecida não é aceite por semelhança estrutural.

Não existe conversão, preenchimento de valores omitidos ou herança de valores
implícitos.

## 12. Validação contra a instalação

Para cada entrada, os testes confirmam que o executável:

- existe sob a raiz do projeto;
- permanece dentro do diretório `observer/`;
- é um ficheiro regular;
- não é link simbólico;
- possui permissão de execução;
- declara o mesmo nome de módulo;
- declara uma versão presente em `module_versions`;
- produz um relatório compatível com `output_contract`;
- termina dentro de `observer_timeout_seconds`;
- respeita os limites de saída e profundidade.

A validação usa o validador oficial do relatório 2.1.0.

A execução de compatibilidade utiliza apenas diretórios temporários e não
persiste relatórios em `data/`, staging ou gerações.

Um Observer registado que não cumpra estas verificações causa falha explícita.

Um Observer não registado nunca é executado apenas para determinar se poderia ser
compatível.

## 13. Testes obrigatórios

Os testes devem cobrir:

- JSON e UTF-8 válidos;
- schema Draft 2020-12 válido;
- identidade e dialecto exatos do schema;
- ausência de referências externas;
- registo oficial válido;
- tamanho máximo do registo;
- campo obrigatório ausente;
- propriedade desconhecida;
- tipo incorreto;
- versão de registo incompatível;
- contrato de relatório incompatível;
- limites ausentes, incorretos ou não inteiros;
- lista vazia ou acima de `max_observers`;
- módulo inválido ou duplicado;
- caminho inválido ou duplicado;
- caminho absoluto;
- componentes `.` e `..`;
- barras consecutivas;
- divergência entre módulo e nome do executável;
- entrada obrigatória, versão ou contrato incorretos;
- ordem incorreta;
- executável ausente;
- diretório em vez de ficheiro;
- link simbólico;
- ficheiro sem permissão de execução;
- identidade ou versão declarada divergente;
- sete Observers oficiais;
- compatibilidade dos relatórios com o contrato 2.1.0;
- limites reais de duração, saída e profundidade;
- importação dos testes sem efeitos operacionais.

Os testes não modificam Observers, Runner, capturador ou dados operacionais.

## 14. Consumo do registo

Um consumidor:

1. localiza o registo oficial;
2. verifica o tipo, o link simbólico e o tamanho;
3. lê exatamente um documento JSON estrito;
4. valida o schema;
5. aplica as regras semânticas;
6. valida os caminhos contra a instalação;
7. usa apenas a lista ordenada resultante.

Uma falha em qualquer etapa impede a utilização parcial do registo.

O consumidor não adiciona módulos encontrados no sistema de ficheiros.

O consumidor não altera o registo, o schema ou os executáveis para resolver uma
incompatibilidade.

A aprovação deste contrato não autoriza o Runner 1.1.0 nem o capturador atual a
consumirem o registo. Essa integração pertence às fases D e E.

## 15. Compatibilidade

A versão 1.0.0 do registo suporta:

- Observers 1.0.0 explicitamente listados;
- contrato serializado de relatório 2.1.0;
- schema do registo 1.0.0.

A versão do registo, a versão do módulo e a versão do contrato de saída são
identidades diferentes.

Alterar a semântica de campos existentes exige revisão de versão segundo SemVer.

Uma futura aceitação de novas versões de módulo exige matriz explícita,
documentação e testes.

## 16. Critérios de aceitação

A versão 1.0.0 só pode ser promovida quando:

- o contrato estiver completo e aprovado;
- o registo contiver exatamente os sete Observers autorizados;
- o schema passar `Draft202012Validator.check_schema`;
- o registo passar validação estrutural e semântica;
- todos os caminhos oficiais forem válidos;
- os sete Observers declararem identidade e versão compatíveis;
- os sete relatórios passarem o validador 2.1.0;
- todos os testes desta fase passarem;
- Report API mantiver `PASS=125 FAIL=0`;
- contrato health mantiver `PASS=28 FAIL=0`;
- contrato serializado mantiver todos os testes aprovados;
- nenhum Observer for modificado;
- Runner e capturador permanecerem inalterados;
- não existirem escritas em dados operacionais;
- o diff contiver apenas alterações aprovadas;
- o administrador humano validar o resultado.

Um teste falhado impede a promoção.

## 17. Evolução

Este documento permaneceu `DRAFT` durante a implementação e os testes.

A versão 1.0.0 foi aprovada após revisão integral, resultados sem falhas e
aprovação explícita.

Uma versão publicada não é alterada retroativamente.

A aprovação do registo não autoriza a execução operacional do novo pipeline.
