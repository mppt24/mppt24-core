#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DECISION_UNDER_TEST="${DECISION_UNDER_TEST:-$PROJECT_ROOT/decision/decision-engine.sh}"
REPORT_UNDER_TEST="${REPORT_UNDER_TEST:-$PROJECT_ROOT/core/report.sh}"

passes=0
failures=0
TMP_REPORT_DIR="$(mktemp -d)"

cleanup() {
    rm -rf -- "$TMP_REPORT_DIR"
}
trap cleanup EXIT

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

export MPPT24_REPORT_DIR="$TMP_REPORT_DIR"

source "$DECISION_UNDER_TEST"
source "$REPORT_UNDER_TEST"

assert_equal \
    "Decision Engine declara versão 2.3.0" \
    "2.3.0" "$MODULE_VERSION"

if collect_status 2>/dev/null; then
    fail_test "collect_status rejeita diretório vazio"
else
    pass_test "collect_status rejeita diretório vazio"
fi

printf '%s\n' '{"module":"observer-a","status":"OK","facts":{}}' \
    >"$TMP_REPORT_DIR/observer-a.json"
printf '%s\n' '{"module":"observer-b","status":"WARNING","facts":{}}' \
    >"$TMP_REPORT_DIR/observer-b.json"
printf '%s\n' '{"module":"observer-c","status":"INVALID","facts":{}}' \
    >"$TMP_REPORT_DIR/observer-c.json"

collect_status
assert_equal "contador OK" "1" "$ok"
assert_equal "contador WARNING" "1" "$warning"
assert_equal "contador ERROR" "0" "$error"
assert_equal "contador UNKNOWN" "1" "$unknown"
assert_equal "get_status preserva módulo" "WARNING" "$(get_status observer-b)"

printf '%s\n' '{"module":"observer-a","status":"OK","facts":{}}' \
    >"$TMP_REPORT_DIR/observer-duplicate.json"

if collect_status 2>/dev/null; then
    fail_test "collect_status rejeita módulo duplicado"
else
    pass_test "collect_status rejeita módulo duplicado"
fi
rm -f -- "$TMP_REPORT_DIR/observer-duplicate.json"

reset_report
set_health security "$STATUS_OK"
assert_equal "set_health aceita estado válido" \
    "OK" "$(jq -r '.security.status' <<<"$REPORT_HEALTH")"

reset_report
if set_health security INVALID 2>/dev/null; then
    fail_test "set_health rejeita estado inválido"
else
    pass_test "set_health rejeita estado inválido"
fi

reset_report
if set_health "" "$STATUS_OK" 2>/dev/null; then
    fail_test "set_health rejeita domínio vazio"
else
    pass_test "set_health rejeita domínio vazio"
fi

reset_report
set_health security "$STATUS_OK"
if set_health security "$STATUS_WARNING" 2>/dev/null; then
    fail_test "set_health rejeita domínio duplicado"
else
    pass_test "set_health rejeita domínio duplicado"
fi

reset_report
set_metadata test 1.0.0
if finalize_report; then
    pass_test "finalize_report permite health vazio"
else
    fail_test "finalize_report permite health vazio"
fi

reset_report
set_metadata test 1.0.0
REPORT_HEALTH='{"security":{}}'
if finalize_report 2>/dev/null; then
    fail_test "finalize_report rejeita domínio sem status"
else
    pass_test "finalize_report rejeita domínio sem status"
fi

reset_report
set_metadata test 1.0.0
REPORT_HEALTH='{"security":{"status":"INVALID"}}'
if finalize_report 2>/dev/null; then
    fail_test "finalize_report rejeita status inválido"
else
    pass_test "finalize_report rejeita status inválido"
fi

reset_report
ALL_STATUSES='{"observer-system":"OK"}'
ALL_FACTS='{
  "observer-system": {
    "time_available": true,
    "ntp_enabled": true,
    "ntp_synchronized": true
  }
}'
build_system_health_conclusions
assert_equal \
    "system fica OK com observer e NTP operacionais" \
    "OK" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

