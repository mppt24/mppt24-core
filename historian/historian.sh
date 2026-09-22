#!/usr/bin/env bash
#
# MPPT24 CORE
# Historian
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$ROOT/core/common.sh"
source "$ROOT/core/report.sh"

readonly MODULE_NAME="historian"
readonly MODULE_VERSION="2.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"
set_status OK
set_confidence 100


SOURCE_DIR="${MPPT24_REPORT_DIR:-$ROOT/data/observer}"
HISTORY_DIR="$ROOT/data/history"

mkdir -p "$HISTORY_DIR"

timestamp="$(date +"%Y%m%d-%H%M%S")"
snapshot="$HISTORY_DIR/snapshot-$timestamp.json"

jq -s '
{
  timestamp: now | strftime("%Y-%m-%dT%H:%M:%S%z"),
  modules: .
}
' "$SOURCE_DIR"/observer-*.json > "$snapshot"

observer_reports=$(find "$SOURCE_DIR" -maxdepth 1 -name 'observer-*.json' | wc -l)

add_fact "snapshot" "$(basename "$snapshot" | jq -R .)"
add_fact "snapshot_path" "$(printf '%s' "$snapshot" | jq -R .)"

add_fact "observer_reports" "$observer_reports"

emit_report
