# MPPT24 CORE
# Decision Engine Input Contract
# Version: 3.0.0

## 1. Objetivo

Este contrato define a entrada operacional do Decision Engine 3.0.0.

O Decision Engine 3.0.0 interpreta exatamente uma geração promovida pelo
Runner 2.0.0.

A entrada deixa de ser um diretório arbitrário contendo ficheiros
`observer-*.json`.

O Decision Engine:

- resolve uma única geração promovida;
- fixa a identidade dessa geração antes de consumir qualquer relatório;
- valida a referência, o manifesto e a geração;
- usa apenas relatórios declarados pelo manifesto;
- distingue dados presentes, ausentes, inválidos e desconhecidos;
- não altera a geração consumida;
- não observa diretamente o sistema operativo;
- não toma ações administrativas.

A decisão final permanece humana.

## 2. Compatibilidade

Este contrato é incompatível com a entrada operacional do Decision Engine
2.3.0 e por isso exige versão principal 3.0.0.

O Decision Engine 2.3.0 permanece preservado até que a implementação 3.0.0,
os testes e a regressão das regras existentes sejam validados.

O Decision Engine 3.0.0 suporta inicialmente:

- Runner: `2.0.0`;
- manifesto de geração: `1.0.0`;
- registo de Observers: `1.0.0`;
- contrato serializado de relatório: `2.1.0`.

Versões desconhecidas não são aceites por semelhança estrutural.

## 3. Raiz de estado

O consumidor recebe uma `STATE_ROOT` explicitamente definida.

A raiz contém, no mínimo:

- `current-generation`;
- `generations/`.

Caminhos externos à raiz não são aceites.

A definição operacional concreta de `STATE_ROOT` pertence à configuração da
fase e não é inferida silenciosamente pelo consumidor.

## 4. Resolução de current-generation

`current-generation` deve ser:

- ficheiro regular;
- não simbólico;
- localizado diretamente em `STATE_ROOT`;
- no máximo `0640`;
- não gravável por `other`.

O conteúdo deve:

- ser UTF-8 válido;
- conter exatamente uma linha;
- terminar em `LF`;
- não conter `CR`;
- conter exclusivamente um `generation_id` válido.

O Decision Engine resolve `current-generation` exatamente uma vez no início da
operação.

O `generation_id` obtido é conservado durante toda a execução.

O consumidor não volta a consultar `current-generation` para escolher outra
geração durante a mesma execução.

## 5. Resolução da geração

A geração é resolvida exclusivamente como:

`STATE_ROOT/generations/<generation_id>`

O `generation_id` nunca é interpretado como caminho livre.

Antes do consumo, o Decision Engine confirma que:

- a raiz da geração existe;
- é um diretório esperado;
- não é um link simbólico;
- o caminho permanece dentro de `STATE_ROOT/generations`;
- a identidade usada é a mesma obtida de `current-generation`.

Áreas `.staging-*` nunca são consumidas.

## 6. Validação oficial

Antes de interpretar qualquer relatório, a geração deve passar pela validação
oficial do contrato de manifesto 1.0.0.

A validação deve confirmar, entre outras garantias já pertencentes ao contrato
do manifesto:

- schema;
- `generation_id`;
- semântica temporal;
- estado da geração;
- identidade do Runner;
- identidade e hash do Registry;
- conjunto exato de relatórios;
- nomes de módulos;
- hashes dos relatórios;
- permissões;
- tipos dos objetos;
- ausência de objetos adicionais;
- estabilidade dos objetos durante a validação.

O Decision Engine não implementa uma segunda versão divergente destas regras.

A validação do manifesto é uma fronteira obrigatória de entrada.

Falha de validação impede interpretação dos relatórios.

## 7. Fonte dos relatórios

O Decision Engine usa somente os relatórios declarados em `manifest.json`.

Não é permitido descobrir relatórios através de glob genérico como fonte de
verdade operacional.

Um ficheiro existente na geração mas não declarado pelo manifesto constitui
violação da geração.

Um relatório declarado pelo manifesto deve corresponder exatamente ao objeto
validado pelo contrato de geração.

O consumidor não altera, corrige ou normaliza silenciosamente um relatório para
o tornar aceitável.

## 8. Geração COMPLETE

Uma geração `COMPLETE` validada pode ser interpretada.

Todos os módulos declarados devem possuir o resultado compatível com uma geração
`COMPLETE` segundo o contrato do manifesto.

A interpretação dos estados e dos factos segue as regras próprias do Decision
Engine.

Uma geração `COMPLETE` pode produzir estado global:

- `OK`;
- `WARNING`;
- `ERROR`;
- `UNKNOWN`;

conforme os estados e factos efetivamente presentes.

## 9. Geração PARTIAL

Uma geração `PARTIAL` validada pode ser interpretada.

A condição parcial deve permanecer explícita durante toda a análise.

Uma geração `PARTIAL` nunca pode produzir estado global `OK`.

Dados de módulos ausentes ou falhados não podem ser inventados nem substituídos
por valores implícitos.

Factos dependentes exclusivamente de um módulo sem relatório válido devem ser
tratados como dados insuficientes.

O relatório final deve tornar explícito que a análise foi produzida a partir de
uma geração parcial.

### 9.1 Política para o Registry 1.0.0

No Registry 1.0.0 todos os módulos declarados são obrigatórios.

O schema do Registry 1.0.0 exige `required: true` para cada Observer e não
suporta módulos opcionais.

O Decision Engine 3.0.0 não inventa nem antecipa uma classificação opcional.

A introdução de módulos opcionais exige:

- nova versão do Registry;
- schema compatível com essa classificação;
- política contratual própria;
- testes específicos;
- aprovação antes da ativação operacional.

### 9.2 Entrada parcial válida

Uma geração `PARTIAL` validada contém:

- pelo menos um módulo com resultado `SUCCESS`;
- pelo menos um módulo obrigatório falhado;
- um relatório validado para cada módulo com resultado `SUCCESS`;
- nenhum relatório para módulos falhados;
- `error_code` e `exit_code` validados para cada falha;
- contadores coerentes no manifesto.

O Decision Engine interpreta exclusivamente os relatórios validados existentes.

As falhas declaradas no manifesto permanecem explícitas durante toda a
interpretação.

O Decision Engine não:

- inventa factos para módulos falhados;
- substitui dados ausentes por valores implícitos;
- considera ausência de dados equivalente a estado normal;
- executa novamente Observers;
- tenta reparar a geração.

