#!/usr/bin/env bash
#
# MPPT24 CORE
# Observer System
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../core/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../core/report.sh"

readonly MODULE_NAME="observer-system"
readonly MODULE_VERSION="1.0.0"

reset_report
set_metadata "$MODULE_NAME" "$MODULE_VERSION"

status="OK"
confidence=100
hostnamectl_available=true
hostnamectl_error=""

if ! system_identity="$(hostnamectl --json=short 2>/dev/null)" || ! jq -e 'type == "object"' <<< "$system_identity" >/dev/null 2>&1; then
    status="ERROR"
    confidence=40
    hostnamectl_available=false
    hostnamectl_error="Não foi possível consultar a identificação do sistema."
    system_identity='{}'
fi

architecture_available=true
architecture_error=""

if ! architecture="$(uname -m 2>/dev/null)" || [[ -z "$architecture" ]]; then
    status="ERROR"
    confidence=40
    architecture_available=false
    architecture_error="Não foi possível consultar a arquitetura do sistema."
    architecture=""
fi

proc_available=true
proc_error=""
uptime_seconds=0
load_1m=0
load_5m=0
load_15m=0
runnable_tasks=0
total_tasks=0

if ! read -r uptime_seconds _ < /proc/uptime || ! read -r load_1m load_5m load_15m task_counts _ < /proc/loadavg; then
    status="ERROR"
    confidence=40
    proc_available=false
    proc_error="Não foi possível consultar uptime e carga em /proc."
else
    runnable_tasks="${task_counts%%/*}"
    total_tasks="${task_counts##*/}"
fi

cpu_available=true
cpu_warning=""

if ! cpu_identity="$(LC_ALL=C lscpu -J 2>/dev/null)" || ! jq -e '(.lscpu | type) == "array"' <<< "$cpu_identity" >/dev/null 2>&1; then
    cpu_available=false
    cpu_warning="Não foi possível consultar a topologia da CPU."
    cpu_identity='{"lscpu":[]}'
    if [[ "$status" == "OK" ]]; then
        status="WARNING"
        confidence=85
    fi
fi

memory_available=true
memory_error=""
memory_total_kb=0
memory_available_kb=0
swap_total_kb=0
swap_free_kb=0

if ! memory_values="$(awk '/^MemTotal:/{mt=$2} /^MemAvailable:/{ma=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2} END{if(mt=="" || ma=="" || st=="" || sf=="") exit 1; print mt, ma, st, sf}' /proc/meminfo 2>/dev/null)"; then
    status="ERROR"
    confidence=40
    memory_available=false
    memory_error="Não foi possível consultar memória e swap em /proc."
else
    read -r memory_total_kb memory_available_kb swap_total_kb swap_free_kb <<< "$memory_values"
fi

thermal_available=true
thermal_warning=""
thermal_zones_json="$(
    for zone in /sys/class/thermal/thermal_zone*; do
        [[ -r "$zone/type" && -r "$zone/temp" ]] || continue
        thermal_name="$(< "$zone/type")"
        thermal_temp="$(< "$zone/temp")"
        [[ "$thermal_temp" =~ ^-?[0-9]+$ ]] || continue
        jq -n --arg name "$thermal_name" --argjson temperature_millicelsius "$thermal_temp" '{name: $name, temperature_millicelsius: $temperature_millicelsius}'
    done | jq -s '.'
)"

if [[ "$(jq 'length' <<< "$thermal_zones_json")" -eq 0 ]]; then
    thermal_available=false
    thermal_warning="Não foi possível consultar zonas térmicas."
    if [[ "$status" == "OK" ]]; then
        status="WARNING"
        confidence=90
    fi
fi

time_available=true
time_warning=""
timezone=""
ntp_enabled=null
ntp_synchronized=null
local_rtc=null

if ! time_data="$(timedatectl show --property=Timezone --property=NTPSynchronized --property=NTP --property=LocalRTC 2>/dev/null)"; then
    time_available=false
else
    timezone="$(awk -F= '$1=="Timezone"{print substr($0, index($0, "=")+1)}' <<< "$time_data")"
    ntp_raw="$(awk -F= '$1=="NTP"{print $2}' <<< "$time_data")"
    ntp_sync_raw="$(awk -F= '$1=="NTPSynchronized"{print $2}' <<< "$time_data")"
    local_rtc_raw="$(awk -F= '$1=="LocalRTC"{print $2}' <<< "$time_data")"

    case "$ntp_raw" in yes) ntp_enabled=true ;; no) ntp_enabled=false ;; *) time_available=false ;; esac
    case "$ntp_sync_raw" in yes) ntp_synchronized=true ;; no) ntp_synchronized=false ;; *) time_available=false ;; esac
    case "$local_rtc_raw" in yes) local_rtc=true ;; no) local_rtc=false ;; *) time_available=false ;; esac
    [[ -n "$timezone" ]] || time_available=false
fi

if [[ "$time_available" != true ]]; then
    time_warning="Não foi possível consultar completamente o estado de tempo e NTP."
    if [[ "$status" == "OK" ]]; then
        status="WARNING"
        confidence=90
    fi
fi


set_status "$status"
set_confidence "$confidence"

add_fact "hostnamectl_available" "$hostnamectl_available"

if [[ "$hostnamectl_available" == true ]]; then
    add_fact "hostname" "$(jq -c '.StaticHostname' <<<"$system_identity")"
    add_fact "operating_system" "$(jq -c '.OperatingSystemPrettyName' <<<"$system_identity")"
    add_fact "kernel" "$(jq -c '.KernelRelease' <<<"$system_identity")"
