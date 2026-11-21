#!/usr/bin/env bash
#
# MPPT24 CORE
# Decision Engine
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$ROOT/core/common.sh"
source "$ROOT/core/report.sh"

readonly MODULE_NAME="decision-engine"
readonly MODULE_VERSION="2.3.0"
readonly REPORT_DIR="${MPPT24_REPORT_DIR:-$ROOT/data/observer}"

ok=0
warning=0
error=0
unknown=0

ALL_FACTS='{}'
ALL_STATUSES='{}'

collect_status() {
    local file
    local module
    local status
    local collected=0

    ok=0
    warning=0
    error=0
    unknown=0
    ALL_STATUSES='{}'

    for file in "$REPORT_DIR"/observer-*.json; do
        [[ -f "$file" ]] || continue

        module="$(jq -er ".module | select(type == \"string\" and length > 0)" "$file")"
        status="$(jq -r ".status // \"UNKNOWN\"" "$file")"

        if jq -e --arg module "$module" "has(\$module)" \
            >/dev/null 2>&1 <<<"$ALL_STATUSES"; then
            printf "%s\n" "ERRO: estado duplicado para o módulo ${module}." >&2
            return 1
        fi

        ALL_STATUSES=$(
            printf "%s\n" "$ALL_STATUSES" |
            jq -e \
                --arg module "$module" \
                --arg status "$status" \
                ". + {(\$module): \$status}"
        )

        ((++collected))

        case "$status" in
            OK)
                ((++ok))
                ;;
            WARNING)
                ((++warning))
                ;;
            ERROR)
                ((++error))
                ;;
            *)
                ((++unknown))
                ;;
        esac
    done

    if (( collected == 0 )); then
        printf "%s\n" "ERRO: nenhum relatório de observer encontrado." >&2
        return 1
    fi
}

get_status() {
    local module="$1"

    jq -r \
        --arg module "$module" \
        ".[\$module] // empty" \
        <<<"$ALL_STATUSES"
}

collect_facts() {
    local file
    local module
    local facts

    for file in "$REPORT_DIR"/observer-*.json; do
        module="$(jq -r '.module' "$file")"
        facts="$(jq -c '.facts' "$file")"

        ALL_FACTS=$(jq             --arg module "$module"             --argjson facts "$facts"             '. + {($module): $facts}' <<<"$ALL_FACTS")
    done
}

get_fact() {
    local module="$1"
    local path="$2"

    jq -r \
        --arg module "$module" \
        --arg path "$path" '
            .[$module] as $obj
            | if ($obj | type) != "object" then
                empty
              elif ($obj | has($path)) then
                $obj[$path]
              else
                try ($obj | getpath($path | split("."))) catch empty
              end
            | select(. != null)
        ' <<<"$ALL_FACTS"
}


set_global_status() {
    if (( error > 0 )); then
        set_status "ERROR"
    elif (( warning > 0 )); then
        set_status "WARNING"
    elif (( unknown > 0 )); then
        set_status "UNKNOWN"
    else
        set_status "OK"
    fi
}

get_interface_field() {
    local ifname="$1"
    local field="$2"

    jq -r         --arg ifname "$ifname"         --arg field "$field" '
            .["observer-network"].interfaces[]
            | select(.ifname == $ifname)
            | .[$field] // empty
        ' <<<"$ALL_FACTS"
}