### 9.3 Estado global de uma geração parcial

O estado global é determinado pela seguinte ordem:

1. se algum relatório validado apresentar estado `ERROR`, o estado global é
   `ERROR`;
2. se não existir `ERROR` e a geração for `PARTIAL`, o estado global é
   `UNKNOWN`.

Uma geração `PARTIAL` nunca produz estado global `OK`.

Estados `WARNING` presentes nos relatórios validados permanecem explícitos nas
análises, conclusões, recomendações e avisos, mesmo quando o estado global é
`UNKNOWN`.

A insuficiência de dados obrigatórios não pode ser ocultada por relatórios
válidos em estado `OK` ou `WARNING`.

### 9.4 Domínios de health

Cada domínio de `health` é avaliado apenas com factos validados.

Para cada domínio:

- evidência validada de `ERROR` produz `ERROR`;
- na ausência de `ERROR`, a falta de um módulo ou facto necessário produz
  `UNKNOWN`;
- `OK` exige a presença e validade de todos os dados necessários;
- warnings conhecidos permanecem explícitos no relatório;
- factos ausentes nunca são convertidos em factos normais.

Quando a insuficiência de dados impede excluir um estado mais grave, a
prioridade conservadora é:

`ERROR` > `UNKNOWN` > `WARNING` > `OK`.

A aplicação desta prioridade não remove nem altera warnings efetivamente
observados.

As dependências de dados de cada regra de `health` devem ser especificadas e
testadas antes da implementação.

### 9.5 Representação da insuficiência de dados

O relatório produzido a partir de uma geração `PARTIAL` identifica
explicitamente:

- a `generation_id`;
- o estado `PARTIAL`;
- o número de módulos declarados;
- o número de módulos bem-sucedidos;
- o número de módulos falhados;
- cada módulo falhado;
- o `error_code` e o `exit_code` de cada falha;
- os domínios de `health` com avaliação incompleta;
- os factos e conclusões que não puderam ser produzidos;
- que o sistema não foi integralmente observado.

### 9.6 Confiança e cobertura

A cobertura é representada pelos contadores exatos e pelos resultados dos
módulos declarados no manifesto.

O Decision Engine não inventa uma percentagem de cobertura ou confiança
calculada através da divisão entre módulos bem-sucedidos e declarados.

A confiança mantém o significado definido pelo contrato de relatório e não
substitui a representação explícita da cobertura.

### 9.7 Regressão obrigatória

A introdução desta política não autoriza alterações silenciosas às regras de
interpretação já validadas no Decision Engine 2.3.0.

Devem existir testes para, no mínimo:

- um módulo obrigatório falhado e os restantes em `OK`;
- um módulo obrigatório falhado e um relatório em `WARNING`;
- um módulo obrigatório falhado e um relatório em `ERROR`;
- vários módulos obrigatórios falhados;
- impossibilidade de `OK` numa geração `PARTIAL`;
- domínios de `health` com factos insuficientes;
- preservação dos warnings conhecidos;
- representação exata dos códigos e contadores do manifesto.

## 10. Geração FAILED

Uma geração `FAILED` não representa o estado observável do sistema.

O Decision Engine 3.0.0 rejeita uma geração `FAILED` como entrada interpretável.

A rejeição é explícita e determinística.

Nenhum estado global `OK`, `WARNING`, `ERROR` ou `UNKNOWN` relativo ao sistema é
derivado dos Observers dessa geração.

## 11. Consistência temporal

Toda a operação usa a mesma `generation_id`.

A atualização posterior de `current-generation` pelo Runner não altera a geração
já selecionada pelo Decision Engine.

Durante a leitura, o consumidor deve detetar alterações incompatíveis nos
artefactos da geração através das garantias do validador oficial.

A promoção de uma geração mais recente não autoriza mistura de relatórios entre
gerações.

## 12. Separação de responsabilidades

O Runner:

- executa Observers;
- constrói a geração;
- valida;
- promove;
- atualiza `current-generation`.

O validador de manifesto:

- valida estrutural e semanticamente a geração;
- confirma integridade e consistência dos artefactos.

O Decision Engine:

- seleciona uma geração promovida;
- exige validação bem-sucedida;
- interpreta exclusivamente os dados dessa geração;
- produz análise, health, conclusões e recomendações.

O Decision Engine não:

- promove gerações;
- repara gerações;
- altera manifestos;
- altera relatórios;
- atualiza `current-generation`;
- executa Observers.

## 13. Preservação das regras de health

As regras de interpretação de `health` existentes no Decision Engine 2.3.0
devem possuir testes de regressão durante a implementação 3.0.0.

A mudança de transporte e validação da entrada não autoriza alteração silenciosa
das regras de health.

Qualquer alteração dessas regras exige decisão e contrato próprios.

## 14. Resultado, erros e diagnósticos

### 14.1 Sucesso técnico

O código textual `SUCCESS` e o código de processo `0` indicam que:

- a geração foi resolvida e validada;
- o snapshot foi recebido e validado;
- a interpretação terminou;
- o relatório final foi validado e emitido.

O código de processo não representa diretamente o estado global observado.

Uma interpretação concluída pode produzir relatório com estado global:

- `OK`;
- `WARNING`;
- `UNKNOWN`;
- `ERROR`.

Uma geração `PARTIAL` interpretada de acordo com a secção 9 também termina com
código de processo `0`.

A condição parcial permanece explícita no relatório e nunca é convertida em
sucesso operacional do sistema.

### 14.2 Códigos próprios do Decision Engine

Os códigos textuais e os códigos de processo próprios do Decision Engine 3.0.0
são:

