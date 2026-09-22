# MPPT24 CORE — Arquitetura do Pipeline

Estado do documento: APROVADO
Versão do documento: 1.0.0
Data: 16 de agosto de 2026

## 1. Objetivo

Este documento define a arquitetura integral do pipeline da MPPT24 CORE.

O objetivo é estabelecer, antes da implementação:

- os componentes e as respetivas responsabilidades;
- as fronteiras de confiança;
- os contratos entre componentes;
- o fluxo e o ciclo de vida dos dados;
- as garantias de consistência, atomicidade e imutabilidade;
- o comportamento perante falhas;
- a política de compatibilidade;
- as condições necessárias para testes, promoção e operação.

Este documento não substitui os contratos específicos dos módulos. Define como
esses módulos se relacionam como um único sistema.

## 2. Princípios de autoridade

A arquitetura respeita os princípios definidos em `MANIFESTO.md`:

1. observar antes de interpretar;
2. interpretar antes de decidir;
3. decidir antes de agir;
4. nunca alterar o sistema sem decisão explícita;
5. nunca inventar factos;
6. basear conhecimento em evidências;
7. atribuir uma única responsabilidade a cada módulo;
8. permitir testes isolados;
9. manter a decisão final no administrador humano;
10. dar prioridade à simplicidade.

Quando existir conflito entre implementação e contrato documentado, a
implementação não deve ser considerada autoridade por si própria. O conflito
deve ser observado, analisado e resolvido explicitamente antes de qualquer
promoção.

## 3. Âmbito

Esta arquitetura cobre:

- registo dos Observers autorizados;
- execução e captura dos Observers;
- validação dos relatórios serializados;
- criação e promoção de gerações;
- manifesto de cada geração;
- consumo pelo Decision Engine;
- preservação histórica;
- concorrência;
- integração operacional futura;
- entrega a consumidores externos e ao administrador humano.

## 4. Fora do âmbito desta fase

Esta fase não:

- altera os Observers existentes;
- modifica a Report API 2.1.0;
- modifica o Decision Engine 2.3.0;
- executa o Runner ou o Historian;
- cria serviços ou timers systemd;
- liga a MPPT24 CORE ao coletor privilegiado do túnel MCP;
- define ações automáticas sobre o sistema observado;
- instala novas dependências;
- promove código operacional.

A implementação só poderá começar depois de esta arquitetura, os contratos,
a matriz de falhas e o plano de testes terem sido analisados e validados.

## 5. Componentes e responsabilidades

### 5.1 Registo de Observers

O registo declara explicitamente os Observers autorizados a participar no
pipeline.

É responsável por definir:

- o nome do módulo;
- o executável correspondente;
- se o módulo é obrigatório ou opcional;
- o contrato de saída aplicável;
- a compatibilidade esperada.

O registo não executa módulos, não recolhe factos e não altera relatórios.

A presença de um ficheiro no diretório `observer/` não é suficiente para o
autorizar a executar.

### 5.2 Observer

Cada Observer recolhe factos pertencentes exclusivamente ao seu domínio e
produz um único relatório JSON em `stdout`.

Um Observer:

- não persiste o próprio relatório;
- não interpreta domínios pertencentes a outros Observers;
- não coordena outros módulos;
- não modifica o sistema observado;
- escreve diagnósticos em `stderr`;
- termina com código diferente de zero quando não consegue cumprir o seu
  contrato.

### 5.3 Report API

A Report API constrói, valida internamente e emite relatórios no formato comum.

A versão 2.1.0 permanece responsável pelo estado interno de construção e pela
emissão em `stdout`.

A Report API não é responsável por:

- executar módulos;
- validar ficheiros externos já persistidos;
- escolher diretórios;
- criar gerações;
- manter história;
- coordenar o pipeline.

### 5.4 Esquema de relatório serializado

O esquema de relatório serializado descreve, de forma declarativa e versionada,
o JSON aceite nas fronteiras entre processos.

É responsável por definir:

- campos obrigatórios;
- tipos;
- valores permitidos;
- propriedades adicionais permitidas ou proibidas;
- regras estruturais reutilizáveis.

O esquema não executa validação por si próprio e não substitui regras semânticas
que não possam ser expressas corretamente no formato escolhido.

### 5.5 Validador de fronteira

O validador de fronteira aplica o esquema e as regras semânticas necessárias a
um relatório já serializado.

É responsável por:

- validar o próprio esquema antes da sua utilização;
- rejeitar JSON inválido;
- rejeitar violações estruturais;
- validar regras semânticas explicitamente documentadas;
- confirmar a identidade esperada do módulo;
- produzir diagnósticos determinísticos;
- não modificar o documento validado.

O validador não recolhe factos, não corrige relatórios e não decide se o estado
observado é aceitável.

### 5.6 Capturador

O capturador processa exatamente um Observer por invocação.

É responsável por:

1. executar o Observer autorizado;
2. capturar separadamente `stdout`, `stderr` e o código de saída;
3. entregar o relatório ao validador de fronteira;
4. persistir o relatório válido apenas na área temporária da geração;
5. devolver ao Runner um resultado inequívoco.

O capturador não promove gerações, não agrega estados e não substitui relatórios
de gerações anteriores.

### 5.7 Runner

O Runner coordena um único ciclo de observação.

É responsável por:

- adquirir o bloqueio exclusivo do pipeline;
- carregar e validar o registo de Observers;
- criar a área temporária da geração;
- invocar o capturador para cada Observer autorizado;
- reunir resultados sem inventar factos;
- construir o manifesto;
- determinar se a geração ficou completa, parcial ou falhada;
- promover atomicamente a geração terminada;
- emitir o seu próprio relatório de execução.

O Runner não interpreta factos do sistema, não produz conclusões técnicas sobre
o estado observado e não modifica gerações já promovidas.

### 5.8 Geração

Uma geração é o conjunto imutável dos resultados pertencentes a um único ciclo
de observação.

Contém:

- um identificador único;
- um manifesto;
- os relatórios válidos produzidos nesse ciclo;
- informação explícita sobre módulos ausentes ou falhados.

