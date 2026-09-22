#!/usr/bin/python3 -I
"""
MPPT24 CORE
Capturador de Observers autorizado por registo, contrato 1.0.0.
"""

import argparse
import contextlib
import ctypes
import errno
import importlib.util
import io
import json
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Sequence

sys.dont_write_bytecode = True

CAPTURE_CONTRACT = "1.0.0"

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_AUTHORIZATION = 4
EXIT_STAGING = 5
EXIT_EXECUTION = 6
EXIT_VALIDATION = 7
EXIT_PERSISTENCE = 8
EXIT_INTERNAL = 9

REGISTRY_MAX_BYTES = 65536
SCHEMA_MAX_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 65536
DIAGNOSTIC_MESSAGE_LIMIT = 240
TERMINATION_GRACE_SECONDS = 0.5
RENAME_NOREPLACE = 1

EXPECTED_SCHEMA_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)
EXPECTED_REGISTRY_SCHEMA_ID = (
    "urn:mppt24:schema:observer-registry:1.0.0"
)

MODULE_PATTERN = re.compile(
    r"^[a-z0-9]+(-[a-z0-9]+)*$"
)
STAGING_NAME_PATTERN = re.compile(
    r"^\.staging-[A-Za-z0-9][A-Za-z0-9._-]*$"
)
MODULE_DECLARATION = re.compile(
    r'^readonly MODULE_NAME="([^"]+)"$',
    re.MULTILINE,
)
VERSION_DECLARATION = re.compile(
    r'^readonly MODULE_VERSION="([^"]+)"$',
    re.MULTILINE,
)

EXPECTED_MODULES = [
    "observer-cpu",
    "observer-memory",
    "observer-network",
    "observer-services",
    "observer-ssh",
    "observer-storage",
    "observer-system",
]

CONTROLLED_ENVIRONMENT = {
    "PATH": (
        "/usr/local/sbin:/usr/local/bin:"
        "/usr/sbin:/usr/bin:/sbin:/bin"
    ),
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
}


@dataclass
class StagingContext:
    root: Path
    observers: Path
    root_identity: tuple[int, int]
    observers_identity: tuple[int, int]


@dataclass
class ExecutionResult:
    stdout: bytes
    stdout_bytes: int
    stderr_bytes: int
    exit_code: int | None
    duration_ms: int
    failure_code: str | None = None


class CaptureFailure(Exception):
    """Falha prevista pelo contrato do capturador."""

    def __init__(
        self,
        exit_code: int,
        code: str,
        message: str,
        *,
        module: str | None = None,
        observer_exit_code: int | None = None,
        stdout_bytes: int = 0,
        stderr_bytes: int = 0,
        duration_ms: int = 0,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.message = message
        self.module = module
        self.observer_exit_code = observer_exit_code
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes
        self.duration_ms = duration_ms


def fail(
    exit_code: int,
    code: str,
    message: str,
    **details: Any,
) -> NoReturn:
    raise CaptureFailure(
        exit_code,
        code,
        message,
        **details,
    )


def sanitize_diagnostic(value: object) -> str:
    text = str(value)
    sanitized = "".join(
        character
        if character.isprintable() and character not in "\t\r\n"
        else "?"
        for character in text
    )
    return sanitized[:DIAGNOSTIC_MESSAGE_LIMIT]


def emit_diagnostic(
    code: str,
    message: str,
) -> None:
    fields = (
        "ERROR",
        sanitize_diagnostic(code),
        sanitize_diagnostic(message),
    )
    print("\t".join(fields), file=sys.stderr)


def make_result(
    *,
    module: str | None,
    outcome: str,
    code: str,
    observer_exit_code: int | None,
    report: str | None,
    stdout_bytes: int,
    stderr_bytes: int,
    duration_ms: int,
) -> dict[str, object]:
    return {
        "capture_contract": CAPTURE_CONTRACT,
        "module": module,
        "outcome": outcome,
        "code": code,
        "observer_exit_code": observer_exit_code,
        "report": report,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "duration_ms": duration_ms,
    }


def emit_result(document: dict[str, object]) -> None:
    print(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


class ContractArgumentParser(argparse.ArgumentParser):
    """ArgumentParser com falhas controladas."""

    def error(self, message: str) -> NoReturn:
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            message,
        )


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    unique_options = {
        "--help",
        "--staging-dir",
    }
    seen_options = set()

    for token in argv:
        option = token.split("=", 1)[0]

        if option not in unique_options:
            continue

        if option in seen_options:
            fail(
                EXIT_USAGE,
                "USAGE_INVALID",
                "a opção não pode ser repetida",
            )

        seen_options.add(option)

    parser = ContractArgumentParser(
        prog="capture-observer.py",
        description="Capturar um Observer MPPT24 autorizado.",
    )
    parser.add_argument(
        "--staging-dir",
        required=True,
    )
    parser.add_argument(
        "module",
    )

    arguments = parser.parse_args(argv)

    if not MODULE_PATTERN.fullmatch(arguments.module):
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "nome de módulo inválido",
        )

    if not arguments.staging_dir:
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "diretório de staging inválido",
            module=arguments.module,
        )

    return arguments


