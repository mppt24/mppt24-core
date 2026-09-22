#!/usr/bin/env bash

set -euo pipefail

ROOT="$(
    cd "$(
        dirname "${BASH_SOURCE[0]}"
    )/.." &&
    pwd
)"

readonly ROOT

readonly RUNNER_STATE_ROOT="${MPPT24_RUNNER_STATE_ROOT:-/var/lib/mppt24-runner}"

readonly RUNNER_RUNTIME_ROOT="${MPPT24_RUNNER_RUNTIME_ROOT:-/run/mppt24-runner}"

readonly PIPELINE_STATE_ROOT="${MPPT24_PIPELINE_STATE_ROOT:-/var/lib/mppt24-pipeline}"

readonly VALIDATOR="$ROOT/core/validate-report.py"
readonly RUNNER="$ROOT/runner/observer-runner.py"
readonly HISTORIAN="$ROOT/historian/historian.sh"
readonly DECISION="$ROOT/decision/decision-engine.py"

fail() {
    printf 'PIPELINE_ERROR=%s\n' "$1" >&2
    exit 1
}

validate_report() {
    local module="$1"
    local path="$2"

    /usr/bin/python3 \
        -I \
        "$VALIDATOR" \
        --expected-module "$module" \
        --max-bytes 262144 \
        --max-depth 32 \
        "$path"
}

for path in \
    "$RUNNER_STATE_ROOT" \
    "$RUNNER_RUNTIME_ROOT" \
    "$PIPELINE_STATE_ROOT"