Uma geração nunca mistura silenciosamente relatórios de ciclos diferentes.

### 5.9 Decision Engine

O Decision Engine interpreta uma única geração já promovida.

É responsável por:

- validar a entrada que consome;
- fixar a identidade da geração antes da leitura;
- usar apenas os relatórios declarados pelo manifesto;
- distinguir dados presentes, ausentes, inválidos e desconhecidos;
- produzir análise, conclusões, health e recomendações justificáveis.

O Decision Engine não observa diretamente o sistema, não altera gerações e não
decide pelo administrador humano.

### 5.10 Historian

O Historian trabalha apenas sobre gerações promovidas e imutáveis.

A sua responsabilidade futura pode incluir:

- indexação;
- comparação temporal;
- identificação de tendências;
- aplicação de uma política de retenção explicitamente autorizada.

O Historian não cria uma segunda cópia indiscriminada dos mesmos relatórios, não
altera factos históricos e não participa na captura corrente.

A responsabilidade operacional exata do Historian deve ser definida num
contrato próprio antes da sua implementação.

### 5.11 Orquestração operacional

A orquestração operacional futura agenda e supervisiona o ponto de entrada
oficial do pipeline.

systemd poderá ser usado para:

- identidade de execução;
- periodicidade;
- dependências operacionais;
- limites de escrita;
- hardening;
- registo de execução.

systemd não deve conter regras de negócio nem substituir a lógica explícita do
Runner.

### 5.12 Consumidores

Consumidores externos recebem apenas artefactos promovidos e validados.

Um consumidor:

- não lê áreas temporárias;
- não altera gerações;
- não recebe privilégios de escrita por conveniência;
- deve distinguir ausência de dados de estado técnico negativo;
- não pode transformar recomendações em ações sem decisão humana explícita.

O coletor privilegiado e o túnel MCP são sistemas separados. Uma integração
futura exige contrato, permissões e análise próprios.

## 6. Fluxo integral e estados da geração

### 6.1 Princípio geral

Cada execução oficial do Runner representa uma tentativa independente de
observar o sistema.

Os resultados de uma tentativa nunca são misturados silenciosamente com
resultados de tentativas anteriores.

O pipeline privilegia:

- verdade sobre aparência de sucesso;
- diagnóstico explícito sobre recuperação silenciosa;
- conjuntos imutáveis sobre ficheiros correntes alteráveis;
- comportamento determinístico sobre execução implícita.

### 6.2 Início do ciclo

O Runner deve:

1. validar as dependências obrigatórias;
2. adquirir um bloqueio exclusivo;
3. carregar e validar o registo;
4. confirmar os diretórios e as permissões necessários;
5. criar um identificador único;
6. criar uma área temporária no mesmo sistema de ficheiros do destino final.

Se uma destas operações falhar antes de existir uma área temporária fiável, a
execução termina explicitamente e nenhuma geração é promovida.

Uma tentativa que não obtém o bloqueio não inicia uma segunda execução
concorrente.

### 6.3 Execução dos Observers

Os Observers são processados pela ordem declarada no registo.

A execução é sequencial por predefinição para:

- reduzir concorrência desnecessária no servidor;
- tornar a ordem reproduzível;
- simplificar diagnósticos;
- evitar interferência entre recolhas;
- reduzir complexidade no primeiro contrato estável.

Execução paralela não faz parte desta arquitetura inicial. Só poderá ser
introduzida por decisão arquitetural e nova validação.

Para cada Observer, o Runner recebe do capturador um resultado que distingue, no
mínimo:

- sucesso;
- executável ausente;
- executável não autorizado;
- falha de execução;
- tempo limite de execução excedido;
- ausência de relatório em `stdout`;
- JSON inválido;
- violação do contrato;
- identidade de módulo incorreta;
- falha de persistência temporária.

A falha de um Observer não interrompe automaticamente a recolha dos restantes,
desde que a infraestrutura da geração continue fiável.

### 6.4 Conteúdo da geração

A área temporária contém apenas:

- relatórios que passaram integralmente a validação;
- um manifesto construído depois de todas as tentativas;
- metadados estritamente necessários e documentados.

Saídas inválidas não são promovidas como relatórios.

Diagnósticos de `stderr` não são copiados integralmente para o manifesto sem
análise, porque podem conter dados excessivos ou sensíveis. O manifesto regista
códigos de resultado e mensagens controladas.

Relatórios de gerações anteriores nunca são copiados para preencher ausências
na geração atual.

### 6.5 Estados da geração

Uma geração tem exatamente um dos seguintes estados:

#### COMPLETE

Todos os Observers declarados para a execução produziram relatórios válidos e
foram persistidos na área temporária.

#### PARTIAL

Pelo menos um Observer produziu um relatório válido e pelo menos um Observer
declarado ficou ausente ou falhou.

A geração identifica explicitamente cada sucesso e cada falha.

Uma geração `PARTIAL` nunca pode ser apresentada como observação integral do
sistema.

#### FAILED

Nenhum Observer declarado produziu um relatório válido, mas foi possível
construir e validar um manifesto fiável da tentativa.

Uma geração `FAILED` não contém factos suficientes para interpretação técnica
do sistema.

### 6.6 Falha estrutural

Uma falha estrutural ocorre quando já não é possível confiar na própria geração,
por exemplo:

- registo inválido;
- diretório temporário inseguro;
- colisão de identificador;
- impossibilidade de construir ou validar o manifesto;
- falha de permissões;
- erro de promoção;
- corrupção detetada.

Uma área temporária com falha estrutural não é promovida.

A limpeza dessa área deve ser segura e limitada ao caminho temporário
explicitamente criado para a tentativa.

### 6.7 Manifesto e promoção

Depois da recolha, o Runner deve:

1. construir o manifesto;
2. validar o manifesto;
3. confirmar que os ficheiros declarados existem;
4. confirmar que não existem relatórios não declarados;
5. calcular e registar os hashes definidos pelo contrato;
6. aplicar as permissões finais;
7. promover o diretório temporário através de `rename` no mesmo sistema de
   ficheiros.

