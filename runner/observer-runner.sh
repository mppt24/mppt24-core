#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer Runner
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$ROOT/core/common.sh"
source "$ROOT/core/report.sh"

readonly MODULE_NAME="observer-runner"
readonly MODULE_VERSION="1.1.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

OBSERVER_DIR="$ROOT/observer"
OUTPUT_DIR="$ROOT/data/observer"

mkdir -p "$OUTPUT_DIR"

executed=0
successful=0
failed=0

for observer in "$OBSERVER_DIR"/observer-*.sh; do

    ((++executed))

    name="$(basename "$observer" .sh)"

    if output="$("$observer")"; then

        if printf '%s\n' "$output" | jq empty >/dev/null 2>&1; then
            printf '%s\n' "$output" > "$OUTPUT_DIR/$name.json"
            ((++successful))
        else
            ((++failed))
            add_warning "$name produziu JSON inválido."
        fi

    else
        ((++failed))
        add_error "$name falhou durante a execução."
    fi

done

if (( failed > 0 )); then
    set_status "WARNING"
else
    set_status "OK"
fi

set_confidence 100

add_fact "executed" "$executed"
add_fact "successful" "$successful"
add_fact "failed" "$failed"
add_fact "reports_written" "$successful"

emit_report
