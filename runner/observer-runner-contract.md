# MPPT24 CORE — Contrato do Runner e das Gerações

Estado do documento: APROVADO
Versão do documento: 1.0.0
Versão do Runner: 2.0.0
Versão do manifesto: 1.0.0
Data: 16 de agosto de 2026

## 1. Objetivo

Este documento define o contrato do Runner 2.0.0, o armazenamento das gerações
e o manifesto de geração 1.0.0 da MPPT24 CORE.

A aprovação inicial deste documento corresponde à subfase E1 da arquitetura.

A subfase E1 define e testa:

- a estrutura lógica de armazenamento;
- o identificador de geração;
- o formato do manifesto;
- o schema do manifesto;
- a validação estrutural e semântica;
- as regras de coerência entre manifesto e ficheiros;
- as condições necessárias à futura promoção.

A subfase E1 não implementa nem ativa o Runner 2.0.0.

A implementação do Runner pertence à subfase E2 e não pode alterar
silenciosamente o contrato aprovado em E1.

## 2. Autoridade e componentes preservados

A arquitetura do pipeline está definida em `ARCHITECTURE.md`, versão 1.0.0.

Este contrato depende dos seguintes contratos aprovados:

- Report API 2.1.0;
- contrato serializado de relatório 2.1.0;
- Registo de Observers 1.0.0;
- Capturador de Observers 1.0.0;
- resultado estruturado do Capturador 1.0.0.

Permanecem inalterados durante E1:

- `runner/observer-runner.sh`;
- `historian/historian.sh`;
- `MANIFESTO.md`;
- os sete Observers 1.0.0;
- o Decision Engine 2.3.0;
- os dados em `data/`.

## 3. Artefactos da subfase E1

Os artefactos oficiais de E1 são:

- contrato:
  `runner/observer-runner-contract.md`;
- schema:
  `schemas/generation-manifest/1.0.0/generation-manifest.schema.json`;
- validador:
  `core/validate-manifest.py`;
- testes:
  `tests/generation-manifest-contract-test.py`;
- fixtures:
  `tests/fixtures/generation-manifest-1.0.0/`.

O manifesto de cada geração chama-se exatamente `manifest.json`.

O documento humano `MANIFESTO.md` não é um manifesto de geração e não é
substituído, renomeado ou reinterpretado por este contrato.

O schema, o validador e os testes pertencem a E1.

O novo executável do Runner e a sua ativação pertencem exclusivamente a E2.

## 4. Raízes lógicas

O contrato distingue:

- `PROJECT_ROOT`, que contém código e contratos versionados;
- `STATE_ROOT`, que contém gerações e a referência atual;
- `RUNTIME_ROOT`, que contém o bloqueio e artefactos transitórios do Runner.

E1 não define nem ativa caminhos operacionais físicos para `STATE_ROOT` ou
`RUNTIME_ROOT`.

Durante testes, estas raízes são diretórios temporários absolutos e isolados.

Nenhum caminho do contrato depende de `/home/mppt24`.

O código em `PROJECT_ROOT` não é usado como armazenamento operacional.

## 5. Estrutura de STATE_ROOT

A estrutura lógica é:

    STATE_ROOT/
    ├── current-generation
    └── generations/
        ├── <generation_id>/
        │   ├── manifest.json
        │   └── observers/
        │       └── <module>.json
        └── .staging-<generation_id>/
            └── observers/

Uma geração promovida contém exatamente:

- `manifest.json`;
- `observers/`;
- os relatórios declarados no manifesto.

Uma staging em construção contém apenas os objetos temporários previstos pelo
contrato e nunca é tratada como geração promovida.

O manifesto é criado apenas depois de terminarem todas as tentativas de captura.

A staging e o destino promovido pertencem ao mesmo diretório `generations/` e,
por consequência, ao mesmo sistema de ficheiros.

## 6. Objetos proibidos

Uma geração ou staging não contém:

- links simbólicos;
- hard links deliberados;
- sockets;
- dispositivos;
- FIFOs;
- caminhos que escapem à geração;
- backups;
- caches;
- relatórios não declarados;
- ficheiros temporários depois da promoção;
- dados copiados de gerações anteriores.

Objetos desconhecidos ou inesperados impedem a validação e a promoção.

## 7. Identificador de geração

`generation_id` segue exatamente:

    YYYYMMDDTHHMMSSffffffZ-<32 hexadecimal minúsculos>

