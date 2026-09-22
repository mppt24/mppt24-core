#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer CPU
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-cpu"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100

if [[ -r /proc/loadavg && -r /proc/cpuinfo ]]; then

    load1="$(awk '{print $1}' /proc/loadavg)"
    load5="$(awk '{print $2}' /proc/loadavg)"
    load15="$(awk '{print $3}' /proc/loadavg)"

    cpu_count="$(grep -c '^processor' /proc/cpuinfo)"

    model="$(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo)"

    add_fact_string "model" "$model"
    add_fact "cpu_count" "$cpu_count"
    add_fact_string "load_1min" "$load1"
    add_fact_string "load_5min" "$load5"
    add_fact_string "load_15min" "$load15"

else
    status="ERROR"
    confidence=0
    add_error "Não foi possível obter informação da CPU."
fi

set_status "$status"
set_confidence "$confidence"

emit_report