class DuplicateKeyError(ValueError):
    """Chave JSON repetida."""


class NonFiniteNumberError(ValueError):
    """Número não pertencente a JSON."""


def reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result = {}

    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value

    return result


def reject_non_finite(value: str) -> NoReturn:
    raise NonFiniteNumberError(value)


def parse_json_strict(
    content: bytes,
    description: str,
) -> Any:
    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        DuplicateKeyError,
        NonFiniteNumberError,
        RecursionError,
    ):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} não contém JSON estrito válido",
        )


def secure_read_configuration(
    path: Path,
    maximum_bytes: int,
    description: str,
) -> bytes:
    try:
        path_status = os.lstat(path)
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} indisponível",
        )

    if stat.S_ISLNK(path_status.st_mode):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} não pode ser link simbólico",
        )

    if not stat.S_ISREG(path_status.st_mode):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} não é ficheiro regular",
        )

    if path_status.st_size > maximum_bytes:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} excede o limite",
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        descriptor = os.open(path, flags)
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} não pôde ser aberto",
        )

    try:
        opened_status = os.fstat(descriptor)

        if not stat.S_ISREG(opened_status.st_mode):
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                f"{description} não é ficheiro regular",
            )

        if (
            opened_status.st_dev != path_status.st_dev
            or opened_status.st_ino != path_status.st_ino
        ):
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                f"{description} mudou antes da leitura",
            )

        chunks = []
        total = 0

        while True:
            chunk = os.read(
                descriptor,
                READ_CHUNK_BYTES,
            )

            if not chunk:
                break

            total += len(chunk)

            if total > maximum_bytes:
                fail(
                    EXIT_CONFIGURATION,
                    "REGISTRY_INVALID",
                    f"{description} excede o limite",
                )

            chunks.append(chunk)

        completed_status = os.fstat(descriptor)
    except CaptureFailure:
        raise
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} falhou durante a leitura",
        )
    finally:
        os.close(descriptor)

    stable_fields = (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )

    if any(
        getattr(opened_status, field)
        != getattr(completed_status, field)
        for field in stable_fields
    ):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} mudou durante a leitura",
        )

    content = b"".join(chunks)

    if len(content) != completed_status.st_size:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            f"{description} teve leitura incompleta",
        )

    return content


def load_jsonschema_dependency() -> tuple[Any, Any]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "python3-jsonschema indisponível",
        )

    return Draft202012Validator, SchemaError


def external_references(document: object) -> list[str]:
    external = []
    stack = [document]

    while stack:
        value = stack.pop()

        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"}:
                    if (
                        not isinstance(child, str)
                        or not child.startswith("#")
                    ):
                        external.append(str(child))
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)

    return external