A expressão regular é:

    ^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$

Exemplo:

    20260816T233109123456Z-0123456789abcdef0123456789abcdef

A parte temporal contém:

- ano, mês e dia;
- hora, minuto e segundo;
- seis algarismos de microssegundos;
- marcador literal `Z` para UTC.

O sufixo contém 128 bits representados por 32 algarismos hexadecimais
minúsculos.

A data e a hora devem ser semanticamente válidas.

A parte temporal de `generation_id` corresponde exatamente a `started_at`,
apenas sem separadores e sem o ponto dos microssegundos.

O identificador:

- é um único nome de diretório;
- não contém `/`, `.` como componente, `..`, espaços ou caracteres de controlo;
- não é aceite apenas por corresponder à expressão regular;
- é validado semanticamente antes de ser usado num caminho;
- não constitui segredo.

O nome da staging é exatamente `.staging-<generation_id>`.

O nome da geração promovida é exatamente `<generation_id>`.

Uma colisão de qualquer destes nomes causa falha estrutural. Um nome existente
não é substituído nem reutilizado.

## 8. Formato temporal

`started_at` e `completed_at` usam exatamente:

    YYYY-MM-DDTHH:MM:SS.ffffffZ

Os valores:

- são codificados em UTC;
- contêm sempre seis algarismos de microssegundos;
- são semanticamente válidos;
- não aceitam offsets alternativos;
- não aceitam segundos intercalares;
- não dependem do locale.

`completed_at` não pode ser anterior a `started_at`.

O Runner mede durações operacionais com relógio monotónico. Os timestamps UTC
identificam o ciclo, mas não substituem o relógio monotónico para limites.

## 9. Permissões e tipos

Os limites máximos de permissões são:

- `STATE_ROOT`: `0750`;
- `generations/`: `0750`;
- staging e `observers/` durante construção: `0750`;
- ficheiros durante construção: `0640`;
- geração e `observers/` depois da promoção: `0550`;
- `manifest.json` e relatórios promovidos: `0440`;
- `current-generation`: `0640`.

Nenhum objeto pode ser gravável por `other`.

Os relatórios e o manifesto são ficheiros regulares com exatamente um hard link.

Os diretórios esperados são diretórios reais e não links simbólicos.

A futura implementação confirma tipos e identidades através de descritores
sempre que a operação depender da continuidade do mesmo objeto.

E1 testa estas regras apenas em raízes temporárias.

## 10. Referência current-generation

`current-generation` é um ficheiro de texto regular e não um link simbólico.

O conteúdo é exatamente:

    <generation_id>\n

A referência não contém caminhos absolutos, componentes livres ou texto
adicional.

A atualização futura usa um ficheiro temporário exclusivo e `rename` dentro de
`STATE_ROOT`.

A geração é promovida antes da atualização da referência.

Uma falha na atualização preserva a geração promovida e a referência anterior.

E1 define e testa o formato da referência, mas não atualiza qualquer referência
operacional.

## 11. Documento do manifesto

O manifesto é um único documento JSON codificado em UTF-8.

O ficheiro não pode exceder 262144 bytes.

O objeto de topo contém exatamente:

- `manifest_version`;
- `generation_id`;
- `started_at`;
- `completed_at`;
- `state`;
- `runner`;
- `registry`;
- `summary`;
- `modules`.

Propriedades desconhecidas são rejeitadas.

`manifest_version` é exatamente `1.0.0`.

`state` aceita exatamente:

- `COMPLETE`;
- `PARTIAL`;
- `FAILED`.

O manifesto não contém os factos dos Observers, caminhos absolutos, mensagens
arbitrárias de `stderr` ou o hash de si próprio.

## 12. Identidade do Runner

`runner` contém exatamente:

- `module`;
- `version`.

Nesta versão:

- `module` é exatamente `observer-runner`;
- `version` é exatamente `2.0.0`.

A versão do Runner e a versão do manifesto são identidades independentes.

## 13. Identidade do registo

`registry` contém exatamente:

- `version`;
- `hash_algorithm`;
- `sha256`.

Nesta versão:

- `version` é exatamente `1.0.0`;
- `hash_algorithm` é exatamente `sha256`;
- `sha256` contém 64 algarismos hexadecimais minúsculos.

O hash é calculado sobre os bytes exatos do ficheiro oficial do registo que foi
lido e validado para o ciclo.