A promoção torna visível a geração inteira enquanto uma unidade de armazenamento.

A imutabilidade é uma garantia do contrato e do fluxo operacional. Não significa
que o sistema de ficheiros aplique automaticamente um atributo imutável.

Os hashes permitem detetar alteração posterior, mas não substituem permissões,
controlo de acesso ou validação.

### 6.8 Referência para a geração atual

Depois de promover a geração, o Runner atualiza uma referência pequena e
controlada para o identificador da geração mais recente.

A referência deve ser atualizada através de ficheiro temporário e `rename`.

A promoção do diretório acontece antes da atualização da referência. Assim, a
referência nunca deve apontar para uma geração ainda não promovida.

Estas duas operações não constituem uma única transação do sistema de ficheiros.
Se a geração for promovida e a atualização da referência falhar:

- a geração permanece preservada;
- a referência anterior permanece válida;
- a falha é declarada;
- a recuperação exige uma operação explícita e auditável.

Os consumidores devem resolver a referência uma única vez no início e conservar
o identificador resolvido durante toda a leitura.

### 6.9 Consumo pelo Decision Engine

O Decision Engine pode interpretar:

- uma geração `COMPLETE`;
- uma geração `PARTIAL`, desde que represente explicitamente módulos ausentes
  como dados insuficientes e nunca produza um estado global `OK`.

Uma geração `FAILED` não é interpretada como estado do sistema. Deve causar uma
falha explícita de entrada ou um resultado equivalente definido no futuro
contrato do Decision Engine.

O comportamento detalhado perante gerações parciais pertence ao novo contrato
de entrada do Decision Engine e deve ser validado antes de implementação.

### 6.10 Preservação

A promoção de uma nova geração não elimina nem modifica gerações anteriores.

Qualquer política futura de retenção deve:

- pertencer ao Historian ou a um componente explicitamente autorizado;
- estar documentada;
- ser testada;
- impedir remoções amplas ou ambíguas;
- manter evidência suficiente para auditoria;
- exigir decisão humana antes da ativação inicial.

## 7. Estrutura de armazenamento e permissões

### 7.1 Separação de raízes

A arquitetura distingue três raízes lógicas:

- `PROJECT_ROOT`: código, contratos, esquemas, testes e documentação em Git;
- `STATE_ROOT`: gerações promovidas, referência atual e índices persistentes;
- `RUNTIME_ROOT`: bloqueio e outros artefactos transitórios.

Os caminhos físicos destas raízes pertencem à configuração operacional.

Durante desenvolvimento e testes, `STATE_ROOT` e `RUNTIME_ROOT` devem poder ser
substituídos por diretórios isolados.

Uma futura unidade systemd poderá criar e proteger as raízes operacionais.

Os contratos não dependem de `/home/mppt24` como caminho absoluto.

O código existente em `PROJECT_ROOT` não deve ser usado implicitamente como
armazenamento operacional.

### 7.2 Estrutura persistente

A estrutura lógica de `STATE_ROOT` contém:

- `current-generation`;
- `generations/`;
- uma subdiretório por geração promovida.

Cada geração contém:

- `manifest.json`;
- `observers/`;
- apenas os relatórios declarados no manifesto.

A construção ocorre numa diretório temporária com nome iniciado por `.staging-`,
dentro de `generations/`.

A diretório temporária e o destino final pertencem ao mesmo sistema de ficheiros.

Uma diretório temporária nunca pode ser tratada como geração promovida.

### 7.3 Identificador de geração

O identificador de geração deve ser:

- único;
- seguro para utilização como um único nome de diretório;
- limitado a caracteres explicitamente autorizados;
- independente do locale;
- ordenável temporalmente quando possível;
- validado antes de ser usado num caminho.

A forma prevista combina um timestamp UTC com um sufixo que impeça colisões.

O formato exato e a expressão de validação pertencem ao contrato do manifesto.

O identificador não constitui segredo nem substitui controlo de acesso.

### 7.4 Conteúdo permitido

Uma geração promovida contém apenas:

- `manifest.json`;
- a diretório `observers/`;
- os relatórios declarados no manifesto.

Não são permitidos:

- links simbólicos;
- hard links deliberados;
- sockets;
- dispositivos;
- FIFOs;
- ficheiros temporários;
- backups;
- relatórios não declarados;
- caminhos que escapem à geração.

Antes da promoção, o Runner confirma que os objetos encontrados são apenas
ficheiros regulares e diretórios esperadas.

### 7.5 Referência atual

`current-generation` é um ficheiro de texto regular, não um link simbólico.

Contém apenas um identificador válido e uma terminação de linha.

O consumidor deve:

1. ler a referência;
2. validar integralmente o identificador;
3. construir o caminho dentro de `generations/`;
4. confirmar que o caminho resolvido permanece dentro de `STATE_ROOT`;
5. conservar o mesmo identificador durante toda a operação.

A referência não contém caminhos absolutos nem caminhos relativos livres.

### 7.6 Permissões

As permissões operacionais previstas são:

- raízes e diretórios de controlo: no máximo `0750`;
- `current-generation`: no máximo `0640`;
- ficheiros em construção: no máximo `0640`;
- relatórios e manifesto promovidos: preferencialmente `0440`;
- diretórios internas promovidas: preferencialmente `0550`.

O proprietário e o grupo serão definidos antes da ativação operacional.

Nenhum artefacto operacional pode ser gravável por `other`.

As permissões reduzem alterações acidentais, mas não substituem identidade de
execução, validação ou verificação de hashes.

### 7.7 Bloqueio

O bloqueio oficial pertence a `RUNTIME_ROOT`, nunca a uma geração.

Todos os pontos oficiais que iniciem um ciclo adquirem o mesmo bloqueio
exclusivo.

O bloqueio é cooperativo e não substitui permissões.

Consumidores de gerações promovidas não precisam do bloqueio de escrita, porque
leem conjuntos que não são modificados.

### 7.8 Relatório do Runner

O relatório comum do Runner descreve o resultado integral da invocação,
incluindo promoção e atualização de `current-generation`.

