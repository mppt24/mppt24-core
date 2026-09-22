# MPPT24 CORE — Contrato do Capturador de Observers

Estado do documento: APROVADO
Versão do documento: 1.0.0
Versão do capturador: 1.0.0
Versão do resultado: 1.0.0
Data: 16 de agosto de 2026

## 1. Objetivo

Este documento define a interface, as responsabilidades, os limites e os
resultados do Capturador de Observers da MPPT24 CORE.

O capturador processa exatamente um Observer autorizado por invocação.

É responsável por:

1. validar a autorização do módulo;
2. executar o Observer registado;
3. capturar separadamente `stdout`, `stderr` e o código de saída;
4. aplicar limites de tempo e tamanho;
5. entregar o relatório ao validador oficial 2.1.0;
6. persistir um relatório válido apenas em staging;
7. devolver um resultado inequívoco ao chamador.

O capturador:

- não cria gerações;
- não cria a raiz de staging;
- não escreve manifestos;
- não agrega estados;
- não promove gerações;
- não atualiza `current-generation`;
- não substitui relatórios de gerações anteriores;
- não escreve em `data/observer`.

## 2. Autoridade

A arquitetura do pipeline está definida em `ARCHITECTURE.md`, versão 1.0.0.

A autorização dos módulos está definida pelo Registo de Observers 1.0.0.

A validação de relatórios usa exclusivamente o contrato serializado 2.1.0.

Os limites operacionais são obtidos do registo validado e não ficam duplicados
como valores ocultos no capturador.

Quando existir divergência entre o capturador, o registo, os schemas, o
executável ou os contratos aprovados, a captura falha explicitamente.

## 3. Artefactos e compatibilidade

Os novos artefactos oficiais são:

- capturador: `core/capture-observer.py`;
- contrato: `core/capture-observer-contract.md`;
- schema do resultado:
  `schemas/capture-result/1.0.0/capture-result.schema.json`;
- testes: `tests/capture-observer-contract-test.py`.

O ficheiro `core/capture-observer.sh` pertence ao fluxo legado.

O capturador legado:

- permanece inalterado nesta fase;
- não implementa este contrato;
- não é usado pelo novo pipeline;
- não é removido sem plano específico.

Os contratos antigos que referem persistência em `data/observer/` não concedem
essa autorização ao capturador 1.0.0.

## 4. Interface

A interface é:

    capture-observer.py --staging-dir DIRECTORY MODULE

`MODULE` identifica exatamente um módulo presente no registo oficial.

`--staging-dir` identifica uma raiz de staging já criada e preparada pelo
chamador.

`--help` apresenta a utilização, termina com código `0` e não executa captura.

Cada opção pode aparecer no máximo uma vez.

Argumentos desconhecidos, opções repetidas, módulos adicionais ou argumentos
ausentes são rejeitados como uso inválido.

O capturador processa uma única entrada do registo por invocação.

## 5. Localizações fixas

O capturador determina relativamente à própria instalação:

- a raiz do projeto;
- `config/observer-registry.json`;
- o schema do registo 1.0.0;
- o executável registado;
- `core/validate-report.py`;
- o schema do resultado 1.0.0.

A interface operacional não permite substituir estes caminhos.

O capturador não usa `PATH` para localizar Observers, schemas, registo ou
validador.

Não existem comandos de shell construídos a partir de argumentos.

## 6. Registo e autorização

Antes da execução, o capturador:

1. lê o registo oficial como JSON estrito;
2. valida o schema do registo;
3. confirma a versão 1.0.0;
4. aplica as regras semânticas do registo;
5. procura uma única entrada cujo `module` seja igual a `MODULE`;
6. rejeita módulos não registados;
7. usa exclusivamente o caminho `executable` dessa entrada;
8. obtém os limites dessa versão do registo.

A presença de um ficheiro em `observer/` não autoriza a sua execução.

O capturador não procura nomes semelhantes, aliases, substitutos ou versões
alternativas.

O executável selecionado deve:

- existir;
- permanecer dentro de `observer/`;
- ser um ficheiro regular;
- não ser link simbólico;
- possuir permissão de execução;
- corresponder ao nome do módulo;
- declarar uma versão presente em `module_versions`.

