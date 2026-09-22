#!/usr/bin/env bash
#
# MPPT24 CORE
# Captura atómica da saída de um Observer
#

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ $# -ne 2 ]]; then
    echo "Uso: $0 <nome-do-observer> <nome-da-saida>" >&2
    exit 2
fi

module_name="$1"
output_name="$2"

if [[ ! "$module_name" =~ ^[a-z0-9-]+$ || ! "$output_name" =~ ^[a-z0-9-]+$ ]]; then
    echo "Erro: nomes inválidos." >&2
    exit 2
fi

observer="${CORE_DIR}/observer/${module_name}.sh"
target_dir="${CORE_DIR}/data/observer"
target="${target_dir}/${output_name}.json"

if [[ ! -x "$observer" ]]; then
    echo "Erro: Observer inexistente ou não executável: $observer" >&2
    exit 1
fi

if [[ ! -d "$target_dir" ]]; then
    echo "Erro: diretório de destino inexistente: $target_dir" >&2
    exit 1
fi

umask 027
tmp_file="$(mktemp "${target_dir}/.${output_name}.json.tmp.XXXXXX")"

cleanup() {
    if [[ -n "${tmp_file:-}" && -e "$tmp_file" ]]; then
        rm -f -- "$tmp_file"
    fi
}
trap cleanup EXIT

"$observer" > "$tmp_file"

jq -e --arg module "$module_name" '
    type == "object" and
    .module == $module and
    (.version | type == "string") and
    (.timestamp | type == "string") and
    ([.status] | inside(["OK", "WARNING", "ERROR", "UNKNOWN"])) and
    (.confidence | type == "number") and
    (.confidence == (.confidence | floor)) and
    (.confidence >= 0 and .confidence <= 100) and
    (.facts | type == "object") and
    (.warnings | type == "array") and
    (.errors | type == "array")
' "$tmp_file" >/dev/null

chmod 640 "$tmp_file"
mv -f -- "$tmp_file" "$target"
trap - EXIT

printf '%s\n' "$target"
