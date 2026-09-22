#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_UNDER_TEST="${REPORT_UNDER_TEST:-$PROJECT_ROOT/core/report.sh}"

passes=0
failures=0

pass_test() {
    printf 'PASS: %s\n' "$1"
    ((++passes))
}

fail_test() {
    printf 'FAIL: %s\n' "$1" >&2
    ((++failures))
}

assert_equal() {
    local label="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$actual" == "$expected" ]]; then
        pass_test "$label"
    else
        printf '  esperado=%s obtido=%s\n' "$expected" "$actual" >&2
        fail_test "$label"
    fi
}

expect_success() {
    local label="$1"
    shift

    if "$@" >/dev/null 2>&1; then
        pass_test "$label"
    else
        fail_test "$label"
    fi
}

expect_failure() {
    local label="$1"
    shift

    if "$@" >/dev/null 2>&1; then
        fail_test "$label"
    else
        pass_test "$label"
    fi
}

source "$REPORT_UNDER_TEST"

DEFAULT_CONFIDENCE=73
reset_report

assert_equal \
    "reset_report usa DEFAULT_CONFIDENCE" \
    "73" \
    "$REPORT_CONFIDENCE"

expect_success \
    "set_metadata aceita nome e SemVer válidos" \
    set_metadata observer-test 1.2.3

expect_success \
    "set_metadata aceita prerelease e build metadata" \
    set_metadata observer-test 1.2.3-alpha.1+build.5

metadata_module_before="$REPORT_MODULE"
metadata_version_before="$REPORT_VERSION"
metadata_timestamp_before="$REPORT_TIMESTAMP"

while IFS="|" read -r module version label
do
    expect_failure \
        "set_metadata rejeita ${label}" \
        set_metadata "$module" "$version"

    assert_equal \
        "${label} preserva module" \
        "$metadata_module_before" "$REPORT_MODULE"

    assert_equal \
        "${label} preserva version" \
        "$metadata_version_before" "$REPORT_VERSION"

    assert_equal \
        "${label} preserva timestamp" \
        "$metadata_timestamp_before" "$REPORT_TIMESTAMP"

    REPORT_MODULE="$metadata_module_before"
    REPORT_VERSION="$metadata_version_before"
    REPORT_TIMESTAMP="$metadata_timestamp_before"
done <<'INVALID_METADATA_CASES'
|1.2.3|módulo vazio
Observer Test|1.2.3|módulo com espaços
-observer|1.2.3|hífen inicial
observer-test|version-one|versão não SemVer
observer-test|01.2.3|zero inicial em SemVer
INVALID_METADATA_CASES


reset_report

expect_success \
    "set_status aceita OK" \
    set_status "$STATUS_OK"

expect_success \
    "set_status aceita WARNING" \
    set_status "$STATUS_WARNING"

expect_success \
    "set_status aceita ERROR" \
    set_status "$STATUS_ERROR"

expect_success \
    "set_status aceita UNKNOWN" \
    set_status "$STATUS_UNKNOWN"

status_before="$REPORT_STATUS"

expect_failure \
    "set_status rejeita estado inválido" \
    set_status INVALID

assert_equal \
    "estado inválido preserva status" \
    "$status_before" "$REPORT_STATUS"

reset_report

expect_success \
    "set_confidence aceita zero" \
    set_confidence 0

expect_success \
    "set_confidence aceita cem" \
    set_confidence 100

while IFS="|" read -r invalid_confidence label
do
    reset_report
    set_confidence 42

    expect_failure \
        "set_confidence rejeita ${label}" \
        set_confidence "$invalid_confidence"

    assert_equal \
        "${label} preserva confidence" \
        "42" "$REPORT_CONFIDENCE"
done <<'INVALID_CONFIDENCE_CASES'
-1|valor negativo
101|valor acima de cem
50.5|valor não inteiro
INVALID_CONFIDENCE_CASES


reset_report