O manifesto não incorpora o caminho do registo nem uma cópia do seu conteúdo.

## 14. Resumo

`summary` contém exatamente:

- `declared`;
- `successful`;
- `failed`;
- `reports_written`.

Todos os valores são inteiros JSON não negativos.

As regras são:

- `declared` é igual ao número de entradas em `modules`;
- `declared` é maior que zero;
- `declared` não excede `max_observers` do registo;
- `successful` é igual ao número de entradas `SUCCESS`;
- `failed` é igual ao número de entradas `FAILED`;
- `successful + failed` é igual a `declared`;
- `reports_written` é igual a `successful`.

Os contadores são derivados das entradas e não aceites isoladamente como
verdade.

## 15. Entradas dos módulos

`modules` é uma lista não vazia, ordenada exatamente segundo o registo validado.

Cada entrada contém exatamente:

- `module`;
- `required`;
- `outcome`;
- `error_code`;
- `exit_code`;
- `stdout_bytes`;
- `stderr_bytes`;
- `duration_ms`;
- `report`.

`module` é único e corresponde à entrada do registo na mesma posição.

`required` é igual ao valor do registo.

`outcome` aceita exatamente `SUCCESS` ou `FAILED`.

`stdout_bytes`, `stderr_bytes` e `duration_ms` são inteiros JSON não negativos e
preservam os valores do resultado estruturado do capturador.

`exit_code` preserva `observer_exit_code` do resultado do capturador. É um
inteiro quando existiu código observável e é nulo quando esse código não existe.

Quando `outcome` é `SUCCESS`:

- `error_code` é nulo;
- `exit_code` é `0`;
- `report` contém exatamente um descritor válido;
- o resultado correspondente do capturador tinha código `SUCCESS`.

Quando `outcome` é `FAILED`:

- `error_code` contém uma categoria permitida;
- `report` é nulo;
- não existe relatório para esse módulo em `observers/`.

## 16. Códigos de falha registáveis

Os códigos de falha de módulo permitidos no manifesto 1.0.0 são:

- `EXECUTABLE_MISSING`;
- `EXECUTABLE_INVALID`;
- `EXECUTION_FAILED`;
- `EXECUTION_TIMEOUT`;
- `OUTPUT_LIMIT_EXCEEDED`;
- `STDERR_LIMIT_EXCEEDED`;
- `EMPTY_REPORT`;
- `INVALID_JSON`;
- `CONTRACT_VIOLATION`;
- `MODULE_MISMATCH`.

Os nomes preservam exatamente o contrato aprovado do Capturador 1.0.0.

As designações conceptuais `EXECUTABLE_NOT_AUTHORIZED` e `EMPTY_STDOUT`
existentes na arquitetura são concretizadas, respetivamente, por
`EXECUTABLE_INVALID` ou `MODULE_NOT_AUTHORIZED`, conforme a causa, e por
`EMPTY_REPORT`.

`MODULE_NOT_AUTHORIZED` durante uma execução construída a partir do registo
validado revela incoerência estrutural e não é convertido numa falha normal de
módulo.

Os seguintes códigos do capturador causam falha estrutural da tentativa e não são
registados como simples falha de módulo numa geração promovida:

- `USAGE_INVALID`;
- `DEPENDENCY_UNAVAILABLE`;
- `REGISTRY_INVALID`;
- `MODULE_NOT_AUTHORIZED`;
- `STAGING_INVALID`;
- `TEMPORARY_PERSISTENCE_FAILED`;
- `INTERNAL_ERROR`.

Uma falha estrutural impede a construção ou promoção da geração.

Não existe tradução baseada em mensagens humanas ou conteúdo arbitrário de
`stderr`.

## 17. Descritor do relatório

Quando uma entrada tem `outcome` igual a `SUCCESS`, `report` contém exatamente:

- `path`;
- `module`;
- `contract_version`;
- `version`;
- `timestamp`;
- `status`;
- `size_bytes`;
- `sha256`.

`path` é exatamente:

    observers/<module>.json

O caminho:

- é relativo à raiz da geração;
- usa `/`;
- não contém componentes vazios, `.` ou `..`;
- não é absoluto;
- corresponde exatamente ao campo `module`.

`module`, `version`, `timestamp` e `status` são obtidos do relatório validado e
coincidem com os seus valores.

`contract_version` é exatamente `2.1.0`.