É emitido em `stdout` depois de o ciclo terminar.

Não é acrescentado a uma geração depois da promoção.

O manifesto documenta a geração. O relatório do Runner documenta a invocação do
coordenador. Estes artefactos têm responsabilidades distintas.

### 7.9 Artefactos legados

Os diretórios atuais:

- `data/observer`;
- `data/history`;

não são automaticamente apagados, convertidos ou misturados com a nova
estrutura.

Qualquer migração, arquivo ou remoção exige:

- inventário;
- análise de consumidores;
- backup;
- plano reversível;
- validação humana explícita.

## 8. Contrato conceptual do manifesto

### 8.1 Objetivo

O manifesto é a descrição canónica de uma geração.

Permite determinar, sem inferência por nomes de ficheiros:

- qual foi a tentativa;
- quando começou e terminou;
- que registo foi usado;
- que módulos eram esperados;
- quais tiveram sucesso;
- quais falharam;
- que relatórios pertencem à geração;
- se a geração é `COMPLETE`, `PARTIAL` ou `FAILED`.

O manifesto não contém os factos recolhidos pelos Observers.

### 8.2 Campos principais

O manifesto deve conter:

- `manifest_version`;
- `generation_id`;
- `started_at`;
- `completed_at`;
- `state`;
- `runner`;
- `registry`;
- `summary`;
- `modules`.

O contrato do manifesto é versionado independentemente da Report API.

### 8.3 Identidade e tempo

`manifest_version` identifica a versão SemVer do contrato do manifesto.

`generation_id` deve ser exatamente igual ao nome da diretório promovida.

`started_at` e `completed_at` devem:

- usar UTC;
- seguir um formato único definido no contrato;
- ser semanticamente válidos;
- garantir que `completed_at` não é anterior a `started_at`.

### 8.4 Runner e registo

`runner` identifica o módulo e a versão que coordenaram a geração.

`registry` identifica:

- a versão do registo;
- o algoritmo de hash;
- o hash do conteúdo validado do registo.

O hash permite demonstrar qual configuração autorizou a execução.

O manifesto não incorpora caminhos absolutos para o registo ou para o código.

### 8.5 Resumo

`summary` contém contadores inteiros não negativos:

- `declared`;
- `successful`;
- `failed`;
- `reports_written`.

As regras semânticas são:

- `declared` é igual ao número de entradas em `modules`;
- `successful + failed` é igual a `declared`;
- `reports_written` é igual a `successful`;
- os contadores são derivados das entradas, não aceites como verdade isolada.

Qualquer incoerência entre contadores e entradas invalida o manifesto.

### 8.6 Entradas dos módulos

`modules` é uma lista ordenada segundo o registo.

Cada entrada contém:

- `module`;
- `required`;
- `outcome`;
- `error_code`;
- `exit_code`;
- `report`.

`module` é único na lista.

`required` preserva a classificação declarada no registo.

`outcome` aceita apenas `SUCCESS` ou `FAILED`.

Quando `outcome` é `FAILED`, `error_code` identifica uma categoria documentada,
e `report` é nulo.

Quando `outcome` é `SUCCESS`, `error_code` é nulo e `report` descreve o relatório
validado.

`exit_code` preserva o código devolvido quando existiu execução. Quando não
existiu execução, o valor é nulo.

### 8.7 Descritor do relatório

Quando existe sucesso, `report` contém:

- `path`;
- `module`;
- `contract_version`;
- `version`;
- `timestamp`;
- `status`;
- `size_bytes`;
- `sha256`.

`contract_version` identifica o contrato serializado aplicado pelo validador.

`path` é relativo à raiz da geração e deve corresponder exatamente ao módulo.

Não são permitidos caminhos absolutos, componentes `..` ou normalizações
ambíguas.

`module`, `version`, `timestamp` e `status` devem coincidir com o conteúdo do
relatório validado.

`size_bytes` corresponde ao tamanho exato do ficheiro promovido.

`sha256` é uma string hexadecimal minúscula com o hash dos bytes exatos do
relatório.

O manifesto não inclui o hash de si próprio.

### 8.8 Códigos de falha dos módulos

O contrato deve distinguir, no mínimo:

- `EXECUTABLE_MISSING`;
- `EXECUTABLE_NOT_AUTHORIZED`;
- `EXECUTION_FAILED`;
- `EXECUTION_TIMEOUT`;
- `EMPTY_STDOUT`;
- `INVALID_JSON`;
- `CONTRACT_VIOLATION`;
- `MODULE_MISMATCH`;
- `TEMPORARY_PERSISTENCE_FAILED`.

Os códigos são estáveis e adequados a processamento automático.

Mensagens humanas podem complementar o código, mas não o substituir.

Dados arbitrários de `stderr` não são usados como código nem copiados sem
limites para o manifesto.

### 8.9 Coerência do estado

O manifesto é inválido se `declared` for zero.

O estado obedece às seguintes regras:

- `COMPLETE`: `successful` é igual a `declared`;
- `PARTIAL`: `successful` é maior que zero e menor que `declared`;
- `FAILED`: `successful` é zero.

Uma entrada `SUCCESS` possui exatamente um descritor de relatório válido.

Uma entrada `FAILED` não possui descritor de relatório válido.

Todos os relatórios existentes devem aparecer exatamente uma vez em `modules`.

Todos os módulos do registo aplicável devem aparecer exatamente uma vez em
`modules`.

Uma incoerência entre `state`, `summary`, `modules` ou ficheiros invalida o
manifesto e impede a promoção.

### 8.10 Validação e evolução

O esquema usa JSON Schema Draft 2020-12 e declara explicitamente o dialecto.

A validação deve funcionar sem acesso à Internet.

Referências remotas não são obtidas durante a execução operacional.

O próprio esquema é validado antes de validar manifestos.

Objetos controlados pelo contrato rejeitam propriedades desconhecidas.

Uma adição ao formato exige nova versão compatível do contrato.

Regras que JSON Schema não consiga expressar corretamente são aplicadas por uma
camada semântica pequena, documentada e testada.