| Código textual | Saída | Significado |
|---|---:|---|
| `SUCCESS` | `0` | geração interpretada e relatório final emitido |
| `USAGE_INVALID` | `2` | argumentos inválidos |
| `CONFIGURATION_INVALID` | `3` | configuração local inválida |
| `DEPENDENCY_UNAVAILABLE` | `3` | dependência obrigatória indisponível |
| `VALIDATOR_INVALID` | `3` | validador oficial ausente, inseguro ou incompatível |
| `STATE_ROOT_INVALID` | `4` | `STATE_ROOT` ausente, insegura ou incompatível |
| `CURRENT_GENERATION_MISSING` | `4` | referência atual ausente |
| `CURRENT_GENERATION_UNREADABLE` | `4` | referência atual ilegível ou insegura |
| `CURRENT_GENERATION_TOO_LARGE` | `4` | referência atual excede o limite |
| `CURRENT_GENERATION_INVALID` | `4` | conteúdo, tipo ou permissões inválidos |
| `CURRENT_GENERATION_CHANGED` | `4` | objeto mudou durante a resolução |
| `GENERATION_INVALID` | `4` | diretório ou identificador inseguro |
| `SNAPSHOT_MISSING` | `5` | validador terminou sem snapshot |
| `SNAPSHOT_UNREADABLE` | `5` | snapshot não pôde ser capturado |
| `SNAPSHOT_TOO_LARGE` | `5` | snapshot excedeu o limite |
| `SNAPSHOT_INVALID` | `6` | snapshot viola o schema ou a serialização |
| `GENERATION_FAILED` | `6` | geração válida sem módulos bem-sucedidos |
| `SNAPSHOT_SEMANTIC_VIOLATION` | `7` | relações internas incoerentes |
| `SNAPSHOT_MISMATCH` | `8` | snapshot diverge da geração pedida |
| `VALIDATOR_PROTOCOL_VIOLATION` | `8` | código ou saída do validador incoerente |
| `REPORT_EMISSION_FAILED` | `8` | relatório final não pôde ser emitido integralmente |
| `INTERNAL_ERROR` | `9` | falha interna inesperada |

Um código textual não muda de significado dentro da versão principal 3.

Novos códigos exigem atualização do contrato e testes correspondentes.

### 14.3 Falhas do validador oficial

O validador oficial permanece a autoridade para os seus próprios códigos de
falha.

Uma falha do validador só é aceite como diagnóstico contratual quando:

- o código de processo pertence à interface oficial;
- `stdout` está vazio;
- `stderr` contém exatamente um diagnóstico válido;
- o código textual corresponde à categoria do código de processo;
- a localização e a mensagem respeitam os limites definidos;
- não existe conteúdo adicional.

Quando estas condições são cumpridas, o Decision Engine:

- conserva o código textual;
- conserva o código de processo;
- volta a sanitizar a localização e a mensagem;
- emite um único diagnóstico controlado;
- não produz relatório final.

O código `USAGE_INVALID` devolvido pelo validador não é propagado como erro do
utilizador, porque os argumentos do processo filho são construídos internamente.

Um `USAGE_INVALID` do validador constitui
`VALIDATOR_PROTOCOL_VIOLATION`.

Qualquer combinação incoerente de código, `stdout` ou `stderr` constitui
`VALIDATOR_PROTOCOL_VIOLATION`.

### 14.4 Geração FAILED

Uma geração `FAILED` pode ser estrutural e semanticamente válida segundo o
contrato do manifesto.

Depois de receber um snapshot válido com estado `FAILED`, o Decision Engine
termina com:

- código textual `GENERATION_FAILED`;
- código de processo `6`;
- diagnóstico controlado;
- nenhum relatório de interpretação.

Esta rejeição não é convertida em `SNAPSHOT_INVALID`.

### 14.5 Formato dos diagnósticos

Uma falha prevista produz exatamente uma linha em `stderr` com o formato:

`ERROR<TAB>CODE<TAB>LOCATION<TAB>MESSAGE<LF>`

O diagnóstico:

- usa um código textual contratual;
- substitui caracteres de controlo provenientes da entrada;
- limita o tamanho da localização e da mensagem;
- não copia conteúdo arbitrário do snapshot;
- não expõe caminhos externos desnecessários;
- não inclui traceback;
- é determinístico para a mesma causa.

Durante uma falha, `stdout` não contém um relatório final válido.

Uma exceção inesperada é convertida em `INTERNAL_ERROR`.

### 14.6 Interface de saída

Em caso de sucesso:

- o relatório final é integralmente construído e validado antes da emissão;
- `stdout` é reservado ao relatório final;
- `stderr` permanece vazio;
- o código de processo é `0`.

Em caso de falha:

- nenhum relatório final é apresentado como válido;
- `stderr` contém o diagnóstico controlado;
- o código de processo é diferente de zero.

O snapshot recebido do validador é uma interface interna.

O snapshot nunca é encaminhado diretamente para a saída final do Decision
Engine.

## 15. Matriz de testes obrigatórios

### 15.1 Schema e fixtures

Devem existir testes que confirmem:

- identidade e dialecto do schema do snapshot 1.0.0;
- validade do próprio schema segundo JSON Schema Draft 2020-12;
- ausência de referências externas no schema do envelope;
- cinco propriedades obrigatórias e rejeição de propriedades adicionais;
- tipos, versão, estados e limites definidos no envelope;
- validade das fixtures `COMPLETE`, `PARTIAL` e `FAILED`;
- serialização determinística das fixtures oficiais;
- preservação da ordem dos módulos em `reports`;
- validação separada do manifesto e de cada relatório incorporado.

### 15.2 Resolução de current-generation

Devem existir testes isolados para:

- `STATE_ROOT` válido;
- `STATE_ROOT` ausente, inseguro ou com permissões excessivas;
- `current-generation` válido;
- referência ausente;
- referência ilegível;
- referência simbólica;
- referência com tipo diferente de ficheiro regular;
- referência acima do limite;
- UTF-8 inválido;
- identificador inválido;
- conteúdo adicional ou terminação inválida;
- mudança do objeto durante a leitura;
- geração inexistente;
- geração fora da raiz autorizada;
- fixação da mesma `generation_id` durante toda a operação;
- mudança de `current-generation` depois da resolução sem alteração da
  identidade já fixada.

### 15.3 Captura e serialização do snapshot

Devem existir testes para:

- sucesso com exatamente um documento JSON compacto e um `LF`;
- snapshot vazio;
- snapshot acima de 16777216 bytes;
- diagnóstico acima de 4096 bytes;
- BOM;
- UTF-8 inválido;
- JSON vazio ou truncado;
- conteúdo depois do documento;
- chave duplicada;
- número não finito;
- profundidade superior a 40 níveis;
- ausência do `LF` final;
- mais de um `LF` fora de sequências JSON escapadas;
- escrita interrompida;
- tempo de execução superior a 60 segundos;
- aplicação dos limites durante a captura.

### 15.4 Envelope e documentos incorporados

Devem existir testes para:

- cada propriedade obrigatória ausente;
- propriedade adicional;
- `snapshot_version` incompatível;
- estado inválido;
- tipo incorreto de cada propriedade;
- mais de 32 propriedades em `reports`;
- manifesto que viola o schema 1.0.0;
- relatório que viola o schema 2.1.0;
- schema local ausente, inseguro, inválido ou com identidade divergente;
- garantia de que nenhuma resolução de schema usa a rede.