def validate_registry_semantics(
    document: dict[str, Any],
) -> None:
    observers = document["observers"]
    modules = [
        entry["module"]
        for entry in observers
    ]
    executables = [
        entry["executable"]
        for entry in observers
    ]

    if modules != EXPECTED_MODULES:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "lista ou ordem de módulos incompatível",
        )

    if len(modules) != len(set(modules)):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "módulo duplicado",
        )

    if len(executables) != len(set(executables)):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "executável duplicado",
        )

    for entry in observers:
        module = entry["module"]
        executable = entry["executable"]
        path = PurePosixPath(executable)

        if path.is_absolute():
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "caminho absoluto no registo",
            )

        expected = f"observer/{module}.sh"

        if executable != expected:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "módulo e executável divergentes",
            )

        if entry["required"] is not True:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "Observer não obrigatório",
            )

        if entry["module_versions"] != ["1.0.0"]:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "versão de módulo incompatível",
            )

        if entry["output_contract"] != document["report_contract"]:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "contrato de saída incompatível",
            )


def load_registry(
    project_root: Path,
) -> dict[str, Any]:
    validator_class, schema_error_class = (
        load_jsonschema_dependency()
    )

    schema_path = (
        project_root
        / "schemas"
        / "observer-registry"
        / "1.0.0"
        / "observer-registry.schema.json"
    )
    registry_path = (
        project_root
        / "config"
        / "observer-registry.json"
    )

    schema_content = secure_read_configuration(
        schema_path,
        SCHEMA_MAX_BYTES,
        "schema do registo",
    )
    registry_content = secure_read_configuration(
        registry_path,
        REGISTRY_MAX_BYTES,
        "registo",
    )

    schema = parse_json_strict(
        schema_content,
        "schema do registo",
    )
    registry = parse_json_strict(
        registry_content,
        "registo",
    )

    if (
        not isinstance(schema, dict)
        or schema.get("$schema") != EXPECTED_SCHEMA_DIALECT
        or schema.get("$id") != EXPECTED_REGISTRY_SCHEMA_ID
    ):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "identidade ou dialecto do schema inválido",
        )

    if external_references(schema):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "schema do registo contém referência externa",
        )

    try:
        validator_class.check_schema(schema)
    except schema_error_class:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "schema do registo inválido",
        )

    errors = list(
        validator_class(schema).iter_errors(registry)
    )

    if errors:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registo viola o schema",
        )

    if not isinstance(registry, dict):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registo não é objeto",
        )

    validate_registry_semantics(registry)

    return registry


def select_registry_entry(
    registry: dict[str, Any],
    module: str,
) -> dict[str, Any]:
    matches = [
        entry
        for entry in registry["observers"]
        if entry["module"] == module
    ]

    if len(matches) != 1:
        fail(
            EXIT_AUTHORIZATION,
            "MODULE_NOT_AUTHORIZED",
            "módulo não autorizado",
            module=module,
        )

    return matches[0]


def read_and_validate_executable(
    project_root: Path,
    entry: dict[str, Any],
) -> Path:
    module = entry["module"]
    observer_directory = project_root / "observer"
    executable = project_root / entry["executable"]

    try:
        directory_status = os.lstat(observer_directory)
    except OSError:
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_MISSING",
            "diretório de Observers ausente",
            module=module,
        )

    if (
        stat.S_ISLNK(directory_status.st_mode)
        or not stat.S_ISDIR(directory_status.st_mode)
    ):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "diretório de Observers inseguro",
            module=module,
        )

    try:
        executable_status = os.lstat(executable)
    except FileNotFoundError:
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_MISSING",
            "executável registado ausente",
            module=module,
        )
    except OSError:
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável registado inacessível",
            module=module,
        )

    if stat.S_ISLNK(executable_status.st_mode):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável não pode ser link simbólico",
            module=module,
        )

    if not stat.S_ISREG(executable_status.st_mode):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável não é ficheiro regular",
            module=module,
        )

    if not os.access(executable, os.X_OK):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "ficheiro não executável",
            module=module,
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        descriptor = os.open(executable, flags)
    except OSError:
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável não pôde ser aberto",
            module=module,
        )

    try:
        opened_status = os.fstat(descriptor)

        if (
            opened_status.st_dev != executable_status.st_dev
            or opened_status.st_ino != executable_status.st_ino
        ):
            fail(
                EXIT_AUTHORIZATION,
                "EXECUTABLE_INVALID",
                "executável mudou antes da leitura",
                module=module,
            )

        content = bytearray()

        while True:
            chunk = os.read(
                descriptor,
                READ_CHUNK_BYTES,
            )

            if not chunk:
                break

            content.extend(chunk)

            if len(content) > SCHEMA_MAX_BYTES:
                fail(
                    EXIT_AUTHORIZATION,
                    "EXECUTABLE_INVALID",
                    "executável excede o limite de inspeção",
                    module=module,
                )

        completed_status = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    if (
        opened_status.st_size != completed_status.st_size
        or opened_status.st_mtime_ns
        != completed_status.st_mtime_ns
        or opened_status.st_ctime_ns
        != completed_status.st_ctime_ns
    ):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável mudou durante a leitura",
            module=module,
        )

    try:
        source = bytes(content).decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "executável não contém UTF-8 válido",
            module=module,
        )

    module_match = MODULE_DECLARATION.search(source)
    version_match = VERSION_DECLARATION.search(source)

    if (
        module_match is None
        or module_match.group(1) != module
    ):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "identidade declarada divergente",
            module=module,
        )

    if (
        version_match is None
        or version_match.group(1)
        not in entry["module_versions"]
    ):
        fail(
            EXIT_AUTHORIZATION,
            "EXECUTABLE_INVALID",
            "versão declarada divergente",
            module=module,
        )

    return executable


