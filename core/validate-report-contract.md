# MPPT24 CORE — Contrato do Validador de Relatórios

Estado do documento: APROVADO
Versão do documento: 1.0.0
Contrato de relatório suportado: 2.1.0
Data: 16 de agosto de 2026

## 1. Objetivo

Este documento define o comportamento do validador de fronteira para relatórios
serializados da MPPT24 CORE.

O validador recebe um documento JSON já emitido por outro processo e determina
se esse documento cumpre integralmente o contrato de relatório 2.1.0.

O validador:

- não recolhe factos;
- não corrige documentos;
- não altera a Report API;
- não interpreta o estado técnico;
- não persiste relatórios;
- não acede à Internet;
- não executa o módulo produtor.

## 2. Autoridade

O contrato comum do relatório está definido em `SPECIFICATION.md`, versão 2.1.0.

O schema descreve as regras estruturais que podem ser expressas corretamente em
JSON Schema Draft 2020-12.

Este documento define as regras de fronteira e as validações semânticas
adicionais.

Quando existir divergência entre o schema, o validador, a especificação e a
Report API, o relatório não deve ser aceite até o conflito ser analisado e
resolvido explicitamente.

## 3. Dependências

A implementação utiliza apenas:

- Python 3;
- biblioteca padrão do Python;
- pacote Ubuntu `python3-jsonschema`;
- schema local do relatório 2.1.0.

Nenhuma dependência é descarregada ou instalada durante a validação.

O schema local não pode exceder 1 MiB. Este limite pertence ao contrato do
validador e protege a validação do próprio schema.

## 4. Interface

A interface prevista é:

    validate-report.py --max-bytes BYTES --max-depth DEPTH \
        [--expected-module MODULE] REPORT

`REPORT` identifica exatamente um ficheiro a validar.

`--max-bytes` e `--max-depth` são obrigatórios. Os respetivos valores pertencem
à configuração versionada do pipeline e não ficam ocultos no código.

`--expected-module` confirma a identidade declarada no relatório quando o
chamador conhece antecipadamente o módulo esperado.

O caminho do schema 2.1.0 é determinado pela instalação do projeto e não é
substituído por entrada arbitrária durante a execução operacional.

`--help` apresenta a utilização, termina com código `0` e não executa validação.

Cada opção pode aparecer no máximo uma vez. Opções repetidas são rejeitadas como
uso inválido.

## 5. Entrada estrita

Antes de aplicar o schema, o validador confirma:

1. que o caminho identifica um ficheiro regular;
2. que o caminho não é um link simbólico;
3. que o tamanho não excede `--max-bytes`;
4. que o conteúdo é UTF-8 válido;
5. que existe exatamente um documento JSON;
6. que não existem chaves duplicadas em nenhum objeto;
7. que não existem `NaN`, `Infinity` ou `-Infinity`;
8. que a profundidade não excede `--max-depth`.

A raiz de um objeto ou array tem profundidade `1`. Apenas objetos e arrays
aninhados aumentam a profundidade; valores escalares não acrescentam níveis.

O documento é rejeitado integralmente quando qualquer verificação falha.

O validador não remove campos, não converte tipos e não normaliza valores.

## 6. Leitura segura

O relatório é aberto uma única vez através de descritor de ficheiro.

Quando o sistema operativo disponibilizar as capacidades necessárias, a abertura
usa proteção contra links simbólicos e herança indevida do descritor.

Depois da abertura, o validador confirma através do descritor:

- tipo regular do ficheiro;
- tamanho permitido;
- identidade estável durante a leitura;
- leitura completa até ao fim.

A validação utiliza os bytes lidos desse descritor. Não reabre o caminho para
aplicar verificações posteriores.

Uma alteração detetada durante a leitura causa rejeição explícita.

## 7. Validação estrutural

O schema declara explicitamente JSON Schema Draft 2020-12.

O objeto de topo contém exatamente os 13 campos definidos em
`SPECIFICATION.md` e rejeita propriedades desconhecidas.