### 15.5 Correspondências semânticas

Devem existir testes para:

- correspondência da `generation_id` externa com o manifesto;
- correspondência do estado externo com o manifesto;
- correspondência com a `generation_id` solicitada ao validador;
- igualdade entre `reports`, módulos `SUCCESS`, `successful` e
  `reports_written`;
- ausência de relatório para cada módulo `FAILED`;
- relatório ausente;
- relatório adicional;
- chave de `reports` divergente do módulo;
- módulo, versão, timestamp ou estado divergente do descritor;
- módulos duplicados;
- ordem divergente;
- contadores incoerentes;
- manifesto adulterado;
- hash ou tamanho divergente detetado pelo validador oficial;
- leitura consistente de uma única geração.

### 15.6 Estados da geração

Devem existir testes para:

- geração `COMPLETE` com todos os módulos bem-sucedidos;
- geração `PARTIAL` com um módulo bem-sucedido;
- geração `PARTIAL` com vários módulos bem-sucedidos;
- geração `PARTIAL` com um módulo falhado;
- geração `PARTIAL` com vários módulos falhados;
- impossibilidade de estado global `OK` numa geração `PARTIAL`;
- estado global `ERROR` quando existe evidência validada de `ERROR`;
- estado global `UNKNOWN` numa geração `PARTIAL` sem evidência de `ERROR`;
- preservação de warnings conhecidos numa geração `PARTIAL`;
- geração `FAILED` com `reports` vazio;
- rejeição explícita de `FAILED` através de `GENERATION_FAILED`;
- ausência de relatório final para uma geração `FAILED`.

No Registry 1.0.0 todos os módulos são obrigatórios.

Testes relativos a módulos opcionais só pertencem a uma futura versão do
Registry e do respetivo contrato que suporte explicitamente essa classificação.

### 15.7 Erros, diagnósticos e protocolo

Devem existir testes para:

- cada código textual e código de processo definido na secção 14;
- diagnóstico com exatamente quatro campos separados por `TAB`;
- exatamente um `LF` final no diagnóstico;
- sanitização de caracteres de controlo;
- limites de localização e mensagem;
- ausência de traceback;
- `stdout` reservado ao relatório final em caso de sucesso;
- `stderr` vazio em caso de sucesso;
- ausência de relatório final válido em caso de falha;
- propagação controlada de falhas válidas do validador;
- conversão de `USAGE_INVALID` do validador em
  `VALIDATOR_PROTOCOL_VIOLATION`;
- código, `stdout` ou `stderr` incoerentes;
- exceção inesperada convertida em `INTERNAL_ERROR`;
- falha de emissão integral convertida em `REPORT_EMISSION_FAILED`.

### 15.8 Regras de health

Cada regra de `health` deve possuir dependências de dados explicitamente
identificadas e testes para:

- todos os factos necessários presentes;
- módulo necessário falhado;
- facto necessário ausente;
- evidência validada de `ERROR`;
- warning conhecido com dados completos;
- warning conhecido com dados incompletos;
- prioridade `ERROR` sobre `UNKNOWN`;
- prioridade `UNKNOWN` sobre `WARNING`;
- impossibilidade de converter ausência em estado normal;
- factos e conclusões que não puderam ser produzidos;
- representação exata da cobertura através dos contadores do manifesto;
- regressão integral das regras validadas no Decision Engine 2.3.0.

### 15.9 Compatibilidade, isolamento e não regressão

Devem existir testes que confirmem:

- interface silenciosa do validador sem
  `--emit-validated-snapshot`;
- código zero e ausência de `stdout` e `stderr` nessa interface;
- emissão de snapshot apenas com a opção explícita;
- regras de validação idênticas nos dois modos;
- Runner 2.0.0 sem alteração de comportamento;
- Decision Engine 2.3.0 intacto durante o desenvolvimento;
- ausência de reabertura do manifesto e dos relatórios pelo consumidor;
- ausência de mistura entre snapshot e novas leituras da geração;
- ausência de acesso à rede durante a validação;
- utilização exclusiva de raízes temporárias e isoladas;
- ausência de alterações a dados operacionais reais;
- resultados determinísticos para a mesma entrada.

## 16. Ordem de implementação

A implementação só começa depois de:

1. este contrato ser revisto;
2. a política da secção 9.1 ser decidida;
3. os códigos de erro serem definidos;
4. os testes do contrato serem especificados.

O Decision Engine 2.3.0 permanece intacto até existir implementação 3.0.0
validada e uma promoção explicitamente aprovada.

## 17. Fronteira de snapshot validado

### 17.1 Autoridade de validação

`core/validate-manifest.py` permanece a única autoridade oficial para validar
o contrato de manifesto 1.0.0, a geração e os relatórios nela declarados.

O Decision Engine 3.0.0 não reimplementa nem mantém uma segunda versão das
regras estruturais, semânticas, criptográficas ou de permissões pertencentes
ao validador oficial.

A validação é executada sobre a geração identificada pela `generation_id`
fixada no início da operação.

### 17.2 Interface opcional

O validador oficial deve possuir um modo explícito e opcional para produzir um
snapshot validado destinado a consumidores autorizados.

A interface silenciosa existente permanece inalterada:

- sucesso produz código de saída zero e nenhuma saída;
- falha produz um código de saída não zero e diagnóstico controlado;
- o Runner 2.0.0 continua a usar exclusivamente esta interface silenciosa.

O modo de snapshot só é ativado através de uma opção explícita.

A ativação dessa opção não altera as regras usadas para validar a geração.

### 17.3 Origem do snapshot

O snapshot é construído exclusivamente a partir dos conteúdos que o validador
já leu e validou durante a mesma execução.

Depois da revalidação final da geração, do manifesto e dos relatórios, o
validador pode serializar esses conteúdos validados sem voltar a abrir os
ficheiros pelos respetivos caminhos.

Nenhum relatório ausente, falhado, adicional ou não declarado pode ser
introduzido no snapshot.

O snapshot identifica explicitamente:

- a versão do próprio contrato de snapshot;
- a `generation_id`;
- o estado da geração;
- o manifesto validado;
- os módulos declarados;
- o resultado de cada módulo;
- os relatórios validados correspondentes aos módulos com resultado
  `SUCCESS`.

### 17.4 Consumo pelo Decision Engine