def ensure_no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)

    for component in path.parts[1:]:
        current = current / component

        try:
            current_status = os.lstat(current)
        except OSError:
            fail(
                EXIT_STAGING,
                "STAGING_INVALID",
                "componente de staging indisponível",
            )

        if stat.S_ISLNK(current_status.st_mode):
            fail(
                EXIT_STAGING,
                "STAGING_INVALID",
                "staging atravessa link simbólico",
            )


def validate_staging(
    value: str,
    module: str,
) -> StagingContext:
    staging = Path(value)

    if not staging.is_absolute():
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "staging deve usar caminho absoluto",
            module=module,
        )

    if not STAGING_NAME_PATTERN.fullmatch(staging.name):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "nome de staging inválido",
            module=module,
        )

    ensure_no_symlink_components(staging)

    try:
        staging_status = os.lstat(staging)
    except OSError:
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "staging inexistente",
            module=module,
        )

    if (
        stat.S_ISLNK(staging_status.st_mode)
        or not stat.S_ISDIR(staging_status.st_mode)
    ):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "staging não é diretório seguro",
            module=module,
        )

    observers = staging / "observers"

    try:
        observers_status = os.lstat(observers)
    except OSError:
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "subdiretório observers ausente",
            module=module,
        )

    if (
        stat.S_ISLNK(observers_status.st_mode)
        or not stat.S_ISDIR(observers_status.st_mode)
    ):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "subdiretório observers inseguro",
            module=module,
        )

    if not os.access(observers, os.W_OK | os.X_OK):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "subdiretório observers sem acesso",
            module=module,
        )

    destination = observers / f"{module}.json"

    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    except OSError:
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "destino não pôde ser examinado",
            module=module,
        )
    else:
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "destino já existe",
            module=module,
        )

    return StagingContext(
        root=staging,
        observers=observers,
        root_identity=(
            staging_status.st_dev,
            staging_status.st_ino,
        ),
        observers_identity=(
            observers_status.st_dev,
            observers_status.st_ino,
        ),
    )