reset_report
ALL_STATUSES='{"observer-system":"OK"}'
ALL_FACTS='{
  "observer-system": {
    "time_available": true,
    "ntp_enabled": true,
    "ntp_synchronized": false
  }
}'
build_system_health_conclusions
assert_equal \
    "system fica WARNING com NTP não sincronizado" \
    "WARNING" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

reset_report
ALL_STATUSES='{"observer-system":"OK"}'
ALL_FACTS='{
  "observer-system": {
    "time_available": true
  }
}'
build_system_health_conclusions
assert_equal \
    "system fica UNKNOWN com factos temporais insuficientes" \
    "UNKNOWN" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

reset_report
ALL_STATUSES='{"observer-system":"WARNING"}'
ALL_FACTS='{}'
build_system_health_conclusions
assert_equal \
    "system preserva WARNING do observer-system" \
    "WARNING" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

reset_report
ALL_STATUSES='{"observer-system":"ERROR"}'
ALL_FACTS='{}'
build_system_health_conclusions
assert_equal \
    "system preserva ERROR do observer-system" \
    "ERROR" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

reset_report
ALL_STATUSES='{}'
ALL_FACTS='{}'
build_system_health_conclusions
assert_equal \
    "system fica UNKNOWN sem estado do observer-system" \
    "UNKNOWN" \
    "$(jq -r '.system.status' <<<"$REPORT_HEALTH")"

build_storage_analysis() {
    :
}

build_cpu_analysis() {
    :
}

build_memory_analysis() {
    :
}

build_services_analysis() {
    :
}

build_network_analysis() {
    :
}

build_ssh_analysis() {
    :
}

build_global_conclusions() {
    :
}

test_overall_status() {
    local label="$1"
    local expected="$2"
    local ok_count="$3"
    local warning_count="$4"
    local error_count="$5"
    local unknown_count="$6"

    reset_report
    ok="$ok_count"
    warning="$warning_count"
    error="$error_count"
    unknown="$unknown_count"

    build_analysis

    assert_equal \
        "$label" \
        "$expected" \
        "$(jq -r '.overall.status' <<<"$REPORT_HEALTH")"
}

test_overall_status \
    "overall fica OK sem estados adversos" \
    "OK" 7 0 0 0

test_overall_status \
    "overall fica WARNING quando existe WARNING" \
    "WARNING" 6 1 0 0

test_overall_status \
    "overall fica ERROR quando existe ERROR" \
    "ERROR" 6 0 1 0

test_overall_status \
    "overall fica UNKNOWN quando existe estado desconhecido" \
    "UNKNOWN" 6 0 0 1

REPORT_STATUS="OK"
REPORT_HEALTH='{
  "overall": {"status": "OK"},
  "system": {"status": "OK"},
  "security": {"status": "OK"},
  "resources": {"status": "OK"},
  "connectivity": {"status": "OK"},
  "services": {"status": "OK"}
}'

if validate_health_contract; then
    pass_test "contrato health completo é aceite"
else
    fail_test "contrato health completo é aceite"
fi

REPORT_STATUS="OK"
REPORT_HEALTH='{
  "overall": {"status": "OK"},
  "security": {"status": "OK"},
  "resources": {"status": "OK"},
  "connectivity": {"status": "OK"},
  "services": {"status": "OK"}
}'

if validate_health_contract 2>/dev/null; then
    fail_test "contrato sem domínio system é rejeitado"
else
    pass_test "contrato sem domínio system é rejeitado"
fi

REPORT_STATUS="WARNING"
REPORT_HEALTH='{
  "overall": {"status": "OK"},
  "system": {"status": "OK"},
  "security": {"status": "OK"},
  "resources": {"status": "OK"},
  "connectivity": {"status": "OK"},
  "services": {"status": "OK"}
}'

if validate_health_contract 2>/dev/null; then
    fail_test "overall incoerente com REPORT_STATUS é rejeitado"
else
    pass_test "overall incoerente com REPORT_STATUS é rejeitado"
fi

printf '\nResultados: PASS=%d FAIL=%d\n' "$passes" "$failures"

if (( failures > 0 )); then
    exit 1
fi