get_interface_status() {
    local ifname="$1"

    jq -r         --arg ifname "$ifname" '
            .["observer-network"].interfaces[]
            | select(.ifname == $ifname)
            | if ((.flags | index("UP")) and (.flags | index("LOWER_UP")))
                then "UP"
                else (.operstate // "UNKNOWN")
              end
        ' <<<"$ALL_FACTS"
}

build_facts() {
    add_fact "observer_reports" "$((ok + warning + error + unknown))"
    add_fact "ok" "$ok"
    add_fact "warning" "$warning"
    add_fact "error" "$error"
    add_fact "unknown" "$unknown"
}

build_cpu_analysis() {
    local cpu_count load1 load5 load15

    cpu_count="$(get_fact observer-cpu cpu_count)"
    load1="$(get_fact observer-cpu load_1min)"
    load5="$(get_fact observer-cpu load_5min)"
    load15="$(get_fact observer-cpu load_15min)"

    [[ -n "$cpu_count" ]] || cpu_count="desconhecido"
    [[ -n "$load1" ]] || load1="desconhecida"
    [[ -n "$load5" ]] || load5="desconhecida"
    [[ -n "$load15" ]] || load15="desconhecida"

    add_analysis "CPU: ${cpu_count} CPUs lógicos."
    add_analysis "CPU: carga 1m=${load1}, 5m=${load5}, 15m=${load15}."
}

build_storage_analysis() {
    local disk_count

    disk_count="$(get_fact observer-storage disk_count)"
    [[ -n "$disk_count" ]] || disk_count="desconhecido"

    add_analysis "Storage: ${disk_count} discos detetados."
}

build_memory_analysis() {
    local mem_total mem_available swap_total swap_free
    local ram_total_gib ram_available_gib
    local swap_total_gib swap_free_gib

    mem_total="$(get_fact observer-memory 'memory.MemTotal')"
    mem_available="$(get_fact observer-memory 'memory.MemAvailable')"
    swap_total="$(get_fact observer-memory 'memory.SwapTotal')"
    swap_free="$(get_fact observer-memory 'memory.SwapFree')"

    [[ -n "$mem_total" ]] || mem_total=0
    [[ -n "$swap_total" ]] || swap_total=0

    ram_total_gib=$(awk -v v="$mem_total" 'BEGIN { printf "%.2f", v / 1024 / 1024 }')
    ram_available_gib=$(awk -v v="$mem_available" 'BEGIN { printf "%.2f", v / 1024 / 1024 }')
    swap_total_gib=$(awk -v v="$swap_total" 'BEGIN { printf "%.2f", v / 1024 / 1024 }')
    swap_free_gib=$(awk -v v="$swap_free" 'BEGIN { printf "%.2f", v / 1024 / 1024 }')

    add_analysis "Memory: ${ram_total_gib} GiB RAM total, ${ram_available_gib} GiB disponíveis."
    add_analysis "Swap: ${swap_total_gib} GiB total, ${swap_free_gib} GiB livres."
}

build_services_analysis() {
    local ssh tailscale fail2ban adguard

    ssh="$(get_fact observer-services ssh.service)"
    tailscale="$(get_fact observer-services tailscaled.service)"
    fail2ban="$(get_fact observer-services fail2ban.service)"
    adguard="$(get_fact observer-services AdGuardHome.service)"

    [[ -n "$ssh" ]] || ssh="desconhecido"
    [[ -n "$tailscale" ]] || tailscale="desconhecido"
    [[ -n "$fail2ban" ]] || fail2ban="desconhecido"
    [[ -n "$adguard" ]] || adguard="desconhecido"

    add_analysis "Services: SSH = ${ssh}."
    add_analysis "Services: Tailscale = ${tailscale}."
    add_analysis "Services: Fail2Ban = ${fail2ban}."
    add_analysis "Services: AdGuardHome = ${adguard}."
}

build_network_analysis() {
    local lan_state ts_state wg_state gateway

    lan_state="$(get_interface_status enp8s0)"
    ts_state="$(get_interface_status tailscale0)"
    wg_state="$(get_interface_status wg0)"

    gateway="$(jq -r '
        .["observer-network"].default_routes[0].gateway // empty
    ' <<<"$ALL_FACTS")"

    [[ -n "$lan_state" ]] || lan_state="desconhecido"
    [[ -n "$ts_state" ]] || ts_state="desconhecido"
    [[ -n "$wg_state" ]] || wg_state="desconhecido"
    [[ -n "$gateway" ]] || gateway="desconhecido"

    add_analysis "Network: LAN (enp8s0) = ${lan_state}."
    add_analysis "Network: Tailscale = ${ts_state}."
    add_analysis "Network: WireGuard = ${wg_state}."
    add_analysis "Network: Gateway = ${gateway}."
}

build_ssh_analysis() {
    local service socket invalid failed pubkey

    service="$(get_fact observer-ssh ssh_service_active)"
    socket="$(get_fact observer-ssh ssh_socket_active)"
    invalid="$(get_fact observer-ssh invalid_user_events_24h)"
    failed="$(get_fact observer-ssh failed_password_events_24h)"
    pubkey="$(get_fact observer-ssh accepted_publickey_events_24h)"

    [[ -n "$service" ]] || service="desconhecido"
    [[ -n "$socket" ]] || socket="desconhecido"
    [[ -n "$invalid" ]] || invalid=0
    [[ -n "$pubkey" ]] || pubkey=0

    add_analysis "SSH: serviço = ${service}."
    add_analysis "SSH: socket = ${socket}."
    add_analysis "SSH: invalid users (24h) = ${invalid}."
    add_analysis "SSH: failed passwords (24h) = ${failed}."
    add_analysis "SSH: autenticações por chave pública (24h) = ${pubkey}."


}

build_analysis() {
    add_analysis "Observers processados: $((ok + warning + error + unknown))."
    add_analysis "Estados: OK=$ok, WARNING=$warning, ERROR=$error, UNKNOWN=$unknown."

    build_storage_analysis
    build_cpu_analysis
    build_memory_analysis
    build_services_analysis
    build_network_analysis
    build_ssh_analysis
    build_global_conclusions

    if (( error > 0 )); then
        set_health overall ERROR
        add_summary "Estado global crítico."
        add_analysis "Estado global: ERROR (existe pelo menos um observer em ERROR)."
        add_conclusion "Estado global: ERROR (existe pelo menos um observer em ERROR)."
    elif (( warning > 0 )); then
        set_health overall WARNING
        add_summary "Estado global requer atenção."
        add_analysis "Estado global: WARNING (existem observers em WARNING e nenhum em ERROR)."
        add_conclusion "Estado global: WARNING (existem observers em WARNING e nenhum em ERROR)."
    elif (( unknown > 0 )); then
        set_health overall UNKNOWN
        add_summary "Estado global desconhecido."
        add_analysis "Estado global: UNKNOWN (existem observers sem estado conhecido)."
        add_conclusion "Estado global: UNKNOWN (existem observers sem estado conhecido)."
    else
        set_health overall OK
        add_summary "Estado global operacional."
        add_conclusion "Estado global: OK (todos os observers estão em estado OK)."
    fi
}

build_global_conclusions() {
    build_system_health_conclusions
    build_security_conclusions
    build_resource_conclusions
    build_connectivity_conclusions
    build_service_conclusions
}

build_system_health_conclusions() {
    local observer_status time_available ntp_enabled ntp_synchronized

    observer_status="$(get_status observer-system)"
    time_available="$(get_fact observer-system time_available)"
    ntp_enabled="$(get_fact observer-system ntp_enabled)"
    ntp_synchronized="$(get_fact observer-system ntp_synchronized)"

    case "$observer_status" in
        ERROR)
            set_health system ERROR
            add_summary "Sistema base em estado crítico."
            add_conclusion "Sistema: uma fonte essencial do observer-system está indisponível."
            ;;
        WARNING)
            set_health system WARNING
            add_summary "Sistema base requer atenção."
            add_conclusion "Sistema: uma fonte secundária do observer-system está indisponível."
            ;;
        OK)
            if [[ "$time_available" != "true" ||
                  ! "$ntp_enabled" =~ ^(true|false)$ ||
                  ! "$ntp_synchronized" =~ ^(true|false)$ ]]; then

                set_health system UNKNOWN
                add_summary "Estado do sistema base desconhecido."
                add_conclusion "Sistema: estado técnico e factos temporais são inconsistentes ou insuficientes."
            elif [[ "$ntp_enabled" != "true" || "$ntp_synchronized" != "true" ]]; then
                set_health system WARNING
                add_summary "Sistema base requer atenção."
                add_conclusion "Sistema: sincronização NTP não está plenamente operacional."
            else
                set_health system OK
                add_summary "Sistema base operacional."
                add_conclusion "Sistema: fontes do sistema disponíveis e sincronização NTP operacional."
            fi
            ;;
        *)
            set_health system UNKNOWN
            add_summary "Estado do sistema base desconhecido."
            add_conclusion "Sistema: estado do observer-system ausente ou desconhecido."
            ;;
    esac
}