def process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def terminate_process_group(
    process: subprocess.Popen[bytes],
) -> None:
    process_group = process.pid

    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass

    deadline = (
        time.monotonic()
        + TERMINATION_GRACE_SECONDS
    )

    while (
        time.monotonic() < deadline
        and process_group_exists(process_group)
    ):
        time.sleep(0.01)

    if process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        process.wait(
            timeout=TERMINATION_GRACE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait()


def execute_observer(
    executable: Path,
    limits: dict[str, int],
    module: str,
) -> ExecutionResult:
    started_ns = time.monotonic_ns()
    previous_umask = os.umask(0o027)

    try:
        try:
            process = subprocess.Popen(
                [str(executable)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=executable.parent.parent,
                env=CONTROLLED_ENVIRONMENT,
                close_fds=True,
                start_new_session=True,
            )
        except OSError:
            duration_ms = (
                time.monotonic_ns() - started_ns
            ) // 1_000_000
            fail(
                EXIT_EXECUTION,
                "EXECUTION_FAILED",
                "não foi possível iniciar o Observer",
                module=module,
                duration_ms=duration_ms,
            )
    finally:
        os.umask(previous_umask)

    if process.stdout is None or process.stderr is None:
        terminate_process_group(process)
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "pipes do Observer indisponíveis",
            module=module,
        )

    stdout_buffer = bytearray()
    stdout_bytes = 0
    stderr_bytes = 0
    failure_code = None

    stream_selector = selectors.DefaultSelector()
    streams = {
        process.stdout.fileno(): (
            "stdout",
            process.stdout,
        ),
        process.stderr.fileno(): (
            "stderr",
            process.stderr,
        ),
    }

    for descriptor, (
        stream_name,
        stream,
    ) in streams.items():
        os.set_blocking(descriptor, False)
        stream_selector.register(
            descriptor,
            selectors.EVENT_READ,
            data=stream_name,
        )

    timeout_seconds = limits[
        "observer_timeout_seconds"
    ]
    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    try:
        while stream_selector.get_map():
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                failure_code = "EXECUTION_TIMEOUT"
                break

            events = stream_selector.select(
                min(0.1, remaining)
            )

            for key, _mask in events:
                descriptor = key.fd
                stream_name = key.data

                try:
                    chunk = os.read(
                        descriptor,
                        READ_CHUNK_BYTES,
                    )
                except BlockingIOError:
                    continue

                if not chunk:
                    stream_selector.unregister(
                        descriptor
                    )
                    continue

                if stream_name == "stdout":
                    stdout_bytes += len(chunk)

                    available = (
                        limits["stdout_max_bytes"]
                        + 1
                        - len(stdout_buffer)
                    )

                    if available > 0:
                        stdout_buffer.extend(
                            chunk[:available]
                        )

                    if (
                        stdout_bytes
                        > limits["stdout_max_bytes"]
                    ):
                        failure_code = (
                            "OUTPUT_LIMIT_EXCEEDED"
                        )
                        break
                else:
                    stderr_bytes += len(chunk)

                    if (
                        stderr_bytes
                        > limits["stderr_max_bytes"]
                    ):
                        failure_code = (
                            "STDERR_LIMIT_EXCEEDED"
                        )
                        break

            if failure_code is not None:
                break

        if failure_code is None:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                failure_code = "EXECUTION_TIMEOUT"
            else:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    failure_code = "EXECUTION_TIMEOUT"

        if failure_code is not None:
            terminate_process_group(process)
        else:
            process.wait()
    finally:
        stream_selector.close()
        process.stdout.close()
        process.stderr.close()

    duration_ms = (
        time.monotonic_ns() - started_ns
    ) // 1_000_000

    return ExecutionResult(
        stdout=bytes(stdout_buffer),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        exit_code=process.returncode,
        duration_ms=duration_ms,
        failure_code=failure_code,
    )


def load_report_validator(
    project_root: Path,
) -> Any:
    validator_path = (
        project_root
        / "core"
        / "validate-report.py"
    )

    try:
        path_status = os.lstat(validator_path)
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "validador de relatórios indisponível",
        )

    if (
        stat.S_ISLNK(path_status.st_mode)
        or not stat.S_ISREG(path_status.st_mode)
    ):
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "validador de relatórios inseguro",
        )

    specification = importlib.util.spec_from_file_location(
        "mppt24_validate_report",
        validator_path,
    )

    if (
        specification is None
        or specification.loader is None
    ):
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "validador de relatórios não carregável",
        )

    module = importlib.util.module_from_spec(
        specification
    )

    try:
        specification.loader.exec_module(module)
    except Exception:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "falha ao carregar validador de relatórios",
        )

    return module