O Decision Engine 3.0.0 interpreta exclusivamente o snapshot recebido com
sucesso do validador oficial.

Depois da validação, o Decision Engine não volta a abrir:

- `manifest.json`;
- a diretoria `observers/`;
- os relatórios individuais da geração.

A interpretação, as regras de `health`, as conclusões e as recomendações usam
apenas os dados do snapshot capturado.

Uma falha, saída incompleta, saída excessiva ou snapshot inválido impede a
interpretação.

### 17.5 Resolução da referência atual

A resolução segura de `current-generation` ocorre antes da chamada ao
validador e pertence à fronteira de entrada do Decision Engine.

O Decision Engine:

1. valida `STATE_ROOT`;
2. lê e valida `current-generation`;
3. fixa uma única `generation_id`;
4. resolve `STATE_ROOT/generations/<generation_id>`;
5. confirma que a geração permanece dentro da raiz autorizada;
6. solicita ao validador um snapshot dessa identidade exata.

Uma atualização posterior de `current-generation` não altera a geração já
fixada para a operação em curso.

### 17.6 Atomicidade da interpretação

O snapshot capturado constitui a entrada imutável da interpretação.

Alterações detetadas pelo validador durante a leitura ou revalidação causam
falha e impedem a emissão de um snapshot utilizável.

O Decision Engine não mistura:

- dados obtidos antes e depois da validação;
- relatórios de gerações diferentes;
- dados do snapshot com novas leituras do sistema de ficheiros.

### 17.7 Decisões e artefactos contratuais

Ficam definidos por este contrato:

- o caráter explícito e opcional do modo de snapshot;
- a preservação da interface silenciosa usada pelo Runner 2.0.0;
- a construção do snapshot a partir dos conteúdos já validados;
- a proibição de reabrir os relatórios depois da validação;
- a utilização do snapshot como única entrada da interpretação;
- a separação entre `stdout` e `stderr`;
- os códigos de processo e códigos textuais da secção 14;
- o formato contratual dos diagnósticos;
- a política para gerações `PARTIAL` definida na secção 9;
- a rejeição explícita de gerações `FAILED`;
- a opção `--emit-validated-snapshot`;
- o contrato de snapshot 1.0.0 definido na secção 18;
- a validação local separada do envelope, manifesto e relatórios;
- as dependências e prioridades de `health` definidas na secção 19.
- a arquitetura Python e o ponto de entrada definidos na secção 20;

Estão preparados e validados:

- o schema oficial do envelope de snapshot 1.0.0;
- as fixtures válidas `COMPLETE`, `PARTIAL` e `FAILED`;
- a matriz de testes da secção 15;
- os testes-base do schema, envelope e documentos incorporados;
- a identificação das dependências de dados das regras de `health`.

Antes da implementação do código operacional devem ainda ser preparados e
validados:

- os testes das correspondências semânticas;
- os testes de serialização e limites de captura;
- os testes da resolução segura de `current-generation`;
- os testes dos códigos, diagnósticos e protocolo do validador;
- os testes de `health` para dados completos e insuficientes;
- os testes de compatibilidade da interface silenciosa;
- os testes de regressão integral do Decision Engine 2.3.0.

Os casos inválidos são materializados em raízes temporárias a partir das
fixtures oficiais sempre que não seja necessária uma fixture permanente de
bytes.

Nenhum comportamento pode ser decidido silenciosamente durante a
implementação.

### 17.8 Compatibilidade e promoção

A introdução do modo de snapshot não altera o comportamento usado atualmente
pelo Runner 2.0.0.

O Decision Engine 2.3.0 permanece intacto e operacional durante o
desenvolvimento.

O contrato, a implementação, os testes e a regressão integral das regras de
`health` devem ser validados antes de qualquer promoção explícita do Decision
Engine 3.0.0.

## 18. Contrato do snapshot validado 1.0.0

### 18.1 Ativação da interface

O modo de snapshot é ativado exclusivamente pela opção:

`--emit-validated-snapshot`

Sem esta opção, o validador mantém a interface silenciosa usada pelo Runner
2.0.0.

Com esta opção e validação bem-sucedida:

- o código de processo é `0`;
- `stdout` contém exatamente um snapshot;
- `stderr` permanece vazio.

A opção não altera as regras de validação da geração, do manifesto ou dos
relatórios.

### 18.2 Objeto de topo

O snapshot é um único objeto JSON com exatamente as propriedades:

- `snapshot_version`;
- `generation_id`;
- `state`;
- `manifest`;
- `reports`.

Todas as propriedades são obrigatórias.

Propriedades adicionais não são permitidas.

`snapshot_version` contém exatamente:

`1.0.0`

`generation_id` contém o identificador fixado pelo consumidor e validado pelo
validador.

`state` contém exatamente um de:

- `COMPLETE`;
- `PARTIAL`;
- `FAILED`.

### 18.3 Manifesto e relatórios

`manifest` contém integralmente o documento do manifesto 1.0.0 já validado.

O snapshot não cria uma representação reduzida ou alternativa do manifesto.

`reports` é um objeto cujas chaves são nomes de módulos.

Cada valor de `reports` contém integralmente o documento de relatório 2.1.0 já
validado para esse módulo.

As chaves de `reports` são serializadas segundo a ordem dos módulos no
manifesto.

A interpretação semântica não depende da ordem das propriedades de um objeto
JSON.

### 18.4 Correspondências obrigatórias

Devem verificar-se todas as relações seguintes:

`snapshot.generation_id == snapshot.manifest.generation_id`

`snapshot.state == snapshot.manifest.state`

O número de propriedades em `reports` é igual a:

- `manifest.summary.successful`;
- `manifest.summary.reports_written`.

Para cada entrada de `manifest.modules` com resultado `SUCCESS`:

- existe exatamente uma propriedade homónima em `reports`;
- a chave coincide com o campo `module` do relatório;
- módulo, versão, timestamp e estado coincidem com o descritor do manifesto;
- o relatório pertence ao contrato 2.1.0.

Para cada entrada com resultado `FAILED`:

- não existe propriedade homónima em `reports`;
- `report` permanece `null` no manifesto;
- `error_code` e `exit_code` permanecem disponíveis no manifesto.

Não são permitidos relatórios adicionais.

### 18.5 Estados da geração

Para uma geração `COMPLETE`:

- todos os módulos têm resultado `SUCCESS`;
- existe exatamente um relatório por módulo;
- `reports` contém todos os módulos declarados.