else
    add_fact "hostname" "null"
    add_fact "operating_system" "null"
    add_fact "kernel" "null"
fi

add_fact "architecture_available" "$architecture_available"

if [[ "$architecture_available" == true ]]; then
    add_fact_string "architecture" "$architecture"
else
    add_fact "architecture" "null"
fi

if [[ "$hostnamectl_available" == true ]]; then
    add_fact "chassis" "$(jq -c '.Chassis' <<<"$system_identity")"
    add_fact "hardware_vendor" "$(jq -c '.HardwareVendor' <<<"$system_identity")"
    add_fact "hardware_model" "$(jq -c '.HardwareModel' <<<"$system_identity")"
    add_fact "firmware_version" "$(jq -c '.FirmwareVersion' <<<"$system_identity")"
    add_fact "firmware_date" "$(jq -c 'if .FirmwareDate then (.FirmwareDate / 1000000 | todateiso8601) else null end' <<<"$system_identity")"
    add_fact "boot_id" "$(jq -c '.BootID' <<<"$system_identity")"
else
    add_fact "chassis" "null"
    add_fact "hardware_vendor" "null"
    add_fact "hardware_model" "null"
    add_fact "firmware_version" "null"
    add_fact "firmware_date" "null"
    add_fact "boot_id" "null"
fi

add_fact "proc_available" "$proc_available"

if [[ "$proc_available" == true ]]; then
    add_fact "uptime_seconds" "${uptime_seconds:-0}"
    add_fact "load_average_1m" "${load_1m:-0}"
    add_fact "load_average_5m" "${load_5m:-0}"
    add_fact "load_average_15m" "${load_15m:-0}"
    add_fact "runnable_tasks" "${runnable_tasks:-0}"
    add_fact "total_tasks" "${total_tasks:-0}"
else
    add_fact "uptime_seconds" "null"
    add_fact "load_average_1m" "null"
    add_fact "load_average_5m" "null"
    add_fact "load_average_15m" "null"
    add_fact "runnable_tasks" "null"
    add_fact "total_tasks" "null"
fi

add_fact "cpu_available" "$cpu_available"

if [[ "$cpu_available" == true ]]; then
    add_fact "cpu_model" "$(jq -c '([.lscpu[] | select(.field == "Model name:") | .data][0] // null)' <<<"$cpu_identity")"
    add_fact "cpu_logical" "$(jq -c '(([.lscpu[] | select(.field == "CPU(s):") | .data][0] // null) | tonumber?)' <<<"$cpu_identity")"
    add_fact "cpu_sockets" "$(jq -c '(([.lscpu[] | select(.field == "Socket(s):") | .data][0] // null) | tonumber?)' <<<"$cpu_identity")"
    add_fact "cpu_cores_per_socket" "$(jq -c '(([.lscpu[] | select(.field == "Core(s) per socket:") | .data][0] // null) | tonumber?)' <<<"$cpu_identity")"
    add_fact "cpu_threads_per_core" "$(jq -c '(([.lscpu[] | select(.field == "Thread(s) per core:") | .data][0] // null) | tonumber?)' <<<"$cpu_identity")"
else
    add_fact "cpu_model" "null"
    add_fact "cpu_logical" "null"
    add_fact "cpu_sockets" "null"
    add_fact "cpu_cores_per_socket" "null"
    add_fact "cpu_threads_per_core" "null"
fi

add_fact "memory_available" "$memory_available"

if [[ "$memory_available" == true ]]; then
    add_fact "memory_total_kb" "${memory_total_kb:-0}"
    add_fact "memory_available_kb" "${memory_available_kb:-0}"
    add_fact "swap_total_kb" "${swap_total_kb:-0}"
    add_fact "swap_free_kb" "${swap_free_kb:-0}"
else
    add_fact "memory_total_kb" "null"
    add_fact "memory_available_kb" "null"
    add_fact "swap_total_kb" "null"
    add_fact "swap_free_kb" "null"
fi

add_fact "thermal_available" "$thermal_available"

if [[ "$thermal_available" == true ]]; then
    add_fact "thermal_zones" "$thermal_zones_json"
else
    add_fact "thermal_zones" "null"
fi

add_fact "time_available" "$time_available"

if [[ "$time_available" == true ]]; then
    add_fact_string "timezone" "$timezone"
    add_fact "ntp_enabled" "$ntp_enabled"
    add_fact "ntp_synchronized" "$ntp_synchronized"
    add_fact "local_rtc" "$local_rtc"
else
    add_fact "timezone" "null"
    add_fact "ntp_enabled" "null"
    add_fact "ntp_synchronized" "null"
    add_fact "local_rtc" "null"
fi

if [[ -n "$cpu_warning" ]]; then
    add_warning "$cpu_warning"
fi

if [[ -n "$thermal_warning" ]]; then
    add_warning "$thermal_warning"
fi

if [[ -n "$time_warning" ]]; then
    add_warning "$time_warning"
fi

if [[ -n "$hostnamectl_error" ]]; then
    add_error "$hostnamectl_error"
fi

if [[ -n "$architecture_error" ]]; then
    add_error "$architecture_error"
fi

if [[ -n "$proc_error" ]]; then
    add_error "$proc_error"
fi

if [[ -n "$memory_error" ]]; then
    add_error "$memory_error"
fi

emit_report