def validate_report_candidate(
    project_root: Path,
    content: bytes,
    module_name: str,
    maximum_depth: int,
) -> dict[str, Any]:
    validator_module = load_report_validator(
        project_root
    )

    try:
        validator_class, schema_error_class = (
            validator_module.load_jsonschema_dependency()
        )
        _schema, validator = (
            validator_module.load_schema(
                validator_class,
                schema_error_class,
            )
        )
    except Exception:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "contrato de relatório indisponível",
            module=module_name,
        )

    diagnostics = io.StringIO()

    try:
        with contextlib.redirect_stderr(diagnostics):
            text = validator_module.decode_utf8(
                content,
                "report",
            )
            document = (
                validator_module.parse_json_strict(
                    text,
                    "report",
                )
            )
            validator_module.enforce_depth(
                document,
                maximum_depth,
            )
            validator_module.validate_structure(
                document,
                validator,
            )
            validator_module.validate_semantics(
                document,
                module_name,
            )
    except validator_module.ValidationFailure as error:
        json_codes = {
            "INVALID_UTF8",
            "INVALID_JSON",
            "DUPLICATE_KEY",
            "NON_FINITE_NUMBER",
        }

        if error.code in json_codes:
            result_code = "INVALID_JSON"
        elif error.code == "MODULE_MISMATCH":
            result_code = "MODULE_MISMATCH"
        else:
            result_code = "CONTRACT_VIOLATION"

        fail(
            EXIT_VALIDATION,
            result_code,
            "relatório rejeitado pelo contrato 2.1.0",
            module=module_name,
        )
    except Exception:
        fail(
            EXIT_VALIDATION,
            "CONTRACT_VIOLATION",
            "falha controlada durante a validação",
            module=module_name,
        )

    if not isinstance(document, dict):
        fail(
            EXIT_VALIDATION,
            "CONTRACT_VIOLATION",
            "relatório validado não é objeto",
            module=module_name,
        )

    return document


def load_rename_noreplace() -> Any:
    library = ctypes.CDLL(
        None,
        use_errno=True,
    )

    try:
        renameat2 = library.renameat2
    except AttributeError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "renameat2 indisponível",
        )

    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int

    return renameat2


def rename_noreplace(
    renameat2: Any,
    directory_descriptor: int,
    source_name: str,
    destination_name: str,
    module: str,
) -> None:
    result = renameat2(
        directory_descriptor,
        os.fsencode(source_name),
        directory_descriptor,
        os.fsencode(destination_name),
        RENAME_NOREPLACE,
    )

    if result == 0:
        return

    error_number = ctypes.get_errno()

    if error_number == errno.EEXIST:
        message = "destino passou a existir"
    else:
        message = "publicação atómica falhou"

    fail(
        EXIT_PERSISTENCE,
        "TEMPORARY_PERSISTENCE_FAILED",
        message,
        module=module,
    )


def revalidate_staging(
    staging: StagingContext,
    module: str,
) -> None:
    ensure_no_symlink_components(staging.root)

    try:
        root_status = os.lstat(staging.root)
        observers_status = os.lstat(
            staging.observers
        )
    except OSError:
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "staging mudou antes da persistência",
            module=module,
        )

    root_identity = (
        root_status.st_dev,
        root_status.st_ino,
    )
    observers_identity = (
        observers_status.st_dev,
        observers_status.st_ino,
    )

    if (
        stat.S_ISLNK(root_status.st_mode)
        or not stat.S_ISDIR(root_status.st_mode)
        or root_identity != staging.root_identity
    ):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "raiz de staging mudou",
            module=module,
        )

    if (
        stat.S_ISLNK(observers_status.st_mode)
        or not stat.S_ISDIR(observers_status.st_mode)
        or observers_identity
        != staging.observers_identity
    ):
        fail(
            EXIT_STAGING,
            "STAGING_INVALID",
            "subdiretório observers mudou",
            module=module,
        )


