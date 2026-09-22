#!/usr/bin/env bash
#
# MPPT24 CORE
# Biblioteca comum
#

set -euo pipefail

[[ -n "${MPPT24_COMMON_SH_LOADED:-}" ]] && return 0
readonly MPPT24_COMMON_SH_LOADED=1

# Diretório raiz do projeto
readonly CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Carregar configuração global
source "${CORE_DIR}/config/core.conf"

# Timestamp ISO 8601
timestamp() {
    date +"%Y-%m-%dT%H:%M:%S%z"
}