Para uma geração `PARTIAL`:

- existe pelo menos um módulo `SUCCESS`;
- existe pelo menos um módulo `FAILED`;
- `reports` contém exatamente os módulos bem-sucedidos.

Para uma geração `FAILED`:

- todos os módulos têm resultado `FAILED`;
- `reports` é o objeto vazio `{}`;
- o snapshot pode ser válido;
- o Decision Engine rejeita a interpretação conforme a secção 14.4.

### 18.6 Schema e validação local separada

O contrato de snapshot possui versão `1.0.0`.

O identificador do schema do envelope é:

`urn:mppt24:schema:validated-generation-snapshot:1.0.0`

O caminho previsto é:

`schemas/validated-generation-snapshot/1.0.0/validated-generation-snapshot.schema.json`

O schema do snapshot valida exclusivamente o envelope:

- as cinco propriedades obrigatórias;
- `snapshot_version`;
- os tipos das propriedades;
- os estados permitidos;
- o limite máximo de propriedades em `reports`;
- a rejeição de propriedades adicionais.

O schema do envelope não contém referências externas.

O consumidor carrega separadamente, através de caminhos locais fixos:

- o schema do envelope de snapshot 1.0.0;
- o schema do manifesto de geração 1.0.0;
- o schema de relatório 2.1.0.

Antes de validar documentos, o consumidor confirma a identidade, o dialecto e
a validade de cada schema local.

A validação ocorre pela seguinte ordem:

1. validar o envelope através do schema do snapshot;
2. validar `manifest` através do schema oficial do manifesto 1.0.0;
3. validar cada valor de `reports` através do schema oficial de relatório
   2.1.0;
4. validar as correspondências semânticas da secção 18.4.

Nenhuma referência é resolvida através da rede.

As regras do manifesto e dos relatórios permanecem exclusivamente nos seus
schemas oficiais e não são copiadas para o schema do envelope.

Uma falha num schema local constitui erro de configuração.

Uma violação do envelope ou de um documento incorporado constitui
`SNAPSHOT_INVALID`.

Uma divergência entre documentos individualmente válidos é classificada
segundo as relações semânticas e de identidade da secção 14.

### 18.7 Serialização

O snapshot:

- é um único documento JSON;
- usa UTF-8 estrito;
- não contém BOM;
- não contém chaves duplicadas;
- não contém números não finitos;
- possui profundidade máxima de 40 níveis;
- usa serialização compacta;
- possui construção determinística;
- termina com exatamente um `LF`;
- não contém dados depois do `LF` final.

O validador serializa apenas dados já mantidos em memória e revalidados.

O validador não volta a abrir o manifesto ou os relatórios para produzir o
snapshot.

### 18.8 Limites

Os limites da interface são:

| Elemento | Limite |
|---|---:|
| snapshot completo em `stdout` | 16777216 bytes |
| diagnóstico completo em `stderr` | 4096 bytes |
| execução do validador | 60 segundos |
| localização do diagnóstico | 240 caracteres |
| mensagem do diagnóstico | 240 caracteres |

O limite do snapshot inclui o `LF` final.

Os limites são aplicados durante a captura e não apenas depois de o processo
terminar.

Uma saída que exceda o limite não é truncada e aceite como válida.

### 18.9 Captura incompleta ou incoerente

Com código de processo `0`:

- zero bytes em `stdout` produz `SNAPSHOT_MISSING`;
- excesso do limite produz `SNAPSHOT_TOO_LARGE`;
- JSON truncado ou inválido produz `SNAPSHOT_INVALID`;
- violação do schema produz `SNAPSHOT_INVALID`;
- relações internas incoerentes produzem
  `SNAPSHOT_SEMANTIC_VIOLATION`;
- identidade divergente produz `SNAPSHOT_MISMATCH`;
- qualquer conteúdo em `stderr` produz
  `VALIDATOR_PROTOCOL_VIOLATION`.

Uma escrita interrompida nunca é completada, corrigida ou interpretada
silenciosamente pelo consumidor.

Com código de processo diferente de zero aplica-se a secção 14.3.

O tempo limite termina a execução do validador e impede qualquer interpretação.

### 18.10 Validação pelo consumidor

Antes da interpretação, o Decision Engine:

1. confirma os limites de captura;
2. confirma UTF-8 estrito e a terminação;
3. analisa JSON estrito;
4. valida o schema do snapshot;
5. confirma `snapshot_version`;
6. confirma a `generation_id` solicitada;
7. confirma todas as relações da secção 18.4;
8. confirma o estado da geração;
9. fixa o objeto validado como única entrada da interpretação.

O Decision Engine não reabre a geração depois desta validação.

A autoridade sobre a integridade do manifesto, hashes, permissões, tipos dos
objetos e contratos dos relatórios permanece no validador oficial.

O consumidor valida a interface recebida e as correspondências necessárias,
sem criar uma segunda implementação do validador da geração.

## 19. Dependências das regras de health

### 19.1 Princípios comuns

Cada domínio de `health` é calculado exclusivamente a partir do manifesto e dos
relatórios presentes no snapshot validado.

As dependências classificam-se como:

- determinantes: necessárias para calcular o estado do domínio;
- suplementares: acrescentam conclusões, mas não alteram por si só o estado.

Um módulo com resultado `FAILED` não possui relatório nem factos.

Quando um módulo ou facto determinante está indisponível, inválido ou não
permite distinguir os estados previstos, o domínio correspondente produz
`UNKNOWN`, salvo quando já existe evidência validada de `ERROR`.

Um facto ausente não é convertido num valor normal, falso ou zero.

Uma entidade explicitamente observada como inativa, indisponível ou inexistente
não é um facto ausente. O seu significado operacional é determinado pelas
regras do respetivo domínio.

Factos suplementares ausentes ou inválidos não são inventados e não produzem
conclusões baseadas em valores implícitos.

### 19.2 Domínio overall

O domínio `overall` depende de:

- `manifest.state`;
- resultado de cada módulo declarado;
- estado de cada relatório correspondente a um módulo `SUCCESS`.

Para uma geração `COMPLETE`, preserva-se a agregação do Decision Engine 2.3.0:

1. pelo menos um relatório em `ERROR` produz `ERROR`;
2. na ausência de `ERROR`, pelo menos um relatório em `WARNING` produz
   `WARNING`;
3. na ausência de `ERROR` e `WARNING`, pelo menos um relatório em `UNKNOWN`
   produz `UNKNOWN`;