def publish_report(
    staging: StagingContext,
    module: str,
    content: bytes,
    renameat2: Any,
) -> str:
    revalidate_staging(
        staging,
        module,
    )

    directory_flags = os.O_RDONLY
    directory_flags |= getattr(
        os,
        "O_DIRECTORY",
        0,
    )
    directory_flags |= getattr(
        os,
        "O_CLOEXEC",
        0,
    )
    directory_flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    try:
        directory_descriptor = os.open(
            staging.observers,
            directory_flags,
        )
    except OSError:
        fail(
            EXIT_PERSISTENCE,
            "TEMPORARY_PERSISTENCE_FAILED",
            "não foi possível abrir observers",
            module=module,
        )

    temporary_name = None
    temporary_descriptor = None
    destination_name = f"{module}.json"
    published = False

    try:
        directory_status = os.fstat(
            directory_descriptor
        )
        directory_identity = (
            directory_status.st_dev,
            directory_status.st_ino,
        )

        if (
            not stat.S_ISDIR(directory_status.st_mode)
            or directory_identity
            != staging.observers_identity
        ):
            fail(
                EXIT_PERSISTENCE,
                "TEMPORARY_PERSISTENCE_FAILED",
                "descritor de observers divergente",
                module=module,
            )

        try:
            os.stat(
                destination_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            fail(
                EXIT_PERSISTENCE,
                "TEMPORARY_PERSISTENCE_FAILED",
                "destino passou a existir",
                module=module,
            )

        file_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        )
        file_flags |= getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        file_flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        for _attempt in range(16):
            candidate = (
                f".{module}.json.tmp."
                f"{secrets.token_hex(8)}"
            )

            try:
                temporary_descriptor = os.open(
                    candidate,
                    file_flags,
                    0o640,
                    dir_fd=directory_descriptor,
                )
            except FileExistsError:
                continue

            temporary_name = candidate
            break

        if temporary_descriptor is None:
            fail(
                EXIT_PERSISTENCE,
                "TEMPORARY_PERSISTENCE_FAILED",
                "não foi possível criar temporário",
                module=module,
            )

        offset = 0

        while offset < len(content):
            written = os.write(
                temporary_descriptor,
                content[offset:],
            )

            if written <= 0:
                fail(
                    EXIT_PERSISTENCE,
                    "TEMPORARY_PERSISTENCE_FAILED",
                    "escrita temporária incompleta",
                    module=module,
                )

            offset += written

        os.fchmod(
            temporary_descriptor,
            0o640,
        )
        os.fsync(temporary_descriptor)

        temporary_status = os.fstat(
            temporary_descriptor
        )

        if temporary_status.st_size != len(content):
            fail(
                EXIT_PERSISTENCE,
                "TEMPORARY_PERSISTENCE_FAILED",
                "tamanho temporário divergente",
                module=module,
            )

        os.close(temporary_descriptor)
        temporary_descriptor = None

        rename_noreplace(
            renameat2,
            directory_descriptor,
            temporary_name,
            destination_name,
            module,
        )
        published = True
        temporary_name = None

        final_status = os.stat(
            destination_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )

        if (
            not stat.S_ISREG(final_status.st_mode)
            or final_status.st_size != len(content)
            or stat.S_IMODE(final_status.st_mode)
            != 0o640
            or final_status.st_nlink != 1
        ):
            fail(
                EXIT_PERSISTENCE,
                "TEMPORARY_PERSISTENCE_FAILED",
                "relatório publicado inválido",
                module=module,
            )
    except CaptureFailure:
        if published:
            try:
                os.unlink(
                    destination_name,
                    dir_fd=directory_descriptor,
                )
            except OSError:
                pass
        raise
    except OSError:
        if published:
            try:
                os.unlink(
                    destination_name,
                    dir_fd=directory_descriptor,
                )
            except OSError:
                pass

        fail(
            EXIT_PERSISTENCE,
            "TEMPORARY_PERSISTENCE_FAILED",
            "falha durante persistência temporária",
            module=module,
        )
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)

        if temporary_name is not None:
            try:
                os.unlink(
                    temporary_name,
                    dir_fd=directory_descriptor,
                )
            except OSError:
                pass

        os.close(directory_descriptor)

    return f"observers/{destination_name}"


def enrich_failure(
    error: CaptureFailure,
    execution: ExecutionResult,
    module: str,
) -> CaptureFailure:
    error.module = module
    error.observer_exit_code = (
        execution.exit_code
    )
    error.stdout_bytes = (
        execution.stdout_bytes
    )
    error.stderr_bytes = (
        execution.stderr_bytes
    )
    error.duration_ms = (
        execution.duration_ms
    )
    return error