build_security_conclusions() {
    local journal invalid failed pubkey

    journal="$(get_fact observer-ssh journal_available)"
    invalid="$(get_fact observer-ssh invalid_user_events_24h)"
    failed="$(get_fact observer-ssh failed_password_events_24h)"
    pubkey="$(get_fact observer-ssh accepted_publickey_events_24h)"

    [[ -n "$invalid" ]] || invalid=0
    [[ -n "$pubkey" ]] || pubkey=0

    if [[ "$journal" != "true" || ! "$failed" =~ ^[0-9]+$ ]]; then
        set_health security UNKNOWN
        add_summary "Estado da segurança desconhecido."
        add_conclusion "Segurança: dados insuficientes para determinar o estado."
    elif (( failed > 0 )); then
        set_health security WARNING
        add_summary "Segurança requer atenção."
        add_conclusion "Segurança: detetadas ${failed} tentativas de autenticação por palavra-passe nas últimas 24 horas."
    else
        set_health security OK
        add_summary "Segurança operacional."
        add_conclusion "Segurança: não foram detetadas tentativas de autenticação por palavra-passe."
    fi

    if (( pubkey > 0 )); then
        add_conclusion "Segurança: autenticação por chave pública em utilização."
    fi

    if (( invalid > 0 )); then
        add_conclusion "Segurança: observadas ${invalid} tentativas de utilizadores inválidos nas últimas 24 horas."
    fi
}