4. todos os relatórios em `OK` produzem `OK`.

Para uma geração `PARTIAL`:

1. pelo menos um relatório validado em `ERROR` produz `ERROR`;
2. na ausência de `ERROR`, o resultado é `UNKNOWN`.

Uma geração `PARTIAL` nunca produz `overall = OK` nem oculta estados `WARNING`
presentes nos relatórios existentes.

Uma geração `FAILED` não é interpretada e aplica a secção 14.4.

O valor de `health.overall.status` é sempre igual ao campo `status` do relatório
final.

### 19.3 Domínio system

O domínio `system` utiliza:

- estado do relatório `observer-system`;
- facto determinante `time_available`;
- facto determinante `ntp_enabled`;
- facto determinante `ntp_synchronized`.

As regras são:

1. módulo falhado, estado ausente ou estado desconhecido produz `UNKNOWN`;
2. estado `ERROR` produz `ERROR`;
3. estado `WARNING` produz `WARNING`;
4. estado `OK` com algum facto determinante ausente ou inválido produz
   `UNKNOWN`;
5. estado `OK` com `time_available = true` e NTP desativado ou não sincronizado
   produz `WARNING`;
6. estado `OK` com `time_available = true`, NTP ativado e sincronizado produz
   `OK`.

`ntp_enabled = false` e `ntp_synchronized = false` são factos válidos e não
podem ser confundidos com ausência.

### 19.4 Domínio security

O domínio `security` utiliza o relatório `observer-ssh`.

São factos determinantes:

- `journal_available`;
- `failed_password_events_24h`.

São factos suplementares:

- `invalid_user_events_24h`;
- `accepted_publickey_events_24h`.

As regras determinantes são:

1. módulo falhado produz `UNKNOWN`;
2. `journal_available` ausente, inválido ou diferente de `true` produz
   `UNKNOWN`;
3. `failed_password_events_24h` ausente ou não inteiro não negativo produz
   `UNKNOWN`;
4. um valor superior a zero em `failed_password_events_24h` produz `WARNING`;
5. um valor igual a zero produz `OK`.

Um valor inteiro positivo em `invalid_user_events_24h` acrescenta a conclusão
sobre utilizadores inválidos.

Um valor inteiro positivo em `accepted_publickey_events_24h` acrescenta a
conclusão sobre utilização de autenticação por chave pública.

A ausência ou invalidade de um facto suplementar impede apenas a conclusão que
depende desse facto e nunca é convertida em zero.

### 19.5 Domínio resources

O domínio `resources` utiliza:

- `observer-cpu.cpu_count`;
- `observer-cpu.load_15min`;
- `observer-memory.memory.MemTotal`;
- `observer-memory.memory.MemAvailable`;
- `observer-memory.memory.SwapTotal`;
- `observer-memory.memory.SwapFree`.

Todos estes factos são determinantes.

O módulo `observer-cpu` ou `observer-memory` falhado, ou qualquer facto
determinante ausente ou inválido, produz `UNKNOWN`.

Com todos os factos válidos:

1. `load_15min >= cpu_count * 2` produz `ERROR`;
2. `MemAvailable < 5% de MemTotal` produz `ERROR`;
3. na ausência de `ERROR`, `load_15min >= cpu_count` produz `WARNING`;
4. na ausência de `ERROR`, `MemAvailable < 15% de MemTotal` produz `WARNING`;
5. na ausência de `ERROR`, swap utilizado igual ou superior a 75% produz
   `WARNING`;
6. nenhuma condição anterior produz `OK`.

A regra de swap só é aplicada quando `SwapTotal` é superior a zero.

### 19.6 Domínio connectivity

O domínio `connectivity` utiliza o relatório `observer-network`.

São estruturas determinantes:

- `interfaces`, como array;
- `default_routes`, como array.

São entidades operacionais esperadas:

- interface LAN `enp8s0`;
- interface Tailscale `tailscale0`;
- interface WireGuard `wg0`;
- primeira rota predefinida;
- campos `gateway` e `dev` da primeira rota predefinida.

Um módulo falhado, estrutura determinante ausente ou inválida, ou uma entidade
presente com dados insuficientes para determinar o respetivo estado produz
`UNKNOWN`.

Quando as estruturas são válidas e representam integralmente a observação:

1. `enp8s0` ausente ou diferente de `UP` produz `ERROR`;
2. ausência de rota predefinida produz `ERROR`;
3. gateway ausente ou dispositivo da rota diferente de `enp8s0` produz
   `ERROR`;
4. na ausência de `ERROR`, `tailscale0` ou `wg0` ausente ou diferente de `UP`
   produz `WARNING`;
5. LAN, gateway, Tailscale e WireGuard operacionais produzem `OK`.

Uma interface está `UP` quando os factos validados indicam simultaneamente as
flags `UP` e `LOWER_UP`.

A ausência observada de uma interface esperada é uma condição operacional. Não
é convertida em insuficiência de dados quando o relatório representa
integralmente o conjunto de interfaces observado.

### 19.7 Domínio services

O domínio `services` utiliza o relatório `observer-services` e os factos
determinantes:

- `ssh.service`;
- `tailscaled.service`;
- `fail2ban.service`;
- `AdGuardHome.service`.

As regras são:

1. módulo falhado ou algum facto determinante ausente ou inválido produz
   `UNKNOWN`;
2. `ssh.service` ou `AdGuardHome.service` diferente de `active` produz
   `ERROR`;
3. na ausência de `ERROR`, `tailscaled.service` ou `fail2ban.service`
   diferente de `active` produz `WARNING`;
4. todos os quatro serviços em `active` produzem `OK`.

As conclusões individuais sobre serviços operacionais só são produzidas para
factos explicitamente validados como `active`.

### 19.8 Preservação e adaptação das regras 2.3.0

Os limiares e classificações operacionais definidos nesta secção preservam as
regras validadas no Decision Engine 2.3.0.

As adaptações necessárias para o Decision Engine 3.0.0 limitam-se a:

- utilizar exclusivamente o snapshot validado;
- considerar os resultados dos módulos declarados no manifesto;
- representar módulos falhados e factos determinantes ausentes como
  insuficiência de dados;
- impedir `overall = OK` numa geração `PARTIAL`;
- preservar warnings e erros conhecidos mesmo quando existe observação
  incompleta.

Qualquer alteração futura de módulos, factos, limiares ou prioridades exige
atualização contratual e testes antes da implementação.