expect_success \
    "add_fact aceita número" \
    add_fact number 42

expect_success \
    "add_fact aceita booleano false" \
    add_fact boolean false

expect_success \
    "add_fact aceita null" \
    add_fact null_value null

expect_success \
    "add_fact aceita objeto" \
    add_fact object_value '{"item":1}'

expect_success \
    "add_fact aceita array" \
    add_fact array_value '[1,2,3]'

expect_success \
    "add_fact_string aceita texto especial" \
    add_fact_string text_value 'texto "citado" com barra \ e espaço'

if jq -e '
    .number == 42
    and .boolean == false
    and .null_value == null
    and .object_value == {"item":1}
    and .array_value == [1,2,3]
    and .text_value == "texto \"citado\" com barra \\ e espaço"
' <<<"$REPORT_FACTS" >/dev/null
then
    pass_test "factos preservam tipos e conteúdo"
else
    fail_test "factos preservam tipos e conteúdo"
fi

facts_before="$REPORT_FACTS"

expect_failure \
    "add_fact rejeita chave duplicada" \
    add_fact number 99

assert_equal \
    "add_fact duplicado preserva facts" \
    "$facts_before" "$REPORT_FACTS"

reset_report

expect_failure \
    "add_fact rejeita chave vazia" \
    add_fact "" 1

assert_equal \
    "chave vazia preserva facts" \
    "{}" "$REPORT_FACTS"

reset_report

expect_failure \
    "add_fact rejeita JSON inválido" \
    add_fact invalid_value not-json

assert_equal \
    "JSON inválido preserva facts" \
    "{}" "$REPORT_FACTS"


while IFS='|' read -r add_function report_variable label
do
    reset_report

    expect_success \
        "${label} aceita texto não vazio" \
        "$add_function" "mensagem de teste"

    assert_equal \
        "${label} adiciona exatamente um elemento" \
        "1" \
        "$(jq -r 'length' <<<"${!report_variable}")"

    array_before="${!report_variable}"

    expect_failure \
        "${label} rejeita texto vazio" \
        "$add_function" ""

    assert_equal \
        "texto vazio preserva ${label}" \
        "$array_before" "${!report_variable}"

    printf -v "$report_variable" "%s" "$array_before"

    expect_failure \
        "${label} rejeita texto duplicado" \
        "$add_function" "mensagem de teste"

    assert_equal \
        "duplicado preserva ${label}" \
        "$array_before" "${!report_variable}"

done <<'TEXT_ARRAY_CASES'
add_warning|REPORT_WARNINGS|warnings
add_error|REPORT_ERRORS|errors
add_analysis|REPORT_ANALYSIS|analysis
add_conclusion|REPORT_CONCLUSIONS|conclusions
add_summary|REPORT_SUMMARY|summary
add_recommendation|REPORT_RECOMMENDATIONS|recommendations
TEXT_ARRAY_CASES

reset_report

expect_success \
    "set_health aceita domínio simples" \
    set_health system "$STATUS_OK"

expect_success \
    "set_health aceita domínio com hífen" \
    set_health remote-access "$STATUS_WARNING"

health_before="$REPORT_HEALTH"

while IFS="|" read -r domain status label
do
    expect_failure \
        "set_health rejeita ${label}" \
        set_health "$domain" "$status"

    assert_equal \
        "${label} preserva health" \
        "$health_before" "$REPORT_HEALTH"

    REPORT_HEALTH="$health_before"
done <<'INVALID_HEALTH_CASES'
|OK|domínio vazio
remote access|OK|domínio com espaços
System|OK|domínio com maiúsculas
-system|OK|hífen inicial
security|INVALID|estado inválido
system|WARNING|domínio duplicado
INVALID_HEALTH_CASES


reset_report
set_metadata test-module 1.0.0

expect_success \
    "finalize_report permite health vazio" \
    finalize_report

REPORT_HEALTH='{
  "system": {
    "status": "OK",
    "confidence": 95,
    "details": {
      "source": "observer-system"
    }
  }
}'