O schema valida:

- nome normalizado do módulo;
- versão SemVer;
- padrão textual do timestamp;
- estado técnico reconhecido;
- confiança inteira entre `0` e `100`;
- `facts` como objeto com chaves não vazias;
- seis arrays de strings não vazias e sem duplicados;
- `health` como objeto com domínios normalizados;
- presença e validade de `status` em cada domínio de `health`.

Os valores de `facts` podem usar qualquer tipo JSON.

Os domínios de `health` podem conter propriedades adicionais definidas pelo
contrato específico do módulo.

O schema utiliza apenas referências internas ao próprio documento.

## 8. Validação semântica

Depois da validação estrutural, o validador confirma:

- validade real da data e da hora;
- validade do desvio UTC;
- correspondência com o formato `YYYY-MM-DDTHH:MM:SS+HHMM` ou
  `YYYY-MM-DDTHH:MM:SS-HHMM`;
- igualdade entre `module` e `--expected-module`, quando fornecido.

A validação temporal usa a biblioteca padrão do Python e não depende do
comportamento opcional de `format`.

O schema deve declarar exatamente o dialecto Draft 2020-12 e o identificador
`urn:mppt24:schema:report:2.1.0`.

O próprio schema é validado com `Draft202012Validator.check_schema` antes de ser
usado.

A implementação rejeita schemas com referências externas. Nenhuma referência é
resolvida através da rede.

A validação termina imediatamente se o schema local estiver ausente, ilegível ou
inválido.

## 9. Resultado e diagnósticos

Um relatório válido produz:

- código de saída `0`;
- nenhum conteúdo em `stdout`;
- nenhum diagnóstico em `stderr`.

Uma falha produz código diferente de zero e diagnósticos em `stderr`.

Cada diagnóstico usa campos controlados:

    ERROR<TAB>CODE<TAB>LOCATION<TAB>MESSAGE

`CODE` é estável e adequado a processamento automático.

`LOCATION` identifica o argumento, o ficheiro ou a localização JSON aplicável.

Caracteres de controlo provenientes da entrada não são copiados diretamente para
o diagnóstico.

Violações estruturais independentes são apresentadas numa ordem determinística.
Falhas que impedem a leitura ou interpretação produzem apenas os diagnósticos
aplicáveis até esse ponto.

## 10. Códigos de saída

Os códigos de saída são:

- `0`: relatório válido;
- `2`: uso ou argumentos inválidos;
- `3`: dependência obrigatória indisponível;
- `4`: schema local ausente, inseguro ou inválido;
- `5`: entrada ilegível, insegura ou JSON inválido;
- `6`: violação estrutural do contrato;
- `7`: violação semântica do contrato;
- `8`: falha interna inesperada.

O código numérico indica a categoria. O campo `CODE` identifica a causa
específica.

## 11. Códigos de diagnóstico

O contrato define, no mínimo:

- `USAGE_INVALID`;
- `DEPENDENCY_UNAVAILABLE`;
- `SCHEMA_MISSING`;
- `SCHEMA_UNREADABLE`;
- `SCHEMA_TOO_LARGE`;
- `SCHEMA_NOT_REGULAR`;
- `SCHEMA_SYMLINK`;
- `SCHEMA_INVALID`;
- `SCHEMA_EXTERNAL_REFERENCE`;
- `INPUT_MISSING`;
- `INPUT_UNREADABLE`;
- `INPUT_NOT_REGULAR`;
- `INPUT_SYMLINK`;
- `INPUT_TOO_LARGE`;
- `INPUT_CHANGED`;
- `INVALID_UTF8`;
- `INVALID_JSON`;
- `DUPLICATE_KEY`;
- `NON_FINITE_NUMBER`;
- `DEPTH_LIMIT_EXCEEDED`;
- `CONTRACT_VIOLATION`;
- `INVALID_TIMESTAMP`;
- `MODULE_MISMATCH`;
- `INTERNAL_ERROR`.

Novos códigos exigem atualização deste contrato e testes correspondentes.

