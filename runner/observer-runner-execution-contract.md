# MPPT24 CORE — Contrato de Execução do Runner

Estado do documento: APROVADO
Versão do documento: 1.0.0
Versão do Runner: 2.0.0
Data: 18 de agosto de 2026

## 1. Objetivo

Este documento define o contrato de execução do Runner 2.0.0 da MPPT24 CORE.

Corresponde à subfase E2.1 da arquitetura e complementa, sem alterar
retroativamente:

- `ARCHITECTURE.md`, versão 1.0.0;
- `runner/observer-runner-contract.md`, versão 1.0.0;
- o manifesto de geração 1.0.0;
- o Capturador de Observers 1.0.0;
- o Registo de Observers 1.0.0;
- o relatório serializado 2.1.0.

Este contrato resolve as decisões necessárias à implementação E2 que não foram
fixadas na subfase E1.

A aprovação deste documento autoriza a implementação e os testes isolados do
novo Runner, mas não autoriza a sua ativação operacional.

## 2. Âmbito da subfase E2.1

E2.1 define:

- a interface de execução;
- a validação de `STATE_ROOT` e `RUNTIME_ROOT`;
- o bloqueio exclusivo;
- os códigos de processo;
- os limites globais do ciclo;
- a criação da staging;
- a coordenação sequencial do Capturador;
- a construção do manifesto;
- a sincronização e durabilidade;
- a promoção da geração;
- a atualização de `current-generation`;
- o relatório comum do Runner;
- a limpeza limitada;
- as regras de recuperação;
- os testes obrigatórios da implementação.

E2.1 não:

- ativa o Runner;
- cria caminhos operacionais definitivos;
- instala unidades systemd;
- modifica dados operacionais;
- migra artefactos legados;
- altera gerações promovidas;
- implementa o Decision Engine 3.0.0;
- define políticas de retenção.

## 3. Artefactos

Os artefactos previstos da implementação E2 são:

- contrato de execução:
  `runner/observer-runner-execution-contract.md`;
- executável:
  `runner/observer-runner.py`;
- testes:
  `tests/observer-runner-contract-test.py`.

O Runner usa os schemas, validadores, registo e contratos oficiais já
versionados no projeto.

Não é criado um schema separado para o resultado do Runner. O relatório do
Runner segue o contrato serializado 2.1.0.

O executável legado `runner/observer-runner.sh` permanece inalterado.

## 4. Interface

A interface é:

    observer-runner.py \
        --state-root STATE_ROOT \
        --runtime-root RUNTIME_ROOT

`--state-root` e `--runtime-root` são obrigatórios.

Cada opção pode aparecer no máximo uma vez.

Não são aceites argumentos posicionais ou opções desconhecidas.

`--help` apresenta a utilização, termina com código `0` e não inicia um ciclo.

As duas raízes são fornecidas através de caminhos absolutos.

Não existem valores operacionais implícitos ou dependentes de
`/home/mppt24`.

Durante desenvolvimento e testes, as raízes pertencem exclusivamente a
diretórios temporários isolados.

Os caminhos físicos operacionais pertencem à Fase H e exigem aprovação
separada.

## 5. Validação das raízes

`STATE_ROOT` e `RUNTIME_ROOT`:

- existem antes do início do ciclo;
- são diretórios reais;
- não são links simbólicos;
- não atravessam componentes que sejam links simbólicos;
- são propriedade do utilizador efetivo do Runner;
- permitem leitura, escrita e travessia ao proprietário;
- não possuem permissões superiores a `0750`;
- não são graváveis por `other`;
- permanecem com a mesma identidade durante o ciclo.

As duas raízes são distintas.

Nenhuma raiz pode estar contida na outra.

O Runner não cria, substitui ou corrige as raízes recebidas.

`STATE_ROOT` contém exatamente:

- `generations/`;
- opcionalmente, `current-generation`.

`generations/`:

- existe antes do início do ciclo;
- é um diretório real;
- não é link simbólico;
- pertence ao utilizador efetivo;
- não possui permissões superiores a `0750`;
- pertence ao mesmo sistema de ficheiros de `STATE_ROOT`.

Objetos adicionais diretamente em `STATE_ROOT` causam falha de configuração.

Durante a atualização prevista na secção 19, é permitido exatamente um ficheiro
temporário `.current-generation-<generation_id>.tmp` pertencente à invocação.
Esta exceção termina antes da conclusão do ciclo.

`current-generation`, quando existe, é validado antes da criação de uma nova
staging.

Uma referência ausente é aceite como estado inicial.

Uma referência existente mas inválida não é corrigida ou substituída
automaticamente e impede o início do ciclo.

Quando a referência existe, o Runner confirma também que o destino:

- existe dentro de `generations/`;
- possui exatamente o nome declarado;
- é um diretório real e promovido;
- não é uma staging;
- passa integralmente o Validador de Manifestos oficial.

Uma geração anterior ausente, insegura ou inválida impede o início do ciclo.

`RUNTIME_ROOT` é dedicado ao Runner.

Na versão 2.0.0, o único objeto persistente permitido diretamente em
`RUNTIME_ROOT` é:

    observer-runner.lock

A validação confirma dispositivo, inode, tipo, proprietário e permissões das
raízes antes de operações que dependam da continuidade do mesmo objeto.

Uma mudança de identidade durante a execução causa falha estrutural.

## 6. Bloqueio exclusivo

O bloqueio oficial usa:

    RUNTIME_ROOT/observer-runner.lock

O ficheiro de bloqueio:

- é um ficheiro regular;
- não é link simbólico;
- possui exatamente um hard link;
- pertence ao utilizador efetivo do Runner;
- não possui permissões superiores a `0640`;
- não contém dados necessários à recuperação;
- não é removido no fim da execução.

Quando o ficheiro ainda não existe, é criado de forma exclusiva com modo
máximo `0640`.

O Runner abre o ficheiro com proteção contra links simbólicos quando essa
capacidade está disponível.

O bloqueio usa `fcntl.flock` com as operações equivalentes a:

    LOCK_EX | LOCK_NB

O descritor permanece aberto durante toda a invocação, incluindo:

- validação das raízes;
- criação e execução do ciclo;
- construção e validação do manifesto;
- sincronização;
- promoção;
- atualização da referência;
- limpeza aplicável;
- construção do relatório final.

Se outro processo já possuir o bloqueio:

- o Runner não espera;
- não cria uma geração;
- não cria uma staging;
- não executa Observers;
- não modifica `STATE_ROOT`;
- emite um relatório válido com estado `WARNING`;
- declara o código textual `LOCK_BUSY`;
- termina com o código de processo reservado a bloqueio ocupado.

O bloqueio é cooperativo e não substitui permissões, validação de caminhos ou
verificação de identidades.

Uma falha ao criar, abrir, validar ou manter o ficheiro de bloqueio é uma falha
estrutural e não é apresentada como `LOCK_BUSY`.

## 7. Identificador e tempo do ciclo

O Runner cria um único `generation_id` por ciclo iniciado.

O formato e a validação semântica seguem exatamente o contrato aprovado do
manifesto 1.0.0:

    YYYYMMDDTHHMMSSffffffZ-<32 hexadecimal minúsculos>

A parte temporal é obtida em UTC.

O sufixo contém 128 bits produzidos por um gerador criptograficamente seguro e
é representado por 32 algarismos hexadecimais minúsculos.

`started_at` é fixado no mesmo instante usado na parte temporal de
`generation_id`.

A correspondência entre `generation_id` e `started_at` é exata, sem
arredondamento ou normalização posterior.

Antes de criar a staging, o Runner confirma que não existem:

- `.staging-<generation_id>`;
- `<generation_id>`.

Uma colisão não causa reutilização, substituição ou remoção.

Na versão 2.0.0, uma colisão é declarada como falha estrutural. O Runner não
gera silenciosamente outro identificador dentro da mesma invocação.

`completed_at` é fixado depois de terminarem todas as tentativas de captura e
antes da construção do manifesto.

`completed_at` não pode ser anterior a `started_at`.

O Runner usa um relógio monotónico para:

- duração total do ciclo;
- limites de execução;
- medições operacionais.

Os timestamps UTC identificam o ciclo, mas não são usados para impor limites.

Um recuo do relógio UTC que torne o intervalo inválido causa falha estrutural e
impede a promoção.

## 8. Limites globais

Os limites dos Observers são obtidos exclusivamente do Registo de Observers
1.0.0 validado.

Na versão 2.0.0, o Runner define adicionalmente:

- duração máxima total da invocação iniciada: `1200` segundos;
- período de graça para terminação externa: `1` segundo;
- tamanho máximo de um resultado do Capturador: `65536` bytes;
- tamanho máximo do relatório serializado do Runner: `262144` bytes;
- profundidade máxima do relatório do Runner: `32`;
- espaço livre mínimo antes da staging: `16777216` bytes;
- espaço livre mínimo antes do manifesto: `16777216` bytes;
- espaço livre mínimo antes da promoção: `16777216` bytes.

O limite total começa depois da aquisição do bloqueio e antes do carregamento
do registo.

O limite total inclui:

- validação da configuração;
- criação da staging;
- todas as invocações do Capturador;
- construção e validação do manifesto;
- sincronização;
- promoção;
- atualização da referência;
- limpeza aplicável.

O limite total é verificado antes e depois de cada fronteira controlável.

Uma chamada de sistema bloqueada não é apresentada como interruptível quando o
sistema operativo não fornece essa garantia. Depois de recuperar o controlo, o
Runner reconhece o limite excedido e não inicia a etapa seguinte.

A construção e emissão do relatório final permanecem limitadas, mesmo quando o
limite total do ciclo já tiver sido excedido.

Cada invocação do Capturador possui um limite externo igual a:

    observer_timeout_seconds + 10 segundos

Este limite externo não substitui o limite interno do Capturador. Protege o
Runner caso o próprio processo do Capturador não termine de forma controlada.

O número de módulos:

- é maior que zero;
- não excede `limits.max_observers`;
- corresponde exatamente à lista validada do registo.

O espaço livre é medido no sistema de ficheiros de `generations/`.

Um valor inferior ao mínimo causa falha estrutural antes da operação seguinte.

Uma falha real de escrita, sincronização ou alocação continua a ser tratada
como falha estrutural mesmo quando a verificação anterior indicava espaço
suficiente.

Nenhum limite excedido é convertido em sucesso, truncagem silenciosa ou
relatório parcial aceite.

Os valores desta secção são constantes públicas da versão 2.0.0 e são
verificados pelos testes.

## 9. Criação da staging

Depois de validar o registo, o Runner cria exclusivamente:

    STATE_ROOT/generations/.staging-<generation_id>/

A staging:

- é criada com uma operação que falha se o nome já existir;
- é um diretório real;
- não é link simbólico;
- pertence ao utilizador efetivo;
- possui modo máximo `0750`;
- pertence ao mesmo sistema de ficheiros de `generations/`.

Dentro da staging, o Runner cria exclusivamente:

    observers/

`observers/` obedece às mesmas regras de tipo, propriedade e modo da staging.

O Runner conserva durante a invocação:

- dispositivo e inode de `STATE_ROOT`;
- dispositivo e inode de `generations/`;
- dispositivo e inode da staging;
- dispositivo e inode de `observers/`;
- o `generation_id` criado pela invocação.

Estes valores constituem a identidade transitória da tentativa.

Antes de cada operação dependente da staging, o Runner confirma que os objetos
mantêm tipo e identidade.

A staging não contém um ficheiro de identidade adicional.

Antes da construção do manifesto, contém apenas:

- `observers/`;
- relatórios regulares persistidos pelo Capturador.

O Runner não copia relatórios de gerações anteriores.

Uma falha na criação ou validação da staging é estrutural.

## 10. Invocação do Capturador

Os Observers são processados sequencialmente e pela ordem exata do registo
validado.

O Runner invoca, para cada módulo:

    /usr/bin/python3 -I \
        PROJECT_ROOT/core/capture-observer.py \
        --staging-dir STAGING_DIRECTORY \
        MODULE

A invocação:

- não usa shell;
- usa uma lista explícita de argumentos;
- desativa `stdin`;
- captura `stdout` e `stderr` separadamente;
- aplica limites durante a execução;
- usa um ambiente mínimo e controlado;
- não herda variáveis desnecessárias;
- usa locale previsível;
- usa timezone UTC;
- usa `umask` restritiva;
- não possui acesso especial à rede;
- não requer privilégios administrativos.

O diretório de trabalho é `PROJECT_ROOT`.

O Runner não chama diretamente os executáveis dos Observers.

O Runner não interpreta conteúdo arbitrário de `stderr`.

Se `stdout` ou `stderr` do processo do Capturador exceder o limite aplicável, o
processo e os seus descendentes são terminados de forma controlada.

O processo do Capturador inicia um novo grupo de processos.

Na terminação externa, o Runner:

1. envia `SIGTERM` ao grupo;
2. aguarda no máximo `1` segundo;
3. envia `SIGKILL` ao grupo quando ainda existirem processos;
4. recolhe o estado final sem esperar indefinidamente.

O limite de `stdout` do Capturador é `65536` bytes.

O limite de `stderr` do Capturador é `65536` bytes.

Uma falha externa do processo do Capturador que impeça obter um resultado
estruturado fiável é uma falha estrutural da tentativa.

## 11. Resultado estruturado do Capturador

Cada invocação deve produzir exatamente um documento compatível com:

    schemas/capture-result/1.0.0/capture-result.schema.json

O Runner valida, antes de usar o resultado:

1. limite de tamanho;
2. UTF-8;
3. documento JSON único;
4. ausência de chaves duplicadas;
5. ausência de números não finitos;
6. profundidade máxima;
7. JSON Schema Draft 2020-12;
8. versão `capture_contract`;
9. identidade do módulo;
10. coerência entre código de processo, `outcome`, `code` e campos associados.

O processo com resultado `SUCCESS`:

- termina com código `0`;
- declara `outcome` igual a `SUCCESS`;
- declara `code` igual a `SUCCESS`;
- declara o módulo esperado;
- declara `observer_exit_code` igual a `0`;
- declara o caminho exato `observers/<module>.json`;
- deixa exatamente um relatório correspondente na staging.

As falhas normais de módulo registáveis no manifesto são:

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

Uma falha normal:

- declara `outcome` igual a `FAILED`;
- usa um código permitido;
- não declara um relatório;
- não deixa relatório final para o módulo;
- não interrompe automaticamente os módulos seguintes.

Os códigos estruturais são:

- `USAGE_INVALID`;
- `DEPENDENCY_UNAVAILABLE`;
- `REGISTRY_INVALID`;
- `MODULE_NOT_AUTHORIZED`;
- `STAGING_INVALID`;
- `TEMPORARY_PERSISTENCE_FAILED`;
- `INTERNAL_ERROR`.

Um código estrutural, resultado ausente, resultado malformado ou incoerência
entre o processo e o documento interrompe a recolha e impede a promoção.

O Runner preserva no manifesto, sem conversão:

- `observer_exit_code`;
- `stdout_bytes`;
- `stderr_bytes`;
- `duration_ms`.

O Runner não deriva códigos a partir de mensagens humanas.

Depois de cada invocação, confirma novamente a identidade da staging e de
`observers/`.

## 12. Carregamento do registo

O Runner lê:

    PROJECT_ROOT/config/observer-registry.json

e valida o documento com:

    PROJECT_ROOT/schemas/observer-registry/1.0.0/observer-registry.schema.json

O registo e o schema:

- são ficheiros regulares;
- não são links simbólicos;
- possuem exatamente um hard link;
- são lidos com limites;
- permanecem com a mesma identidade durante a leitura;
- contêm UTF-8 e JSON estritos;
- não contêm chaves duplicadas;
- não contêm números não finitos;
- não utilizam referências externas de schema.

O próprio schema é validado como JSON Schema Draft 2020-12.

A validação semântica segue o contrato aprovado do Registo de Observers 1.0.0.

O Runner calcula `registry.sha256` sobre os bytes exatos do registo validado.

O Runner não aceita um registo alternativo por argumento, variável de ambiente
ou caminho de configuração externo.

Uma mudança do registo ou do schema durante o ciclo causa falha estrutural.

## 13. Relatórios persistidos

Para cada resultado `SUCCESS`, o Runner abre o relatório indicado pelo
Capturador e confirma:

- caminho exato `observers/<module>.json`;
- ficheiro regular;
- ausência de link simbólico;
- exatamente um hard link;
- propriedade do utilizador efetivo;
- modo máximo `0640` durante a staging;
- tamanho positivo e dentro do limite do registo;
- identidade estável durante a leitura;
- hash SHA-256 sobre os bytes exatos;
- contrato serializado 2.1.0 válido;
- módulo correspondente;
- versão autorizada pelo registo;
- `contract_version` correspondente a `output_contract`.

A validação usa o validador oficial:

    PROJECT_ROOT/core/validate-report.py

O Runner obtém do relatório validado apenas os campos necessários ao descritor:

- `module`;
- `version`;
- `timestamp`;
- `status`.

O descritor acrescenta:

- `path`;
- `contract_version`;
- `size_bytes`;
- `sha256`.

Uma entrada de captura com `outcome` igual a `FAILED` não possui relatório.

Um relatório ausente, adicional, duplicado, inseguro, alterado ou incoerente
causa falha estrutural e impede a construção do manifesto.

## 14. Construção do manifesto

O manifesto é construído apenas depois de terminarem todas as tentativas
normais de captura.

As entradas em `modules`:

- correspondem exatamente ao registo;
- preservam a ordem do registo;
- não são inferidas por enumeração de diretórios;
- contêm uma entrada por módulo declarado.

Para cada módulo, o Runner preserva:

- `module`;
- `required`;
- `outcome`;
- `error_code`;
- `exit_code`;
- `stdout_bytes`;
- `stderr_bytes`;
- `duration_ms`;
- `report`.

Os contadores são calculados a partir das entradas concluídas:

- `declared` é o número de módulos;
- `successful` é o número de entradas `SUCCESS`;
- `failed` é o número de entradas `FAILED`;
- `reports_written` é igual a `successful`.

O estado é derivado exclusivamente por:

- `COMPLETE` quando `successful == declared`;
- `PARTIAL` quando `0 < successful < declared`;
- `FAILED` quando `successful == 0`.

O manifesto usa exatamente:

- `manifest_version`: `1.0.0`;
- `runner.module`: `observer-runner`;
- `runner.version`: `2.0.0`;
- `registry.version`: `1.0.0`;
- `registry.hash_algorithm`: `sha256`.

O documento é serializado como UTF-8, com resultado determinístico e uma nova
linha final.

O Runner confirma o limite de `262144` bytes antes da persistência.

## 15. Persistência e validação do manifesto

O manifesto é inicialmente escrito num ficheiro temporário exclusivo dentro da
staging.

O nome temporário:

- começa por `.manifest-`;
- contém apenas caracteres autorizados;
- não coincide com qualquer nome final;
- pertence exclusivamente à invocação atual.

O ficheiro temporário:

- é regular;
- não é link simbólico;
- possui exatamente um hard link;
- é criado com modo máximo `0640`;
- é escrito integralmente;
- é sincronizado antes da publicação.

Depois da escrita completa, o Runner publica:

    manifest.json

através de `rename` sem substituir um destino existente.

Depois da publicação, o Runner sincroniza a staging.

Nenhum ficheiro temporário permanece antes da validação oficial.

O Runner invoca, sem shell:

    /usr/bin/python3 -I \
        PROJECT_ROOT/core/validate-manifest.py \
        --expected-generation-id GENERATION_ID \
        STAGING_DIRECTORY

A validação:

- possui `stdin` desativado;
- possui `stdout` e `stderr` limitados;
- usa ambiente controlado;
- deve terminar com código `0`;
- não pode produzir conteúdo em `stdout` ou `stderr`.

Qualquer código diferente de zero, diagnóstico inesperado, excesso de saída ou
falha do processo impede a promoção.

Depois da validação, o Runner confirma novamente:

- identidade das raízes;
- identidade da staging;
- identidade de `observers/`;
- identidade de `manifest.json`;
- identidade de cada relatório;
- ausência de objetos desconhecidos.

## 16. Permissões finais

Depois da primeira validação oficial do manifesto, o Runner aplica:

- `0440` a cada relatório;
- `0440` a `manifest.json`;
- `0550` a `observers/`;
- `0550` à staging.

O Runner não acrescenta permissões de escrita para grupo ou `other`.

Depois de aplicar as permissões, confirma:

- tipo de cada objeto;
- propriedade;
- número de hard links;
- dispositivo e inode;
- modo exato;
- tamanho dos ficheiros;
- hashes dos relatórios;
- ausência de objetos adicionais.

O Runner executa novamente o Validador de Manifestos sobre a staging com as
permissões finais.

Uma falha na aplicação ou confirmação das permissões impede a promoção.

## 17. Sincronização da geração

Depois da validação com permissões finais, a ordem de sincronização é:

1. abrir e sincronizar cada relatório declarado;
2. abrir e sincronizar `manifest.json`;
3. sincronizar `observers/`;
4. sincronizar a staging;
5. sincronizar `generations/`.

Os ficheiros são sincronizados apenas depois de confirmar novamente a sua
identidade.

Os diretórios são abertos como diretórios reais e sem seguir links simbólicos.

Quando o sistema disponibiliza `O_DIRECTORY`, `O_NOFOLLOW` ou capacidades
equivalentes, o Runner utiliza-as.

Uma falha de abertura, identidade ou `fsync`:

- impede a promoção;
- é declarada como falha estrutural;
- não é convertida em aviso;
- não permite continuar para `current-generation`.

A conclusão de `fsync` confirma que o sistema operativo aceitou o pedido de
sincronização. Não constitui promessa sobre garantias físicas que o hardware
não forneça.

## 18. Promoção da geração

O destino final é:

    STATE_ROOT/generations/<generation_id>/

Imediatamente antes da promoção, o Runner confirma:

- identidade de `STATE_ROOT`;
- identidade de `generations/`;
- identidade da staging;
- ausência do destino final;
- inexistência de objetos temporários;
- permissões finais;
- validade do manifesto e dos relatórios;
- espaço livre mínimo.

A promoção usa `renameat2` com semântica `RENAME_NOREPLACE`.

A implementação não substitui o destino por `rename` permissivo.

Se a capacidade de não substituição atómica estiver indisponível, a execução
termina com falha de dependência antes do ciclo.

Depois do `renameat2`, o Runner:

1. confirma o mesmo dispositivo e inode no caminho final;
2. confirma que a staging deixou de existir;
3. sincroniza `generations/`;
4. confirma novamente a estrutura da geração promovida.

A geração só é declarada promovida depois da sincronização de `generations/`.

Se o `renameat2` tiver ocorrido mas a confirmação ou sincronização falhar:

- a geração não é removida;
- `current-generation` não é atualizado;
- o resultado operacional é declarado indeterminado;
- é necessária recuperação explícita e auditável.

Uma geração promovida nunca é modificada pelo Runner.

## 19. Atualização de current-generation

A atualização começa apenas depois de a geração ser declarada promovida.

O conteúdo novo é exatamente:

    <generation_id>\n

O Runner cria dentro de `STATE_ROOT` um ficheiro temporário exclusivo cujo nome:

- começa por `.current-generation-`;
- contém o `generation_id`;
- termina em `.tmp`;
- pertence exclusivamente à invocação atual.

O ficheiro temporário:

- é regular;
- não é link simbólico;
- possui exatamente um hard link;
- pertence ao utilizador efetivo;
- possui modo `0640`;
- contém apenas a referência nova;
- é sincronizado antes da publicação.

Antes da substituição, o Runner confirma que a referência anterior continua
ausente ou possui a mesma identidade e conteúdo validados no início do ciclo.

A publicação usa `rename` atómico dentro de `STATE_ROOT`.

Nesta operação, a substituição da referência anterior é intencional.

Depois do `rename`, o Runner:

1. confirma o tipo e conteúdo de `current-generation`;
2. confirma o modo `0640`;
3. confirma que aponta para a geração promovida;
4. sincroniza `STATE_ROOT`;
5. lê e valida novamente a referência.