expect_success \
    "finalize_report permite propriedades adicionais em health" \
    finalize_report

REPORT_HEALTH='{"system":{}}'

expect_failure \
    "finalize_report rejeita domínio sem status" \
    finalize_report

REPORT_HEALTH='{"system":{"status":"INVALID"}}'

expect_failure \
    "finalize_report rejeita status de health inválido" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_MODULE="Invalid Module"

expect_failure \
    "finalize_report rejeita nome de módulo inválido" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_VERSION="version-one"

expect_failure \
    "finalize_report rejeita versão não SemVer" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_TIMESTAMP="2026-02-31T12:00:00+0000"

expect_failure \
    "finalize_report rejeita data impossível" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_STATUS="INVALID"

expect_failure \
    "finalize_report rejeita estado inválido" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_CONFIDENCE="50.5"

expect_failure \
    "finalize_report rejeita confiança não inteira" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_FACTS='{"":1}'

expect_failure \
    "finalize_report rejeita chave de facto vazia" \
    finalize_report

reset_report
set_metadata test-module 1.0.0
REPORT_HEALTH='{"System":{"status":"OK"}}'

expect_failure \
    "finalize_report rejeita domínio health não normalizado" \
    finalize_report

while IFS='|' read -r report_variable label
do
    reset_report
    set_metadata test-module 1.0.0
    printf -v "$report_variable" '%s' '[""]'

    expect_failure \
        "finalize_report rejeita texto vazio em ${label}" \
        finalize_report

    reset_report
    set_metadata test-module 1.0.0
    printf -v "$report_variable" '%s' '["duplicado","duplicado"]'

    expect_failure \
        "finalize_report rejeita duplicados em ${label}" \
        finalize_report
done <<'FINAL_ARRAY_CASES'
REPORT_WARNINGS|warnings
REPORT_ERRORS|errors
REPORT_ANALYSIS|analysis
REPORT_CONCLUSIONS|conclusions
REPORT_SUMMARY|summary
REPORT_RECOMMENDATIONS|recommendations
FINAL_ARRAY_CASES

reset_report
set_metadata test-module 2.4.0-beta.1+build.7
set_status "$STATUS_WARNING"
set_confidence 88
add_fact answer 42
add_fact_string message "relatório completo"
add_warning "aviso único"
add_error "erro registado"
add_analysis "análise única"
add_conclusion "conclusão única"
set_health system "$STATUS_WARNING"
add_summary "resumo único"
add_recommendation "recomendação única"

if emitted_report="$(emit_report 2>/dev/null)"
then
    pass_test "emit_report produz relatório válido"
else
    emitted_report='{}'
    fail_test "emit_report produz relatório válido"
fi

if jq -e '
    type == "object"
    and (
      keys | sort
    ) == (
      [
        "module",
        "version",
        "timestamp",
        "status",
        "confidence",
        "facts",
        "analysis",
        "conclusions",
        "health",
        "summary",
        "recommendations",
        "warnings",
        "errors"
      ] | sort
    )
    and .module == "test-module"
    and .version == "2.4.0-beta.1+build.7"
    and .status == "WARNING"
    and .confidence == 88
    and .facts.answer == 42
    and .facts.message == "relatório completo"
    and .analysis == ["análise única"]
    and .conclusions == ["conclusão única"]
    and .health.system.status == "WARNING"
    and .summary == ["resumo único"]
    and .recommendations == ["recomendação única"]
    and .warnings == ["aviso único"]
    and .errors == ["erro registado"]
' <<<"$emitted_report" >/dev/null
then
    pass_test "emit_report preserva esquema e conteúdo integral"
else
    fail_test "emit_report preserva esquema e conteúdo integral"
fi

printf '\nResultados: PASS=%d FAIL=%d\n' "$passes" "$failures"

if (( failures > 0 )); then
    exit 1
fi