O validador apresenta todos os erros relevantes numa ordem determinística,
sempre que isso seja possível.

Nenhum manifesto inválido é promovido.

## 9. Modelo de ameaças e limites

### 9.1 Princípio de confiança

Nenhum artefacto é confiável apenas por ter sido produzido dentro do projeto.

São considerados não confiáveis até validação:

- saída de Observers;
- conteúdo de áreas temporárias;
- manifesto recebido por um consumidor;
- `current-generation`;
- nomes e caminhos obtidos de ficheiros;
- dados vindos do sistema operativo;
- dados fornecidos por integrações externas.

Uma geração promovida continua sujeita a verificação de estrutura, contrato e
hashes antes de consumo.

Validação reduz risco, mas não transforma uma conta comprometida numa origem
confiável.

### 9.2 Ameaças consideradas

A arquitetura considera, no mínimo:

- Observer defeituoso ou bloqueado;
- JSON malformado ou excessivamente grande;
- caminhos manipulados;
- links inesperados;
- ficheiros substituídos depois da validação;
- duas execuções concorrentes;
- referência atual corrompida;
- mistura de gerações;
- disco cheio;
- interrupção do processo;
- reinício ou perda de energia;
- dependência vulnerável;
- diagnóstico com dados sensíveis;
- configuração ou código alterados sem promoção;
- consumidor com permissões excessivas.

A arquitetura não presume que hashes, permissões ou atomicidade resolvam todas
estas ameaças isoladamente.

### 9.3 Execução controlada

O ponto de entrada operacional deve usar:

- identidade sem privilégios administrativos;
- ambiente mínimo e previsível;
- `PATH` explícito;
- locale explícito;
- timezone explícita para metadados do ciclo;
- `umask` restritiva;
- diretórios validados;
- descritores de ficheiro controlados.

A identidade operacional não deve pertencer, por conveniência, a grupos como:

- `sudo`;
- `docker`;
- `lxd`.

Observers privilegiados não são executados dentro deste processo.

Qualquer recolha privilegiada permanece num coletor separado, com contrato e
permissões próprios.

### 9.4 Limites de recursos

O contrato operacional deve definir e testar limites para:

- duração de cada Observer;
- duração total do ciclo;
- tamanho máximo de `stdout`;
- tamanho máximo de `stderr` capturado;
- tamanho máximo de cada relatório;
- tamanho máximo do manifesto;
- profundidade máxima do JSON;
- número máximo de módulos;
- espaço livre mínimo antes da promoção.

Os limites exatos pertencem à configuração versionada e não ficam implícitos no
código.

Um limite excedido causa falha explícita e nunca truncagem silenciosa de um
relatório aceite.

O código de falha `OUTPUT_LIMIT_EXCEEDED` deve distinguir excesso de saída de
outras falhas de execução.

### 9.5 Atomicidade e durabilidade

Atomicidade de visibilidade e durabilidade após perda de energia são garantias
diferentes.

`rename` impede que consumidores vejam metade de um ficheiro ou diretório
promovido, mas não prova sozinho que todos os dados chegaram ao armazenamento
físico.

Antes da promoção operacional, a implementação deve definir e testar:

- sincronização dos ficheiros da geração;
- sincronização das diretórios relevantes;
- ordem entre promoção e atualização da referência;
- comportamento perante falha em cada ponto.

Se houver interrupção depois da promoção e antes da atualização da referência:

- a geração pode existir sem ser a atual;
- a referência anterior permanece válida;
- a recuperação valida a geração antes de qualquer alteração;
- nenhuma geração é apagada automaticamente por parecer órfã.

### 9.6 Diagnósticos e privacidade

`stdout` de um Observer é reservado ao relatório JSON.

`stderr` é diagnóstico não confiável e sujeito a limite.

O pipeline não deve promover automaticamente:

- comandos completos com segredos;
- variáveis de ambiente;
- tokens;
- chaves;
- conteúdo arbitrário de ficheiros;
- endereços ou identificadores sem necessidade contratual.

Mensagens persistidas usam códigos estáveis e texto controlado.

Detalhes adicionais só podem ser registados quando necessários, autorizados e
protegidos por permissões adequadas.

### 9.7 Dependências e cadeia de fornecimento

O pipeline prefere dependências fornecidas e atualizadas pelo Ubuntu.

Cada dependência obrigatória deve ter:

- finalidade documentada;
- versão mínima ou capacidade necessária;
- verificação explícita;
- falha clara quando indisponível;
- acompanhamento por atualizações de segurança.

Código ou esquemas não são obtidos da Internet durante uma execução operacional.

Uma atualização de dependência exige repetição dos testes relevantes.

### 9.8 Limite de ação

Nenhum resultado do pipeline autoriza automaticamente alteração do sistema.

Estados, conclusões e recomendações são informação para análise.

Qualquer ação futura exige componente, contrato, permissões e decisão humana
separados.

## 10. Falhas e resultado do Runner

### 10.1 Princípio

O estado do relatório do Runner descreve o resultado da invocação do Runner.

Não descreve diretamente a saúde do sistema observado.

O estado da geração e o estado do relatório do Runner são relacionados, mas não
são o mesmo campo nem o mesmo contrato.

### 10.2 Estados do relatório do Runner

O Runner usa:

- `OK`: geração `COMPLETE`, promovida e definida como atual;
- `WARNING`: geração `PARTIAL`, promovida e definida como atual;
- `ERROR`: geração `FAILED`, falha estrutural, falha de promoção ou falha na
  atualização da referência;
- `UNKNOWN`: apenas quando o próprio Runner não consegue determinar com
  confiança o resultado operacional.

Uma tentativa rejeitada por bloqueio ocupado produz `WARNING`, não inicia
geração e declara explicitamente `LOCK_BUSY`.

`confidence` representa confiança no relatório do Runner, não percentagem de
Observers bem-sucedidos.

### 10.3 Factos do Runner

O relatório do Runner deve distinguir, no mínimo:

- `lock_acquired`;
- `cycle_started`;
- `generation_id`;
- `generation_state`;
- `declared`;
- `successful`;
- `failed`;
- `reports_written`;
- `generation_promoted`;
- `current_generation_updated`.

Valores não aplicáveis são representados explicitamente segundo o contrato, não
substituídos por valores inventados.

As listas de módulos com sucesso e falha pertencem aos factos estruturados ou ao
manifesto, não apenas a mensagens humanas.

O relatório nunca declara promoção ou atualização sem confirmar a operação.

### 10.4 Matriz principal

| Situação | Geração | Referência atual | Runner |
|---|---|---|---|
| Bloqueio ocupado | Não criada | Inalterada | `WARNING` |
| Falha de dependência, registo ou diretório | Não promovida | Inalterada | `ERROR` |
| Todos os módulos têm sucesso | `COMPLETE` promovida | Atualizada | `OK` |
| Parte dos módulos falha | `PARTIAL` promovida | Atualizada | `WARNING` |
| Todos os módulos falham, manifesto válido | `FAILED` promovida | Atualizada | `ERROR` |
| Manifesto inválido | Não promovida | Inalterada | `ERROR` |
| Promoção falha | Não considerada promovida | Inalterada | `ERROR` |
| Geração promovida, referência falha | Preservada sem ser atual | Referência anterior | `ERROR` |
| Corrupção detetada | Não consumida | Não corrigida automaticamente | `ERROR` |

Uma referência anterior válida nunca é apagada antes de a nova referência ser
promovida.

Uma geração não é declarada atual apenas por existir em `generations/`.

### 10.5 Código de saída

Código zero significa apenas execução integralmente bem-sucedida com estado
`OK`.

Estados `WARNING`, `ERROR` e `UNKNOWN` devolvem código diferente de zero.

O contrato do Runner define códigos distintos para:

- uso ou configuração inválidos;
- bloqueio ocupado;
- geração parcial;
- geração falhada;
- falha estrutural.

Sempre que a Report API estiver funcional, o Runner emite um relatório válido
mesmo quando termina com código diferente de zero.

Se uma dependência impedir a construção do próprio relatório, a falha é
declarada em `stderr` e nenhum JSON parcial é emitido.

### 10.6 Limpeza e recuperação

A limpeza automática limita-se à área temporária criada pela própria invocação.

Antes de remover uma área temporária, o Runner confirma:

- pai esperado;
- nome reservado;
- ausência de links;
- identidade da tentativa;
- inexistência de promoção.

Uma geração promovida nunca é removida pelo mecanismo de limpeza temporária.

Se uma interrupção deixar uma área `.staging-`, a recuperação:

- inventaria o conteúdo;
- valida o caminho;
- não promove automaticamente;
- não remove automaticamente sem política aprovada;
- produz evidência para decisão humana.

Uma falha de limpeza é declarada e não é ocultada pelo resultado anterior.

## 11. Versões e compatibilidade

### 11.1 Princípio

Cada contrato público declara uma versão SemVer própria.

Uma versão publicada não é alterada retroativamente.

Alterações são entregues através de nova versão, com documentação e testes.

Uma implementação não pode alegar compatibilidade apenas porque consegue ler
parte de um documento.

### 11.2 Componentes preservados

Durante esta fase permanecem inalterados:

- Report API 2.1.0;
- Decision Engine 2.3.0;
- Observers 1.0.0.

O esquema do relatório serializado deve descrever o contrato 2.1.0 existente.

Se for descoberta uma divergência, o conflito é documentado e analisado. O
esquema não redefine silenciosamente o contrato aprovado.

### 11.3 Novos contratos previstos

As versões iniciais previstas são:

- esquema serializado do relatório: `2.1.0`;
- registo de Observers: `1.0.0`;
- manifesto de geração: `1.0.0`;
- contrato do capturador: `1.0.0`;
- novo contrato do Runner: `2.0.0`.

O Runner passa de 1.1.0 para 2.0.0 porque a interface, persistência e semântica
de falhas mudam de forma incompatível.

A alteração da entrada do Decision Engine exige uma futura versão principal,
prevista como 3.0.0.

A redefinição do Historian exige contrato próprio e, se substituir o
comportamento 2.0.0, uma futura versão principal.

Estas versões só se tornam definitivas depois de cada contrato ser escrito,
testado e validado.

### 11.4 Regras de compatibilidade

Cada consumidor mantém uma lista explícita das versões de contrato suportadas.

Uma versão desconhecida não é aceite por semelhança estrutural.

Versões com o mesmo major só são aceites automaticamente quando a matriz de
compatibilidade o declarar e os testes o demonstrarem.

A versão do módulo e a versão do contrato do relatório são identidades
diferentes.

O manifesto regista ambas quando existe relatório.

Conversão entre versões:

- não ocorre silenciosamente;
- usa ferramenta ou fase explícita;
- preserva a origem;
- regista a transformação;
- possui testes e plano de reversão.

Nenhum consumidor altera o documento original para o tornar compatível.

### 11.5 Condições de publicação

Uma nova versão de contrato exige:

- documento atualizado;
- esquema válido, quando aplicável;
- exemplos válidos e inválidos;
- testes unitários;
- testes de integração;
- matriz de compatibilidade;
- análise de migração;
- plano de reversão;
- registo da alteração em Git.

Uma versão não é declarada concluída apenas porque o caminho de sucesso funciona.

A arquitetura passa de draft para 1.0.0 apenas depois da revisão integral e da
validação humana.

A publicação da arquitetura não autoriza automaticamente a implementação.

## 12. Plano de testes integral

### 12.1 Princípios

Os testes são definidos antes da implementação.

Cada requisito arquitetural deve corresponder a pelo menos um teste ou a uma
verificação documentada.

Os testes:

- usam diretórios temporários isolados;
- não escrevem em `data/observer` ou `data/history`;
- não alteram gerações operacionais;
- não exigem privilégios de root;
- não dependem de Internet;
- produzem resultados determinísticos;
- preservam evidência suficiente quando falham.

Uma suite não é considerada válida se testa apenas o caminho de sucesso.

### 12.2 Camadas