## 7. Staging

`--staging-dir` deve ser um caminho absoluto.

A raiz indicada deve:

- existir antes da invocação;
- ser um diretório;
- não ser link simbólico;
- não atravessar componentes que sejam links simbólicos;
- ter nome iniciado por `.staging-`;
- possuir um sufixo não vazio;
- ser acessível pela identidade do processo.

A subdiretório `observers/` deve:

- existir antes da invocação;
- ser um diretório;
- não ser link simbólico;
- permanecer dentro da raiz de staging;
- permitir criação do relatório temporário.

O capturador não cria a raiz de staging nem `observers/`.

O destino é exatamente:

    STAGING/observers/<module>.json

Um destino já existente, incluindo link simbólico, causa falha.

O capturador não substitui, acrescenta ou reutiliza um relatório existente.

## 8. Execução controlada

O Observer é iniciado diretamente, sem shell e sem argumentos adicionais.

O ambiente contém apenas valores explicitamente controlados, incluindo:

- `PATH` fixo;
- `LANG=C.UTF-8`;
- `LC_ALL=C.UTF-8`;
- `TZ=UTC`.

O processo usa:

- `umask 027`;
- descritores controlados;
- `stdin` desligado;
- pipes separados para `stdout` e `stderr`;
- grupo de processo próprio.

O capturador não transmite automaticamente variáveis do ambiente chamador.

Quando ocorre timeout ou excesso de saída, o capturador termina o grupo de
processo do Observer e recolhe o estado final sem bloquear indefinidamente.

O código de saída do Observer é preservado no resultado quando existe um código
observável.

## 9. Limites

Os limites são obtidos do objeto `limits` do registo 1.0.0:

- `observer_timeout_seconds`;
- `stdout_max_bytes`;
- `stderr_max_bytes`;
- `report_max_bytes`;
- `json_max_depth`.

O capturador aplica os limites durante a execução e não apenas depois de o
Observer terminar.

A leitura de cada pipe é limitada e não permite crescimento de memória sem
limite.

`OUTPUT_LIMIT_EXCEEDED` identifica excesso de `stdout`.

`STDERR_LIMIT_EXCEEDED` identifica excesso de `stderr`.

Uma saída acima do limite nunca é truncada e aceite como relatório.

## 10. Tratamento de stdout e stderr

`stdout` contém exclusivamente o candidato a relatório.

`stdout` vazio causa `EMPTY_REPORT`.

Um código de saída diferente de zero causa `EXECUTION_FAILED`, mesmo que exista
conteúdo em `stdout`.

`stderr` é capturado separadamente apenas até ao limite aplicável.

O conteúdo arbitrário de `stderr`:

- não é incluído no relatório;
- não é persistido em staging;
- não é copiado para o resultado estruturado;
- não é reproduzido integralmente nos diagnósticos.

O resultado regista apenas o número de bytes capturados ou observados segundo o
limite.

## 11. Validação de fronteira

O candidato a relatório permanece em memória limitada até terminar a validação.

O capturador utiliza a implementação oficial de
`core/validate-report.py` para aplicar:

- UTF-8 estrito;
- JSON estrito;
- rejeição de chaves duplicadas;
- rejeição de números não finitos;
- limite de profundidade;
- schema do relatório 2.1.0;
- timestamp semântico;
- identidade esperada do módulo.

A validação é aplicada aos bytes capturados sem reabrir um caminho fornecido pelo
Observer.

Um candidato inválido nunca é escrito em staging.

As categorias são distinguidas como:

- `INVALID_JSON`;
- `CONTRACT_VIOLATION`;
- `MODULE_MISMATCH`.

Outras violações semânticas do relatório usam `CONTRACT_VIOLATION`.

O capturador não corrige, completa, converte ou normaliza o relatório.

## 12. Persistência temporária

Depois da validação integral, o capturador:

1. confirma novamente a identidade da raiz de staging;
2. confirma novamente a identidade de `observers/`;
3. confirma que o destino não existe;
4. cria um ficheiro temporário exclusivo dentro de `observers/`;
5. escreve integralmente os bytes validados;
6. aplica modo `0640`;
7. confirma escrita completa;
8. publica atomicamente sem substituir um destino existente;
9. remove qualquer temporário remanescente.

