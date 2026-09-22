#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer Storage
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-storage"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100

if devices_json="$(lsblk -J -o NAME,TYPE,SIZE,FSTYPE,UUID,MOUNTPOINTS 2>/dev/null)"; then
    devices_json="$(printf '%s\n' "$devices_json" | jq '.blockdevices |= map(select(.type=="disk"))')"
    disk_count="$(printf '%s\n' "$devices_json" | jq '.blockdevices | length')"
else
    status="ERROR"
    confidence=0
    devices_json="null"
    disk_count="null"
    add_error "Não foi possível obter informação dos dispositivos com lsblk."
fi

set_status "$status"
set_confidence "$confidence"

add_fact "disk_count" "${disk_count}"
add_fact "devices" "${devices_json}"

emit_report
