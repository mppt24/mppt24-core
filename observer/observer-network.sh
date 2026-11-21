#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer Network
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-network"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100

if ! command -v ip >/dev/null 2>&1; then
    status="ERROR"
    confidence=0
    add_error "O comando 'ip' não está disponível."
elif ! interfaces="$(ip -j address 2>/dev/null)" ||
     ! routes="$(ip -j route show default 2>/dev/null)"; then
    status="ERROR"
    confidence=0
    add_error "Não foi possível recolher os dados de rede com o comando 'ip'."
else
    add_fact "interfaces" "$interfaces"
    add_fact "default_routes" "$routes"
fi

set_status "$status"
set_confidence "$confidence"

emit_report
