#!/usr/bin/env bash
#
# MPPT24 CORE
# Sistema de Relatórios
#

set -euo pipefail

# Carregar funções comuns
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

REPORT_MODULE=""
REPORT_VERSION=""
REPORT_TIMESTAMP=""

_require_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        printf "%s\n" "ERRO: jq não está disponível." >&2
        return 1
    fi
}

_is_valid_module_name() {
    local module="${1-}"

    [[ "$module" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]
}

_is_valid_status() {
    local status="${1-}"

    case "$status" in
        "$STATUS_OK"|"$STATUS_WARNING"|"$STATUS_ERROR"|"$STATUS_UNKNOWN")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

_is_valid_confidence() {
    local confidence="${1-}"

    [[ "$confidence" =~ ^[0-9]+$ ]] &&
        (( confidence >= 0 && confidence <= 100 ))
}

_is_valid_semver() {
    local version="${1-}"
    local without_build core prerelease
    local major minor patch extra identifier

    [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$ ]] ||
        return 1

    without_build="${version%%+*}"
    core="${without_build%%-*}"
    prerelease=""

    if [[ "$without_build" == *-* ]]; then
        prerelease="${without_build#*-}"
    fi

    IFS="." read -r major minor patch extra <<<"$core"

    [[ -z "${extra:-}" ]] || return 1

    for identifier in "$major" "$minor" "$patch"; do
        [[ "$identifier" == "0" || "$identifier" != 0* ]] || return 1
    done

    if [[ -n "$prerelease" ]]; then
        while IFS= read -r identifier; do
            if [[ "$identifier" =~ ^[0-9]+$ &&
                  "$identifier" != "0" &&
                  "$identifier" == 0* ]]; then
                return 1
            fi
        done < <(tr "." "\n" <<<"$prerelease")
    fi

    return 0
}

