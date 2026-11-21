#!/usr/bin/env bash
set -uo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." || exit 1
shopt -s nullglob
suites=(tests/*-contract-test.py tests/*-contract-test.sh)

if (( ${#suites[@]} == 0 )); then
    printf '%s\n' "Nenhuma suite de contrato encontrada." >&2
    exit 1
fi

failed=0
for suite in "${suites[@]}"; do
    printf '\n%s\n' "$suite"
    case "$suite" in
        *.py) /usr/bin/python3 -I "$suite" || ((++failed)) ;;
        *.sh) bash "$suite" || ((++failed)) ;;
    esac
done

printf '\nSuites: %d; falhas: %d\n' "${#suites[@]}" "$failed"
(( failed == 0 ))