def execute_capture(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    project_root = (
        Path(__file__).resolve().parent.parent
    )
    module = arguments.module

    renameat2 = load_rename_noreplace()
    registry = load_registry(project_root)
    entry = select_registry_entry(
        registry,
        module,
    )
    executable = read_and_validate_executable(
        project_root,
        entry,
    )
    staging = validate_staging(
        arguments.staging_dir,
        module,
    )
    limits = registry["limits"]

    execution = execute_observer(
        executable,
        limits,
        module,
    )

    if execution.failure_code is not None:
        fail(
            EXIT_EXECUTION,
            execution.failure_code,
            "execução interrompida por limite",
            module=module,
            observer_exit_code=execution.exit_code,
            stdout_bytes=execution.stdout_bytes,
            stderr_bytes=execution.stderr_bytes,
            duration_ms=execution.duration_ms,
        )

    if execution.exit_code != 0:
        fail(
            EXIT_EXECUTION,
            "EXECUTION_FAILED",
            "Observer terminou com código não zero",
            module=module,
            observer_exit_code=execution.exit_code,
            stdout_bytes=execution.stdout_bytes,
            stderr_bytes=execution.stderr_bytes,
            duration_ms=execution.duration_ms,
        )

    if execution.stdout_bytes == 0:
        fail(
            EXIT_EXECUTION,
            "EMPTY_REPORT",
            "Observer não produziu relatório",
            module=module,
            observer_exit_code=execution.exit_code,
            stdout_bytes=0,
            stderr_bytes=execution.stderr_bytes,
            duration_ms=execution.duration_ms,
        )

    if (
        execution.stdout_bytes
        > limits["report_max_bytes"]
    ):
        fail(
            EXIT_EXECUTION,
            "OUTPUT_LIMIT_EXCEEDED",
            "relatório excede o limite",
            module=module,
            observer_exit_code=execution.exit_code,
            stdout_bytes=execution.stdout_bytes,
            stderr_bytes=execution.stderr_bytes,
            duration_ms=execution.duration_ms,
        )

    try:
        document = validate_report_candidate(
            project_root,
            execution.stdout,
            module,
            limits["json_max_depth"],
        )
    except CaptureFailure as error:
        raise enrich_failure(
            error,
            execution,
            module,
        )

    if (
        document.get("version")
        not in entry["module_versions"]
    ):
        fail(
            EXIT_VALIDATION,
            "CONTRACT_VIOLATION",
            "versão emitida não é compatível",
            module=module,
            observer_exit_code=execution.exit_code,
            stdout_bytes=execution.stdout_bytes,
            stderr_bytes=execution.stderr_bytes,
            duration_ms=execution.duration_ms,
        )

    try:
        report_path = publish_report(
            staging,
            module,
            execution.stdout,
            renameat2,
        )
    except CaptureFailure as error:
        raise enrich_failure(
            error,
            execution,
            module,
        )

    return make_result(
        module=module,
        outcome="SUCCESS",
        code="SUCCESS",
        observer_exit_code=execution.exit_code,
        report=report_path,
        stdout_bytes=execution.stdout_bytes,
        stderr_bytes=execution.stderr_bytes,
        duration_ms=execution.duration_ms,
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    effective_argv = (
        sys.argv[1:]
        if argv is None
        else argv
    )
    identified_module = None

    try:
        arguments = parse_arguments(
            effective_argv
        )
        identified_module = arguments.module
        result = execute_capture(arguments)
        emit_result(result)
        return EXIT_SUCCESS
    except CaptureFailure as error:
        module = (
            error.module
            if error.module is not None
            else identified_module
        )
        result = make_result(
            module=module,
            outcome="FAILED",
            code=error.code,
            observer_exit_code=(
                error.observer_exit_code
            ),
            report=None,
            stdout_bytes=error.stdout_bytes,
            stderr_bytes=error.stderr_bytes,
            duration_ms=error.duration_ms,
        )
        emit_result(result)
        emit_diagnostic(
            error.code,
            error.message,
        )
        return error.exit_code
    except Exception:
        result = make_result(
            module=identified_module,
            outcome="FAILED",
            code="INTERNAL_ERROR",
            observer_exit_code=None,
            report=None,
            stdout_bytes=0,
            stderr_bytes=0,
            duration_ms=0,
        )
        emit_result(result)
        emit_diagnostic(
            "INTERNAL_ERROR",
            "falha interna inesperada",
        )
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