build_resource_conclusions() {
    local cpu_count load15 mem_total mem_available swap_total swap_free

    cpu_count="$(get_fact observer-cpu cpu_count)"
    load15="$(get_fact observer-cpu load_15min)"
    mem_total="$(get_fact observer-memory memory.MemTotal)"
    mem_available="$(get_fact observer-memory memory.MemAvailable)"
    swap_total="$(get_fact observer-memory memory.SwapTotal)"
    swap_free="$(get_fact observer-memory memory.SwapFree)"


    if [[ ! "$cpu_count" =~ ^[1-9][0-9]*$ || ! "$load15" =~ ^[0-9]+([.][0-9]+)?$ || ! "$mem_total" =~ ^[1-9][0-9]*$ || ! "$mem_available" =~ ^[0-9]+$ || ! "$swap_total" =~ ^[0-9]+$ || ! "$swap_free" =~ ^[0-9]+$ ]]; then
        set_health resources UNKNOWN
        add_summary "Estado dos recursos desconhecido."
        add_conclusion "Recursos: dados insuficientes para determinar o estado."
    elif awk -v loadavg="$load15" -v cpus="$cpu_count" 'BEGIN { exit !(loadavg >= cpus * 2) }' || (( mem_available * 100 < mem_total * 5 )); then
        set_health resources ERROR
        add_summary "Recursos em estado crítico."
        add_conclusion "Recursos: limites críticos atingidos."
    elif awk -v loadavg="$load15" -v cpus="$cpu_count" 'BEGIN { exit !(loadavg >= cpus) }' || (( mem_available * 100 < mem_total * 15 )) || (( swap_total > 0 && (swap_total - swap_free) * 100 >= swap_total * 75 )); then
        set_health resources WARNING
        add_summary "Recursos requerem atenção."
        add_conclusion "Recursos: pelo menos um limite de atenção foi atingido."
    else
        set_health resources OK
        add_summary "Recursos dentro dos parâmetros."
        add_conclusion "Recursos: carga, memória e swap dentro dos valores esperados."
    fi


}