O plano contém:

1. validação estática;
2. testes unitários;
3. testes de contrato;
4. testes de integração;
5. testes de falha e recuperação;
6. testes de segurança;
7. validação de compatibilidade;
8. validação operacional controlada.

### 12.3 Validação estática

A validação inclui:

- `bash -n` para scripts Bash;
- validação sintática de JSON;
- validação dos próprios JSON Schemas;
- verificação de permissões esperadas;
- pesquisa de caminhos operacionais fixos;
- pesquisa de execução automática durante `source`.

ShellCheck e `shfmt` podem ser avaliados como ferramentas de desenvolvimento,
mas não são dependências operacionais obrigatórias nesta fase.

### 12.4 Testes unitários preservados

Continuam obrigatórios:

- Report API 2.1.0: `PASS=125 FAIL=0`;
- contrato health do Decision Engine 2.3.0: `PASS=28 FAIL=0`;
- compatibilidade direta dos sete Observers: `VALIDATED=7 FAIL=0`.

Uma nova fase não pode reduzir estes resultados sem análise e decisão explícitas.

### 12.5 Testes de esquemas e validador

Devem verificar:

- relatório válido completo;
- manifesto válido para cada estado;
- campo obrigatório ausente;
- tipo incorreto;
- propriedade desconhecida;
- versão não suportada;
- SemVer inválida;
- timestamp impossível;
- intervalo temporal invertido;
- módulo duplicado;
- módulo incorreto;
- contadores incoerentes;
- estado incoerente;
- caminho absoluto ou com `..`;
- hash ou tamanho incorreto;
- JSON demasiado profundo;
- documento acima do limite;
- tentativa de referência remota.

Os erros devem ser determinísticos e identificar a localização da violação.

### 12.6 Testes do capturador

Observers falsos devem simular:

- sucesso;
- código de saída não zero;
- timeout;
- `stdout` vazio;
- JSON inválido;
- relatório contratualmente inválido;
- módulo incorreto;
- saída acima do limite;
- `stderr` acima do limite;
- falha de escrita temporária.

Nenhum caso usa os Observers ou diretórios operacionais reais.

### 12.7 Testes do Runner

Devem cobrir:

- bloqueio livre e ocupado;
- registo válido e inválido;
- zero módulos;
- geração `COMPLETE`;
- geração `PARTIAL`;
- geração `FAILED`;
- manifesto inválido;
- colisão de identificador;
- falha de promoção;
- falha de atualização da referência;
- permissões finais;
- limpeza limitada;
- carregamento por `source` sem execução automática.

### 12.8 Testes do Decision Engine

O futuro contrato de entrada deve testar:

- geração `COMPLETE`;
- geração `PARTIAL`;
- rejeição de geração `FAILED`;
- referência inválida;
- manifesto adulterado;
- relatório ausente;
- relatório adicional;
- hash divergente;
- módulo obrigatório ausente;
- módulo opcional ausente;
- impossibilidade de produzir `OK` com geração parcial;
- leitura consistente da mesma geração durante todo o processo.

### 12.9 Testes de integração

O ciclo integral usa raízes temporárias e verifica:

1. registo;
2. sete Observers;
3. captura;
4. validação;
5. manifesto;
6. promoção;
7. referência;
8. consumo pelo Decision Engine.

A validação com os sete Observers oficiais é de leitura e não escreve nos dados
operacionais.

O resultado deve identificar a mesma geração em todas as etapas.

### 12.10 Testes de segurança

Devem tentar introduzir:

- link simbólico;
- hard link inesperado;
- FIFO;
- socket;
- caminho fora da raiz;
- nome não autorizado;
- ficheiro gravável por `other`;
- ambiente manipulado;
- propriedade desconhecida;
- referência remota de esquema;
- conteúdo excessivo.

A suite confirma que nenhum destes casos é promovido.

### 12.11 Testes de falha e recuperação

Através de injeção controlada de falhas, devem ser simuladas interrupções:

- antes do manifesto;
- depois do manifesto;
- antes da promoção;
- depois da promoção;
- antes da atualização da referência;
- depois da atualização da referência.

Os testes não desligam o servidor nem provocam falhas reais no disco.

Cada ponto confirma artefactos preservados, referência válida e diagnóstico
esperado.

### 12.12 Ferramentas de teste

As suites Bash existentes podem continuar a usar o formato atual.

Testes do validador podem usar a biblioteca padrão de testes do Python e o
pacote Ubuntu `python3-jsonschema`.

Bats, ShellCheck e `shfmt` não são instalados automaticamente.

A eventual adoção dessas ferramentas exige análise própria e não altera as
dependências operacionais do pipeline.

Nenhum teste transfere ferramentas ou código da Internet durante a execução.

### 12.13 Critérios de aceitação

Uma fase só pode ser promovida quando:

- todas as suites aplicáveis terminam com zero falhas;
- os testes existentes continuam aprovados;
- não existem escritas em dados operacionais;
- não existem acessos de rede inesperados;
- não são necessários privilégios de root;
- os contratos e exemplos correspondem à implementação;
- a matriz de compatibilidade está atualizada;
- o diff Git contém apenas alterações aprovadas;
- existe plano de reversão;
- o resultado foi apresentado e validado pelo administrador humano.

Uma falha conhecida não é convertida em exceção silenciosa para obter uma suite
verde.

## 13. Ordem de implementação

### 13.1 Regra geral

A implementação é dividida em fases pequenas e independentes.

Cada fase segue:

1. observar o estado;
2. analisar dependências;
3. escrever ou atualizar o contrato;
4. validar o desenho com o administrador;
5. criar branch e cópia de trabalho;
6. implementar;
7. testar isoladamente;
8. testar integração aplicável;
9. apresentar diff e resultados;
10. promover apenas depois de aprovação;
11. registar a alteração em Git.

Uma fase não começa a alterar o componente seguinte antes de a fase atual estar
concluída e integrada.

A conclusão de uma fase não autoriza automaticamente a seguinte.

### 13.2 Fase A — Arquitetura

Entregas:

- `ARCHITECTURE.md`;
- modelo de ameaças;
- fluxo;
- matriz de falhas;
- política de versões;
- plano de testes;
- ordem de implementação.

Nenhum código operacional é alterado nesta fase.

### 13.3 Fase B — Contrato serializado

Entregas:

- JSON Schema do relatório 2.1.0;
- validador de fronteira;
- contrato do validador;
- exemplos;
- testes de conformidade;
- validação dos sete Observers.

A Report API 2.1.0 não é modificada.

### 13.4 Fase C — Registo de Observers

Entregas:

- formato e schema do registo 1.0.0;
- lista explícita dos sete Observers;
- regras de caminhos e versões;
- limites operacionais versionados;
- testes do registo.

Nenhum Observer é modificado nesta fase.

### 13.5 Fase D — Capturador

Entregas:

- contrato do capturador 1.0.0;
- execução de um Observer;
- limites de tempo e saída;
- validação de fronteira;
- persistência apenas em staging;
- códigos de resultado;
- testes com Observers falsos.

O capturador não promove gerações.

### 13.6 Fase E — Runner e gerações

Entregas:

- contrato do Runner 2.0.0;
- schema do manifesto 1.0.0;
- bloqueio;
- criação de staging;
- coordenação sequencial;
- manifesto;
- hashes;
- promoção;
- `current-generation`;
- relatório do Runner;
- testes de falha e recuperação.

A validação termina em raízes temporárias antes de qualquer operação real.

A fase E possui dois pontos de paragem obrigatórios:

1. E1: contrato de armazenamento e manifesto, sem implementação do Runner;
2. E2: implementação do Runner, apenas depois da validação de E1.

E2 não pode alterar silenciosamente o contrato aprovado em E1.

### 13.7 Fase F — Decision Engine

Entregas:

- novo contrato de entrada;
- versão principal prevista 3.0.0;
- consumo de uma geração fixa;
- validação do manifesto e hashes;
- tratamento de `COMPLETE` e `PARTIAL`;
- rejeição de `FAILED`;
- testes de consistência temporal;
- regressão das regras de health existentes.

O Decision Engine 2.3.0 permanece preservado até à promoção validada.

### 13.8 Fase G — Historian

Entregas:

- definição da responsabilidade operacional;
- contrato próprio;
- indexação e comparação sem alterar gerações;
- política de retenção separada e desativada por predefinição;
- testes históricos.

Nenhum artefacto legado é eliminado nesta fase sem plano específico.

### 13.9 Fase H — Ativação operacional

Só começa depois de o pipeline integral funcionar manualmente e em isolamento.

Entregas:

- identidade operacional dedicada;
- caminhos físicos de `STATE_ROOT` e `RUNTIME_ROOT`;
- permissões e grupos;
- unidade systemd protegida;
- timer inicialmente desativado;
- execução manual controlada;
- observação de logs e recursos;
- plano de desativação;
- ativação do timer apenas após aprovação.

A primeira execução operacional não migra nem remove dados legados.

### 13.10 Fase I — Consumidores externos

Qualquer ligação a MCP, IA, API ou outra ferramenta exige:

- contrato de leitura;
- versão suportada;
- permissões mínimas;
- política de privacidade;
- testes com dados controlados;
- impossibilidade de escrita nas gerações;
- aprovação separada.

Nenhum consumidor externo condiciona a arquitetura interna por conveniência.

### 13.11 Controlo de âmbito

Cada branch altera apenas os componentes declarados para a fase.

Problemas encontrados fora do âmbito são:

1. registados;
2. analisados;
3. classificados;
4. adiados ou tratados numa fase própria.

Não são corrigidos lateralmente sem aprovação.

### 13.12 Reversão

Antes de cada promoção:

- o estado Git está identificado;
- os ficheiros oficiais têm origem conhecida;
- a cópia de trabalho foi validada;
- existe forma de regressar à versão anterior;
- dados operacionais antigos permanecem intactos.

Reversão de código e reversão de dados são operações diferentes e possuem planos
separados.

## 14. Decisões pendentes

As seguintes decisões são deliberadamente adiadas para o contrato da fase
correspondente:

- caminhos físicos de `STATE_ROOT` e `RUNTIME_ROOT`;
- utilizador e grupo operacionais;
- formato exato de `generation_id`;
- formato e localização do registo;
- nomes e localização dos schemas;
- formato temporal exato do manifesto;
- limites de tempo, tamanho, profundidade e espaço;
- códigos numéricos de saída do Runner;
- mecanismo concreto de sincronização para durabilidade;
- comportamento detalhado do Decision Engine perante módulos ausentes;
- formato do índice futuro do Historian;
- política de retenção;
- periodicidade operacional;
- destino e retenção de logs;
- política de integração com consumidores externos.

Cada decisão deve ser resolvida antes da implementação da fase que depende dela.

Valores não são introduzidos no código antes de serem documentados e testados.

Uma decisão pendente não pode ser preenchida por pressuposto silencioso.

## 15. Referências técnicas

Consultadas durante a análise em 16 de agosto de 2026:

- NIST SP 800-218 — Secure Software Development Framework:
  https://csrc.nist.gov/pubs/sp/800/218/final
- CISA — Secure by Design:
  https://www.cisa.gov/securebydesign
- JSON Schema Draft 2020-12:
  https://json-schema.org/draft/2020-12
- JSON Schema — Specification:
  https://json-schema.org/specification
- Python jsonschema:
  https://python-jsonschema.readthedocs.io/
- Semantic Versioning 2.0.0:
  https://semver.org/
- POSIX `rename`:
  https://pubs.opengroup.org/onlinepubs/000095399/functions/rename.html
- Linux `flock`:
  https://man7.org/linux/man-pages/man2/flock.2.html
- systemd service execution:
  https://www.freedesktop.org/software/systemd/man/systemd.exec.html
- jq manual:
  https://jqlang.org/manual/
- Ubuntu Security Notices:
  https://ubuntu.com/security/notices

As referências orientam o desenho, mas não substituem os contratos específicos
da MPPT24 CORE.