A referência só é declarada atualizada depois da sincronização de
`STATE_ROOT`.

Se a atualização falhar antes do `rename`:

- o temporário da invocação pode ser removido após validação da sua identidade;
- a geração promovida é preservada;
- a referência anterior permanece válida.

Se o `rename` ocorrer mas a confirmação ou sincronização falhar:

- não existe tentativa automática de reposição;
- a geração promovida é preservada;
- o resultado operacional é declarado indeterminado;
- a situação exige recuperação explícita e auditável.

O Runner nunca apaga previamente a referência anterior.

## 20. Códigos de processo

Os códigos de processo da versão 2.0.0 são:

| Código | Código textual | Significado |
|---:|---|---|
| `0` | `SUCCESS` | geração `COMPLETE`, promovida e atual |
| `2` | `USAGE_INVALID` | argumentos inválidos |
| `3` | `CONFIGURATION_INVALID` | configuração local inválida |
| `3` | `DEPENDENCY_UNAVAILABLE` | dependência obrigatória indisponível |
| `4` | `LOCK_BUSY` | outro ciclo possui o bloqueio |
| `5` | `GENERATION_PARTIAL` | geração `PARTIAL`, promovida e atual |
| `6` | `GENERATION_FAILED` | geração `FAILED`, promovida e atual |
| `7` | `STRUCTURAL_FAILURE` | ciclo interrompido por falha estrutural |
| `8` | `OUTCOME_UNKNOWN` | resultado operacional indeterminado |
| `9` | `INTERNAL_ERROR` | falha interna inesperada |

Código `0` significa apenas que:

- a geração é `COMPLETE`;
- a geração foi promovida;
- `current-generation` foi atualizado e sincronizado;
- o relatório final é válido.

Uma geração `PARTIAL` ou `FAILED` promovida não termina com código `0`.

Uma falha estrutural antes da promoção termina com código `7`.

Uma falha estrutural conhecida depois da promoção, mas antes de alterar a
referência, também termina com código `7`.

O código `8` é reservado aos casos em que uma operação crítica ocorreu, mas a
sua confirmação ou sincronização falhou e o Runner não pode declarar com
confiança o estado durável.

Os códigos não são derivados de texto humano.

## 21. Relatório do Runner

Salvo `--help`, o Runner tenta emitir exatamente um relatório JSON em `stdout`
para cada invocação.

O relatório segue o contrato serializado 2.1.0 e contém:

- `module`: `observer-runner`;
- `version`: `2.0.0`;
- timestamp no formato do relatório 2.1.0;
- estado da invocação;
- confiança no resultado operacional;
- factos estruturados;
- mensagens controladas.

O estado é:

- `OK` para `SUCCESS`;
- `WARNING` para `LOCK_BUSY` e `GENERATION_PARTIAL`;
- `ERROR` para `USAGE_INVALID`, `CONFIGURATION_INVALID`,
  `DEPENDENCY_UNAVAILABLE`, `GENERATION_FAILED` e `STRUCTURAL_FAILURE`;
- `UNKNOWN` para `OUTCOME_UNKNOWN` e `INTERNAL_ERROR` quando o resultado não
  puder ser determinado com confiança.

Um `INTERNAL_ERROR` conhecido antes de qualquer operação ambígua usa `ERROR` e
confiança `100`. Usa `UNKNOWN` e confiança `0` apenas quando o estado operacional
não puder ser determinado.

`confidence` é `100` quando o Runner conhece de forma determinística o resultado
declarado.

`confidence` é `0` quando o resultado operacional é indeterminado.

Os factos contêm exatamente, no mínimo:

- `result_code`;
- `lock_acquired`;
- `cycle_started`;
- `generation_id`;
- `generation_state`;
- `declared`;
- `successful`;
- `failed`;
- `reports_written`;
- `successful_modules`;
- `failed_modules`;
- `generation_promoted`;
- `current_generation_updated`.

Valores ainda não aplicáveis são representados por `null`.

Valores booleanos são booleanos JSON e não texto.

Contadores conhecidos são inteiros JSON não negativos.

As listas de módulos preservam a ordem do registo.

`analysis`, `conclusions` e `health` permanecem vazios porque o Runner não
interpreta a saúde do sistema observado.

`summary`, `recommendations`, `warnings` e `errors` contêm apenas mensagens
controladas pelo código.

O relatório não inclui:

- factos recolhidos pelos Observers;
- conteúdo arbitrário de `stderr`;
- variáveis de ambiente;
- caminhos absolutos;
- tokens ou segredos;
- tracebacks.

A implementação Python constrói diretamente o documento serializado 2.1.0.

Não executa nem carrega `core/report.sh`.

O validador oficial do relatório é carregado a partir do caminho fixo do projeto
e aplicado ao documento em memória.

O Runner não cria um ficheiro temporário para validar o seu próprio relatório.

Antes da emissão, valida o relatório através do validador oficial:

    PROJECT_ROOT/core/validate-report.py

A validação usa:

- módulo esperado `observer-runner`;
- tamanho máximo `262144`;
- profundidade máxima `32`.

O relatório é serializado deterministicamente como UTF-8 e termina com uma nova
linha.

Em caso de relatório válido:

- `stdout` contém apenas o documento;
- `stderr` permanece vazio.

Se uma dependência impedir a construção ou validação do próprio relatório:

- nenhum JSON parcial é emitido;
- `stdout` permanece vazio;
- `stderr` recebe um diagnóstico controlado;
- o processo termina com o código aplicável.

O Runner nunca emite um relatório que declare promoção ou atualização sem
confirmação das respetivas operações.

### 21.1 Semântica dos factos

`lock_acquired` é:

- `false` antes da aquisição e quando existe `LOCK_BUSY`;
- `true` depois da aquisição confirmada.

`cycle_started` passa a `true` imediatamente antes da criação de
`generation_id` e `started_at`.

Falhas anteriores a esse ponto mantêm:

- `cycle_started` igual a `false`;
- `generation_id` igual a `null`;
- `generation_state` igual a `null`.

`declared` é preenchido apenas depois da validação integral do registo.

`successful`, `failed`, `reports_written`, `successful_modules` e
`failed_modules` são preenchidos apenas depois de terminarem todas as tentativas
normais de captura.