`version` pertence a `module_versions` da entrada correspondente do registo.

`timestamp` segue o contrato serializado de relatório 2.1.0.

`status` aceita exatamente:

- `OK`;
- `WARNING`;
- `ERROR`;
- `UNKNOWN`.

`size_bytes` é um inteiro JSON positivo e corresponde ao tamanho exato dos bytes
do ficheiro.

`sha256` contém 64 algarismos hexadecimais minúsculos e corresponde ao hash dos
bytes exatos do relatório.

O relatório é um ficheiro regular, não é link simbólico e possui exatamente um
hard link.

## 18. Coerência do estado

O estado é derivado das entradas:

- `COMPLETE`: `successful` é igual a `declared`;
- `PARTIAL`: `successful` é maior que zero e menor que `declared`;
- `FAILED`: `successful` é zero.

Uma geração `COMPLETE` contém um relatório válido para cada módulo declarado.

Uma geração `PARTIAL` contém pelo menos um relatório válido e identifica
explicitamente todas as falhas.

Uma geração `FAILED` não contém relatórios de Observers, mas contém um manifesto
válido e fiável da tentativa.

O campo `required` não altera estas três fórmulas na versão 1.0.0. Preserva a
classificação do registo para consumidores e evolução futura.

Uma incoerência entre `state`, `summary` ou `modules` invalida o manifesto.

## 19. Coerência com o registo

A validação utiliza o Registo de Observers 1.0.0 oficial e previamente validado.

O manifesto contém exatamente uma entrada por Observer registado, pela mesma
ordem.

Para cada posição:

- `module` coincide com o registo;
- `required` coincide com o registo;
- um relatório de sucesso usa uma versão presente em `module_versions`;
- `contract_version` coincide com `output_contract`.

O hash em `registry.sha256` coincide com os bytes exatos do registo validado.

A versão do registo coincide com `registry.version`.

Um módulo adicional, ausente, duplicado ou reordenado invalida o manifesto.

## 20. Coerência com a geração

O validador recebe um diretório de geração ou staging e um
`generation_id` esperado.

O nome do diretório é exatamente um dos seguintes:

- `<generation_id>`;
- `.staging-<generation_id>`.

A raiz validada contém exatamente:

- `manifest.json`;
- `observers/`.

`observers/` contém exatamente os relatórios associados a entradas `SUCCESS`.

Cada relatório:

- aparece exatamente uma vez no manifesto;
- existe no caminho declarado;
- é um ficheiro regular;
- não é link simbólico;
- possui exatamente um hard link;
- não excede o limite de relatório do registo;
- possui tamanho igual a `size_bytes`;
- possui hash igual a `sha256`;
- passa o validador oficial do relatório 2.1.0;
- declara a mesma identidade, versão, timestamp e estado do descritor.

Uma entrada `FAILED` não possui relatório.

Um relatório adicional, ausente, duplicado, adulterado ou colocado noutro
caminho invalida a geração.

O manifesto e `observers/` não podem ser substituídos ou mudar durante a
validação.

## 21. Entrada JSON estrita

Antes de aplicar o schema, o validador confirma:

1. que `manifest.json` é um ficheiro regular;
2. que não é link simbólico;
3. que possui exatamente um hard link;
4. que não excede 262144 bytes;
5. que o conteúdo é UTF-8 válido;
6. que existe exatamente um documento JSON;
7. que não existem chaves duplicadas;
8. que não existem `NaN`, `Infinity` ou `-Infinity`;
9. que a profundidade não excede 32.

O documento é rejeitado integralmente quando qualquer verificação falha.

O validador não remove campos, converte tipos, preenche valores ou normaliza
conteúdo.

## 22. Schema do manifesto

O schema usa JSON Schema Draft 2020-12 e declara exatamente:

- dialecto `https://json-schema.org/draft/2020-12/schema`;
- identificador
  `urn:mppt24:schema:generation-manifest:1.0.0`.

O próprio schema é validado antes da utilização.

O schema utiliza apenas referências internas ao próprio documento.

Referências externas, incluindo referências de rede, são proibidas.

Objetos controlados rejeitam propriedades desconhecidas.

As regras relacionais entre tempos, contadores, módulos, registo e ficheiros são
aplicadas pela camada semântica documentada e testada.

## 23. Interface do validador