O nome temporário não deriva de conteúdo fornecido pelo Observer.

A publicação usa semântica de não substituição.

Uma falha antes da publicação não deixa relatório final.

Uma falha de persistência produz `TEMPORARY_PERSISTENCE_FAILED`.

Este contrato garante atomicidade de visibilidade dentro de staging.

A sincronização para durabilidade após perda de energia pertence ao contrato do
Runner e da promoção de gerações.

## 13. Resultado estruturado

Para resultados previstos, o capturador emite exatamente um documento JSON em
`stdout`.

O resultado contém exatamente:

- `capture_contract`;
- `module`;
- `outcome`;
- `code`;
- `observer_exit_code`;
- `report`;
- `stdout_bytes`;
- `stderr_bytes`;
- `duration_ms`.

`capture_contract` é exatamente `1.0.0`.

`module` contém o módulo solicitado quando este pôde ser identificado de forma
válida; caso contrário é nulo.

`outcome` aceita apenas `SUCCESS` ou `FAILED`.

`code` contém um código textual estável.

`observer_exit_code` contém um inteiro quando o processo devolveu um código
observável; caso contrário é nulo.

`report` contém `observers/<module>.json` apenas em caso de sucesso; nos restantes
casos é nulo.

`stdout_bytes` e `stderr_bytes` são inteiros não negativos.

`duration_ms` é um inteiro não negativo medido com relógio monotónico.

Um resultado `SUCCESS` implica:

- código textual `SUCCESS`;
- código de processo do capturador `0`;
- código do Observer `0`;
- caminho de relatório não nulo;
- relatório final existente em staging.

Um resultado `FAILED` implica caminho de relatório nulo e código de processo do
capturador diferente de zero.

O resultado não contém texto arbitrário produzido pelo Observer.

## 14. Códigos de resultado e saída

Os códigos textuais e os códigos de processo são:

| Código textual | Saída | Significado |
|---|---:|---|
| `SUCCESS` | `0` | relatório validado e persistido |
| `USAGE_INVALID` | `2` | argumentos inválidos |
| `DEPENDENCY_UNAVAILABLE` | `3` | dependência obrigatória indisponível |
| `REGISTRY_INVALID` | `3` | registo ou schema do registo inválido |
| `MODULE_NOT_AUTHORIZED` | `4` | módulo ausente do registo |
| `EXECUTABLE_MISSING` | `4` | executável registado ausente |
| `EXECUTABLE_INVALID` | `4` | executável inseguro ou incompatível |
| `STAGING_INVALID` | `5` | staging ausente, inseguro ou incompatível |
| `EXECUTION_FAILED` | `6` | Observer terminou com falha |
| `EXECUTION_TIMEOUT` | `6` | tempo limite excedido |
| `OUTPUT_LIMIT_EXCEEDED` | `6` | `stdout` excedeu o limite |
| `STDERR_LIMIT_EXCEEDED` | `6` | `stderr` excedeu o limite |
| `EMPTY_REPORT` | `6` | Observer terminou sem relatório |
| `INVALID_JSON` | `7` | candidato não é JSON estrito válido |
| `CONTRACT_VIOLATION` | `7` | relatório viola o contrato 2.1.0 |
| `MODULE_MISMATCH` | `7` | identidade do relatório divergente |
| `TEMPORARY_PERSISTENCE_FAILED` | `8` | falha de escrita ou publicação |
| `INTERNAL_ERROR` | `9` | falha interna inesperada |

Um código textual não muda de significado dentro da mesma versão principal.

Novos códigos exigem atualização do contrato, schema e testes.

## 15. Diagnósticos

Falhas previstas produzem um diagnóstico controlado em `stderr`:

    ERROR<TAB>CODE<TAB>MESSAGE

`MESSAGE` é estável, limitada e não inclui conteúdo arbitrário do Observer.

Caracteres de controlo provenientes de argumentos ou caminhos não são copiados
diretamente.

O documento JSON em `stdout` é a interface automática principal.

Uma falha que impeça a construção segura do resultado JSON produz apenas um
diagnóstico controlado e código diferente de zero.