Se uma falha estrutural interromper a recolha:

- os contadores finais permanecem `null`;
- as listas finais permanecem `null`;
- resultados intermédios não são apresentados como geração concluída.

`generation_state` é preenchido apenas depois de o estado ser derivado de todas
as entradas.

`generation_promoted` é:

- `false` antes do `renameat2`;
- `true` apenas depois da confirmação e sincronização;
- `null` quando o `renameat2` ocorreu, mas o resultado durável não pôde ser
  confirmado.

`current_generation_updated` é:

- `false` antes do `rename` da referência;
- `true` apenas depois da confirmação e sincronização;
- `null` quando o `rename` ocorreu, mas o resultado durável não pôde ser
  confirmado.

### 21.2 Matriz normativa do resultado

| Situação | Saída | Estado | Promovida | Atual |
|---|---:|---|---|---|
| Ajuda | `0` | sem relatório | não aplicável | não aplicável |
| Uso inválido | `2` | `ERROR` | `false` | `false` |
| Configuração ou dependência inválida | `3` | `ERROR` | `false` | `false` |
| Bloqueio ocupado | `4` | `WARNING` | `false` | `false` |
| Geração `COMPLETE` atual | `0` | `OK` | `true` | `true` |
| Geração `PARTIAL` atual | `5` | `WARNING` | `true` | `true` |
| Geração `FAILED` atual | `6` | `ERROR` | `true` | `true` |
| Falha estrutural antes da promoção | `7` | `ERROR` | `false` | `false` |
| Promovida, referência não alterada | `7` | `ERROR` | `true` | `false` |
| Promoção não confirmável | `8` | `UNKNOWN` | `null` | `false` |
| Referência não confirmável | `8` | `UNKNOWN` | `true` | `null` |
| Erro interno com resultado conhecido | `9` | `ERROR` | valor conhecido | valor conhecido |
| Erro interno com resultado incerto | `9` | `UNKNOWN` | conhecido ou `null` | conhecido ou `null` |

A matriz não permite converter uma falha em sucesso para simplificar o
relatório.

## 22. Limpeza limitada

A limpeza automática limita-se a objetos temporários criados pela própria
invocação.

Antes de remover uma staging, o Runner confirma:

- pai igual a `generations/` validado;
- nome exato `.staging-<generation_id>`;
- dispositivo e inode conservados pela invocação;
- ausência do destino promovido correspondente;
- ausência de links simbólicos;
- ausência de montagens ou objetos especiais;
- estrutura integralmente percorrível sem seguir links.

A remoção usa travessia controlada e não segue links simbólicos.

Se a staging já tiver permissões finais, o Runner pode restaurar apenas as
permissões mínimas de proprietário necessárias à remoção, depois de confirmar
a identidade de todos os objetos.

O Runner não remove a staging quando:

- a identidade diverge;
- o caminho é ambíguo;
- existe um objeto desconhecido ou inseguro;
- a promoção pode ter ocorrido;
- não consegue demonstrar que a staging pertence à invocação.

O Runner nunca remove:

- uma geração promovida;
- uma staging de outra invocação;
- uma staging encontrada no início do ciclo;
- `current-generation`;
- o ficheiro de bloqueio;
- objetos fora das raízes recebidas.

Um ficheiro temporário de manifesto ou referência pode ser removido apenas
quando conserva a identidade registada pela invocação e não foi promovido.

Uma falha de limpeza:

- é declarada;
- não é ocultada pelo resultado anterior;
- não autoriza uma remoção mais ampla;
- pode preservar a staging para análise humana.

## 23. Recuperação

A versão 2.0.0 não executa recuperação automática de artefactos deixados por
invocações anteriores.

Uma staging preexistente:

- é inventariada apenas pelo nome;
- não é promovida;
- não é removida;
- não é reutilizada;
- não impede um novo ciclo quando possui outro `generation_id`.

Uma staging que colida com o novo identificador causa falha estrutural.

Uma geração promovida sem referência atual correspondente:

- é preservada;
- não é definida automaticamente como atual;
- não é removida;
- exige validação e decisão humana explícitas.

Uma referência inválida não é reconstruída por inferência a partir da geração
mais recente.

A recuperação futura deve ser uma operação separada, auditável e aprovada.

## 24. Dependências e isolamento

As dependências operacionais da implementação E2 são:

- `/usr/bin/python3`;
- biblioteca padrão do Python;
- pacote Ubuntu `python3-jsonschema`;
- contratos, schemas e validadores locais aprovados;
- `renameat2` com `RENAME_NOREPLACE`;
- `flock`;
- sistema de ficheiros com suporte às operações documentadas.

Nenhuma dependência é instalada, atualizada ou descarregada pelo Runner.

O Runner:

- não abre sockets;
- não consulta DNS;
- não acede à Internet;
- não inicia shell;
- não executa comandos fornecidos pelo utilizador;
- não aceita caminhos alternativos para código ou contratos;
- não escreve em `PROJECT_ROOT`;
- não escreve em `data/`;
- não requer `sudo`;
- não modifica configurações do sistema;
- não executa o Decision Engine;
- não executa o Historian.

A execução dos Observers ocorre exclusivamente através do Capturador aprovado.

O ambiente dos processos filhos contém apenas valores controlados necessários
à execução.

A importação de `runner/observer-runner.py`:

- não analisa argumentos;
- não adquire bloqueio;
- não cria diretórios;
- não executa Observers;
- não produz saída;
- não inicia um ciclo.

## 25. Ordem normativa da invocação

A ordem é:

1. analisar argumentos;
2. verificar dependências necessárias ao relatório;
3. validar minimamente `RUNTIME_ROOT`;
4. criar ou abrir o ficheiro de bloqueio;
5. tentar adquirir o bloqueio exclusivo;
6. iniciar o limite monotónico total;
7. validar integralmente as duas raízes;
8. validar a referência anterior, quando existe;
9. carregar e validar schemas e registo;
10. confirmar número de módulos e limites;
11. verificar espaço livre;
12. criar `generation_id` e `started_at`;
13. confirmar ausência de colisões;
14. criar staging e `observers/`;
15. invocar o Capturador sequencialmente;
16. validar cada resultado estruturado;
17. validar os relatórios persistidos;
18. fixar `completed_at`;
19. construir e persistir o manifesto;
20. executar a primeira validação oficial;
21. aplicar permissões finais;
22. executar a segunda validação oficial;
23. sincronizar ficheiros e diretórios;
24. confirmar identidades e espaço livre;
25. promover a geração;
26. confirmar e sincronizar a promoção;
27. criar e sincronizar a referência temporária;
28. confirmar a referência anterior;
29. atualizar `current-generation`;
30. confirmar e sincronizar a referência nova;
31. executar limpeza temporária aplicável;
32. construir e validar o relatório do Runner;
33. libertar o bloqueio;
34. emitir o relatório e terminar com o código correspondente.

Quando uma etapa falha, apenas as etapas de diagnóstico, relatório, limpeza
segura e libertação do bloqueio que continuem aplicáveis podem ser executadas.

O relatório nunca antecipa como concluída uma operação posterior.

## 26. Testes obrigatórios da E2

A implementação possui uma suite própria:

    tests/observer-runner-contract-test.py

Todos os testes usam raízes temporárias absolutas e isoladas.

Nenhum teste escreve em caminhos operacionais.

### 26.1 Interface e importação

Os testes cobrem:

- `--help`;
- argumentos ausentes;
- opção desconhecida;
- opção repetida;
- argumento posicional adicional;
- `STATE_ROOT` relativo;
- `RUNTIME_ROOT` relativo;
- importação sem execução automática;
- ausência de saída durante importação;
- ausência de cache Python.
- `sys.dont_write_bytecode` ativo;

### 26.2 Raízes e estrutura

Os testes cobrem:

- raízes válidas;
- raiz ausente;
- raiz como ficheiro;
- raiz como link simbólico;
- componente intermédio como link simbólico;
- raízes iguais;
- raiz contida na outra;
- proprietário divergente;
- permissões excessivas;
- ausência de permissões necessárias;
- `generations/` ausente;
- `generations/` como ficheiro;
- `generations/` como link simbólico;
- sistema de ficheiros divergente;
- objeto desconhecido em `STATE_ROOT`;
- mudança de identidade durante o ciclo.

### 26.3 Referência anterior

Os testes cobrem:

- referência inicialmente ausente;
- referência válida;
- referência sem nova linha;
- referência com texto adicional;
- UTF-8 inválido;
- identificador impossível;
- referência como diretório;
- referência como link simbólico;
- hard link adicional;
- permissões excessivas;
- geração referenciada ausente;
- geração referenciada como link simbólico;
- geração referenciada com manifesto inválido;
- geração referenciada com relatório adulterado;
- alteração concorrente antes da substituição.

### 26.4 Bloqueio

Os testes cobrem:

- criação segura do ficheiro;
- ficheiro regular existente;
- bloqueio livre;
- bloqueio ocupado;
- ausência de espera quando ocupado;
- bloqueio como diretório;
- bloqueio como link simbólico;
- hard link adicional;
- proprietário divergente;
- permissões excessivas;
- falha de criação;
- falha de aquisição;
- manutenção do descritor até ao fim;
- ausência de staging e execução quando ocupado.

### 26.5 Registo e dependências

Os testes cobrem:

- registo válido;
- registo ausente;
- registo como link simbólico;
- registo com hard link adicional;
- registo alterado durante leitura;
- schema ausente;
- schema inseguro;
- schema inválido;
- referência externa de schema;
- chave duplicada;
- número não finito;
- versão incompatível;
- zero módulos;
- módulos acima do limite;
- módulo duplicado;
- ordem do registo;
- dependência `jsonschema` indisponível;
- `renameat2` indisponível.

### 26.6 Identificador, relógios e limites

Os testes cobrem:

- formato do identificador;
- data UTC válida;
- sufixo aleatório com 128 bits;
- correspondência exata com `started_at`;
- colisão com staging;
- colisão com geração promovida;
- ausência de segunda tentativa silenciosa;
- `completed_at` anterior a `started_at`;
- uso de relógio monotónico;
- limite total do ciclo;
- limite externo do Capturador;
- pouco espaço antes da staging;
- pouco espaço antes do manifesto;
- pouco espaço antes da promoção.

### 26.7 Staging

Os testes cobrem:

- criação exclusiva;
- modo inicial;
- criação de `observers/`;
- colisão;
- staging como ficheiro;
- mudança de inode;
- `observers/` ausente;
- `observers/` como ficheiro;
- `observers/` como link simbólico;
- objeto desconhecido;
- relatório copiado de outra geração;
- sistema de ficheiros divergente.

### 26.8 Coordenação do Capturador

Os testes cobrem:

- ordem sequencial exata;
- ambiente controlado;
- `stdin` desativado;
- ausência de shell;
- limite de `stdout`;
- limite de `stderr`;
- timeout externo;
- terminação de descendentes;
- novo grupo de processos;
- período de graça de terminação;
- escalada de `SIGTERM` para `SIGKILL`;
- resultado vazio;
- resultado truncado;
- documento adicional;
- UTF-8 inválido;
- chave duplicada;
- número não finito;
- profundidade excessiva;
- propriedade desconhecida;
- versão incompatível;
- módulo divergente;
- código de processo divergente;
- caminho de relatório divergente;
- todos os códigos normais permitidos;
- todos os códigos estruturais;
- continuação após falha normal;
- interrupção após falha estrutural.

### 26.9 Relatórios dos Observers

Os testes cobrem:

- relatório válido;
- relatório ausente;
- relatório adicional;
- relatório como diretório;
- relatório como link simbólico;
- hard link adicional;
- proprietário divergente;
- permissões excessivas;
- relatório vazio;
- relatório acima do limite;
- tamanho alterado;
- hash alterado;
- identidade alterada durante leitura;
- contrato 2.1.0 inválido;
- módulo divergente;
- versão não autorizada;
- timestamp divergente;
- estado divergente.

### 26.10 Manifesto

Os testes cobrem:

