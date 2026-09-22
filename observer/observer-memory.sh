#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer Memory
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-memory"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100

if [[ -r /proc/meminfo ]]; then
    mem_json="$(
        awk '
        {
            gsub(":", "", $1)
            if ($2 ~ /^[0-9]+$/)
                printf "\"%s\": %s,\n", $1, $2
        }
        ' /proc/meminfo |
        sed '$ s/,$//' |
        awk 'BEGIN{print "{"} {print} END{print "}"}'
    )"

    add_fact "memory" "$mem_json"
else
    status="ERROR"
    confidence=0
    add_error "Não foi possível ler /proc/meminfo."
fi

set_status "$status"
set_confidence "$confidence"

emit_report
