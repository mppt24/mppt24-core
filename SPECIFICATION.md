# MPPT24 CORE — Especificação comum
# Versão do contrato: 2.1.0

## Objetivo

Definir o contrato comum de construção, validação e emissão dos relatórios
produzidos pelos módulos da MPPT24 CORE.

Todos os módulos devem produzir um único objeto JSON válido em `stdout`.
Mensagens de diagnóstico e erros de validação devem ser escritas em
`stderr`.

## Dependências

A API comum de relatórios requer:

- Bash;
- `jq`;
- GNU `date`;
- `core/common.sh`;
- `config/core.conf`.

A ausência de uma dependência obrigatória deve causar uma falha explícita.

## Estrutura do relatório

Todos os relatórios contêm os campos:

- `module`;
- `version`;
- `timestamp`;
- `status`;
- `confidence`;
- `facts`;
- `analysis`;
- `conclusions`;
- `health`;
- `summary`;
- `recommendations`;
- `warnings`;
- `errors`.

## Metadados

`module` é uma string não vazia e normalizada. Apenas são permitidos:

- letras minúsculas de `a` a `z`;
- algarismos de `0` a `9`;
- hífenes simples entre segmentos não vazios.

São inválidos nomes com espaços, maiúsculas, hífen inicial, hífen final ou
hífenes consecutivos.

`version` segue Semantic Versioning. São aceites os componentes opcionais
de pré-lançamento e metadados de compilação. Os componentes numéricos não
podem conter zeros iniciais, exceto o valor `0`.

`timestamp` utiliza o formato `YYYY-MM-DDTHH:MM:SS+HHMM` ou
`YYYY-MM-DDTHH:MM:SS-HHMM`. A data, a hora e o desvio UTC devem representar
valores reais.

## Estados técnicos

`status` só pode assumir um dos valores:

- `OK`: recolha ou processamento concluído;
- `WARNING`: resultado disponível com limitações;
- `ERROR`: falha relevante numa fonte ou operação;
- `UNKNOWN`: dados insuficientes para determinar o estado técnico.

O estado técnico não representa automaticamente gravidade operacional.

Um estado inválido deve ser rejeitado antes de alterar o relatório em
construção.

## Confiança

`confidence` é um número inteiro entre `0` e `100`, inclusive.

O valor inicial é obtido de `DEFAULT_CONFIDENCE`. Se essa configuração não
estiver definida, é utilizado o valor `100`.

A confiança mede a qualidade e a completude dos dados. Não mede perigo,
risco ou probabilidade de ataque.

Um valor inválido deve ser rejeitado antes de alterar o relatório em
construção.

## Factos

`facts` é um objeto JSON. Pode estar vazio.

Cada chave deve ser uma string não vazia e só pode ser definida uma vez no
mesmo relatório.

Os valores preservam o respetivo tipo JSON, incluindo:

- string;
- número;
- booleano;
- `null`;
- objeto;
- array.

O valor `false`, o valor `0` e a string vazia são valores válidos e não
podem ser confundidos com um facto ausente.

Quando uma fonte falha, os factos dependentes dessa fonte devem ser `null`
ou omitidos de acordo com o contrato específico do módulo. Nunca devem ser
inventados valores substitutos.

## Campos de texto interpretativo

Os campos seguintes são arrays JSON de strings:

- `analysis`;
- `conclusions`;
- `summary`;
- `recommendations`;
- `warnings`;
- `errors`.

Cada elemento deve ser uma string não vazia. Não são permitidos elementos
duplicados dentro do mesmo campo.

Estes arrays podem estar vazios.

## Health

`health` é um objeto JSON e pode estar vazio quando o módulo não define
domínios de saúde.

Cada nome de domínio segue as mesmas regras de normalização aplicadas a
`module`.

Cada domínio é um objeto que contém obrigatoriamente:

- `status`.

O estado do domínio só pode ser `OK`, `WARNING`, `ERROR` ou `UNKNOWN`.

Um domínio pode conter propriedades adicionais definidas pelo contrato
específico do módulo.

O mesmo domínio não pode ser definido mais de uma vez no relatório.

## Atomicidade da construção

As operações que adicionam ou alteram dados devem validar os novos valores
antes de modificar o estado interno do relatório.

Quando uma operação falha:

- deve devolver um código diferente de zero;
- deve escrever uma mensagem explicativa em `stderr`;
- não deve produzir dados parciais em `stdout`;
- deve preservar integralmente o valor anterior do campo afetado.

Esta garantia aplica-se, no mínimo, a:

- metadados;
- estado;
- confiança;
- factos;
- domínios de health;
- arrays de texto.

## Validação final

Antes da emissão, o relatório completo deve ser novamente validado.

A validação final confirma:

1. nome do módulo normalizado;
2. versão SemVer válida;
3. timestamp sintaticamente e semanticamente válido;
4. estado técnico reconhecido;
5. confiança inteira entre `0` e `100`;
6. `facts` como objeto JSON com chaves não vazias;
7. `health` como objeto com domínios normalizados e estados válidos;
8. arrays de texto com strings não vazias e sem duplicados.

A emissão só ocorre depois da validação completa.

Se a validação falhar, nenhum relatório JSON deve ser emitido.

## API pública

A biblioteca `core/report.sh` disponibiliza:

- `reset_report`;
- `set_metadata`;
- `set_status`;
- `set_confidence`;
- `add_fact`;
- `add_fact_string`;
- `add_analysis`;
- `add_conclusion`;
- `set_health`;
- `add_summary`;
- `add_recommendation`;
- `add_warning`;
- `add_error`;
- `finalize_report`;
- `emit_report`.

As funções auxiliares cujo nome começa por `_` são internas e não fazem
parte da API pública.

`reset_report` inicia uma nova construção sem dados herdados do relatório
anterior.

`finalize_report` valida o estado interno sem emitir JSON.

`emit_report` executa a validação final e, apenas em caso de sucesso, escreve
o relatório normalizado em `stdout`.

## Exemplo

    {
      "module": "observer-example",
      "version": "1.0.0",
      "timestamp": "2026-08-16T12:30:45+0100",
      "status": "WARNING",
      "confidence": 90,
      "facts": {
        "source_available": true,
        "events": 3
      },
      "analysis": [
        "Foram observados três eventos."
      ],
      "conclusions": [
        "A fonte está disponível, mas requer análise."
      ],
      "health": {
        "source": {
          "status": "WARNING"
        }
      },
      "summary": [
        "Resultado disponível com limitações."
      ],
      "recommendations": [
        "Rever os eventos observados."
      ],
      "warnings": [
        "Foram encontradas condições que requerem atenção."
      ],
      "errors": []
    }

## Responsabilidades

Todos os módulos devem:

1. produzir resultados verificáveis;
2. preservar os tipos dos factos;
3. nunca inventar informação;
4. nunca ocultar erros;
5. separar factos de interpretação;
6. permitir testes isolados;
7. não alterar o estado operacional fora da sua responsabilidade explícita.

Os Observers são passivos e não alteram o estado operacional do sistema
observado.