Um código existente não muda de significado dentro da mesma versão principal.

## 12. Ordem de validação

A ordem é:

1. argumentos;
2. dependência Python obrigatória;
3. localização e segurança do schema;
4. referências do schema;
5. validade do próprio schema;
6. abertura segura da entrada;
7. tamanho e estabilidade da entrada;
8. descodificação UTF-8;
9. leitura JSON estrita;
10. profundidade;
11. estrutura segundo o schema;
12. timestamp;
13. módulo esperado.

Uma falha numa etapa impede a execução das etapas que dependem dela.

A ordem não pode ser alterada de forma a permitir acesso à rede, leitura
desnecessária ou aceitação parcial.

## 13. Limites da implementação

O programa possui um ponto de entrada protegido por `if __name__ == "__main__"`.

Importar o ficheiro para testes não executa validações nem altera o sistema.

A execução operacional usa o interpretador Python do sistema em modo isolado,
sem depender de `PYTHONPATH`, pacotes do utilizador ou configuração obtida do
ambiente.

O programa:

- não cria ficheiros;
- não altera permissões;
- não segue links simbólicos de entrada;
- não inicia processos externos;
- não usa shell;
- não abre sockets;
- não consulta DNS;
- não inclui o conteúdo integral do relatório nos erros;
- não apresenta traceback ao utilizador numa falha prevista.

Uma exceção inesperada é convertida em `INTERNAL_ERROR`, preservando o detalhe
apenas no contexto de teste controlado.

## 14. Testes obrigatórios

Os testes devem cobrir:

- schema válido e schema inválido;
- referência externa no schema;
- relatório válido mínimo e completo;
- sete Observers oficiais;
- Decision Engine 2.3.0;
- ficheiro ausente, diretório e link simbólico;
- limite de tamanho;
- UTF-8 inválido;
- JSON vazio, truncado ou com conteúdo adicional;
- chaves duplicadas em qualquer profundidade;
- `NaN`, `Infinity` e `-Infinity`;
- limite de profundidade;
- campo obrigatório ausente;
- propriedade de topo desconhecida;
- tipo incorreto;
- nome de módulo inválido;
- SemVer inválida;
- timestamp impossível;
- estado inválido;
- confiança fora do intervalo ou não inteira;
- chave vazia em `facts`;
- texto vazio ou duplicado;
- domínio `health` inválido;
- domínio sem `status`;
- estado `health` inválido;
- propriedades adicionais válidas dentro de `health`;
- módulo esperado correto e incorreto;
- ordem e formato dos diagnósticos;
- códigos de saída;
- importação sem efeitos laterais.

Os testes usam apenas diretórios temporários e não escrevem nos dados
operacionais.

## 15. Compatibilidade

Esta versão aceita exclusivamente o contrato de relatório 2.1.0.

A versão do módulo declarada em `version` não substitui a versão do contrato
validado.

Uma futura versão do relatório exige schema e matriz de compatibilidade próprios.

O validador não tenta converter documentos de versões desconhecidas.

## 16. Critérios de aceitação

A implementação só pode ser promovida quando:

- o próprio schema passa a validação Draft 2020-12;
- todos os testes deste contrato passam;
- os sete Observers são aceites com a identidade esperada;
- o Decision Engine 2.3.0 é aceite;
- Report API mantém `PASS=125 FAIL=0`;
- contrato health mantém `PASS=28 FAIL=0`;
- compatibilidade direta mantém `VALIDATED=7 FAIL=0`;
- não existem acessos de rede;
- não existem escritas em dados operacionais;
- não são necessários privilégios administrativos;
- o diff contém apenas alterações aprovadas;
- o administrador humano valida o resultado.

Um teste falhado impede a promoção.

## 17. Evolução

Este documento permaneceu `DRAFT` durante a implementação e os testes.

A versão 1.0.0 foi aprovada após revisão integral, resultados sem falhas e
aprovação explícita.

A aprovação deste contrato não autoriza alterações aos componentes preservados
da fase anterior.