- geração `COMPLETE`;
- geração `PARTIAL`;
- geração `FAILED`;
- ordem dos módulos;
- `required` preservado;
- códigos e métricas preservados;
- contadores derivados;
- estado derivado;
- hash exato do registo;
- descritores exatos;
- serialização determinística;
- nova linha final;
- limite de tamanho;
- falha de escrita temporária;
- falha de sincronização temporária;
- colisão de `manifest.json`;
- primeira validação rejeitada;
- segunda validação rejeitada;
- diagnóstico inesperado do validador.

### 26.11 Permissões e durabilidade

Os testes cobrem:

- modos iniciais;
- modos finais exatos;
- falha de `chmod`;
- confirmação depois de `chmod`;
- ordem de todos os `fsync`;
- falha ao sincronizar cada relatório;
- falha ao sincronizar o manifesto;
- falha ao sincronizar `observers/`;
- falha ao sincronizar a staging;
- falha ao sincronizar `generations/`;
- nenhuma promoção depois de falha de sincronização.

### 26.12 Promoção

Os testes cobrem:

- promoção com `RENAME_NOREPLACE`;
- proibição de substituição;
- colisão criada imediatamente antes da promoção;
- falha de `renameat2`;
- identidade preservada depois da promoção;
- staging ausente depois da promoção;
- geração final válida;
- falha de confirmação depois do `renameat2`;
- falha de `fsync` depois do `renameat2`;
- resultado indeterminado depois de promoção não confirmável;
- ausência de atualização da referência nesse caso;
- preservação da geração promovida.

### 26.13 current-generation

Os testes cobrem:

- primeira publicação;
- substituição de referência anterior válida;
- conteúdo exato;
- modo exato;
- ficheiro temporário exclusivo;
- falha de escrita;
- falha de sincronização temporária;
- alteração concorrente da referência anterior;
- falha de `rename`;
- referência anterior preservada antes do `rename`;
- falha de confirmação depois do `rename`;
- falha de sincronização de `STATE_ROOT`;
- resultado indeterminado depois de substituição não confirmável;
- ausência de reposição automática;
- leitura final consistente.

### 26.14 Limpeza e recuperação

Os testes cobrem:

- limpeza da staging própria;
- limpeza de temporário próprio;
- staging com permissões finais;
- pai divergente;
- nome divergente;
- inode divergente;
- link simbólico inesperado;
- FIFO;
- socket;
- montagem divergente simulada;
- objeto desconhecido;
- promoção possivelmente ocorrida;
- preservação perante dúvida;
- preservação de staging anterior;
- preservação de geração promovida;
- falha de limpeza declarada;
- ausência de recuperação automática.

### 26.15 Relatório e códigos do Runner

Os testes cobrem:

- relatório `OK`;
- relatório `WARNING` por bloqueio;
- relatório `WARNING` por geração parcial;
- relatório `ERROR` por geração falhada;
- relatório `ERROR` por falha estrutural;
- relatório `UNKNOWN` por resultado indeterminado;
- todos os códigos de processo;
- confiança `100`;
- confiança `0`;
- factos obrigatórios;
- semântica de cada facto;
- transições de `null`, `false` e `true`;
- todas as linhas da matriz normativa;
- valores `null`;
- booleanos JSON;
- contadores JSON;
- listas ordenadas;
- ausência de factos dos Observers;
- ausência de caminhos absolutos;
- ausência de conteúdo arbitrário de `stderr`;
- contrato serializado 2.1.0 válido;
- limite e profundidade;
- exatamente um documento em `stdout`;
- `stderr` vazio quando o relatório é válido;
- falha controlada quando o relatório não pode ser construído.

### 26.16 Segurança, integração e regressão

Os testes confirmam:

- ausência de sockets e DNS;
- ausência de acesso à Internet;
- ausência de shell;
- ausência de comandos controlados pelo utilizador;
- ausência de escrita em `PROJECT_ROOT`;
- ausência de escrita em `data/`;
- ausência de privilégios administrativos;
- execução integral com os sete Observers oficiais em raízes temporárias;
- mesma geração no manifesto e na referência;
- validação final da geração promovida;
- preservação do Runner legado;
- preservação do Historian;
- preservação de `MANIFESTO.md`;
- preservação dos sete Observers;
- preservação do Decision Engine;
- preservação dos dados operacionais;
- regressão integral das suites aprovadas.

As falhas de disco, relógio, concorrência e interrupção são simuladas por
injeção controlada.

Os testes não desligam o servidor, não enchem discos e não provocam falhas reais
no sistema de ficheiros.

## 27. Critérios de aprovação da E2.1

E2.1 só pode ser aprovada quando:

- este contrato estiver completo e aprovado;
- não existirem decisões silenciosamente preenchidas no código;
- a interface, limites e códigos estiverem aceites;
- a sequência de durabilidade estiver aceita;
- a matriz de testes cobrir todas as garantias documentadas;
- o contrato E1 permanecer inalterado;
- os componentes operacionais permanecerem inalterados;
- o administrador humano aprovar explicitamente o documento.

A aprovação de E2.1 autoriza apenas a implementação E2.2 em isolamento.

Não autoriza caminhos físicos operacionais, systemd, agendamento ou ativação.

## 28. Critérios de aprovação da E2.2

E2.2 só pode ser aprovada quando:

- a implementação corresponder integralmente a este contrato;
- todos os testes do Runner terminarem sem falhas;
- todas as suites anteriores permanecerem aprovadas;
- o ciclo integral funcionar em raízes temporárias;
- as falhas injetadas produzirem os artefactos e códigos esperados;
- nenhuma geração inválida for promovida;
- nenhuma referência apontar para geração não promovida;
- não existirem escritas operacionais;
- não existirem acessos de rede inesperados;
- não forem necessários privilégios administrativos;
- o diff Git contiver apenas alterações aprovadas;
- existir validação humana explícita.

Um teste falhado impede a promoção.

## 29. Evolução

Este documento permaneceu `DRAFT` durante a revisão da E2.1.

A versão 1.0.0 foi aprovada após revisão integral e aprovação explícita.

Depois de aprovado, o documento não é alterado retroativamente.

A implementação E2.2 não pode redefinir silenciosamente este contrato.

A aprovação da E2 não ativa o Runner 2.0.0.

A ativação operacional pertence exclusivamente à Fase H.
