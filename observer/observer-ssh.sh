#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer SSH
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-ssh"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

systemctl_available=true
systemctl_warning=""

service_active="$(systemctl is-active ssh.service 2>/dev/null || true)"
service_enabled="$(systemctl is-enabled ssh.service 2>/dev/null || true)"
socket_active="$(systemctl is-active ssh.socket 2>/dev/null || true)"
socket_enabled="$(systemctl is-enabled ssh.socket 2>/dev/null || true)"
listen_endpoints_raw=""

if ! listen_endpoints_raw="$(systemctl show ssh.socket --property=Listen --value 2>/dev/null)"; then
    systemctl_available=false
    systemctl_warning="Não foi possível consultar completamente o estado SSH no systemd."
fi

if [[ -z "$service_active" || -z "$service_enabled" || -z "$socket_active" || -z "$socket_enabled" ]]; then
    systemctl_available=false
    systemctl_warning="Não foi possível consultar completamente o estado SSH no systemd."
fi

listen_endpoints_json="$(printf '%s\n' "$listen_endpoints_raw" | sed 's/ (Stream)$//' | jq -Rsc 'split("\n") | map(select(length > 0))')"
status="OK"
confidence=100
if [[ "$systemctl_available" != true ]]; then
    status="WARNING"
    confidence=80
fi
journal_available=true
journal_error=""

if ! journal_data="$(journalctl --since "24 hours ago" -u ssh.service --no-pager --quiet -o cat 2>/dev/null)"; then
    status="ERROR"
    confidence=50
    journal_available=false
    journal_error="Não foi possível consultar o journal SSH."
    journal_data=""
fi
read -r invalid_user_events invalid_user_closed_events root_closed_preauth_events failed_password_events accepted_publickey_events banner_exchange_events < <(printf '%s\n' "$journal_data" | awk '/Invalid user .* from /{invalid++} /Connection (closed|reset) by invalid user/{closed_invalid++} /Connection closed by authenticating user root/{root_closed++} /Failed password/{failed_password++} /Accepted publickey/{accepted_key++} /banner exchange:/{banner++} END{print invalid+0, closed_invalid+0, root_closed+0, failed_password+0, accepted_key+0, banner+0}')
invalid_user_ips_json="$(printf '%s\n' "$journal_data" | awk '/Invalid user .* from /{for(i=1;i<=NF;i++) if($i=="from"){print $(i+1); break}}' | sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"
root_closed_ips_json="$(printf '%s\n' "$journal_data" | awk '/Connection closed by authenticating user root /{for(i=1;i<=NF;i++) if($i=="root"){print $(i+1); break}}' | sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"
accepted_publickey_ips_json="$(printf '%s\n' "$journal_data" | awk '/Accepted publickey /{for(i=1;i<=NF;i++) if($i=="from"){print $(i+1); break}}' | sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"
banner_exchange_ips_json="$(printf '%s\n' "$journal_data" | awk '/banner exchange: Connection from /{for(i=1;i<=NF;i++) if($i=="from"){print $(i+1); break}}' | sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"


set_status "$status"
set_confidence "$confidence"

add_fact "systemctl_available" "$systemctl_available"

if [[ "$systemctl_available" == true ]]; then
    add_fact_string "ssh_service_active" "${service_active:-unknown}"
    add_fact_string "ssh_service_enabled" "${service_enabled:-unknown}"
    add_fact_string "ssh_socket_active" "${socket_active:-unknown}"
    add_fact_string "ssh_socket_enabled" "${socket_enabled:-unknown}"
    add_fact "ssh_listen_endpoints" "${listen_endpoints_json:-[]}"
else
    add_fact "ssh_service_active" "null"
    add_fact "ssh_service_enabled" "null"
    add_fact "ssh_socket_active" "null"
    add_fact "ssh_socket_enabled" "null"
    add_fact "ssh_listen_endpoints" "null"
fi

add_fact "journal_available" "$journal_available"
add_fact "observation_window_hours" "24"

if [[ "$journal_available" == true ]]; then
    add_fact "invalid_user_events_24h" "${invalid_user_events:-0}"
    add_fact "invalid_user_closed_events_24h" "${invalid_user_closed_events:-0}"
    add_fact "root_closed_preauth_events_24h" "${root_closed_preauth_events:-0}"
    add_fact "failed_password_events_24h" "${failed_password_events:-0}"
    add_fact "accepted_publickey_events_24h" "${accepted_publickey_events:-0}"
    add_fact "banner_exchange_events_24h" "${banner_exchange_events:-0}"
    add_fact "invalid_user_unique_ips_24h" "${invalid_user_ips_json:-[]}"
    add_fact "root_closed_preauth_unique_ips_24h" "${root_closed_ips_json:-[]}"
    add_fact "accepted_publickey_unique_ips_24h" "${accepted_publickey_ips_json:-[]}"
    add_fact "banner_exchange_unique_ips_24h" "${banner_exchange_ips_json:-[]}"
else
    add_fact "invalid_user_events_24h" "null"
    add_fact "invalid_user_closed_events_24h" "null"
    add_fact "root_closed_preauth_events_24h" "null"
    add_fact "failed_password_events_24h" "null"
    add_fact "accepted_publickey_events_24h" "null"
    add_fact "banner_exchange_events_24h" "null"
    add_fact "invalid_user_unique_ips_24h" "null"
    add_fact "root_closed_preauth_unique_ips_24h" "null"
    add_fact "accepted_publickey_unique_ips_24h" "null"
    add_fact "banner_exchange_unique_ips_24h" "null"
fi

if [[ -n "$systemctl_warning" ]]; then
    add_warning "$systemctl_warning"
fi

if [[ -n "$journal_error" ]]; then
    add_error "$journal_error"
fi

emit_report