build_connectivity_conclusions() {
    local lan ts wg gateway gateway_dev network_data

    lan="$(get_interface_status enp8s0)"
    ts="$(get_interface_status tailscale0)"
    wg="$(get_interface_status wg0)"

    network_data="$(jq -r 'if ((.["observer-network"].interfaces | type) == "array" and (.["observer-network"].default_routes | type) == "array") then "true" else "false" end' <<<"$ALL_FACTS")"
    gateway="$(jq -r         '.["observer-network"].default_routes[0].gateway // empty'         <<<"$ALL_FACTS")"

    gateway_dev="$(jq -r '.["observer-network"].default_routes[0].dev // empty' <<<"$ALL_FACTS")"
    [[ -n "$gateway" ]] || gateway="desconhecido"

    if [[ "$network_data" != "true" ]]; then
        set_health connectivity UNKNOWN
        add_summary "Estado da conectividade desconhecido."
        add_conclusion "Conectividade: dados insuficientes para determinar o estado."
    elif [[ "$lan" != "UP" || "$gateway" == "desconhecido" || "$gateway_dev" != "enp8s0" ]]; then
        set_health connectivity ERROR
        add_summary "Conectividade essencial indisponível."
        add_conclusion "Conectividade: LAN ou gateway predefinido não estão no estado esperado."
    elif [[ "$ts" != "UP" || "$wg" != "UP" ]]; then
        set_health connectivity WARNING
        add_summary "Conectividade requer atenção."
        add_conclusion "Conectividade: LAN operacional, mas existe uma VPN esperada indisponível."
    else
        set_health connectivity OK
        add_summary "Conectividade operacional."
        add_conclusion "Conectividade: LAN, gateway e VPNs esperadas estão operacionais."
    fi

    if [[ "$ts" == "UP" ]]; then
        add_conclusion "Conectividade: acesso remoto Tailscale operacional."
    fi

    if [[ "$wg" == "UP" ]]; then
        add_conclusion "Conectividade: interface WireGuard operacional."
    fi

    add_conclusion "Conectividade: gateway predefinido = ${gateway}."
}

build_service_conclusions() {
    local ssh tailscale fail2ban adguard

    ssh="$(get_fact observer-services ssh.service)"
    tailscale="$(get_fact observer-services tailscaled.service)"
    fail2ban="$(get_fact observer-services fail2ban.service)"
    adguard="$(get_fact observer-services AdGuardHome.service)"

    if [[ -z "$ssh" || -z "$tailscale" || -z "$fail2ban" || -z "$adguard" ]]; then
        set_health services UNKNOWN
        add_summary "Estado dos serviços desconhecido."
        add_conclusion "Serviços: dados insuficientes para determinar o estado."
    elif [[ "$ssh" != "active" || "$adguard" != "active" ]]; then
        set_health services ERROR
        add_summary "Serviços essenciais indisponíveis."
        add_conclusion "Serviços: SSH ou AdGuardHome não estão operacionais."
    elif [[ "$tailscale" != "active" || "$fail2ban" != "active" ]]; then
        set_health services WARNING
        add_summary "Serviços requerem atenção."
        add_conclusion "Serviços: Tailscale ou Fail2Ban não estão operacionais."
    else
        set_health services OK
        add_summary "Serviços essenciais operacionais."
    fi

    if [[ "$ssh" == "active" ]]; then
        add_conclusion "Serviços: SSH operacional."
    fi
    if [[ "$tailscale" == "active" ]]; then
        add_conclusion "Serviços: Tailscale operacional."
    fi

    if [[ "$fail2ban" == "active" ]]; then
        add_conclusion "Serviços: Fail2Ban operacional."
    fi

    if [[ "$adguard" == "active" ]]; then
        add_conclusion "Serviços: AdGuardHome operacional."
    fi

    if [[ "$ssh" == "active" &&           "$tailscale" == "active" &&           "$fail2ban" == "active" &&           "$adguard" == "active" ]]; then
        add_conclusion "Serviços: todos os serviços essenciais monitorizados encontram-se operacionais."
    fi
}

validate_health_contract() {
    if ! jq -e \
        --arg overall "$REPORT_STATUS" \
        "
            type == \"object\"
            and (
                ([\"overall\", \"system\", \"security\", \"resources\", \"connectivity\", \"services\"] - keys)
                | length == 0
            )
            and (.overall.status == \$overall)
        " \
        >/dev/null 2>&1 <<<"$REPORT_HEALTH"; then
        printf "%s\n" "ERRO: contrato health do Decision Engine incompleto ou incoerente." >&2
        return 1
    fi
}

build_recommendations() {
    if (( error > 0 )); then
        add_recommendation "Existem observers em estado ERROR. Rever esses relatórios antes de qualquer intervenção."
    elif (( warning > 0 )); then
        add_recommendation "Existem observers em estado WARNING. Recomenda-se análise antes de alterações."
    else
        add_recommendation "Todos os observers estão em estado OK. Nenhuma ação recomendada."
    fi
}

main() {
    reset_report
    set_metadata "$MODULE_NAME" "$MODULE_VERSION"

    collect_status
    collect_facts
    set_global_status
    set_confidence 100
    build_facts
    build_analysis
    validate_health_contract
    build_recommendations
    emit_report
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main
fi