do
    [[ "$path" == /* ]] \
        || fail "path_not_absolute"
done

for dependency in \
    /usr/bin/python3 \
    /usr/bin/jq \
    /usr/bin/git \
    /usr/bin/bash
do
    [[ -x "$dependency" ]] \
        || fail "dependency_unavailable"
done

[[ -x "$RUNNER" ]] \
    || fail "runner_unavailable"

[[ -x "$HISTORIAN" ]] \
    || fail "historian_unavailable"

[[ -x "$DECISION" ]] \
    || fail "decision_engine_unavailable"

[[ -f "$VALIDATOR" ]] \
    || fail "validator_unavailable"

[[ -d "$RUNNER_STATE_ROOT" ]] \
    || fail "runner_state_unavailable"

[[ -d "$RUNNER_STATE_ROOT/generations" ]] \
    || fail "generations_unavailable"

[[ -d "$RUNNER_RUNTIME_ROOT" ]] \
    || fail "runner_runtime_unavailable"

[[ -d "$PIPELINE_STATE_ROOT" ]] \
    || fail "pipeline_state_unavailable"

if [[ -n "$(
    /usr/bin/git \
        -C "$ROOT" \
        status \
        --porcelain \
        --untracked-files=no
)" ]]
then
    fail "versioned_worktree_dirty"
fi

/usr/bin/install \
    -d \
    -m 0750 \
    "$PIPELINE_STATE_ROOT/runs"

run_id="$(
    /usr/bin/date \
        -u \
        +'%Y%m%dT%H%M%S%NZ'
)-$$"

run_dir="$PIPELINE_STATE_ROOT/runs/$run_id"

/usr/bin/install \
    -d \
    -m 0750 \
    "$run_dir"

runner_report="$run_dir/runner.json"
runner_stderr="$run_dir/runner.stderr"
historian_report="$run_dir/historian.json"
historian_stderr="$run_dir/historian.stderr"
decision_report="$run_dir/decision.json"
decision_stderr="$run_dir/decision.stderr"
pipeline_report="$run_dir/pipeline.json"

set +e

/usr/bin/python3 \
    -B \
    -I \
    "$RUNNER" \
    --state-root "$RUNNER_STATE_ROOT" \
    --runtime-root "$RUNNER_RUNTIME_ROOT" \
    >"$runner_report" \
    2>"$runner_stderr"

runner_exit=$?

set -e

if [[ -s "$runner_report" ]]
then
    validate_report \
        observer-runner \
        "$runner_report"
fi

if [[ "$runner_exit" -ne 0 ]]
then
    printf 'RUN_ID=%s\n' "$run_id"
    printf 'RUN_DIR=%s\n' "$run_dir"
    printf 'RUNNER_EXIT=%s\n' "$runner_exit"
    fail "runner_failed"
fi

[[ -s "$runner_report" ]] \
    || fail "runner_report_absent"

[[ ! -s "$runner_stderr" ]] \
    || fail "runner_stderr_not_empty"

/usr/bin/jq -e '
    .module == "observer-runner"
    and .version == "2.0.0"
    and .status == "OK"
    and .confidence == 100
    and .facts.result_code == "SUCCESS"
    and .facts.generation_state == "COMPLETE"
    and .facts.declared == 7
    and .facts.successful == 7
    and .facts.failed == 0
    and .facts.reports_written == 7
    and .facts.generation_promoted == true
    and .facts.current_generation_updated == true
' \
    "$runner_report" \
    >/dev/null \
    || fail "runner_report_invalid"

generation="$(
    /usr/bin/jq \
        -er \
        '.facts.generation_id' \
        "$runner_report"
)"

current="$(
    /usr/bin/cat \
        "$RUNNER_STATE_ROOT/current-generation"
)"

[[ "$current" == "$generation" ]] \
    || fail "current_generation_mismatch"

generation_root="$RUNNER_STATE_ROOT/generations/$generation"
reports="$generation_root/observers"

[[ -d "$generation_root" ]] \
    || fail "generation_unavailable"

[[ -f "$generation_root/manifest.json" ]] \
    || fail "manifest_unavailable"

[[ -d "$reports" ]] \
    || fail "observer_reports_unavailable"

/usr/bin/jq -e \
    --arg generation "$generation" '
    .manifest_version == "1.0.0"
    and .generation_id == $generation
    and .state == "COMPLETE"
    and .summary.declared == 7
    and .summary.successful == 7
    and .summary.failed == 0
    and .summary.reports_written == 7
    and .runner.module == "observer-runner"
    and .runner.version == "2.0.0"
' \
    "$generation_root/manifest.json" \
    >/dev/null \
    || fail "manifest_invalid"

[[ "$(
    /usr/bin/find \
        "$reports" \
        -maxdepth 1 \
        -type f \
        -name 'observer-*.json' \
        | /usr/bin/wc -l
)" -eq 7 ]] \
    || fail "observer_report_count_invalid"

set +e

MPPT24_REPORT_DIR="$reports" \
    /usr/bin/bash \
    "$HISTORIAN" \
    >"$historian_report" \
    2>"$historian_stderr"

historian_exit=$?

set -e

[[ "$historian_exit" -eq 0 ]] \
    || fail "historian_failed"

[[ -s "$historian_report" ]] \
    || fail "historian_report_absent"

[[ ! -s "$historian_stderr" ]] \
    || fail "historian_stderr_not_empty"

validate_report \
    historian \
    "$historian_report"

/usr/bin/jq -e '
    .module == "historian"
    and .version == "2.0.0"
    and .status == "OK"
    and .confidence == 100
    and .facts.observer_reports == 7
' \
    "$historian_report" \
    >/dev/null \
    || fail "historian_report_invalid"

set +e

/usr/bin/python3 \
    -I \
    "$DECISION" \
    --state-root "$RUNNER_STATE_ROOT" \
    >"$decision_report" \
    2>"$decision_stderr"

decision_exit=$?

set -e

[[ "$decision_exit" -eq 0 ]] \
    || fail "decision_engine_failed"

[[ -s "$decision_report" ]] \
    || fail "decision_report_absent"

[[ ! -s "$decision_stderr" ]] \
    || fail "decision_stderr_not_empty"

validate_report \
    decision-engine \
    "$decision_report"

/usr/bin/jq -e '
    .module == "decision-engine"
    and .version == "3.0.0"
    and .confidence == 100
    and .facts.observer_reports == 7
    and (
        .facts.ok
        + .facts.warning
        + .facts.error
        + .facts.unknown
    ) == 7
' \
    "$decision_report" \
    >/dev/null \
    || fail "decision_report_invalid"

timestamp="$(
    /usr/bin/date \
        -u \
        +'%Y-%m-%dT%H:%M:%S%z'
)"

/usr/bin/jq \
    -n \
    --arg timestamp "$timestamp" \
    --arg run_id "$run_id" \
    --arg generation_id "$generation" \
    --arg runner_status "$(
        /usr/bin/jq -r '.status' "$runner_report"
    )" \
    --arg historian_status "$(
        /usr/bin/jq -r '.status' "$historian_report"
    )" \
    --arg decision_status "$(
        /usr/bin/jq -r '.status' "$decision_report"
    )" \
    '{
        timestamp: $timestamp,
        run_id: $run_id,
        generation_id: $generation_id,
        status: "OK",
        runner: {
            status: $runner_status
        },
        historian: {
            status: $historian_status
        },
        decision_engine: {
            status: $decision_status
        }
    }' \
    >"$pipeline_report"

chmod \
    0640 \
    "$runner_report" \
    "$runner_stderr" \
    "$historian_report" \
    "$historian_stderr" \
    "$decision_report" \
    "$decision_stderr" \
    "$pipeline_report"

printf 'PIPELINE_RESULT=SUCCESS\n'
printf 'RUN_ID=%s\n' "$run_id"
printf 'GENERATION_ID=%s\n' "$generation"
printf 'RUN_DIR=%s\n' "$run_dir"
printf 'PIPELINE_REPORT=%s\n' "$pipeline_report"
