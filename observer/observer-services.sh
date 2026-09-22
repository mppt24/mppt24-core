#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer Services
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-services"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100

services=(
    ssh.service
    tailscaled.service
    fail2ban.service
    AdGuardHome.service
)

for service in "${services[@]}"; do
    if systemctl list-unit-files "$service" >/dev/null 2>&1; then
        state="$(systemctl is-active "$service" 2>/dev/null || true)"
        add_fact_string "$service" "$state"

        if [[ "$state" != "active" ]]; then
            status="WARNING"
            add_warning "$service está em estado '$state'."
        fi
    else
        add_fact_string "$service" "not-installed"
        add_warning "$service não está instalado."
    fi
done

set_status "$status"
set_confidence "$confidence"

emit_report