_is_valid_timestamp() {
    local value="${1-}"

    [[ "$value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{4}$ ]] ||
        return 1

    LC_ALL=C date --date="$value" "+%s" >/dev/null 2>&1
}

# Inicializar relatório
reset_report() {
    local default_confidence="${DEFAULT_CONFIDENCE:-100}"

    if ! _is_valid_confidence "$default_confidence"; then
        printf "%s\n" "ERRO: DEFAULT_CONFIDENCE inválido: ${default_confidence}" >&2
        return 1
    fi

    REPORT_MODULE=""
    REPORT_VERSION=""
    REPORT_TIMESTAMP=""
    REPORT_STATUS="$STATUS_UNKNOWN"
    REPORT_CONFIDENCE="$default_confidence"
    REPORT_FACTS='{}'
    REPORT_WARNINGS='[]'
    REPORT_ERRORS='[]'
    REPORT_ANALYSIS='[]'
    REPORT_CONCLUSIONS='[]'
    REPORT_HEALTH='{}'
    REPORT_SUMMARY='[]'
    REPORT_RECOMMENDATIONS='[]'
}

# Definir estado
set_status() {
    local status="${1-}"

    if ! _is_valid_status "$status"; then
        printf "%s\n" "ERRO: estado do relatório inválido: ${status}" >&2
        return 1
    fi

    REPORT_STATUS="$status"
}

# Definir metadados
set_metadata() {
    local module="${1-}"
    local version="${2-}"
    local new_timestamp

    if ! _is_valid_module_name "$module"; then
        printf "%s\n" "ERRO: nome de módulo inválido: ${module}" >&2
        return 1
    fi

    if ! _is_valid_semver "$version"; then
        printf "%s\n" "ERRO: versão SemVer inválida: ${version}" >&2
        return 1
    fi

    new_timestamp="$(timestamp)"

    if ! _is_valid_timestamp "$new_timestamp"; then
        printf "%s\n" "ERRO: timestamp gerado inválido: ${new_timestamp}" >&2
        return 1
    fi

    REPORT_MODULE="$module"
    REPORT_VERSION="$version"
    REPORT_TIMESTAMP="$new_timestamp"
}

# Definir confiança
set_confidence() {
    local confidence="${1-}"

    if ! _is_valid_confidence "$confidence"; then
        printf "%s\n" "ERRO: confiança deve ser um inteiro entre 0 e 100." >&2
        return 1
    fi

    REPORT_CONFIDENCE="$confidence"
}

# Adicionar facto
add_fact() {
    local key="${1-}"
    local value="${2-}"
    local updated_facts

    _require_jq || return 1

    if [[ -z "$key" ]]; then
        printf "%s\n" "ERRO: chave de facto vazia." >&2
        return 1
    fi

    if ! updated_facts=$(
        printf "%s\n" "$REPORT_FACTS" |
        jq -e \
            --arg key "$key" \
            --argjson value "$value" '
                if has($key) then
                    error("duplicate fact: \($key)")
                else
                    . + {($key): $value}
                end
            '
    ); then
        printf "%s\n" "ERRO: não foi possível adicionar o facto: ${key}" >&2
        return 1
    fi

    REPORT_FACTS="$updated_facts"
}

_add_text_item() {
    local variable="${1-}"
    local item="${2-}"
    local label="${3-}"
    local current_value updated_value

    _require_jq || return 1

    if [[ -z "$item" ]]; then
        printf "%s\n" "ERRO: ${label} não pode conter texto vazio." >&2
        return 1
    fi

    current_value="${!variable}"

    if ! jq -e 'type == "array"' \
        >/dev/null 2>&1 <<<"$current_value"; then
        printf "%s\n" "ERRO: estado interno inválido em ${label}." >&2
        return 1
    fi

    if jq -e --arg item "$item" 'index($item) != null' \
        >/dev/null 2>&1 <<<"$current_value"; then
        printf "%s\n" "ERRO: texto duplicado em ${label}: ${item}" >&2
        return 1
    fi

    if ! updated_value=$(
        printf "%s\n" "$current_value" |
        jq -e --arg item "$item" '. + [$item]'
    ); then
        printf "%s\n" "ERRO: não foi possível atualizar ${label}." >&2
        return 1
    fi

    printf -v "$variable" "%s" "$updated_value"
}

# Adicionar facto de texto
add_fact_string() {
    local key="${1-}"
    local value="${2-}"
    local value_json

    _require_jq || return 1

    if ! value_json=$(jq -Rn --arg value "$value" '$value'); then

        printf "%s\n" "ERRO: não foi possível codificar o facto de texto: ${key}" >&2
        return 1
    fi

    add_fact "$key" "$value_json"
}

# Adicionar aviso
add_warning() {
    _add_text_item REPORT_WARNINGS "${1-}" "warnings"
}

# Adicionar erro
add_error() {
    _add_text_item REPORT_ERRORS "${1-}" "errors"
}

# Adicionar análise
add_analysis() {
    _add_text_item REPORT_ANALYSIS "${1-}" "analysis"
}

# Adicionar conclusão
add_conclusion() {
    _add_text_item REPORT_CONCLUSIONS "${1-}" "conclusions"
}

set_health() {
    local domain="${1-}"
    local status="${2-}"
    local updated_health

    _require_jq || return 1

    if ! _is_valid_module_name "$domain"; then
        printf "%s\n" "ERRO: domínio de health inválido: ${domain}" >&2
        return 1
    fi

    if ! _is_valid_status "$status"; then
        printf "%s\n" "ERRO: estado de health inválido para ${domain}: ${status}" >&2
        return 1
    fi

    if ! jq -e 'type == "object"' \
        >/dev/null 2>&1 <<<"$REPORT_HEALTH"; then
        printf "%s\n" "ERRO: estado interno de health inválido." >&2
        return 1
    fi

    if jq -e --arg domain "$domain" 'has($domain)' \
        >/dev/null 2>&1 <<<"$REPORT_HEALTH"; then
        printf "%s\n" "ERRO: domínio de health duplicado: ${domain}" >&2
        return 1
    fi

    if ! updated_health=$(
        printf "%s\n" "$REPORT_HEALTH" |
        jq -e \
            --arg domain "$domain" \
            --arg status "$status" \
            '. + {($domain): {status: $status}}'
    ); then
        printf "%s\n" "ERRO: não foi possível atualizar health." >&2
        return 1
    fi

    REPORT_HEALTH="$updated_health"
}

# Adicionar resumo
add_summary() {
    _add_text_item REPORT_SUMMARY "${1-}" "summary"
}

# Adicionar recomendação
add_recommendation() {
    _add_text_item REPORT_RECOMMENDATIONS "${1-}" "recommendations"
}

_is_valid_text_array() {
    local value="${1-}"

    _require_jq || return 1

    jq -e '
        type == "array"
        and all(.[]; type == "string" and length > 0)
        and (length == (unique | length))
    ' >/dev/null 2>&1 <<<"$value"
}

# Validar relatório
finalize_report() {
    local report_variable label value

    _require_jq || return 1

    if ! _is_valid_module_name "$REPORT_MODULE"; then
        printf "%s\n" "ERRO: nome de módulo inválido: ${REPORT_MODULE}" >&2
        return 1
    fi

    if ! _is_valid_semver "$REPORT_VERSION"; then
        printf "%s\n" "ERRO: versão SemVer inválida: ${REPORT_VERSION}" >&2
        return 1
    fi

    if ! _is_valid_timestamp "$REPORT_TIMESTAMP"; then
        printf "%s\n" "ERRO: timestamp do relatório inválido: ${REPORT_TIMESTAMP}" >&2
        return 1
    fi

    if ! _is_valid_status "$REPORT_STATUS"; then
        printf "%s\n" "ERRO: estado do relatório inválido: ${REPORT_STATUS}" >&2
        return 1
    fi

    if ! _is_valid_confidence "$REPORT_CONFIDENCE"; then
        printf "%s\n" "ERRO: confiança deve ser um inteiro entre 0 e 100." >&2
        return 1
    fi

    if ! jq -e '
        type == "object"
        and all(keys[]; length > 0)
    ' >/dev/null 2>&1 <<<"$REPORT_FACTS"; then
        printf "%s\n" "ERRO: facts deve ser um objeto JSON com chaves não vazias." >&2
        return 1
    fi

    if ! jq -e '
        type == "object"
        and all(keys[]; test("^[a-z0-9]+(-[a-z0-9]+)*$"))
        and all(
            .[];
            type == "object"
            and has("status")
            and (.status | type == "string")
            and (
                .status == "OK"
                or .status == "WARNING"
                or .status == "ERROR"
                or .status == "UNKNOWN"
            )
        )
    ' >/dev/null 2>&1 <<<"$REPORT_HEALTH"; then
        printf "%s\n" "ERRO: health deve conter domínios normalizados e estados válidos." >&2
        return 1
    fi

    while IFS="|" read -r report_variable label; do
        value="${!report_variable}"

        if ! _is_valid_text_array "$value"; then
            printf "%s\n" "ERRO: ${label} deve ser uma lista de texto não vazio e sem duplicados." >&2
            return 1
        fi
    done <<'REPORT_TEXT_ARRAYS'
REPORT_WARNINGS|warnings
REPORT_ERRORS|errors
REPORT_ANALYSIS|analysis
REPORT_CONCLUSIONS|conclusions
REPORT_SUMMARY|summary
REPORT_RECOMMENDATIONS|recommendations
REPORT_TEXT_ARRAYS

    return 0
}

# Emitir relatório
emit_report() {
    finalize_report

    jq -n \
      --arg module "$REPORT_MODULE" \
      --arg version "$REPORT_VERSION" \
      --arg timestamp "$REPORT_TIMESTAMP" \
      --arg status "$REPORT_STATUS" \
      --argjson confidence "$REPORT_CONFIDENCE" \
      --argjson facts "$REPORT_FACTS" \
      --argjson analysis "$REPORT_ANALYSIS" \
      --argjson conclusions "$REPORT_CONCLUSIONS" \
      --argjson health "$REPORT_HEALTH" \
      --argjson summary "$REPORT_SUMMARY" \
      --argjson recommendations "$REPORT_RECOMMENDATIONS" \
      --argjson warnings "$REPORT_WARNINGS" \
      --argjson errors "$REPORT_ERRORS" \
      '{
        module: $module,
        version: $version,
        timestamp: $timestamp,
        status: $status,
        confidence: $confidence,
        facts: $facts,
        analysis: $analysis,
        conclusions: $conclusions,
        health: $health,
        summary: $summary,
        recommendations: $recommendations,
        warnings: $warnings,
        errors: $errors
      }'
}