A interface prevista é:

    validate-manifest.py \
        --expected-generation-id GENERATION_ID \
        GENERATION_DIRECTORY

`GENERATION_DIRECTORY` é um diretório absoluto de geração ou staging.

`--expected-generation-id` é obrigatório e identifica a geração que o chamador
pretende validar.

`--help` apresenta a utilização, termina com código `0` e não valida qualquer
geração.

Cada opção pode aparecer no máximo uma vez.

Argumentos desconhecidos, opções repetidas, diretórios adicionais ou argumentos
ausentes são rejeitados como uso inválido.

A interface não permite substituir:

- o registo oficial;
- o schema do registo;
- o schema do manifesto;
- o schema do relatório;
- o validador oficial do relatório.

Estes caminhos são determinados relativamente à instalação do projeto.

## 24. Validação segura do diretório

`GENERATION_DIRECTORY` deve:

- usar um caminho absoluto;
- existir;
- ser um diretório;
- não ser link simbólico;
- não atravessar componentes que sejam links simbólicos;
- ter nome coerente com `generation_id`;
- permanecer estável durante a validação.

O validador não cria, remove, corrige, renomeia ou altera o diretório recebido.

A validação abre ficheiros com proteção contra links simbólicos quando o sistema
operativo disponibiliza essa capacidade.

Tipo, dispositivo, inode, tamanho e metadados relevantes são confirmados antes e
depois das leituras quando uma mudança possa invalidar a confiança.

## 25. Códigos do validador

Os códigos textuais e os códigos de processo são:

| Código textual | Saída | Significado |
|---|---:|---|
| `SUCCESS` | `0` | geração e manifesto válidos |
| `USAGE_INVALID` | `2` | argumentos inválidos |
| `DEPENDENCY_UNAVAILABLE` | `3` | dependência obrigatória indisponível |
| `SCHEMA_INVALID` | `3` | schema local ausente, inseguro ou inválido |
| `REGISTRY_INVALID` | `3` | registo local ausente, inseguro ou inválido |
| `GENERATION_INVALID` | `4` | diretório ou identificador inseguro |
| `MANIFEST_MISSING` | `5` | `manifest.json` ausente |
| `MANIFEST_UNREADABLE` | `5` | manifesto inseguro ou ilegível |
| `MANIFEST_TOO_LARGE` | `5` | manifesto excede 262144 bytes |
| `INVALID_UTF8` | `5` | manifesto não contém UTF-8 válido |
| `INVALID_JSON` | `5` | documento JSON inválido |
| `DUPLICATE_KEY` | `5` | objeto JSON contém chave duplicada |
| `NON_FINITE_NUMBER` | `5` | número JSON não finito |
| `DEPTH_LIMIT_EXCEEDED` | `5` | profundidade superior a 32 |
| `CONTRACT_VIOLATION` | `6` | manifesto viola o schema |
| `SEMANTIC_VIOLATION` | `7` | relações semânticas incoerentes |
| `GENERATION_MISMATCH` | `8` | ficheiros e manifesto divergem |
| `INTERNAL_ERROR` | `9` | falha interna inesperada |

Um código textual não muda de significado dentro da mesma versão principal.

## 26. Diagnósticos

O sucesso termina sem conteúdo em `stdout` ou `stderr`.

Uma falha prevista produz em `stderr` uma ou mais linhas:

    ERROR<TAB>CODE<TAB>LOCATION<TAB>MESSAGE

`LOCATION` usa JSON Pointer para campos do manifesto e uma localização
controlada para ficheiros.

Erros estruturais do schema são ordenados deterministicamente por localização,
regra e mensagem controlada.

`MESSAGE`:

- é limitada;
- não contém conteúdo arbitrário dos relatórios;
- não reproduz dados arbitrários de `stderr`;
- não inclui caracteres de controlo não autorizados.

O validador não apresenta traceback ao utilizador para uma falha prevista.

## 27. Dependências e isolamento

O validador utiliza apenas:

- Python 3;
- biblioteca padrão do Python;
- pacote Ubuntu `python3-jsonschema`;
- schemas e registo locais aprovados;
- validador oficial do relatório 2.1.0.

Nenhuma dependência é instalada ou descarregada durante a validação.

O validador:

- não abre sockets;
- não consulta DNS;
- não acede à Internet;
- não inicia shell;
- não executa Observers;
- não executa o Runner;
- não escreve na geração;
- não requer privilégios administrativos.