## 20. Arquitetura da implementação 3.0.0

### 20.1 Preservação da versão 2.3.0

O ficheiro `decision/decision-engine.sh` permanece a implementação oficial do
Decision Engine 2.3.0 durante todo o desenvolvimento.

O desenvolvimento 3.0.0 não modifica esse ficheiro nem reutiliza o seu
diretório arbitrário de relatórios como fronteira operacional.

A versão 2.3.0 constitui também uma referência de regressão para as regras de
interpretação aplicáveis a gerações `COMPLETE`.

### 20.2 Implementação candidata

A implementação candidata do Decision Engine 3.0.0 usa Python 3 e o caminho:

`decision/decision-engine.py`

Durante o desenvolvimento, novas versões desse ficheiro são preparadas e
validadas como candidatos antes de qualquer promoção operacional.

A identidade declarada é:

- módulo: `decision-engine`;
- versão: `3.0.0`;
- contrato de relatório: `2.1.0`.

A utilização prevista é:

`decision-engine.py --state-root <STATE_ROOT>`

A opção `--state-root` é obrigatória, não pode ser repetida e recebe uma única
raiz explícita.

O consumidor não infere silenciosamente `STATE_ROOT` a partir do diretório do
projeto, do utilizador ou de dados legados.

Argumentos desconhecidos ou posicionais adicionais produzem `USAGE_INVALID`.

### 20.3 Processo e fronteiras internas

A resolução da referência, a captura do validador, a validação do snapshot, a
interpretação e a construção do relatório final ocorrem no mesmo processo do
Decision Engine.

O processo pode executar exclusivamente o validador oficial como processo
filho para obter o snapshot.

O processo filho é invocado através de uma lista fixa de argumentos que inclui:

- `/usr/bin/python3`;
- `-I`;
- caminho local fixo de `core/validate-manifest.py`;
- `--emit-validated-snapshot`;
- `--expected-generation-id`;
- a `generation_id` previamente fixada;
- o caminho da geração previamente resolvida.

O processo filho recebe:

- `stdin` fechado;
- `stdout` e `stderr` separados;
- ambiente mínimo e determinístico;
- descritores não necessários fechados;
- diretório de trabalho local fixo;
- nova sessão de processos através de `start_new_session=True`.

A captura aplica durante a execução os limites da secção 18.8.

Quando o limite de 60 segundos é atingido, o Decision Engine:

1. marca a execução como expirada;
2. envia `SIGTERM` ao grupo da sessão do processo filho;
3. continua a drenar `stdout` e `stderr` sob os limites contratuais;
4. aguarda no máximo 2 segundos pela terminação;
5. envia `SIGKILL` ao grupo se algum processo permanecer;
6. recolhe o estado final do processo filho.

Nenhum snapshot proveniente de uma execução que atingiu o limite temporal é
aceite, mesmo que o processo termine posteriormente com código zero ou tenha
produzido um documento aparentemente completo.

### 20.4 Entrada imutável da interpretação

Depois de validado, o objeto de snapshot em memória é a única entrada da
interpretação.

A implementação 3.0.0 não:

- volta a abrir `manifest.json`;
- volta a enumerar `observers/`;
- volta a abrir relatórios da geração;
- reconstrói um diretório temporário de relatórios;
- invoca o Decision Engine 2.3.0 como intérprete;
- mistura o snapshot com dados obtidos posteriormente do sistema de ficheiros.

As regras portadas recebem estruturas imutáveis ou referências internas que não
são modificadas durante a interpretação.

### 20.5 Validação local e responsabilidades

O processo carrega através de caminhos locais fixos:

- schema do envelope de snapshot 1.0.0;
- schema do manifesto de geração 1.0.0;
- schema de relatório 2.1.0.

A implementação confirma antes da utilização:

- tipo e segurança do ficheiro;
- limite de tamanho;
- UTF-8 e JSON estritos;
- dialecto;
- identificador;
- validade do próprio schema;
- estabilidade do objeto lido.

Não existe resolução de schemas através da rede.

O consumidor valida o envelope, os documentos incorporados e as
correspondências da secção 18.4.

A autoridade sobre a geração, permissões, hashes e estabilidade dos ficheiros
permanece em `core/validate-manifest.py`.

### 20.6 Interpretação e relatório final

As regras de interpretação são portadas individualmente a partir do Decision
Engine 2.3.0 e obedecem à secção 19.

O relatório final:

- é construído integralmente em memória;
- respeita o contrato serializado de relatório 2.1.0;
- contém módulo `decision-engine` e versão `3.0.0`;
- é validado através do schema oficial antes da emissão;
- usa serialização determinística;
- termina com exatamente um `LF`;
- só é escrito em `stdout` depois de estar integralmente validado.

Nenhum fragmento de relatório final é emitido antes da conclusão da validação.

Falha durante construção, validação ou emissão impede que uma saída parcial seja
apresentada como relatório válido.

### 20.7 Estratégia de regressão

Para gerações `COMPLETE`, os testes comparam a implementação 3.0.0 com a versão
2.3.0 usando os mesmos documentos de relatório validados.

A comparação ignora apenas diferenças contratuais intencionais:

- versão do módulo;
- timestamp da execução;
- representação explícita da identidade e cobertura da geração;
- textos novos estritamente necessários para identificar a origem do snapshot.

Devem permanecer equivalentes:

- estado global;
- estados dos seis domínios de `health`;
- limiares de `system`, `security`, `resources`, `connectivity` e `services`;
- factos interpretados;
- conclusões e recomendações cujo significado não seja alterado pelo novo
  contrato de entrada.

As diferenças esperadas para gerações `PARTIAL` e a rejeição de `FAILED` são
testadas diretamente segundo as secções 9, 14, 18 e 19.

Nenhuma diferença adicional é aceite sem alteração contratual e aprovação
explícita.

### 20.8 Dependências e promoção

A implementação utiliza apenas dependências locais já autorizadas pelo projeto,
incluindo Python 3 e `jsonschema`.

A importação do módulo não executa o programa nem produz efeitos laterais.

Os testes usam exclusivamente raízes temporárias e processos controlados.

A implementação candidata não substitui, renomeia nem remove o executável
2.3.0.

Qualquer alteração do ponto de entrada operacional exige:

1. implementação 3.0.0 concluída;
2. matriz obrigatória integralmente validada;
3. regressão 2.3.0 concluída;
4. revisão dos artefactos Git;
5. promoção humana explícita.
