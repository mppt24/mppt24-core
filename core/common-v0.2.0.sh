#!/usr/bin/env bash
#
# MPPT24 CORE
# Biblioteca comum
#

set -euo pipefail

# Diretório raiz do projeto
readonly CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Carregar configuração global
source "${CORE_DIR}/config/core.conf"

# Timestamp ISO 8601
timestamp() {
    date +"%Y-%m-%dT%H:%M:%S%z"
}

# Produz uma estrutura JSON base
emit_json() {
    local module="$1"
    local version="$2"
    local status="$3"

    cat <<JSON
{
  "module": "${module}",
  "version": "${version}",
  "timestamp": "$(timestamp)",
  "status": "${status}",
  "confidence": ${DEFAULT_CONFIDENCE},
  "facts": [],
  "warnings": [],
  "errors": []
}
JSON
}