A importação do módulo não executa validação nem produz efeitos operacionais.

## 28. Ordem da validação

A ordem é:

1. argumentos;
2. dependências;
3. identificador esperado;
4. schema do manifesto;
5. registo e schema do registo;
6. diretório da geração;
7. `manifest.json` estrito;
8. schema do manifesto;
9. identidade e tempos;
10. resumo, estado e módulos;
11. coerência com o registo;
12. estrutura do diretório;
13. relatórios declarados;
14. tamanhos e hashes;
15. conteúdo dos relatórios;
16. confirmação final da estabilidade dos objetos.

Uma falha numa etapa impede as etapas que dependem dela.

A validação completa não altera nenhum objeto recebido.

## 29. Fixtures oficiais

As fixtures mínimas são:

- manifesto `COMPLETE` válido;
- manifesto `PARTIAL` válido;
- manifesto `FAILED` válido;
- manifesto com timestamp impossível;
- manifesto com chave duplicada;
- geração com relatório adulterado.

As fixtures não representam uma geração operacional e são usadas apenas em
diretórios temporários durante os testes.

## 30. Testes obrigatórios de E1

Os testes devem cobrir:

- JSON, UTF-8 e schema Draft 2020-12 válidos;
- identidade e dialecto exatos do schema;
- ausência de referências externas;
- ajuda e uso inválido;
- opção repetida;
- identificador válido e inválido;
- data impossível no identificador;
- divergência entre identificador e `started_at`;
- `completed_at` anterior a `started_at`;
- manifesto ausente;
- manifesto como diretório;
- manifesto como link simbólico;
- manifesto com hard link adicional;
- manifesto acima do limite;
- UTF-8 inválido;
- JSON vazio, truncado ou adicional;
- chave duplicada;
- número não finito;
- profundidade acima do limite;
- campo obrigatório ausente;
- propriedade desconhecida;
- tipo incorreto;
- versões incompatíveis;
- estado `COMPLETE`, `PARTIAL` e `FAILED`;
- estado incoerente;
- contadores incoerentes;
- zero módulos;
- módulo ausente, adicional, duplicado ou reordenado;
- divergência de `required`;
- código de falha inválido;
- sucesso sem relatório;
- falha com relatório;
- código de saída incoerente;
- caminho de relatório inválido;
- versão de módulo incompatível;
- relatório ausente ou adicional;
- relatório como diretório ou link simbólico;
- hard link adicional;
- tamanho divergente;
- hash divergente;
- identidade ou metadados divergentes;
- relatório contratualmente inválido;
- hash do registo divergente;
- registo ou schema local inválido;
- diretório relativo;
- geração como ficheiro ou link simbólico;
- componente intermédio como link simbólico;
- objeto desconhecido na raiz;
- objeto desconhecido em `observers/`;
- mudança durante leitura;
- formato de `current-generation`;
- permissões máximas;
- ordem determinística dos diagnósticos;
- importação sem efeitos;
- ausência de rede e shell;
- preservação dos componentes legados.

Todos os testes utilizam cópias e raízes temporárias.

Nenhum teste escreve em `data/`, numa geração real ou numa referência
operacional.

## 31. Critérios de aceitação de E1

E1 só pode ser aprovada quando:

- este contrato estiver completo e aprovado;
- o schema do manifesto passar Draft 2020-12;
- o validador implementar todas as regras documentadas;
- todas as fixtures válidas forem aceites;
- todas as incoerências obrigatórias forem rejeitadas;
- os hashes forem calculados sobre bytes exatos;
- a validação não alterar a geração;
- não existirem acessos de rede;
- não existirem escritas operacionais;
- os contratos anteriores mantiverem todos os testes aprovados;
- Runner, Historian, Observers e Decision Engine permanecerem inalterados;
- o administrador humano validar os resultados.

Um teste falhado impede a aprovação.

A aprovação de E1 não autoriza execução, promoção ou atualização de
`current-generation`.

## 32. Evolução

Este documento permaneceu `DRAFT` durante a implementação e os testes de E1.

A versão 1.0.0 do documento foi aprovada após revisão integral, resultados sem
falhas e aprovação explícita.

O contrato aprovado em E1 torna-se a base obrigatória da implementação E2.

Uma versão publicada não é alterada retroativamente.

A aprovação deste contrato não ativa o Runner 2.0.0 nem modifica componentes
operacionais.