O capturador não apresenta traceback ao utilizador numa falha prevista.

## 16. Dependências

A implementação utiliza apenas:

- Python 3;
- biblioteca padrão do Python;
- pacote Ubuntu `python3-jsonschema`;
- registo e schemas locais aprovados;
- validador oficial do relatório 2.1.0;
- capacidades Linux necessárias à publicação sem substituição.

Nenhuma dependência é instalada ou descarregada durante a captura.

O capturador:

- não abre sockets;
- não consulta DNS;
- não acede à Internet;
- não inicia shell;
- não executa comandos auxiliares encontrados em `PATH`;
- não requer privilégios administrativos.

## 17. Ordem da operação

A ordem é:

1. argumentos;
2. dependências;
3. registo e schema do registo;
4. autorização do módulo;
5. executável registado;
6. staging e destino;
7. execução limitada;
8. código de saída e presença de relatório;
9. validação de fronteira;
10. persistência temporária;
11. resultado estruturado.

Uma falha numa etapa impede as etapas que dependem dela.

Nenhum relatório é criado antes de todas as validações do candidato terminarem.

Uma falha de um Observer não promove, remove ou modifica qualquer geração.

## 18. Testes obrigatórios

Os testes usam uma raiz de projeto copiada para um diretório temporário.

Observers falsos devem simular:

- sucesso;
- código de saída diferente de zero;
- timeout;
- processo descendente durante timeout;
- `stdout` vazio;
- UTF-8 inválido;
- JSON vazio, truncado ou com conteúdo adicional;
- chaves JSON duplicadas;
- `NaN`, `Infinity` e `-Infinity`;
- relatório estruturalmente inválido;
- timestamp semanticamente inválido;
- módulo incorreto;
- versão de módulo incompatível;
- `stdout` acima do limite;
- `stderr` acima do limite;
- saída simultânea em ambos os pipes.

Os testes de autorização e staging cobrem:

- módulo autorizado;
- módulo não registado;
- executável ausente;
- executável não regular;
- executável sem permissão;
- executável como link simbólico;
- staging ausente;
- caminho relativo;
- nome sem prefixo `.staging-`;
- staging como link simbólico;
- componente intermédio como link simbólico;
- `observers/` ausente;
- `observers/` como link simbólico;
- destino já existente;
- falha de criação temporária;
- falha de escrita;
- falha de publicação;
- remoção de temporários após falha.

Os testes do resultado cobrem:

- schema válido;
- campos e tipos exatos;
- coerência de `SUCCESS`;
- coerência de `FAILED`;
- códigos textuais;
- códigos numéricos;
- formato dos diagnósticos;
- ausência de conteúdo arbitrário do Observer;
- importação sem efeitos laterais.

Nenhum teste usa Observers oficiais para simular falhas.

Nenhum teste escreve em `data/`, numa geração real ou em staging operacional.

## 19. Critérios de aceitação

A versão 1.0.0 só pode ser promovida quando:

- o contrato estiver completo e aprovado;
- o schema do resultado passar Draft 2020-12;
- todos os testes do capturador passarem;
- sucesso persistir exatamente um relatório válido;
- cada falha deixar zero relatórios finais;
- limites forem aplicados durante a execução;
- descendentes forem terminados após timeout ou excesso de saída;
- o capturador legado permanecer inalterado;
- os sete Observers permanecerem inalterados;
- o Registo de Observers mantiver todos os testes aprovados;
- Report API mantiver `PASS=125 FAIL=0`;
- contrato health mantiver `PASS=28 FAIL=0`;
- contrato serializado mantiver todos os testes aprovados;
- não existirem acessos de rede;
- não existirem escritas em dados operacionais;
- não forem necessários privilégios administrativos;
- o diff contiver apenas alterações aprovadas;
- o administrador humano validar o resultado.

Um teste falhado impede a promoção.

## 20. Evolução

Este documento permaneceu `DRAFT` durante a implementação e os testes.

A versão 1.0.0 foi aprovada após revisão integral, resultados sem falhas e
aprovação explícita.

Uma versão publicada não é alterada retroativamente.

A aprovação do capturador não autoriza a implementação ou ativação do Runner
2.0.0.
