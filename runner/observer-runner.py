#!/usr/bin/python3 -I
"""
MPPT24 CORE
Runner de Observers 2.0.0.
"""

import argparse
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, Sequence

sys.dont_write_bytecode = True

RUNNER_MODULE = "observer-runner"
RUNNER_VERSION = "2.0.0"
REPORT_CONTRACT = "2.1.0"
MANIFEST_VERSION = "1.0.0"
REGISTRY_VERSION = "1.0.0"
CAPTURE_CONTRACT = "1.0.0"

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_LOCK_BUSY = 4
EXIT_PARTIAL = 5
EXIT_FAILED = 6
EXIT_STRUCTURAL = 7
EXIT_UNKNOWN = 8
EXIT_INTERNAL = 9

TOTAL_CYCLE_TIMEOUT_SECONDS = 1200
EXTERNAL_TERMINATION_GRACE_SECONDS = 1.0
CAPTURE_RESULT_MAX_BYTES = 65536
CHILD_STDERR_MAX_BYTES = 65536
RUNNER_REPORT_MAX_BYTES = 262144
MANIFEST_MAX_BYTES = 262144
RUNNER_REPORT_MAX_DEPTH = 32
MINIMUM_FREE_BYTES = 16777216

REGISTRY_MAX_BYTES = 65536
SCHEMA_MAX_BYTES = 1024 * 1024
REFERENCE_MAX_BYTES = 256

STATE_ROOT_MAX_MODE = 0o750
RUNTIME_ROOT_MAX_MODE = 0o750
GENERATIONS_MAX_MODE = 0o750
LOCK_MAX_MODE = 0o640
STAGING_MODE = 0o750
STAGING_FILE_MODE = 0o640
PROMOTED_DIRECTORY_MODE = 0o550
PROMOTED_FILE_MODE = 0o440
REFERENCE_MODE = 0o640

LOCK_FILE_NAME = "observer-runner.lock"
GENERATIONS_DIRECTORY_NAME = "generations"
REFERENCE_FILE_NAME = "current-generation"
MANIFEST_FILE_NAME = "manifest.json"
OBSERVERS_DIRECTORY_NAME = "observers"

RENAME_NOREPLACE = 1
AT_FDCWD = -100

GENERATION_ID_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$"
)
MODULE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
)

CONTROL_CHARACTER_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


class RunnerFailure(Exception):
    """Falha contratual controlada."""

    def __init__(
        self,
        exit_code: int,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.message = message


class ContractArgumentParser(
    argparse.ArgumentParser
):
    """ArgumentParser com erro contratual."""

    def error(self, message: str) -> NoReturn:
        raise RunnerFailure(
            EXIT_USAGE,
            "USAGE_INVALID",
            message,
        )


@dataclass
class CycleFacts:
    result_code: str = "INTERNAL_ERROR"
    lock_acquired: bool = False
    cycle_started: bool = False
    generation_id: str | None = None
    generation_state: str | None = None
    declared: int | None = None
    successful: int | None = None
    failed: int | None = None
    reports_written: int | None = None
    successful_modules: list[str] | None = None
    failed_modules: list[str] | None = None
    generation_promoted: bool | None = False
    current_generation_updated: bool | None = False


@dataclass(frozen=True)
class PathIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class SecureContent:
    content: bytes
    identity: PathIdentity
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class InvocationState:
    facts: CycleFacts = field(
        default_factory=CycleFacts
    )
    status: str = "UNKNOWN"
    confidence: int = 0
    summary: list[str] = field(
        default_factory=list
    )
    recommendations: list[str] = field(
        default_factory=list
    )
    warnings: list[str] = field(
        default_factory=list
    )
    errors: list[str] = field(
        default_factory=list
    )


def fail(
    exit_code: int,
    code: str,
    message: str,
) -> NoReturn:
    raise RunnerFailure(
        exit_code,
        code,
        message,
    )


def sanitize_message(value: object) -> str:
    text = str(value)
    text = CONTROL_CHARACTER_PATTERN.sub(
        "?",
        text,
    )
    text = " ".join(text.split())

    if len(text) > 240:
        text = text[:237] + "..."

    return text or "falha controlada"


def parse_arguments(
    argv: Sequence[str],
) -> argparse.Namespace:
    unique_options = {
        "--help",
        "--state-root",
        "--runtime-root",
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
        prog="observer-runner.py",
        description=(
            "Executar um ciclo isolado de "
            "Observers MPPT24."
        ),
    )
    parser.add_argument(
        "--state-root",
        required=True,
    )
    parser.add_argument(
        "--runtime-root",
        required=True,
    )

    arguments = parser.parse_args(argv)

    if not arguments.state_root:
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "STATE_ROOT inválido",
        )

    if not arguments.runtime_root:
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "RUNTIME_ROOT inválido",
        )

    return arguments


class DuplicateKeyError(ValueError):
    """Objeto JSON com chave repetida."""


class NonFiniteNumberError(ValueError):
    """Número não finito proibido."""


def reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    document = {}

    for key, value in pairs:
        if key in document:
            raise DuplicateKeyError(key)

        document[key] = value

    return document


def reject_non_finite(value: str) -> NoReturn:
    raise NonFiniteNumberError(value)


def container_depth(value: object) -> int:
    if isinstance(value, dict):
        if not value:
            return 1

        return 1 + max(
            container_depth(child)
            for child in value.values()
        )

    if isinstance(value, list):
        if not value:
            return 1

        return 1 + max(
            container_depth(child)
            for child in value
        )

    return 0


def parse_json_strict(
    content: bytes,
    *,
    role: str,
    maximum_depth: int,
    exit_code: int,
    failure_code: str,
) -> object:
    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        fail(
            exit_code,
            failure_code,
            f"{role}: UTF-8 inválido",
        )

    try:
        document = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except DuplicateKeyError:
        fail(
            exit_code,
            failure_code,
            f"{role}: chave JSON duplicada",
        )
    except NonFiniteNumberError:
        fail(
            exit_code,
            failure_code,
            f"{role}: número não finito",
        )
    except (
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        fail(
            exit_code,
            failure_code,
            f"{role}: JSON inválido",
        )

    try:
        depth = container_depth(document)
    except RecursionError:
        fail(
            exit_code,
            failure_code,
            f"{role}: profundidade excessiva",
        )

    if depth > maximum_depth:
        fail(
            exit_code,
            failure_code,
            f"{role}: profundidade excessiva",
        )

    return document


def status_signature(
    status_result: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        status_result.st_dev,
        status_result.st_ino,
        status_result.st_size,
        status_result.st_mtime_ns,
        status_result.st_ctime_ns,
    )


def path_identity(
    status_result: os.stat_result,
) -> PathIdentity:
    return PathIdentity(
        device=status_result.st_dev,
        inode=status_result.st_ino,
    )


def secure_read_file(
    path: Path,
    maximum_bytes: int,
    *,
    role: str,
    exit_code: int,
    missing_code: str,
    unsafe_code: str,
) -> SecureContent:
    try:
        path_status = os.lstat(path)
    except FileNotFoundError:
        fail(
            exit_code,
            missing_code,
            f"{role}: ficheiro ausente",
        )
    except OSError:
        fail(
            exit_code,
            unsafe_code,
            f"{role}: estado indisponível",
        )

    if (
        stat.S_ISLNK(path_status.st_mode)
        or not stat.S_ISREG(
            path_status.st_mode
        )
        or path_status.st_nlink != 1
    ):
        fail(
            exit_code,
            unsafe_code,
            f"{role}: ficheiro inseguro",
        )

    if (
        path_status.st_size < 0
        or path_status.st_size > maximum_bytes
    ):
        fail(
            exit_code,
            unsafe_code,
            f"{role}: tamanho inválido",
        )

    flags = os.O_RDONLY

    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(
            path,
            flags,
        )
    except OSError:
        fail(
            exit_code,
            unsafe_code,
            f"{role}: abertura recusada",
        )

    try:
        before_status = os.fstat(
            descriptor
        )

        if (
            not stat.S_ISREG(
                before_status.st_mode
            )
            or before_status.st_nlink != 1
            or status_signature(
                before_status
            ) != status_signature(
                path_status
            )
        ):
            fail(
                exit_code,
                unsafe_code,
                f"{role}: identidade divergente",
            )

        chunks = []
        total = 0

        while True:
            try:
                chunk = os.read(
                    descriptor,
                    min(
                        65536,
                        maximum_bytes
                        + 1
                        - total,
                    ),
                )
            except OSError:
                fail(
                    exit_code,
                    unsafe_code,
                    f"{role}: leitura falhou",
                )

            if not chunk:
                break

            chunks.append(chunk)
            total += len(chunk)

            if total > maximum_bytes:
                fail(
                    exit_code,
                    unsafe_code,
                    f"{role}: tamanho excedido",
                )

        after_status = os.fstat(
            descriptor
        )
    finally:
        os.close(descriptor)

    try:
        final_status = os.lstat(path)
    except OSError:
        fail(
            exit_code,
            unsafe_code,
            f"{role}: ficheiro mudou",
        )

    expected_signature = status_signature(
        before_status
    )

    if (
        status_signature(after_status)
        != expected_signature
        or status_signature(final_status)
        != expected_signature
        or stat.S_ISLNK(final_status.st_mode)
        or not stat.S_ISREG(
            final_status.st_mode
        )
        or final_status.st_nlink != 1
    ):
        fail(
            exit_code,
            unsafe_code,
            f"{role}: ficheiro mudou",
        )

    content = b"".join(chunks)

    if len(content) != before_status.st_size:
        fail(
            exit_code,
            unsafe_code,
            f"{role}: tamanho mudou",
        )

    return SecureContent(
        content=content,
        identity=path_identity(
            before_status
        ),
        size=before_status.st_size,
        mtime_ns=before_status.st_mtime_ns,
        ctime_ns=before_status.st_ctime_ns,
    )


def revalidate_secure_file(
    path: Path,
    secure: SecureContent,
    *,
    role: str,
    exit_code: int,
    failure_code: str,
) -> None:
    try:
        current_status = os.lstat(path)
    except OSError:
        fail(
            exit_code,
            failure_code,
            f"{role}: ficheiro indisponível",
        )

    expected = (
        secure.identity.device,
        secure.identity.inode,
        secure.size,
        secure.mtime_ns,
        secure.ctime_ns,
    )

    if (
        stat.S_ISLNK(current_status.st_mode)
        or not stat.S_ISREG(
            current_status.st_mode
        )
        or current_status.st_nlink != 1
        or status_signature(
            current_status
        ) != expected
    ):
        fail(
            exit_code,
            failure_code,
            f"{role}: identidade alterada",
        )


SCHEMA_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)
REGISTRY_SCHEMA_ID = (
    "urn:mppt24:schema:observer-registry:1.0.0"
)
CAPTURE_SCHEMA_ID = (
    "urn:mppt24:schema:capture-result:1.0.0"
)
REPORT_SCHEMA_ID = (
    "urn:mppt24:schema:report:2.1.0"
)
CONFIGURATION_JSON_MAX_DEPTH = 64


@dataclass(frozen=True)
class SchemaContext:
    path: Path
    document: dict[str, Any]
    secure: SecureContent
    validator: Any


@dataclass(frozen=True)
class RegistryContext:
    path: Path
    document: dict[str, Any]
    secure: SecureContent
    sha256: str


@dataclass(frozen=True)
class ConfigurationContext:
    validator_class: Any
    registry_schema: SchemaContext
    capture_schema: SchemaContext
    report_schema: SchemaContext
    registry: RegistryContext


def load_jsonschema_dependency() -> Any:
    try:
        from jsonschema import (
            Draft202012Validator,
        )
    except ImportError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "python3-jsonschema indisponível",
        )

    return Draft202012Validator


def external_references(
    document: object,
) -> list[str]:
    references = []
    stack = [document]

    while stack:
        value = stack.pop()

        if isinstance(value, dict):
            for key, child in value.items():
                if key in {
                    "$ref",
                    "$dynamicRef",
                }:
                    if (
                        not isinstance(child, str)
                        or not child.startswith("#")
                    ):
                        references.append(
                            str(child)
                        )

                stack.append(child)

        elif isinstance(value, list):
            stack.extend(value)

    return references


def schema_errors(
    validator: Any,
    document: object,
) -> list[Any]:
    return sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(
                str(component)
                for component
                in error.absolute_path
            ),
            str(error.validator),
        ),
    )


def load_schema(
    validator_class: Any,
    path: Path,
    *,
    role: str,
    expected_identifier: str,
) -> SchemaContext:
    secure = secure_read_file(
        path,
        SCHEMA_MAX_BYTES,
        role=role,
        exit_code=EXIT_CONFIGURATION,
        missing_code="DEPENDENCY_UNAVAILABLE",
        unsafe_code="CONFIGURATION_INVALID",
    )
    document = parse_json_strict(
        secure.content,
        role=role,
        maximum_depth=(
            CONFIGURATION_JSON_MAX_DEPTH
        ),
        exit_code=EXIT_CONFIGURATION,
        failure_code="CONFIGURATION_INVALID",
    )

    if not isinstance(document, dict):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: schema não é objeto",
        )

    if document.get("$schema") != SCHEMA_DIALECT:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: dialecto incompatível",
        )

    if document.get("$id") != expected_identifier:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: identidade incompatível",
        )

    if external_references(document):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: referência externa proibida",
        )

    try:
        validator_class.check_schema(
            document
        )
        validator = validator_class(
            document
        )
    except Exception:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: schema inválido",
        )

    return SchemaContext(
        path=path,
        document=document,
        secure=secure,
        validator=validator,
    )


def validate_registry_semantics(
    document: dict[str, Any],
) -> None:
    if (
        document.get("registry_version")
        != REGISTRY_VERSION
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "registo: versão incompatível",
        )

    limits = document.get("limits")
    observers = document.get("observers")

    if (
        not isinstance(limits, dict)
        or not isinstance(observers, list)
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "registo: estrutura inválida",
        )

    maximum = limits.get("max_observers")

    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum <= 0
        or not observers
        or len(observers) > maximum
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "registo: número de módulos inválido",
        )

    modules = set()
    executables = set()

    for entry in observers:
        if not isinstance(entry, dict):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: entrada inválida",
            )

        module = entry.get("module")
        executable = entry.get("executable")
        required = entry.get("required")
        versions = entry.get(
            "module_versions"
        )
        output_contract = entry.get(
            "output_contract"
        )

        if (
            not isinstance(module, str)
            or not MODULE_PATTERN.fullmatch(
                module
            )
            or module in modules
        ):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: módulo inválido",
            )

        expected_executable = (
            f"observer/{module}.sh"
        )

        if (
            executable != expected_executable
            or executable in executables
        ):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: executável inválido",
            )

        if not isinstance(required, bool):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: required inválido",
            )

        if (
            not isinstance(versions, list)
            or not versions
            or not all(
                isinstance(version, str)
                for version in versions
            )
        ):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: versões inválidas",
            )

        if output_contract != REPORT_CONTRACT:
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "registo: contrato incompatível",
            )

        modules.add(module)
        executables.add(executable)


def load_registry(
    path: Path,
    schema: SchemaContext,
) -> RegistryContext:
    secure = secure_read_file(
        path,
        REGISTRY_MAX_BYTES,
        role="registo",
        exit_code=EXIT_CONFIGURATION,
        missing_code="DEPENDENCY_UNAVAILABLE",
        unsafe_code="CONFIGURATION_INVALID",
    )
    document = parse_json_strict(
        secure.content,
        role="registo",
        maximum_depth=(
            CONFIGURATION_JSON_MAX_DEPTH
        ),
        exit_code=EXIT_CONFIGURATION,
        failure_code="CONFIGURATION_INVALID",
    )

    if not isinstance(document, dict):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "registo: documento não é objeto",
        )

    if schema_errors(
        schema.validator,
        document,
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "registo: violação do schema",
        )

    validate_registry_semantics(document)

    return RegistryContext(
        path=path,
        document=document,
        secure=secure,
        sha256=hashlib.sha256(
            secure.content
        ).hexdigest(),
    )


def load_configuration(
    project_root: Path,
) -> ConfigurationContext:
    validator_class = (
        load_jsonschema_dependency()
    )

    registry_schema = load_schema(
        validator_class,
        (
            project_root
            / "schemas"
            / "observer-registry"
            / "1.0.0"
            / "observer-registry.schema.json"
        ),
        role="schema do registo",
        expected_identifier=(
            REGISTRY_SCHEMA_ID
        ),
    )
    capture_schema = load_schema(
        validator_class,
        (
            project_root
            / "schemas"
            / "capture-result"
            / "1.0.0"
            / "capture-result.schema.json"
        ),
        role="schema do resultado",
        expected_identifier=(
            CAPTURE_SCHEMA_ID
        ),
    )
    report_schema = load_schema(
        validator_class,
        (
            project_root
            / "schemas"
            / "report"
            / "2.1.0"
            / "report.schema.json"
        ),
        role="schema do relatório",
        expected_identifier=(
            REPORT_SCHEMA_ID
        ),
    )
    registry = load_registry(
        (
            project_root
            / "config"
            / "observer-registry.json"
        ),
        registry_schema,
    )

    return ConfigurationContext(
        validator_class=validator_class,
        registry_schema=registry_schema,
        capture_schema=capture_schema,
        report_schema=report_schema,
        registry=registry,
    )


def revalidate_configuration(
    context: ConfigurationContext,
) -> None:
    revalidate_secure_file(
        context.registry.path,
        context.registry.secure,
        role="registo",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    for schema in (
        context.registry_schema,
        context.capture_schema,
        context.report_schema,
    ):
        revalidate_secure_file(
            schema.path,
            schema.secure,
            role="schema",
            exit_code=EXIT_STRUCTURAL,
            failure_code=(
                "STRUCTURAL_FAILURE"
            ),
        )


@dataclass(frozen=True)
class DirectoryContext:
    path: Path
    identity: PathIdentity
    mode: int


@dataclass(frozen=True)
class ReferenceContext:
    path: Path
    secure: SecureContent
    generation_id: str
    generation_path: Path


@dataclass(frozen=True)
class RootsContext:
    state: DirectoryContext
    runtime: DirectoryContext
    generations: DirectoryContext
    reference: ReferenceContext | None


def mode_exceeds(
    status_result: os.stat_result,
    maximum: int,
) -> bool:
    mode = stat.S_IMODE(
        status_result.st_mode
    )
    return bool(mode & ~maximum)


def ensure_absolute_clean_path(
    value: str,
    *,
    role: str,
) -> Path:
    path = Path(value)

    if not path.is_absolute():
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: caminho não é absoluto",
        )

    if ".." in path.parts:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: componente proibido",
        )

    normalized = Path(
        os.path.normpath(str(path))
    )

    if not normalized.is_absolute():
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: caminho inválido",
        )

    return normalized


def ensure_no_symlink_components(
    path: Path,
    *,
    role: str,
) -> None:
    current = Path(path.anchor)

    for component in path.parts[1:]:
        current = current / component

        try:
            current_status = os.lstat(
                current
            )
        except OSError:
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                f"{role}: componente indisponível",
            )

        if stat.S_ISLNK(
            current_status.st_mode
        ):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                f"{role}: link simbólico proibido",
            )


def validate_owned_directory(
    path: Path,
    *,
    role: str,
    maximum_mode: int,
    require_owner_write: bool,
) -> DirectoryContext:
    try:
        status_result = os.lstat(path)
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: diretório indisponível",
        )

    if (
        stat.S_ISLNK(status_result.st_mode)
        or not stat.S_ISDIR(
            status_result.st_mode
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: não é diretório seguro",
        )

    if status_result.st_uid != os.geteuid():
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: proprietário divergente",
        )

    if mode_exceeds(
        status_result,
        maximum_mode,
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: permissões excessivas",
        )

    mode = stat.S_IMODE(
        status_result.st_mode
    )
    required = (
        stat.S_IRUSR
        | stat.S_IXUSR
    )

    if require_owner_write:
        required |= stat.S_IWUSR

    if mode & required != required:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: permissões insuficientes",
        )

    return DirectoryContext(
        path=path,
        identity=path_identity(
            status_result
        ),
        mode=mode,
    )


def paths_overlap(
    first: Path,
    second: Path,
) -> bool:
    try:
        common = Path(
            os.path.commonpath(
                [
                    str(first),
                    str(second),
                ]
            )
        )
    except ValueError:
        return False

    return common in {
        first,
        second,
    }


def directory_entry_names(
    path: Path,
    *,
    role: str,
) -> set[str]:
    try:
        with os.scandir(path) as entries:
            return {
                entry.name
                for entry in entries
            }
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            f"{role}: enumeração falhou",
        )


def parse_generation_identifier(
    value: str,
) -> datetime:
    if not GENERATION_ID_PATTERN.fullmatch(
        value
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "generation_id inválido",
        )

    timestamp = value.split("-", 1)[0]

    try:
        parsed = datetime.strptime(
            timestamp,
            "%Y%m%dT%H%M%S%fZ",
        )
    except ValueError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "generation_id impossível",
        )

    return parsed.replace(
        tzinfo=timezone.utc
    )


def validate_current_reference(
    state_root: DirectoryContext,
    generations: DirectoryContext,
) -> ReferenceContext | None:
    path = (
        state_root.path
        / REFERENCE_FILE_NAME
    )

    try:
        path_status = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: estado indisponível",
        )

    if (
        stat.S_ISLNK(path_status.st_mode)
        or not stat.S_ISREG(
            path_status.st_mode
        )
        or path_status.st_nlink != 1
        or path_status.st_uid != os.geteuid()
        or mode_exceeds(
            path_status,
            REFERENCE_MODE,
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: ficheiro inseguro",
        )

    secure = secure_read_file(
        path,
        REFERENCE_MAX_BYTES,
        role="referência",
        exit_code=EXIT_CONFIGURATION,
        missing_code="CONFIGURATION_INVALID",
        unsafe_code="CONFIGURATION_INVALID",
    )

    try:
        text = secure.content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: UTF-8 inválido",
        )

    if (
        not text.endswith("\n")
        or text.count("\n") != 1
        or "\r" in text
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: formato inválido",
        )

    generation_id = text[:-1]
    parse_generation_identifier(
        generation_id
    )
    generation_path = (
        generations.path
        / generation_id
    )

    try:
        generation_status = os.lstat(
            generation_path
        )
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: geração ausente",
        )

    if (
        generation_path.name.startswith(
            ".staging-"
        )
        or stat.S_ISLNK(
            generation_status.st_mode
        )
        or not stat.S_ISDIR(
            generation_status.st_mode
        )
        or generation_status.st_uid
        != os.geteuid()
        or mode_exceeds(
            generation_status,
            PROMOTED_DIRECTORY_MODE,
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "referência: geração insegura",
        )

    return ReferenceContext(
        path=path,
        secure=secure,
        generation_id=generation_id,
        generation_path=generation_path,
    )


def validate_roots(
    state_value: str,
    runtime_value: str,
) -> RootsContext:
    state_path = ensure_absolute_clean_path(
        state_value,
        role="STATE_ROOT",
    )
    runtime_path = ensure_absolute_clean_path(
        runtime_value,
        role="RUNTIME_ROOT",
    )

    if (
        state_path == runtime_path
        or paths_overlap(
            state_path,
            runtime_path,
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "raízes iguais ou sobrepostas",
        )

    ensure_no_symlink_components(
        state_path,
        role="STATE_ROOT",
    )
    ensure_no_symlink_components(
        runtime_path,
        role="RUNTIME_ROOT",
    )

    state = validate_owned_directory(
        state_path,
        role="STATE_ROOT",
        maximum_mode=STATE_ROOT_MAX_MODE,
        require_owner_write=True,
    )
    runtime = validate_owned_directory(
        runtime_path,
        role="RUNTIME_ROOT",
        maximum_mode=RUNTIME_ROOT_MAX_MODE,
        require_owner_write=True,
    )
    generations_path = (
        state_path
        / GENERATIONS_DIRECTORY_NAME
    )
    generations = validate_owned_directory(
        generations_path,
        role="generations",
        maximum_mode=GENERATIONS_MAX_MODE,
        require_owner_write=True,
    )

    try:
        state_device = os.stat(
            state_path,
            follow_symlinks=False,
        ).st_dev
        generations_device = os.stat(
            generations_path,
            follow_symlinks=False,
        ).st_dev
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "raízes: dispositivo indisponível",
        )

    if state_device != generations_device:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "generations: sistema de ficheiros divergente",
        )

    state_names = directory_entry_names(
        state_path,
        role="STATE_ROOT",
    )
    allowed_state_names = {
        GENERATIONS_DIRECTORY_NAME,
        REFERENCE_FILE_NAME,
    }

    if not state_names.issubset(
        allowed_state_names
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "STATE_ROOT: objeto desconhecido",
        )

    runtime_names = directory_entry_names(
        runtime_path,
        role="RUNTIME_ROOT",
    )

    if not runtime_names.issubset(
        {LOCK_FILE_NAME}
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "RUNTIME_ROOT: objeto desconhecido",
        )

    reference = validate_current_reference(
        state,
        generations,
    )

    return RootsContext(
        state=state,
        runtime=runtime,
        generations=generations,
        reference=reference,
    )


def revalidate_directory(
    context: DirectoryContext,
    *,
    role: str,
    maximum_mode: int,
) -> None:
    try:
        current_status = os.lstat(
            context.path
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: diretório indisponível",
        )

    if (
        stat.S_ISLNK(current_status.st_mode)
        or not stat.S_ISDIR(
            current_status.st_mode
        )
        or path_identity(current_status)
        != context.identity
        or current_status.st_uid
        != os.geteuid()
        or mode_exceeds(
            current_status,
            maximum_mode,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: identidade alterada",
        )


def revalidate_roots(
    context: RootsContext,
) -> None:
    revalidate_directory(
        context.state,
        role="STATE_ROOT",
        maximum_mode=STATE_ROOT_MAX_MODE,
    )
    revalidate_directory(
        context.runtime,
        role="RUNTIME_ROOT",
        maximum_mode=RUNTIME_ROOT_MAX_MODE,
    )
    revalidate_directory(
        context.generations,
        role="generations",
        maximum_mode=GENERATIONS_MAX_MODE,
    )

    if context.reference is not None:
        revalidate_secure_file(
            context.reference.path,
            context.reference.secure,
            role="referência",
            exit_code=EXIT_STRUCTURAL,
            failure_code=(
                "STRUCTURAL_FAILURE"
            ),
        )


@dataclass
class LockContext:
    path: Path
    descriptor: int
    identity: PathIdentity
    locked: bool = True


def validate_lock_status(
    status_result: os.stat_result,
) -> None:
    if (
        not stat.S_ISREG(
            status_result.st_mode
        )
        or status_result.st_nlink != 1
        or status_result.st_uid
        != os.geteuid()
        or mode_exceeds(
            status_result,
            LOCK_MAX_MODE,
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "bloqueio: ficheiro inseguro",
        )


def acquire_lock(
    runtime: DirectoryContext,
) -> LockContext:
    revalidate_directory(
        runtime,
        role="RUNTIME_ROOT",
        maximum_mode=RUNTIME_ROOT_MAX_MODE,
    )
    path = runtime.path / LOCK_FILE_NAME

    try:
        previous_status = os.lstat(path)
    except FileNotFoundError:
        previous_status = None
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "bloqueio: estado indisponível",
        )

    if previous_status is not None:
        if stat.S_ISLNK(
            previous_status.st_mode
        ):
            fail(
                EXIT_CONFIGURATION,
                "CONFIGURATION_INVALID",
                "bloqueio: link simbólico",
            )

        validate_lock_status(
            previous_status
        )

    flags = os.O_RDWR | os.O_CREAT

    if previous_status is None:
        flags |= os.O_EXCL

    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(
            path,
            flags,
            LOCK_MAX_MODE,
        )
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "bloqueio: abertura falhou",
        )

    try:
        descriptor_status = os.fstat(
            descriptor
        )
        validate_lock_status(
            descriptor_status
        )

        if previous_status is not None:
            if path_identity(
                descriptor_status
            ) != path_identity(
                previous_status
            ):
                fail(
                    EXIT_CONFIGURATION,
                    "CONFIGURATION_INVALID",
                    "bloqueio: identidade divergente",
                )
        else:
            os.fchmod(
                descriptor,
                LOCK_MAX_MODE,
            )
            descriptor_status = os.fstat(
                descriptor
            )
            validate_lock_status(
                descriptor_status
            )

        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX
                | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            raise RunnerFailure(
                EXIT_LOCK_BUSY,
                "LOCK_BUSY",
                "outro ciclo possui o bloqueio",
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "bloqueio: aquisição falhou",
            )

        try:
            path_status = os.lstat(path)
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "bloqueio: ficheiro mudou",
            )

        if (
            stat.S_ISLNK(path_status.st_mode)
            or path_identity(path_status)
            != path_identity(
                descriptor_status
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "bloqueio: identidade alterada",
            )

        return LockContext(
            path=path,
            descriptor=descriptor,
            identity=path_identity(
                descriptor_status
            ),
        )
    except BaseException:
        os.close(descriptor)
        raise


def revalidate_lock(
    context: LockContext,
) -> None:
    if not context.locked:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "bloqueio: já libertado",
        )

    try:
        descriptor_status = os.fstat(
            context.descriptor
        )
        path_status = os.lstat(
            context.path
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "bloqueio: estado indisponível",
        )

    if (
        not stat.S_ISREG(
            descriptor_status.st_mode
        )
        or descriptor_status.st_nlink != 1
        or path_identity(
            descriptor_status
        ) != context.identity
        or stat.S_ISLNK(path_status.st_mode)
        or path_identity(path_status)
        != context.identity
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "bloqueio: identidade alterada",
        )


def release_lock(
    context: LockContext,
) -> None:
    if not context.locked:
        return

    try:
        fcntl.flock(
            context.descriptor,
            fcntl.LOCK_UN,
        )
    finally:
        os.close(
            context.descriptor
        )
        context.locked = False


@dataclass(frozen=True)
class CycleIdentity:
    generation_id: str
    started_at: str
    started_datetime: datetime


def format_manifest_timestamp(
    value: datetime,
) -> str:
    return value.strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def create_cycle_identity(
    state: InvocationState,
) -> CycleIdentity:
    if (
        state.facts.cycle_started
        or state.facts.generation_id
        is not None
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "ciclo: identidade já criada",
        )

    state.facts.cycle_started = True
    moment = datetime.now(timezone.utc)
    suffix = secrets.token_hex(16)

    if not re.fullmatch(
        r"[0-9a-f]{32}",
        suffix,
    ):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "ciclo: entropia inválida",
        )

    generation_id = (
        moment.strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        + "-"
        + suffix
    )

    if (
        parse_generation_identifier(
            generation_id
        )
        != moment
    ):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "ciclo: instante divergente",
        )

    state.facts.generation_id = (
        generation_id
    )

    return CycleIdentity(
        generation_id=generation_id,
        started_at=(
            format_manifest_timestamp(
                moment
            )
        ),
        started_datetime=moment,
    )


def ensure_minimum_free_space(
    path: Path,
    *,
    role: str,
) -> int:
    try:
        filesystem = os.statvfs(path)
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: espaço indisponível",
        )

    available = (
        filesystem.f_bavail
        * filesystem.f_frsize
    )

    if available < MINIMUM_FREE_BYTES:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: espaço insuficiente",
        )

    return available


def cleanup_empty_transient_directory(
    context: DirectoryContext,
    *,
    role: str,
) -> None:
    revalidate_directory(
        context,
        role=role,
        maximum_mode=STAGING_MODE,
    )

    try:
        with os.scandir(
            context.path
        ) as entries:
            has_entries = next(
                entries,
                None,
            ) is not None
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza não verificável",
        )

    if has_entries:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza insegura",
        )

    try:
        os.rmdir(context.path)
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza falhou",
        )


def create_transient_directory(
    path: Path,
    *,
    role: str,
) -> DirectoryContext:
    try:
        os.mkdir(
            path,
            STAGING_MODE,
        )
    except FileExistsError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: colisão",
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: criação falhou",
        )

    try:
        initial_status = os.lstat(path)
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: identidade indisponível",
        )

    if (
        stat.S_ISLNK(
            initial_status.st_mode
        )
        or not stat.S_ISDIR(
            initial_status.st_mode
        )
        or initial_status.st_uid
        != os.geteuid()
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: objeto inseguro",
        )

    initial = DirectoryContext(
        path=path,
        identity=path_identity(
            initial_status
        ),
        mode=stat.S_IMODE(
            initial_status.st_mode
        ),
    )

    try:
        try:
            os.chmod(
                path,
                STAGING_MODE,
                follow_symlinks=False,
            )
            final_status = os.lstat(path)
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: modo indisponível",
            )

        if (
            stat.S_ISLNK(
                final_status.st_mode
            )
            or not stat.S_ISDIR(
                final_status.st_mode
            )
            or final_status.st_uid
            != os.geteuid()
            or path_identity(
                final_status
            ) != initial.identity
            or stat.S_IMODE(
                final_status.st_mode
            ) != STAGING_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: identidade divergente",
            )

        return DirectoryContext(
            path=path,
            identity=initial.identity,
            mode=STAGING_MODE,
        )
    except BaseException as error:
        try:
            cleanup_empty_transient_directory(
                initial,
                role=role,
            )
        except RunnerFailure as cleanup_error:
            raise cleanup_error from error

        raise


def path_exists_without_following(
    path: Path,
    *,
    role: str,
) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: estado indisponível",
        )

    return True


def validate_cycle_identity(
    cycle: CycleIdentity,
) -> None:
    if (
        not isinstance(
            cycle.generation_id,
            str,
        )
        or not isinstance(
            cycle.started_at,
            str,
        )
        or not isinstance(
            cycle.started_datetime,
            datetime,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "ciclo: contexto inválido",
        )

    try:
        parsed = parse_generation_identifier(
            cycle.generation_id
        )
    except RunnerFailure as error:
        raise RunnerFailure(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "ciclo: identificador inválido",
        ) from error

    if (
        parsed != cycle.started_datetime
        or cycle.started_at
        != format_manifest_timestamp(
            cycle.started_datetime
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "ciclo: instante divergente",
        )


@dataclass(frozen=True)
class StagingContext:
    cycle: CycleIdentity
    root: DirectoryContext
    observers: DirectoryContext


def create_staging(
    roots: RootsContext,
    cycle: CycleIdentity,
) -> StagingContext:
    revalidate_roots(roots)
    validate_cycle_identity(cycle)
    ensure_minimum_free_space(
        roots.generations.path,
        role="staging",
    )

    staging_path = (
        roots.generations.path
        / (
            ".staging-"
            + cycle.generation_id
        )
    )
    final_path = (
        roots.generations.path
        / cycle.generation_id
    )

    if path_exists_without_following(
        staging_path,
        role="staging",
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "staging: identificador em colisão",
        )

    if path_exists_without_following(
        final_path,
        role="geração",
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "geração: identificador em colisão",
        )

    staging = create_transient_directory(
        staging_path,
        role="staging",
    )

    if (
        staging.identity.device
        != roots.generations.identity.device
    ):
        cleanup_empty_transient_directory(
            staging,
            role="staging",
        )
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "staging: dispositivo divergente",
        )

    revalidate_roots(roots)
    revalidate_directory(
        staging,
        role="staging",
        maximum_mode=STAGING_MODE,
    )

    observers_path = (
        staging.path
        / OBSERVERS_DIRECTORY_NAME
    )

    try:
        observers = (
            create_transient_directory(
                observers_path,
                role="observers",
            )
        )
    except BaseException as error:
        try:
            cleanup_empty_transient_directory(
                staging,
                role="staging",
            )
        except RunnerFailure as cleanup_error:
            raise cleanup_error from error

        raise

    if (
        observers.identity.device
        != staging.identity.device
    ):
        cleanup_empty_transient_directory(
            observers,
            role="observers",
        )
        cleanup_empty_transient_directory(
            staging,
            role="staging",
        )
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "observers: dispositivo divergente",
        )

    revalidate_roots(roots)
    revalidate_directory(
        staging,
        role="staging",
        maximum_mode=STAGING_MODE,
    )
    revalidate_directory(
        observers,
        role="observers",
        maximum_mode=STAGING_MODE,
    )

    return StagingContext(
        cycle=cycle,
        root=staging,
        observers=observers,
    )


def revalidate_staging(
    roots: RootsContext,
    context: StagingContext,
) -> None:
    validate_cycle_identity(
        context.cycle
    )
    revalidate_roots(roots)

    expected_root = (
        roots.generations.path
        / (
            ".staging-"
            + context.cycle.generation_id
        )
    )
    expected_observers = (
        expected_root
        / OBSERVERS_DIRECTORY_NAME
    )

    if (
        context.root.path != expected_root
        or context.observers.path
        != expected_observers
        or context.root.identity.device
        != roots.generations.identity.device
        or context.observers.identity.device
        != context.root.identity.device
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "staging: contexto divergente",
        )

    revalidate_directory(
        context.root,
        role="staging",
        maximum_mode=STAGING_MODE,
    )
    revalidate_directory(
        context.observers,
        role="observers",
        maximum_mode=STAGING_MODE,
    )


@dataclass(frozen=True)
class CycleDeadline:
    started_monotonic: float
    deadline_monotonic: float


def start_cycle_deadline() -> CycleDeadline:
    started = time.monotonic()

    if not math.isfinite(started):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "tempo monotónico inválido",
        )

    return CycleDeadline(
        started_monotonic=started,
        deadline_monotonic=(
            started
            + TOTAL_CYCLE_TIMEOUT_SECONDS
        ),
    )


def remaining_cycle_seconds(
    context: CycleDeadline,
) -> float:
    if (
        not math.isfinite(
            context.started_monotonic
        )
        or not math.isfinite(
            context.deadline_monotonic
        )
        or context.deadline_monotonic
        != (
            context.started_monotonic
            + TOTAL_CYCLE_TIMEOUT_SECONDS
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limite total: contexto inválido",
        )

    current = time.monotonic()

    if (
        not math.isfinite(current)
        or current
        < context.started_monotonic
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limite total: relógio inválido",
        )

    remaining = (
        context.deadline_monotonic
        - current
    )

    if remaining <= 0:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limite total excedido",
        )

    return remaining


def check_cycle_deadline(
    context: CycleDeadline,
) -> None:
    remaining_cycle_seconds(context)


NORMAL_CAPTURE_FAILURE_CODES = {
    "EXECUTABLE_MISSING": 4,
    "EXECUTABLE_INVALID": 4,
    "EXECUTION_FAILED": 6,
    "EXECUTION_TIMEOUT": 6,
    "OUTPUT_LIMIT_EXCEEDED": 6,
    "STDERR_LIMIT_EXCEEDED": 6,
    "EMPTY_REPORT": 6,
    "INVALID_JSON": 7,
    "CONTRACT_VIOLATION": 7,
    "MODULE_MISMATCH": 7,
}

STRUCTURAL_CAPTURE_FAILURE_CODES = {
    "USAGE_INVALID": 2,
    "DEPENDENCY_UNAVAILABLE": 3,
    "REGISTRY_INVALID": 3,
    "MODULE_NOT_AUTHORIZED": 4,
    "STAGING_INVALID": 5,
    "TEMPORARY_PERSISTENCE_FAILED": 8,
    "INTERNAL_ERROR": 9,
}


@dataclass(frozen=True)
class CaptureResultContext:
    document: dict[str, Any]
    process_exit_code: int
    module: str
    outcome: str
    code: str
    observer_exit_code: int | None
    report: str | None
    stdout_bytes: int
    stderr_bytes: int
    duration_ms: int


def validate_capture_result(
    content: bytes,
    *,
    process_exit_code: int,
    expected_module: str,
    configuration: ConfigurationContext,
) -> CaptureResultContext:
    if (
        not isinstance(content, bytes)
        or not content
        or len(content)
        > CAPTURE_RESULT_MAX_BYTES
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: tamanho inválido",
        )

    if (
        isinstance(process_exit_code, bool)
        or not isinstance(process_exit_code, int)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: saída inválida",
        )

    if (
        not isinstance(expected_module, str)
        or not MODULE_PATTERN.fullmatch(
            expected_module
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: módulo esperado inválido",
        )

    revalidate_configuration(configuration)

    document = parse_json_strict(
        content,
        role="resultado do Capturador",
        maximum_depth=RUNNER_REPORT_MAX_DEPTH,
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    if not isinstance(document, dict):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: documento não é objeto",
        )

    if schema_errors(
        configuration.capture_schema.validator,
        document,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: violação do schema",
        )

    module = document["module"]
    outcome = document["outcome"]
    code = document["code"]
    observer_exit_code = document[
        "observer_exit_code"
    ]
    report = document["report"]
    stdout_bytes = document["stdout_bytes"]
    stderr_bytes = document["stderr_bytes"]
    duration_ms = document["duration_ms"]

    if (
        document["capture_contract"]
        != CAPTURE_CONTRACT
        or module != expected_module
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "resultado do Capturador: identidade divergente",
        )

    expected_report = (
        f"observers/{expected_module}.json"
    )

    if outcome == "SUCCESS":
        if (
            process_exit_code != 0
            or code != "SUCCESS"
            or observer_exit_code != 0
            or report != expected_report
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "resultado do Capturador: sucesso incoerente",
            )
    else:
        normal_exit = (
            NORMAL_CAPTURE_FAILURE_CODES.get(
                code
            )
        )
        structural_exit = (
            STRUCTURAL_CAPTURE_FAILURE_CODES.get(
                code
            )
        )
        expected_exit = (
            normal_exit
            if normal_exit is not None
            else structural_exit
        )

        if (
            expected_exit is None
            or process_exit_code != expected_exit
            or report is not None
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "resultado do Capturador: falha incoerente",
            )

        if structural_exit is not None:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                (
                    "resultado do Capturador: "
                    "falha estrutural"
                ),
            )

    return CaptureResultContext(
        document=document,
        process_exit_code=process_exit_code,
        module=module,
        outcome=outcome,
        code=code,
        observer_exit_code=observer_exit_code,
        report=report,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        duration_ms=duration_ms,
    )


CHILD_READ_CHUNK_BYTES = 16384


@dataclass(frozen=True)
class CaptureProcessResult:
    stdout: bytes
    stdout_bytes: int
    stderr_bytes: int
    exit_code: int
    duration_ms: int


def build_child_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def capture_process_group_exists(
    process_group: int,
) -> bool:
    if (
        isinstance(process_group, bool)
        or not isinstance(process_group, int)
        or process_group <= 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "processo do Capturador: grupo inválido",
        )

    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "processo do Capturador: grupo inacessível",
        )

    return True


def terminate_capture_process(
    process: subprocess.Popen[bytes],
) -> None:
    process_group = process.pid

    if (
        isinstance(process_group, bool)
        or not isinstance(process_group, int)
        or process_group <= 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "processo do Capturador: PID inválido",
        )

    try:
        os.killpg(
            process_group,
            signal.SIGTERM,
        )
    except ProcessLookupError:
        pass
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "processo do Capturador: SIGTERM falhou",
        )

    termination_deadline = (
        time.monotonic()
        + EXTERNAL_TERMINATION_GRACE_SECONDS
    )

    while time.monotonic() < termination_deadline:
        if not capture_process_group_exists(
            process_group
        ):
            break

        time.sleep(0.01)

    if capture_process_group_exists(
        process_group
    ):
        try:
            os.killpg(
                process_group,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "processo do Capturador: SIGKILL falhou",
            )

    try:
        process.wait(
            timeout=(
                EXTERNAL_TERMINATION_GRACE_SECONDS
            ),
        )
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "processo do Capturador: kill falhou",
            )

        try:
            process.wait(
                timeout=(
                    EXTERNAL_TERMINATION_GRACE_SECONDS
                ),
            )
        except subprocess.TimeoutExpired:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                (
                    "processo do Capturador: "
                    "terminação não confirmada"
                ),
            )


def capture_external_timeout(
    configuration: ConfigurationContext,
    deadline: CycleDeadline,
) -> float:
    limits = configuration.registry.document.get(
        "limits"
    )

    if not isinstance(limits, dict):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: limites indisponíveis",
        )

    observer_timeout = limits.get(
        "observer_timeout_seconds"
    )

    if (
        isinstance(observer_timeout, bool)
        or not isinstance(
            observer_timeout,
            int,
        )
        or observer_timeout <= 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: timeout inválido",
        )

    external_timeout = float(
        observer_timeout + 10
    )
    cycle_remaining = (
        remaining_cycle_seconds(deadline)
    )
    effective_timeout = min(
        external_timeout,
        cycle_remaining,
    )

    if (
        not math.isfinite(effective_timeout)
        or effective_timeout <= 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: timeout indisponível",
        )

    return effective_timeout


def collect_capture_process(
    process: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
) -> CaptureProcessResult:
    if (
        process.stdout is None
        or process.stderr is None
    ):
        terminate_capture_process(process)
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: pipes indisponíveis",
        )

    started_ns = time.monotonic_ns()
    started = time.monotonic()
    process_deadline = (
        started + timeout_seconds
    )
    stdout_buffer = bytearray()
    stdout_bytes = 0
    stderr_bytes = 0
    failure_message = None
    stream_selector = (
        selectors.DefaultSelector()
    )

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

    try:
        for descriptor, (
            stream_name,
            stream,
        ) in streams.items():
            os.set_blocking(
                descriptor,
                False,
            )
            stream_selector.register(
                descriptor,
                selectors.EVENT_READ,
                data=stream_name,
            )

        while stream_selector.get_map():
            current = time.monotonic()

            if (
                not math.isfinite(current)
                or current < started
            ):
                failure_message = (
                    "Capturador: relógio inválido"
                )
                break

            remaining = (
                process_deadline - current
            )

            if remaining <= 0:
                failure_message = (
                    "Capturador: timeout externo"
                )
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
                        CHILD_READ_CHUNK_BYTES,
                    )
                except BlockingIOError:
                    continue
                except OSError:
                    failure_message = (
                        "Capturador: leitura falhou"
                    )
                    break

                if not chunk:
                    stream_selector.unregister(
                        descriptor
                    )
                    continue

                if stream_name == "stdout":
                    stdout_bytes += len(chunk)

                    available = (
                        CAPTURE_RESULT_MAX_BYTES
                        + 1
                        - len(stdout_buffer)
                    )

                    if available > 0:
                        stdout_buffer.extend(
                            chunk[:available]
                        )

                    if (
                        stdout_bytes
                        > CAPTURE_RESULT_MAX_BYTES
                    ):
                        failure_message = (
                            "Capturador: stdout excedido"
                        )
                        break
                else:
                    stderr_bytes += len(chunk)

                    if (
                        stderr_bytes
                        > CHILD_STDERR_MAX_BYTES
                    ):
                        failure_message = (
                            "Capturador: stderr excedido"
                        )
                        break

            if failure_message is not None:
                break

        if failure_message is None:
            remaining = (
                process_deadline
                - time.monotonic()
            )

            if remaining <= 0:
                failure_message = (
                    "Capturador: timeout externo"
                )
            else:
                try:
                    process.wait(
                        timeout=remaining,
                    )
                except subprocess.TimeoutExpired:
                    failure_message = (
                        "Capturador: timeout externo"
                    )

        if failure_message is not None:
            terminate_capture_process(process)
        elif process.poll() is None:
            process.wait()
    finally:
        stream_selector.close()
        process.stdout.close()
        process.stderr.close()

    if failure_message is not None:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            failure_message,
        )

    if (
        isinstance(process.returncode, bool)
        or not isinstance(
            process.returncode,
            int,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: saída não confirmada",
        )

    duration_ms = (
        time.monotonic_ns() - started_ns
    ) // 1_000_000

    if duration_ms < 0:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: duração inválida",
        )

    return CaptureProcessResult(
        stdout=bytes(stdout_buffer),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        exit_code=process.returncode,
        duration_ms=duration_ms,
    )


def invoke_capture_process(
    roots: RootsContext,
    staging: StagingContext,
    configuration: ConfigurationContext,
    deadline: CycleDeadline,
    module: str,
) -> CaptureResultContext:
    if (
        not isinstance(module, str)
        or not MODULE_PATTERN.fullmatch(module)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Capturador: módulo inválido",
        )

    revalidate_configuration(configuration)
    revalidate_staging(
        roots,
        staging,
    )
    check_cycle_deadline(deadline)

    project_root = (
        Path(__file__).resolve().parent.parent
    )
    capture_path = (
        project_root
        / "core"
        / "capture-observer.py"
    )
    capture_secure = secure_read_file(
        capture_path,
        SCHEMA_MAX_BYTES,
        role="Capturador",
        exit_code=EXIT_STRUCTURAL,
        missing_code="STRUCTURAL_FAILURE",
        unsafe_code="STRUCTURAL_FAILURE",
    )
    timeout_seconds = (
        capture_external_timeout(
            configuration,
            deadline,
        )
    )
    arguments = [
        "/usr/bin/python3",
        "-I",
        str(capture_path),
        "--staging-dir",
        str(staging.root.path),
        module,
    ]
    previous_umask = os.umask(0o027)

    try:
        try:
            process = subprocess.Popen(
                arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=project_root,
                env=build_child_environment(),
                close_fds=True,
                start_new_session=True,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "Capturador: início falhou",
            )
    finally:
        os.umask(previous_umask)

    result = collect_capture_process(
        process,
        timeout_seconds=timeout_seconds,
    )

    revalidate_secure_file(
        capture_path,
        capture_secure,
        role="Capturador",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )
    revalidate_configuration(configuration)
    revalidate_staging(
        roots,
        staging,
    )
    check_cycle_deadline(deadline)

    return validate_capture_result(
        result.stdout,
        process_exit_code=result.exit_code,
        expected_module=module,
        configuration=configuration,
    )
@dataclass(frozen=True)
class PersistedReportContext:
    path: Path
    secure: SecureContent
    document: dict[str, Any]
    descriptor: dict[str, Any]


def validate_persisted_report(
    capture: CaptureResultContext,
    *,
    configuration: ConfigurationContext,
    roots: RootsContext,
    staging: StagingContext,
    deadline: CycleDeadline,
) -> PersistedReportContext:
    if (
        not isinstance(
            capture,
            CaptureResultContext,
        )
        or capture.outcome != "SUCCESS"
        or capture.report
        != f"observers/{capture.module}.json"
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: captura inválida",
        )

    revalidate_configuration(configuration)
    revalidate_staging(
        roots,
        staging,
    )
    check_cycle_deadline(deadline)

    registry_entries = [
        entry
        for entry
        in configuration.registry.document[
            "observers"
        ]
        if entry["module"] == capture.module
    ]

    if len(registry_entries) != 1:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: módulo não autorizado",
        )

    registry_entry = registry_entries[0]
    limits = configuration.registry.document[
        "limits"
    ]
    expected_relative_path = (
        f"observers/{capture.module}.json"
    )
    report_path = (
        staging.root.path
        / "observers"
        / f"{capture.module}.json"
    )

    if (
        capture.report
        != expected_relative_path
        or report_path.parent
        != staging.observers.path
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: caminho divergente",
        )

    secure = secure_read_file(
        report_path,
        limits["report_max_bytes"],
        role="relatório persistido",
        exit_code=EXIT_STRUCTURAL,
        missing_code="STRUCTURAL_FAILURE",
        unsafe_code="STRUCTURAL_FAILURE",
    )

    if secure.size <= 0:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: conteúdo vazio",
        )

    try:
        report_status = os.lstat(
            report_path
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: estado indisponível",
        )

    if (
        stat.S_ISLNK(
            report_status.st_mode
        )
        or not stat.S_ISREG(
            report_status.st_mode
        )
        or report_status.st_nlink != 1
        or report_status.st_uid
        != os.geteuid()
        or mode_exceeds(
            report_status,
            STAGING_FILE_MODE,
        )
        or path_identity(
            report_status
        ) != secure.identity
        or report_status.st_size
        != secure.size
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: ficheiro inseguro",
        )

    project_root = (
        Path(__file__).resolve().parent.parent
    )
    validator_path = (
        project_root
        / "core"
        / "validate-report.py"
    )
    validator_secure = secure_read_file(
        validator_path,
        SCHEMA_MAX_BYTES,
        role="Validador de Relatórios",
        exit_code=EXIT_STRUCTURAL,
        missing_code="STRUCTURAL_FAILURE",
        unsafe_code="STRUCTURAL_FAILURE",
    )
    validator_arguments = [
        "/usr/bin/python3",
        "-I",
        str(validator_path),
        "--expected-module",
        capture.module,
        "--max-bytes",
        str(limits["report_max_bytes"]),
        "--max-depth",
        str(limits["json_max_depth"]),
        str(report_path),
    ]

    try:
        validator_process = subprocess.Popen(
            validator_arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
            env=build_child_environment(),
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Validador de Relatórios: início falhou",
        )

    validator_result = collect_capture_process(
        validator_process,
        timeout_seconds=(
            remaining_cycle_seconds(
                deadline
            )
        ),
    )

    if (
        validator_result.exit_code != 0
        or validator_result.stdout_bytes != 0
        or validator_result.stderr_bytes != 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: validação oficial falhou",
        )

    revalidate_secure_file(
        validator_path,
        validator_secure,
        role="Validador de Relatórios",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )
    revalidate_secure_file(
        report_path,
        secure,
        role="relatório persistido",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )
    revalidate_configuration(configuration)
    revalidate_staging(
        roots,
        staging,
    )
    check_cycle_deadline(deadline)

    document = parse_json_strict(
        secure.content,
        role="relatório persistido",
        maximum_depth=limits[
            "json_max_depth"
        ],
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    if (
        not isinstance(document, dict)
        or schema_errors(
            configuration.report_schema.validator,
            document,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: contrato inválido",
        )

    if (
        document["module"] != capture.module
        or document["version"]
        not in registry_entry[
            "module_versions"
        ]
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "relatório persistido: identidade divergente",
        )

    descriptor = {
        "path": expected_relative_path,
        "module": document["module"],
        "contract_version": (
            registry_entry["output_contract"]
        ),
        "version": document["version"],
        "timestamp": document["timestamp"],
        "status": document["status"],
        "size_bytes": secure.size,
        "sha256": hashlib.sha256(
            secure.content
        ).hexdigest(),
    }

    return PersistedReportContext(
        path=report_path,
        secure=secure,
        document=document,
        descriptor=descriptor,
    )

def build_manifest_modules(
    captures: Sequence[CaptureResultContext],
    reports: Sequence[PersistedReportContext],
    *,
    configuration: ConfigurationContext,
) -> list[dict[str, Any]]:
    if not isinstance(
        configuration,
        ConfigurationContext,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: configuração inválida",
        )

    if (
        isinstance(
            captures,
            (str, bytes, bytearray),
        )
        or not isinstance(captures, Sequence)
        or isinstance(
            reports,
            (str, bytes, bytearray),
        )
        or not isinstance(reports, Sequence)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: inventário inválido",
        )

    registry_document = (
        configuration.registry.document
    )

    if (
        not isinstance(registry_document, dict)
        or not isinstance(
            registry_document.get("observers"),
            list,
        )
        or not registry_document["observers"]
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: registo inválido",
        )

    registry_entries = (
        registry_document["observers"]
    )
    registered_modules: list[str] = []

    for registry_entry in registry_entries:
        if (
            not isinstance(registry_entry, dict)
            or not isinstance(
                registry_entry.get("module"),
                str,
            )
            or not MODULE_PATTERN.fullmatch(
                registry_entry["module"]
            )
            or not isinstance(
                registry_entry.get("required"),
                bool,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: entrada de registo inválida",
            )

        module = registry_entry["module"]

        if module in registered_modules:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: módulo duplicado no registo",
            )

        registered_modules.append(module)

    if len(captures) != len(registry_entries):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: número de capturas divergente",
        )

    captures_by_module: dict[
        str,
        CaptureResultContext,
    ] = {}

    for capture in captures:
        if (
            not isinstance(
                capture,
                CaptureResultContext,
            )
            or capture.module
            in captures_by_module
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: captura inválida ou duplicada",
            )

        captures_by_module[
            capture.module
        ] = capture

    if set(captures_by_module) != set(
        registered_modules
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: módulos capturados divergentes",
        )

    reports_by_module: dict[
        str,
        PersistedReportContext,
    ] = {}

    for report in reports:
        if (
            not isinstance(
                report,
                PersistedReportContext,
            )
            or not isinstance(
                report.descriptor,
                dict,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: relatório validado inválido",
            )

        module = report.descriptor.get("module")

        if (
            not isinstance(module, str)
            or module in reports_by_module
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: relatório duplicado ou inválido",
            )

        reports_by_module[module] = report

    if not set(reports_by_module).issubset(
        set(registered_modules)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: relatório de módulo não autorizado",
        )

    modules: list[dict[str, Any]] = []

    for registry_entry in registry_entries:
        module = registry_entry["module"]
        capture = captures_by_module[module]
        expected_report = (
            f"observers/{module}.json"
        )

        if capture.outcome == "SUCCESS":
            if (
                capture.code != "SUCCESS"
                or capture.process_exit_code != 0
                or capture.observer_exit_code != 0
                or capture.report
                != expected_report
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "manifesto: captura de sucesso incoerente",
                )

            persisted = reports_by_module.get(
                module
            )

            if persisted is None:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "manifesto: relatório de sucesso ausente",
                )

            if (
                not isinstance(
                    persisted.document,
                    dict,
                )
                or persisted.document.get(
                    "module"
                )
                != module
                or persisted.descriptor.get(
                    "module"
                )
                != module
                or persisted.descriptor.get(
                    "path"
                )
                != expected_report
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "manifesto: relatório de sucesso divergente",
                )

            error_code = None
            report_descriptor = dict(
                persisted.descriptor
            )

        elif capture.outcome == "FAILED":
            expected_process_exit = (
                NORMAL_CAPTURE_FAILURE_CODES.get(
                    capture.code
                )
            )

            if (
                expected_process_exit is None
                or capture.process_exit_code
                != expected_process_exit
                or capture.report is not None
                or module in reports_by_module
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "manifesto: captura de falha incoerente",
                )

            error_code = capture.code
            report_descriptor = None

        else:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: outcome inválido",
            )

        modules.append(
            {
                "module": module,
                "required": (
                    registry_entry["required"]
                ),
                "outcome": capture.outcome,
                "error_code": error_code,
                "exit_code": (
                    capture.observer_exit_code
                ),
                "stdout_bytes": (
                    capture.stdout_bytes
                ),
                "stderr_bytes": (
                    capture.stderr_bytes
                ),
                "duration_ms": (
                    capture.duration_ms
                ),
                "report": report_descriptor,
            }
        )

    return modules

def create_completed_at(
    cycle: CycleIdentity,
) -> str:
    if not isinstance(
        cycle,
        CycleIdentity,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: ciclo inválido",
        )

    moment = datetime.now(
        timezone.utc
    )

    try:
        if moment < cycle.started_datetime:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: relógio UTC recuou",
            )
    except TypeError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: instante inválido",
        )

    return format_manifest_timestamp(
        moment
    )


def load_rename_noreplace() -> Any:
    try:
        library = ctypes.CDLL(
            None,
            use_errno=True,
        )
        renameat2 = library.renameat2
    except (AttributeError, OSError):
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
    *,
    role: str,
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
        message = f"{role}: destino já existe"
    else:
        message = f"{role}: publicação atómica falhou"

    fail(
        EXIT_STRUCTURAL,
        "STRUCTURAL_FAILURE",
        message,
    )


def remove_owned_temporary_file(
    directory_descriptor: int,
    temporary_name: str,
    identity: PathIdentity,
    *,
    role: str,
) -> None:
    try:
        current_status = os.stat(
            temporary_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza não verificável",
        )

    if (
        stat.S_ISLNK(current_status.st_mode)
        or not stat.S_ISREG(current_status.st_mode)
        or current_status.st_nlink != 1
        or current_status.st_uid != os.geteuid()
        or path_identity(current_status) != identity
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza insegura",
        )

    try:
        os.unlink(
            temporary_name,
            dir_fd=directory_descriptor,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            f"{role}: limpeza falhou",
        )


def persist_manifest(
    roots: RootsContext,
    staging: StagingContext,
    content: bytes,
    renameat2: Any,
) -> SecureContent:
    if (
        not isinstance(content, bytes)
        or not content
        or len(content) > MANIFEST_MAX_BYTES
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: conteúdo persistente inválido",
        )

    revalidate_staging(
        roots,
        staging,
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
            staging.root.path,
            directory_flags,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: staging indisponível",
        )

    temporary_name = (
        ".manifest-"
        + staging.cycle.generation_id
        + ".tmp"
    )
    destination_name = MANIFEST_FILE_NAME
    temporary_descriptor = None
    temporary_identity = None
    published = False

    try:
        directory_status = os.fstat(
            directory_descriptor
        )

        if (
            not stat.S_ISDIR(
                directory_status.st_mode
            )
            or directory_status.st_uid
            != os.geteuid()
            or path_identity(
                directory_status
            ) != staging.root.identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: staging divergente",
            )

        try:
            os.stat(
                destination_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: destino não verificável",
            )
        else:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: destino já existe",
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

        try:
            temporary_descriptor = os.open(
                temporary_name,
                file_flags,
                STAGING_FILE_MODE,
                dir_fd=directory_descriptor,
            )
        except FileExistsError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: temporário em colisão",
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: criação temporária falhou",
            )

        initial_status = os.fstat(
            temporary_descriptor
        )
        temporary_identity = path_identity(
            initial_status
        )

        if (
            not stat.S_ISREG(
                initial_status.st_mode
            )
            or initial_status.st_nlink != 1
            or initial_status.st_uid
            != os.geteuid()
            or mode_exceeds(
                initial_status,
                STAGING_FILE_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: temporário inseguro",
            )

        offset = 0

        while offset < len(content):
            written = os.write(
                temporary_descriptor,
                content[offset:],
            )

            if written <= 0:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "manifesto: escrita temporária incompleta",
                )

            offset += written

        os.fchmod(
            temporary_descriptor,
            STAGING_FILE_MODE,
        )
        os.fsync(
            temporary_descriptor
        )

        completed_status = os.fstat(
            temporary_descriptor
        )

        if (
            not stat.S_ISREG(
                completed_status.st_mode
            )
            or completed_status.st_nlink != 1
            or completed_status.st_uid
            != os.geteuid()
            or path_identity(
                completed_status
            ) != temporary_identity
            or stat.S_IMODE(
                completed_status.st_mode
            ) != STAGING_FILE_MODE
            or completed_status.st_size
            != len(content)
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: temporário divergente",
            )

        rename_noreplace(
            renameat2,
            directory_descriptor,
            temporary_name,
            destination_name,
            role="manifesto",
        )
        published = True
        temporary_name = ""

        final_status = os.stat(
            destination_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )

        if (
            not stat.S_ISREG(
                final_status.st_mode
            )
            or final_status.st_nlink != 1
            or final_status.st_uid
            != os.geteuid()
            or path_identity(
                final_status
            ) != temporary_identity
            or stat.S_IMODE(
                final_status.st_mode
            ) != STAGING_FILE_MODE
            or final_status.st_size
            != len(content)
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: publicação divergente",
            )

        os.fsync(
            directory_descriptor
        )

        synchronized_status = os.fstat(
            directory_descriptor
        )

        if (
            not stat.S_ISDIR(
                synchronized_status.st_mode
            )
            or path_identity(
                synchronized_status
            ) != staging.root.identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: staging mudou após sincronização",
            )

        return SecureContent(
            content=content,
            identity=path_identity(
                final_status
            ),
            size=final_status.st_size,
            mtime_ns=final_status.st_mtime_ns,
            ctime_ns=final_status.st_ctime_ns,
        )
    except RunnerFailure:
        raise
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: persistência falhou",
        )
    finally:
        if temporary_descriptor is not None:
            try:
                os.close(
                    temporary_descriptor
                )
            except OSError:
                pass

        if (
            not published
            and temporary_name
            and temporary_identity is not None
        ):
            remove_owned_temporary_file(
                directory_descriptor,
                temporary_name,
                temporary_identity,
                role="manifesto temporário",
            )

        try:
            os.close(
                directory_descriptor
            )
        except OSError:
            pass

def validate_manifest_official(
    roots: RootsContext,
    staging: StagingContext,
    manifest_secure: SecureContent,
    reports: list[PersistedReportContext],
    deadline: CycleDeadline,
) -> None:
    if (
        not isinstance(roots, RootsContext)
        or not isinstance(staging, StagingContext)
        or not isinstance(
            manifest_secure,
            SecureContent,
        )
        or not isinstance(deadline, CycleDeadline)
        or not isinstance(reports, list)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: contexto de validação inválido",
        )

    report_contexts: dict[
        str,
        PersistedReportContext,
    ] = {}

    for report in reports:
        if (
            not isinstance(
                report,
                PersistedReportContext,
            )
            or not isinstance(
                report.path,
                Path,
            )
            or not isinstance(
                report.secure,
                SecureContent,
            )
            or not isinstance(
                report.descriptor,
                dict,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: relatório inválido",
            )

        module = report.descriptor.get(
            "module"
        )
        relative_path = report.descriptor.get(
            "path"
        )

        if (
            not isinstance(module, str)
            or not MODULE_PATTERN.fullmatch(
                module
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: módulo de relatório inválido",
            )

        file_name = f"{module}.json"
        expected_relative_path = (
            f"{OBSERVERS_DIRECTORY_NAME}/"
            f"{file_name}"
        )
        expected_path = (
            staging.observers.path
            / file_name
        )

        if (
            relative_path
            != expected_relative_path
            or report.path != expected_path
            or file_name in report_contexts
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: relatório divergente",
            )

        report_contexts[file_name] = report

    manifest_path = (
        staging.root.path
        / MANIFEST_FILE_NAME
    )

    def revalidate_staging_file(
        file_path: Path,
        secure: SecureContent,
        *,
        role: str,
    ) -> None:
        revalidate_secure_file(
            file_path,
            secure,
            role=role,
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

        try:
            current_status = os.lstat(
                file_path
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: estado indisponível",
            )

        if (
            current_status.st_uid
            != os.geteuid()
            or mode_exceeds(
                current_status,
                STAGING_FILE_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: propriedades divergentes",
            )

    def structural_entry_names(
        directory_path: Path,
        *,
        role: str,
    ) -> set[str]:
        try:
            with os.scandir(
                directory_path
            ) as entries:
                return {
                    entry.name
                    for entry in entries
                }
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: enumeração falhou",
            )

    def validate_snapshot() -> None:
        revalidate_roots(roots)
        revalidate_staging(
            roots,
            staging,
        )

        revalidate_staging_file(
            manifest_path,
            manifest_secure,
            role="manifesto",
        )

        for report in (
            report_contexts.values()
        ):
            revalidate_staging_file(
                report.path,
                report.secure,
                role="relatório persistido",
            )

        staging_names = (
            structural_entry_names(
                staging.root.path,
                role="staging",
            )
        )
        expected_staging_names = {
            MANIFEST_FILE_NAME,
            OBSERVERS_DIRECTORY_NAME,
        }

        if (
            staging_names
            != expected_staging_names
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "staging: objeto desconhecido",
            )

        observers_names = (
            structural_entry_names(
                staging.observers.path,
                role="observers",
            )
        )
        expected_observers_names = set(
            report_contexts
        )

        if (
            observers_names
            != expected_observers_names
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "observers: objeto desconhecido",
            )

        check_cycle_deadline(deadline)

    validate_snapshot()

    project_root = (
        Path(__file__).resolve().parent.parent
    )
    validator_path = (
        project_root
        / "core"
        / "validate-manifest.py"
    )
    validator_secure = secure_read_file(
        validator_path,
        SCHEMA_MAX_BYTES,
        role="Validador de Manifestos",
        exit_code=EXIT_STRUCTURAL,
        missing_code="STRUCTURAL_FAILURE",
        unsafe_code="STRUCTURAL_FAILURE",
    )

    validator_arguments = [
        "/usr/bin/python3",
        "-I",
        str(validator_path),
        "--expected-generation-id",
        staging.cycle.generation_id,
        str(staging.root.path),
    ]

    try:
        validator_process = (
            subprocess.Popen(
                validator_arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=project_root,
                env=build_child_environment(),
                close_fds=True,
                start_new_session=True,
            )
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "Validador de Manifestos: início falhou",
        )

    validator_result = (
        collect_capture_process(
            validator_process,
            timeout_seconds=(
                remaining_cycle_seconds(
                    deadline
                )
            ),
        )
    )

    if (
        validator_result.exit_code != 0
        or validator_result.stdout_bytes
        != 0
        or validator_result.stderr_bytes
        != 0
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: validação oficial falhou",
        )

    revalidate_secure_file(
        validator_path,
        validator_secure,
        role="Validador de Manifestos",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    validate_snapshot()


def apply_final_permissions(
    roots: RootsContext,
    staging: StagingContext,
    manifest_secure: SecureContent,
    reports: list[PersistedReportContext],
    deadline: CycleDeadline,
) -> tuple[
    StagingContext,
    SecureContent,
    list[PersistedReportContext],
]:
    if (
        not isinstance(roots, RootsContext)
        or not isinstance(staging, StagingContext)
        or not isinstance(
            manifest_secure,
            SecureContent,
        )
        or not isinstance(reports, list)
        or not isinstance(deadline, CycleDeadline)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "permissões finais: contexto inválido",
        )

    report_contexts: dict[
        str,
        PersistedReportContext,
    ] = {}

    for report in reports:
        if (
            not isinstance(
                report,
                PersistedReportContext,
            )
            or not isinstance(
                report.path,
                Path,
            )
            or not isinstance(
                report.secure,
                SecureContent,
            )
            or not isinstance(
                report.descriptor,
                dict,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "permissões finais: relatório inválido",
            )

        module = report.descriptor.get(
            "module"
        )
        relative_path = report.descriptor.get(
            "path"
        )
        expected_hash = report.descriptor.get(
            "sha256"
        )

        if (
            not isinstance(module, str)
            or not MODULE_PATTERN.fullmatch(
                module
            )
            or not isinstance(
                expected_hash,
                str,
            )
            or len(expected_hash) != 64
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "permissões finais: relatório divergente",
            )

        file_name = f"{module}.json"

        if (
            relative_path
            != (
                f"{OBSERVERS_DIRECTORY_NAME}/"
                f"{file_name}"
            )
            or report.path
            != (
                staging.observers.path
                / file_name
            )
            or file_name in report_contexts
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "permissões finais: relatório divergente",
            )

        report_contexts[
            file_name
        ] = report

    manifest_path = (
        staging.root.path
        / MANIFEST_FILE_NAME
    )

    def entry_names(
        directory_path: Path,
        *,
        role: str,
    ) -> set[str]:
        try:
            with os.scandir(
                directory_path
            ) as entries:
                return {
                    entry.name
                    for entry in entries
                }
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: enumeração falhou",
            )

    def validate_inventory() -> None:
        if entry_names(
            staging.root.path,
            role="staging",
        ) != {
            MANIFEST_FILE_NAME,
            OBSERVERS_DIRECTORY_NAME,
        }:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "staging: objeto desconhecido",
            )

        if entry_names(
            staging.observers.path,
            role="observers",
        ) != set(report_contexts):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "observers: objeto desconhecido",
            )

    def finalize_file(
        file_path: Path,
        secure: SecureContent,
        *,
        role: str,
        expected_hash: str | None,
    ) -> SecureContent:
        flags = os.O_RDONLY
        flags |= getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        try:
            descriptor = os.open(
                file_path,
                flags,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: abertura falhou",
            )

        try:
            before_status = os.fstat(
                descriptor
            )

            if (
                not stat.S_ISREG(
                    before_status.st_mode
                )
                or before_status.st_nlink
                != 1
                or before_status.st_uid
                != os.geteuid()
                or path_identity(
                    before_status
                ) != secure.identity
                or before_status.st_size
                != secure.size
                or before_status.st_mtime_ns
                != secure.mtime_ns
                or before_status.st_ctime_ns
                != secure.ctime_ns
                or mode_exceeds(
                    before_status,
                    STAGING_FILE_MODE,
                )
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: identidade divergente",
                )

            try:
                os.fchmod(
                    descriptor,
                    PROMOTED_FILE_MODE,
                )
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: chmod falhou",
                )

            chmod_status = os.fstat(
                descriptor
            )

            if (
                not stat.S_ISREG(
                    chmod_status.st_mode
                )
                or chmod_status.st_nlink
                != 1
                or chmod_status.st_uid
                != os.geteuid()
                or path_identity(
                    chmod_status
                ) != secure.identity
                or chmod_status.st_size
                != secure.size
                or chmod_status.st_mtime_ns
                != secure.mtime_ns
                or stat.S_IMODE(
                    chmod_status.st_mode
                ) != PROMOTED_FILE_MODE
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: chmod divergente",
                )

            try:
                os.lseek(
                    descriptor,
                    0,
                    os.SEEK_SET,
                )
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: leitura indisponível",
                )

            chunks = []
            remaining = secure.size

            while remaining:
                try:
                    chunk = os.read(
                        descriptor,
                        min(
                            remaining,
                            65536,
                        ),
                    )
                except OSError:
                    fail(
                        EXIT_STRUCTURAL,
                        "STRUCTURAL_FAILURE",
                        f"{role}: leitura falhou",
                    )

                if not chunk:
                    fail(
                        EXIT_STRUCTURAL,
                        "STRUCTURAL_FAILURE",
                        f"{role}: leitura incompleta",
                    )

                chunks.append(chunk)
                remaining -= len(chunk)

            try:
                extra = os.read(
                    descriptor,
                    1,
                )
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: leitura final falhou",
                )

            if extra:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: tamanho divergente",
                )

            content = b"".join(chunks)

            final_status = os.fstat(
                descriptor
            )

            if (
                not stat.S_ISREG(
                    final_status.st_mode
                )
                or final_status.st_nlink
                != 1
                or final_status.st_uid
                != os.geteuid()
                or path_identity(
                    final_status
                ) != secure.identity
                or final_status.st_size
                != secure.size
                or final_status.st_mtime_ns
                != chmod_status.st_mtime_ns
                or final_status.st_ctime_ns
                != chmod_status.st_ctime_ns
                or stat.S_IMODE(
                    final_status.st_mode
                ) != PROMOTED_FILE_MODE
                or content != secure.content
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: conteúdo divergente",
                )

            if (
                expected_hash is not None
                and hashlib.sha256(
                    content
                ).hexdigest()
                != expected_hash
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: hash divergente",
                )

            return SecureContent(
                content=content,
                identity=path_identity(
                    final_status
                ),
                size=final_status.st_size,
                mtime_ns=(
                    final_status.st_mtime_ns
                ),
                ctime_ns=(
                    final_status.st_ctime_ns
                ),
            )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def finalize_directory(
        context: DirectoryContext,
        *,
        role: str,
    ) -> DirectoryContext:
        flags = os.O_RDONLY
        flags |= getattr(
            os,
            "O_DIRECTORY",
            0,
        )
        flags |= getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        try:
            descriptor = os.open(
                context.path,
                flags,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: abertura falhou",
            )

        try:
            before_status = os.fstat(
                descriptor
            )

            if (
                not stat.S_ISDIR(
                    before_status.st_mode
                )
                or before_status.st_uid
                != os.geteuid()
                or path_identity(
                    before_status
                ) != context.identity
                or mode_exceeds(
                    before_status,
                    STAGING_MODE,
                )
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: identidade divergente",
                )

            try:
                os.fchmod(
                    descriptor,
                    PROMOTED_DIRECTORY_MODE,
                )
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: chmod falhou",
                )

            final_status = os.fstat(
                descriptor
            )

            if (
                not stat.S_ISDIR(
                    final_status.st_mode
                )
                or final_status.st_uid
                != os.geteuid()
                or path_identity(
                    final_status
                ) != context.identity
                or stat.S_IMODE(
                    final_status.st_mode
                )
                != PROMOTED_DIRECTORY_MODE
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: chmod divergente",
                )

            return DirectoryContext(
                path=context.path,
                identity=path_identity(
                    final_status
                ),
                mode=stat.S_IMODE(
                    final_status.st_mode
                ),
            )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    revalidate_roots(roots)
    revalidate_staging(
        roots,
        staging,
    )

    revalidate_secure_file(
        manifest_path,
        manifest_secure,
        role="manifesto",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    for report in (
        report_contexts.values()
    ):
        revalidate_secure_file(
            report.path,
            report.secure,
            role="relatório persistido",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

    validate_inventory()
    check_cycle_deadline(deadline)

    updated_reports = []

    for file_name in sorted(
        report_contexts
    ):
        report = report_contexts[
            file_name
        ]

        updated_secure = finalize_file(
            report.path,
            report.secure,
            role="relatório persistido",
            expected_hash=(
                report.descriptor["sha256"]
            ),
        )

        updated_reports.append(
            PersistedReportContext(
                path=report.path,
                secure=updated_secure,
                document=report.document,
                descriptor=report.descriptor,
            )
        )

    updated_manifest_secure = (
        finalize_file(
            manifest_path,
            manifest_secure,
            role="manifesto",
            expected_hash=None,
        )
    )

    updated_observers = (
        finalize_directory(
            staging.observers,
            role="observers",
        )
    )

    updated_root = (
        finalize_directory(
            staging.root,
            role="staging",
        )
    )

    updated_staging = StagingContext(
        cycle=staging.cycle,
        root=updated_root,
        observers=updated_observers,
    )

    revalidate_roots(roots)
    revalidate_staging(
        roots,
        updated_staging,
    )

    if (
        stat.S_IMODE(
            os.lstat(
                updated_staging.root.path
            ).st_mode
        )
        != PROMOTED_DIRECTORY_MODE
        or stat.S_IMODE(
            os.lstat(
                updated_staging.observers.path
            ).st_mode
        )
        != PROMOTED_DIRECTORY_MODE
        or stat.S_IMODE(
            os.lstat(
                manifest_path
            ).st_mode
        )
        != PROMOTED_FILE_MODE
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "permissões finais: confirmação falhou",
        )

    for report in updated_reports:
        if stat.S_IMODE(
            os.lstat(
                report.path
            ).st_mode
        ) != PROMOTED_FILE_MODE:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "permissões finais: relatório divergente",
            )

        revalidate_secure_file(
            report.path,
            report.secure,
            role="relatório persistido",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

    revalidate_secure_file(
        manifest_path,
        updated_manifest_secure,
        role="manifesto",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    validate_inventory()
    check_cycle_deadline(deadline)

    return (
        updated_staging,
        updated_manifest_secure,
        updated_reports,
    )


def synchronize_generation(
    roots: RootsContext,
    staging: StagingContext,
    manifest_secure: SecureContent,
    reports: list[PersistedReportContext],
    deadline: CycleDeadline,
) -> None:
    if (
        not isinstance(roots, RootsContext)
        or not isinstance(staging, StagingContext)
        or not isinstance(
            manifest_secure,
            SecureContent,
        )
        or not isinstance(reports, list)
        or not isinstance(deadline, CycleDeadline)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "sincronização: contexto inválido",
        )

    report_contexts = []

    for report in reports:
        if (
            not isinstance(
                report,
                PersistedReportContext,
            )
            or not isinstance(
                report.path,
                Path,
            )
            or not isinstance(
                report.secure,
                SecureContent,
            )
            or not isinstance(
                report.descriptor,
                dict,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: relatório inválido",
            )

        module = report.descriptor.get(
            "module"
        )

        if (
            not isinstance(module, str)
            or not MODULE_PATTERN.fullmatch(
                module
            )
            or report.path
            != (
                staging.observers.path
                / f"{module}.json"
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: relatório divergente",
            )

        if any(
            existing.path == report.path
            for existing in report_contexts
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: relatório duplicado",
            )

        report_contexts.append(report)

    manifest_path = (
        staging.root.path
        / MANIFEST_FILE_NAME
    )

    def entry_names(
        path: Path,
        *,
        role: str,
    ) -> set[str]:
        try:
            with os.scandir(path) as entries:
                return {
                    entry.name
                    for entry in entries
                }
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: enumeração falhou",
            )

    def validate_state() -> None:
        revalidate_roots(roots)
        revalidate_staging(
            roots,
            staging,
        )

        if (
            stat.S_IMODE(
                os.lstat(
                    staging.root.path
                ).st_mode
            )
            != PROMOTED_DIRECTORY_MODE
            or stat.S_IMODE(
                os.lstat(
                    staging.observers.path
                ).st_mode
            )
            != PROMOTED_DIRECTORY_MODE
            or stat.S_IMODE(
                os.lstat(
                    manifest_path
                ).st_mode
            )
            != PROMOTED_FILE_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: permissões divergentes",
            )

        revalidate_secure_file(
            manifest_path,
            manifest_secure,
            role="manifesto",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

        expected_observers = set()

        for report in report_contexts:
            if stat.S_IMODE(
                os.lstat(
                    report.path
                ).st_mode
            ) != PROMOTED_FILE_MODE:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "sincronização: relatório com permissões divergentes",
                )

            revalidate_secure_file(
                report.path,
                report.secure,
                role="relatório persistido",
                exit_code=EXIT_STRUCTURAL,
                failure_code="STRUCTURAL_FAILURE",
            )

            expected_observers.add(
                report.path.name
            )

        if entry_names(
            staging.root.path,
            role="staging",
        ) != {
            MANIFEST_FILE_NAME,
            OBSERVERS_DIRECTORY_NAME,
        }:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: staging divergente",
            )

        if entry_names(
            staging.observers.path,
            role="observers",
        ) != expected_observers:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "sincronização: observers divergente",
            )

        check_cycle_deadline(deadline)

    def sync_file(
        path: Path,
        secure: SecureContent,
        *,
        role: str,
    ) -> None:
        flags = os.O_RDONLY
        flags |= getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        try:
            descriptor = os.open(
                path,
                flags,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: abertura falhou",
            )

        try:
            before = os.fstat(descriptor)

            if (
                not stat.S_ISREG(
                    before.st_mode
                )
                or before.st_nlink != 1
                or before.st_uid
                != os.geteuid()
                or path_identity(before)
                != secure.identity
                or before.st_size
                != secure.size
                or before.st_mtime_ns
                != secure.mtime_ns
                or before.st_ctime_ns
                != secure.ctime_ns
                or stat.S_IMODE(
                    before.st_mode
                ) != PROMOTED_FILE_MODE
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: identidade divergente",
                )

            try:
                os.fsync(descriptor)
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: fsync falhou",
                )

            after = os.fstat(descriptor)

            if (
                path_identity(after)
                != secure.identity
                or after.st_size
                != secure.size
                or after.st_mtime_ns
                != secure.mtime_ns
                or after.st_ctime_ns
                != secure.ctime_ns
                or stat.S_IMODE(
                    after.st_mode
                ) != PROMOTED_FILE_MODE
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: mudou após fsync",
                )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def sync_directory(
        context: DirectoryContext,
        *,
        role: str,
        expected_mode: int,
    ) -> None:
        flags = os.O_RDONLY
        flags |= getattr(
            os,
            "O_DIRECTORY",
            0,
        )
        flags |= getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        try:
            descriptor = os.open(
                context.path,
                flags,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: abertura falhou",
            )

        try:
            before = os.fstat(descriptor)

            if (
                not stat.S_ISDIR(
                    before.st_mode
                )
                or before.st_uid
                != os.geteuid()
                or path_identity(before)
                != context.identity
                or stat.S_IMODE(
                    before.st_mode
                ) != expected_mode
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: identidade divergente",
                )

            try:
                os.fsync(descriptor)
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: fsync falhou",
                )

            after = os.fstat(descriptor)

            if (
                path_identity(after)
                != context.identity
                or stat.S_IMODE(
                    after.st_mode
                ) != expected_mode
            ):
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: mudou após fsync",
                )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    validate_state()

    for report in report_contexts:
        sync_file(
            report.path,
            report.secure,
            role="relatório persistido",
        )

    sync_file(
        manifest_path,
        manifest_secure,
        role="manifesto",
    )

    sync_directory(
        staging.observers,
        role="observers",
        expected_mode=(
            PROMOTED_DIRECTORY_MODE
        ),
    )

    sync_directory(
        staging.root,
        role="staging",
        expected_mode=(
            PROMOTED_DIRECTORY_MODE
        ),
    )

    revalidate_roots(roots)

    sync_directory(
        roots.generations,
        role="generations",
        expected_mode=(
            roots.generations.mode
        ),
    )

    validate_state()


def promote_generation(
    roots: RootsContext,
    staging: StagingContext,
    manifest_secure: SecureContent,
    reports: list[PersistedReportContext],
    deadline: CycleDeadline,
    renameat2: Any,
) -> Path:
    if (
        not isinstance(roots, RootsContext)
        or not isinstance(staging, StagingContext)
        or not isinstance(
            manifest_secure,
            SecureContent,
        )
        or not isinstance(reports, list)
        or not isinstance(deadline, CycleDeadline)
        or not callable(renameat2)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "promoção: contexto inválido",
        )

    generation_id = (
        staging.cycle.generation_id
    )

    parse_generation_identifier(
        generation_id
    )

    expected_staging = (
        roots.generations.path
        / (
            ".staging-"
            + generation_id
        )
    )

    final_path = (
        roots.generations.path
        / generation_id
    )

    if staging.root.path != expected_staging:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "promoção: staging divergente",
        )

    if (
        staging.observers.path
        != (
            staging.root.path
            / OBSERVERS_DIRECTORY_NAME
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "promoção: observers divergente",
        )

    report_contexts = []

    for report in reports:
        if (
            not isinstance(
                report,
                PersistedReportContext,
            )
            or not isinstance(
                report.path,
                Path,
            )
            or not isinstance(
                report.secure,
                SecureContent,
            )
            or not isinstance(
                report.descriptor,
                dict,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: relatório inválido",
            )

        module = report.descriptor.get(
            "module"
        )

        if (
            not isinstance(module, str)
            or not MODULE_PATTERN.fullmatch(
                module
            )
            or report.path
            != (
                staging.observers.path
                / f"{module}.json"
            )
            or any(
                existing.path
                == report.path
                for existing
                in report_contexts
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: relatório divergente",
            )

        report_contexts.append(report)

    manifest_path = (
        staging.root.path
        / MANIFEST_FILE_NAME
    )

    expected_observers = {
        report.path.name
        for report in report_contexts
    }

    def names(
        path: Path,
        *,
        role: str,
    ) -> set[str]:
        try:
            with os.scandir(path) as entries:
                return {
                    entry.name
                    for entry in entries
                }
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                f"{role}: enumeração falhou",
            )

    def validate_before() -> None:
        revalidate_roots(roots)
        revalidate_staging(
            roots,
            staging,
        )

        ensure_minimum_free_space(
            roots.generations.path,
            role="promoção",
        )

        if (
            stat.S_IMODE(
                os.lstat(
                    staging.root.path
                ).st_mode
            )
            != PROMOTED_DIRECTORY_MODE
            or stat.S_IMODE(
                os.lstat(
                    staging.observers.path
                ).st_mode
            )
            != PROMOTED_DIRECTORY_MODE
            or stat.S_IMODE(
                os.lstat(
                    manifest_path
                ).st_mode
            )
            != PROMOTED_FILE_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: permissões divergentes",
            )

        revalidate_secure_file(
            manifest_path,
            manifest_secure,
            role="manifesto",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

        for report in report_contexts:
            if stat.S_IMODE(
                os.lstat(
                    report.path
                ).st_mode
            ) != PROMOTED_FILE_MODE:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "promoção: relatório com permissões divergentes",
                )

            revalidate_secure_file(
                report.path,
                report.secure,
                role="relatório persistido",
                exit_code=EXIT_STRUCTURAL,
                failure_code="STRUCTURAL_FAILURE",
            )

        if names(
            staging.root.path,
            role="staging",
        ) != {
            MANIFEST_FILE_NAME,
            OBSERVERS_DIRECTORY_NAME,
        }:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: staging contém objetos inesperados",
            )

        if names(
            staging.observers.path,
            role="observers",
        ) != expected_observers:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: observers divergente",
            )

        if path_exists_without_following(
            final_path,
            role="geração",
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: destino já existe",
            )

        check_cycle_deadline(deadline)

    validate_before()

    flags = os.O_RDONLY
    flags |= getattr(
        os,
        "O_DIRECTORY",
        0,
    )
    flags |= getattr(
        os,
        "O_CLOEXEC",
        0,
    )
    flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    try:
        directory_descriptor = os.open(
            roots.generations.path,
            flags,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "promoção: generations indisponível",
        )

    promoted = False

    try:
        directory_status = os.fstat(
            directory_descriptor
        )

        if (
            not stat.S_ISDIR(
                directory_status.st_mode
            )
            or directory_status.st_uid
            != os.geteuid()
            or path_identity(
                directory_status
            ) != roots.generations.identity
            or stat.S_IMODE(
                directory_status.st_mode
            ) != roots.generations.mode
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: generations divergente",
            )

        source_name = (
            staging.root.path.name
        )
        destination_name = generation_id

        source_status = os.stat(
            source_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )

        if (
            not stat.S_ISDIR(
                source_status.st_mode
            )
            or source_status.st_uid
            != os.geteuid()
            or path_identity(
                source_status
            ) != staging.root.identity
            or stat.S_IMODE(
                source_status.st_mode
            ) != PROMOTED_DIRECTORY_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: staging divergente antes do rename",
            )

        try:
            os.stat(
                destination_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: destino não verificável",
            )
        else:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: destino já existe",
            )

        check_cycle_deadline(deadline)

        rename_noreplace(
            renameat2,
            directory_descriptor,
            source_name,
            destination_name,
            role="geração",
        )

        promoted = True

        final_status = os.stat(
            destination_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )

        if (
            not stat.S_ISDIR(
                final_status.st_mode
            )
            or final_status.st_uid
            != os.geteuid()
            or path_identity(
                final_status
            ) != staging.root.identity
            or stat.S_IMODE(
                final_status.st_mode
            ) != PROMOTED_DIRECTORY_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: geração final divergente",
            )

        try:
            os.stat(
                source_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: staging não confirmável",
            )
        else:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: staging permaneceu presente",
            )

        os.fsync(
            directory_descriptor
        )

        synchronized_status = os.fstat(
            directory_descriptor
        )

        if (
            not stat.S_ISDIR(
                synchronized_status.st_mode
            )
            or path_identity(
                synchronized_status
            ) != roots.generations.identity
            or stat.S_IMODE(
                synchronized_status.st_mode
            ) != roots.generations.mode
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: generations mudou após fsync",
            )

        final_observers = (
            final_path
            / OBSERVERS_DIRECTORY_NAME
        )

        observer_status = os.lstat(
            final_observers
        )

        if (
            not stat.S_ISDIR(
                observer_status.st_mode
            )
            or observer_status.st_uid
            != os.geteuid()
            or path_identity(
                observer_status
            ) != staging.observers.identity
            or stat.S_IMODE(
                observer_status.st_mode
            ) != PROMOTED_DIRECTORY_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: observers final divergente",
            )

        final_manifest = (
            final_path
            / MANIFEST_FILE_NAME
        )

        revalidate_secure_file(
            final_manifest,
            manifest_secure,
            role="manifesto promovido",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

        if stat.S_IMODE(
            os.lstat(
                final_manifest
            ).st_mode
        ) != PROMOTED_FILE_MODE:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: manifesto final com permissões divergentes",
            )

        if names(
            final_path,
            role="geração promovida",
        ) != {
            MANIFEST_FILE_NAME,
            OBSERVERS_DIRECTORY_NAME,
        }:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: geração final contém objetos inesperados",
            )

        if names(
            final_observers,
            role="observers promovido",
        ) != expected_observers:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "promoção: observers final divergente",
            )

        for report in report_contexts:
            final_report = (
                final_observers
                / report.path.name
            )

            revalidate_secure_file(
                final_report,
                report.secure,
                role="relatório promovido",
                exit_code=EXIT_STRUCTURAL,
                failure_code="STRUCTURAL_FAILURE",
            )

            if stat.S_IMODE(
                os.lstat(
                    final_report
                ).st_mode
            ) != PROMOTED_FILE_MODE:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "promoção: relatório final com permissões divergentes",
                )

        check_cycle_deadline(deadline)

        return final_path

    except RunnerFailure as error:
        if promoted:
            raise RunnerFailure(
                EXIT_UNKNOWN,
                "OUTCOME_UNKNOWN",
                "promoção: resultado operacional indeterminado",
            ) from error

        raise

    except OSError as error:
        if promoted:
            raise RunnerFailure(
                EXIT_UNKNOWN,
                "OUTCOME_UNKNOWN",
                "promoção: resultado operacional indeterminado",
            ) from error

        raise RunnerFailure(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "promoção: operação estrutural falhou",
        ) from error

    finally:
        try:
            os.close(
                directory_descriptor
            )
        except OSError:
            pass


def update_current_generation(
    roots: RootsContext,
    staging: StagingContext,
    generation_path: Path,
    deadline: CycleDeadline,
) -> ReferenceContext:
    if (
        not isinstance(roots, RootsContext)
        or not isinstance(
            staging,
            StagingContext,
        )
        or not isinstance(
            generation_path,
            Path,
        )
        or not isinstance(
            deadline,
            CycleDeadline,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: contexto inválido",
        )

    generation_id = (
        staging.cycle.generation_id
    )

    try:
        parse_generation_identifier(
            generation_id
        )
    except RunnerFailure as error:
        raise RunnerFailure(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: generation_id inválido",
        ) from error

    expected_generation_path = (
        roots.generations.path
        / generation_id
    )

    if (
        generation_path
        != expected_generation_path
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: geração divergente",
        )

    try:
        generation_status = os.lstat(
            generation_path
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: geração indisponível",
        )

    if (
        stat.S_ISLNK(
            generation_status.st_mode
        )
        or not stat.S_ISDIR(
            generation_status.st_mode
        )
        or generation_status.st_uid
        != os.geteuid()
        or path_identity(
            generation_status
        ) != staging.root.identity
        or stat.S_IMODE(
            generation_status.st_mode
        ) != PROMOTED_DIRECTORY_MODE
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: geração promovida divergente",
        )

    reference_path = (
        roots.state.path
        / REFERENCE_FILE_NAME
    )

    content = (
        generation_id + "\n"
    ).encode("utf-8")

    if (
        not content
        or len(content)
        > REFERENCE_MAX_BYTES
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: conteúdo inválido",
        )

    temporary_name = (
        ".current-generation-"
        + generation_id
        + ".tmp"
    )

    flags = os.O_RDONLY
    flags |= getattr(
        os,
        "O_DIRECTORY",
        0,
    )
    flags |= getattr(
        os,
        "O_CLOEXEC",
        0,
    )
    flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    try:
        state_descriptor = os.open(
            roots.state.path,
            flags,
        )
    except OSError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: STATE_ROOT indisponível",
        )

    temporary_descriptor = None
    temporary_identity = None
    published = False

    def validate_state_descriptor() -> None:
        status_result = os.fstat(
            state_descriptor
        )

        if (
            not stat.S_ISDIR(
                status_result.st_mode
            )
            or status_result.st_uid
            != os.geteuid()
            or path_identity(
                status_result
            ) != roots.state.identity
            or stat.S_IMODE(
                status_result.st_mode
            ) != roots.state.mode
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: STATE_ROOT divergente",
            )

    def validate_previous_reference() -> None:
        previous = roots.reference

        if previous is None:
            try:
                os.stat(
                    REFERENCE_FILE_NAME,
                    dir_fd=state_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return
            except OSError:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "referência atual: estado anterior não verificável",
                )

            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: referência apareceu durante o ciclo",
            )

        if (
            previous.path
            != reference_path
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: contexto anterior divergente",
            )

        try:
            current_status = os.stat(
                REFERENCE_FILE_NAME,
                dir_fd=state_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: referência anterior desapareceu",
            )

        if (
            not stat.S_ISREG(
                current_status.st_mode
            )
            or current_status.st_nlink
            != 1
            or current_status.st_uid
            != os.geteuid()
            or path_identity(
                current_status
            ) != previous.secure.identity
            or mode_exceeds(
                current_status,
                REFERENCE_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: referência anterior divergente",
            )

        revalidate_secure_file(
            reference_path,
            previous.secure,
            role="referência anterior",
            exit_code=EXIT_STRUCTURAL,
            failure_code="STRUCTURAL_FAILURE",
        )

    try:
        validate_state_descriptor()

        try:
            generations_status = os.lstat(
                roots.generations.path
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: generations indisponível",
            )

        if (
            not stat.S_ISDIR(
                generations_status.st_mode
            )
            or generations_status.st_uid
            != os.geteuid()
            or path_identity(
                generations_status
            ) != roots.generations.identity
            or stat.S_IMODE(
                generations_status.st_mode
            ) != roots.generations.mode
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: generations divergente",
            )

        validate_previous_reference()
        check_cycle_deadline(deadline)

        file_flags = (
            os.O_RDWR
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

        try:
            temporary_descriptor = os.open(
                temporary_name,
                file_flags,
                REFERENCE_MODE,
                dir_fd=state_descriptor,
            )
        except FileExistsError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: temporário em colisão",
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: criação temporária falhou",
            )

        initial_status = os.fstat(
            temporary_descriptor
        )

        temporary_identity = (
            path_identity(
                initial_status
            )
        )

        if (
            not stat.S_ISREG(
                initial_status.st_mode
            )
            or initial_status.st_nlink
            != 1
            or initial_status.st_uid
            != os.geteuid()
            or mode_exceeds(
                initial_status,
                REFERENCE_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: temporário inseguro",
            )

        offset = 0

        while offset < len(content):
            written = os.write(
                temporary_descriptor,
                content[offset:],
            )

            if written <= 0:
                fail(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "referência atual: escrita temporária incompleta",
                )

            offset += written

        os.fchmod(
            temporary_descriptor,
            REFERENCE_MODE,
        )

        os.fsync(
            temporary_descriptor
        )

        completed_status = os.fstat(
            temporary_descriptor
        )

        if (
            not stat.S_ISREG(
                completed_status.st_mode
            )
            or completed_status.st_nlink
            != 1
            or completed_status.st_uid
            != os.geteuid()
            or path_identity(
                completed_status
            ) != temporary_identity
            or completed_status.st_size
            != len(content)
            or stat.S_IMODE(
                completed_status.st_mode
            ) != REFERENCE_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: temporário divergente",
            )

        os.lseek(
            temporary_descriptor,
            0,
            os.SEEK_SET,
        )

        read_back = b""

        while len(read_back) < len(content):
            chunk = os.read(
                temporary_descriptor,
                len(content)
                - len(read_back),
            )

            if not chunk:
                break

            read_back += chunk

        trailing = os.read(
            temporary_descriptor,
            1,
        )

        if (
            read_back != content
            or trailing
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: conteúdo temporário divergente",
            )

        validate_state_descriptor()
        validate_previous_reference()
        check_cycle_deadline(deadline)

        try:
            os.rename(
                temporary_name,
                REFERENCE_FILE_NAME,
                src_dir_fd=state_descriptor,
                dst_dir_fd=state_descriptor,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: publicação atómica falhou",
            )

        published = True
        temporary_name = ""

        first_reference = (
            validate_current_reference(
                roots.state,
                roots.generations,
            )
        )

        if (
            first_reference is None
            or first_reference.generation_id
            != generation_id
            or first_reference.generation_path
            != generation_path
            or first_reference.secure.content
            != content
            or first_reference.secure.identity
            != temporary_identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: publicação divergente",
            )

        try:
            published_status = os.stat(
                REFERENCE_FILE_NAME,
                dir_fd=state_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: publicação não confirmável",
            )

        if (
            not stat.S_ISREG(
                published_status.st_mode
            )
            or published_status.st_nlink
            != 1
            or published_status.st_uid
            != os.geteuid()
            or path_identity(
                published_status
            ) != temporary_identity
            or stat.S_IMODE(
                published_status.st_mode
            ) != REFERENCE_MODE
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: modo ou identidade divergente",
            )

        os.fsync(
            state_descriptor
        )

        validate_state_descriptor()

        final_reference = (
            validate_current_reference(
                roots.state,
                roots.generations,
            )
        )

        if (
            final_reference is None
            or final_reference.generation_id
            != generation_id
            or final_reference.generation_path
            != generation_path
            or final_reference.secure.content
            != content
            or final_reference.secure.identity
            != temporary_identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "referência atual: validação final divergente",
            )

        return final_reference

    except RunnerFailure as error:
        if published:
            raise RunnerFailure(
                EXIT_UNKNOWN,
                "OUTCOME_UNKNOWN",
                "referência atual: resultado operacional indeterminado",
            ) from error

        raise

    except OSError as error:
        if published:
            raise RunnerFailure(
                EXIT_UNKNOWN,
                "OUTCOME_UNKNOWN",
                "referência atual: resultado operacional indeterminado",
            ) from error

        raise RunnerFailure(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "referência atual: operação estrutural falhou",
        ) from error

    finally:
        if temporary_descriptor is not None:
            try:
                os.close(
                    temporary_descriptor
                )
            except OSError:
                pass

        if (
            not published
            and temporary_name
            and temporary_identity
            is not None
        ):
            remove_owned_temporary_file(
                state_descriptor,
                temporary_name,
                temporary_identity,
                role="referência atual temporária",
            )

        try:
            os.close(
                state_descriptor
            )
        except OSError:
            pass



@dataclass(frozen=True)
class RunnerReportValidatorContext:
    path: Path
    secure: SecureContent
    namespace: dict[str, Any]
    validator: Any


def validate_runtime_root_for_lock(
    value: str,
) -> DirectoryContext:
    path = ensure_absolute_clean_path(
        value,
        role="RUNTIME_ROOT",
    )

    ensure_no_symlink_components(
        path,
        role="RUNTIME_ROOT",
    )

    return validate_owned_directory(
        path,
        role="RUNTIME_ROOT",
        maximum_mode=RUNTIME_ROOT_MAX_MODE,
        require_owner_write=True,
    )


def load_runner_report_validator(
    project_root: Path,
) -> RunnerReportValidatorContext:
    expected_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    if project_root != expected_root:
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "relatório final: raiz do projeto divergente",
        )

    path = (
        project_root
        / "core"
        / "validate-report.py"
    )

    secure = secure_read_file(
        path,
        SCHEMA_MAX_BYTES,
        role="Validador de Relatórios",
        exit_code=EXIT_CONFIGURATION,
        missing_code="DEPENDENCY_UNAVAILABLE",
        unsafe_code="CONFIGURATION_INVALID",
    )

    namespace: dict[str, Any] = {
        "__name__": (
            "mppt24_runner_report_validator"
        ),
        "__file__": str(path),
        "__package__": None,
        "__builtins__": __builtins__,
    }

    try:
        code = compile(
            secure.content,
            str(path),
            "exec",
        )
        exec(
            code,
            namespace,
            namespace,
        )
    except Exception as error:
        raise RunnerFailure(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "relatório final: validador inválido",
        ) from error

    required = (
        "ValidationFailure",
        "load_jsonschema_dependency",
        "load_schema",
        "enforce_depth",
        "validate_structure",
        "validate_semantics",
    )

    if any(
        name not in namespace
        for name in required
    ):
        fail(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "relatório final: API do validador inválida",
        )

    failure_class = namespace[
        "ValidationFailure"
    ]

    try:
        (
            validator_class,
            schema_error_class,
        ) = namespace[
            "load_jsonschema_dependency"
        ]()

        (
            _schema,
            validator,
        ) = namespace[
            "load_schema"
        ](
            validator_class,
            schema_error_class,
        )
    except failure_class as error:
        code_value = getattr(
            error,
            "code",
            "",
        )

        if (
            code_value
            == "DEPENDENCY_UNAVAILABLE"
        ):
            failure_code = (
                "DEPENDENCY_UNAVAILABLE"
            )
        else:
            failure_code = (
                "CONFIGURATION_INVALID"
            )

        raise RunnerFailure(
            EXIT_CONFIGURATION,
            failure_code,
            "relatório final: dependência inválida",
        ) from error
    except Exception as error:
        raise RunnerFailure(
            EXIT_CONFIGURATION,
            "CONFIGURATION_INVALID",
            "relatório final: preparação do validador falhou",
        ) from error

    revalidate_secure_file(
        path,
        secure,
        role="Validador de Relatórios",
        exit_code=EXIT_CONFIGURATION,
        failure_code="CONFIGURATION_INVALID",
    )

    return RunnerReportValidatorContext(
        path=path,
        secure=secure,
        namespace=namespace,
        validator=validator,
    )


def validate_runner_report_in_memory(
    context: RunnerReportValidatorContext,
    document: dict[str, Any],
) -> None:
    if (
        not isinstance(
            context,
            RunnerReportValidatorContext,
        )
        or not isinstance(
            document,
            dict,
        )
    ):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: contexto inválido",
        )

    revalidate_secure_file(
        context.path,
        context.secure,
        role="Validador de Relatórios",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )

    namespace = context.namespace
    failure_class = namespace[
        "ValidationFailure"
    ]

    try:
        namespace[
            "enforce_depth"
        ](
            document,
            RUNNER_REPORT_MAX_DEPTH,
        )

        namespace[
            "validate_structure"
        ](
            document,
            context.validator,
        )

        namespace[
            "validate_semantics"
        ](
            document,
            "observer-runner",
        )
    except failure_class as error:
        raise RunnerFailure(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: validação oficial falhou",
        ) from error
    except Exception as error:
        raise RunnerFailure(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: validador falhou",
        ) from error

    revalidate_secure_file(
        context.path,
        context.secure,
        role="Validador de Relatórios",
        exit_code=EXIT_STRUCTURAL,
        failure_code="STRUCTURAL_FAILURE",
    )


def runner_report_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )


def build_runner_report_document(
    state: InvocationState,
) -> dict[str, Any]:
    if not isinstance(
        state,
        InvocationState,
    ):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: estado inválido",
        )

    facts = state.facts

    document = {
        "module": "observer-runner",
        "version": RUNNER_VERSION,
        "timestamp": (
            runner_report_timestamp()
        ),
        "status": state.status,
        "confidence": state.confidence,
        "facts": {
            "result_code": (
                facts.result_code
            ),
            "lock_acquired": (
                facts.lock_acquired
            ),
            "cycle_started": (
                facts.cycle_started
            ),
            "generation_id": (
                facts.generation_id
            ),
            "generation_state": (
                facts.generation_state
            ),
            "declared": (
                facts.declared
            ),
            "successful": (
                facts.successful
            ),
            "failed": (
                facts.failed
            ),
            "reports_written": (
                facts.reports_written
            ),
            "successful_modules": (
                facts.successful_modules
            ),
            "failed_modules": (
                facts.failed_modules
            ),
            "generation_promoted": (
                facts.generation_promoted
            ),
            "current_generation_updated": (
                facts.current_generation_updated
            ),
        },
        "analysis": [],
        "conclusions": [],
        "health": {},
        "summary": list(
            state.summary
        ),
        "recommendations": list(
            state.recommendations
        ),
        "warnings": list(
            state.warnings
        ),
        "errors": list(
            state.errors
        ),
    }

    return document


def serialize_runner_report_document(
    document: dict[str, Any],
) -> bytes:
    try:
        content = (
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode(
            "utf-8",
            errors="strict",
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeEncodeError,
    ) as error:
        raise RunnerFailure(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: serialização falhou",
        ) from error

    if (
        not content
        or len(content)
        > RUNNER_REPORT_MAX_BYTES
    ):
        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "relatório final: tamanho inválido",
        )

    return content


def build_validated_runner_report(
    state: InvocationState,
    validator: RunnerReportValidatorContext,
) -> bytes:
    document = (
        build_runner_report_document(
            state
        )
    )

    validate_runner_report_in_memory(
        validator,
        document,
    )

    return serialize_runner_report_document(
        document
    )


def apply_invocation_result(
    state: InvocationState,
    exit_code: int,
    result_code: str,
    *,
    uncertain: bool = False,
) -> None:
    state.facts.result_code = result_code

    state.summary.clear()
    state.recommendations.clear()
    state.warnings.clear()
    state.errors.clear()

    if result_code == "SUCCESS":
        state.status = "OK"
        state.confidence = 100
        state.summary.append(
            "Geração completa promovida e definida como atual."
        )
        return

    if result_code == "LOCK_BUSY":
        state.status = "WARNING"
        state.confidence = 100
        state.summary.append(
            "O ciclo não foi iniciado porque o bloqueio está ocupado."
        )
        state.warnings.append(
            "Outro ciclo possui o bloqueio."
        )
        state.recommendations.append(
            "Repetir a execução depois de terminar o ciclo ativo."
        )
        return

    if result_code == "GENERATION_PARTIAL":
        state.status = "WARNING"
        state.confidence = 100
        state.summary.append(
            "Geração parcial promovida e definida como atual."
        )
        state.warnings.append(
            "Um ou mais Observers terminaram com falha normal."
        )
        return

    if result_code == "GENERATION_FAILED":
        state.status = "ERROR"
        state.confidence = 100
        state.summary.append(
            "Geração falhada promovida e definida como atual."
        )
        state.errors.append(
            "Nenhum Observer terminou com sucesso."
        )
        return

    if result_code == "OUTCOME_UNKNOWN":
        state.status = "UNKNOWN"
        state.confidence = 0
        state.summary.append(
            "O resultado operacional não pôde ser determinado."
        )
        state.errors.append(
            "Uma operação crítica ocorreu sem confirmação durável."
        )
        return

    if result_code == "INTERNAL_ERROR":
        if uncertain:
            state.status = "UNKNOWN"
            state.confidence = 0
        else:
            state.status = "ERROR"
            state.confidence = 100

        state.summary.append(
            "A invocação terminou com uma falha interna."
        )
        state.errors.append(
            "O Runner encontrou uma falha interna inesperada."
        )
        return

    state.status = "ERROR"
    state.confidence = 100

    messages = {
        "USAGE_INVALID": (
            "Os argumentos da invocação são inválidos."
        ),
        "CONFIGURATION_INVALID": (
            "A configuração local é inválida."
        ),
        "DEPENDENCY_UNAVAILABLE": (
            "Uma dependência obrigatória está indisponível."
        ),
        "STRUCTURAL_FAILURE": (
            "O ciclo foi interrompido por uma falha estrutural."
        ),
    }

    message = messages.get(
        result_code,
        "A invocação terminou com uma falha controlada.",
    )

    state.summary.append(message)
    state.errors.append(message)


def cleanup_owned_staging(
    roots: RootsContext,
    staging: StagingContext,
    configuration: ConfigurationContext,
) -> None:
    if (
        not isinstance(
            roots,
            RootsContext,
        )
        or not isinstance(
            staging,
            StagingContext,
        )
        or not isinstance(
            configuration,
            ConfigurationContext,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limpeza: contexto inválido",
        )

    revalidate_roots(roots)
    revalidate_staging(
        roots,
        staging,
    )
    revalidate_configuration(
        configuration
    )

    generation_id = (
        staging.cycle.generation_id
    )

    expected_name = (
        ".staging-"
        + generation_id
    )

    if (
        staging.root.path.parent
        != roots.generations.path
        or staging.root.path.name
        != expected_name
        or staging.observers.path
        != (
            staging.root.path
            / OBSERVERS_DIRECTORY_NAME
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limpeza: caminho divergente",
        )

    final_name = generation_id

    flags = os.O_RDONLY
    flags |= getattr(
        os,
        "O_DIRECTORY",
        0,
    )
    flags |= getattr(
        os,
        "O_CLOEXEC",
        0,
    )
    flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    generations_fd = None
    staging_fd = None
    observers_fd = None

    try:
        generations_fd = os.open(
            roots.generations.path,
            flags,
        )

        generations_status = os.fstat(
            generations_fd
        )

        if (
            not stat.S_ISDIR(
                generations_status.st_mode
            )
            or generations_status.st_uid
            != os.geteuid()
            or path_identity(
                generations_status
            ) != roots.generations.identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: generations divergente",
            )

        try:
            os.stat(
                final_name,
                dir_fd=generations_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: promoção não verificável",
            )
        else:
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: promoção possivelmente ocorrida",
            )

        staging_fd = os.open(
            expected_name,
            flags,
            dir_fd=generations_fd,
        )

        staging_status = os.fstat(
            staging_fd
        )

        if (
            not stat.S_ISDIR(
                staging_status.st_mode
            )
            or staging_status.st_uid
            != os.geteuid()
            or path_identity(
                staging_status
            ) != staging.root.identity
            or staging_status.st_dev
            != generations_status.st_dev
            or mode_exceeds(
                staging_status,
                STAGING_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: staging divergente",
            )

        root_names = set(
            os.listdir(
                staging_fd
            )
        )

        allowed_root_names = {
            OBSERVERS_DIRECTORY_NAME,
            MANIFEST_FILE_NAME,
        }

        if not root_names.issubset(
            allowed_root_names
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: objeto desconhecido na staging",
            )

        if (
            OBSERVERS_DIRECTORY_NAME
            not in root_names
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: observers ausente",
            )

        observers_fd = os.open(
            OBSERVERS_DIRECTORY_NAME,
            flags,
            dir_fd=staging_fd,
        )

        observers_status = os.fstat(
            observers_fd
        )

        if (
            not stat.S_ISDIR(
                observers_status.st_mode
            )
            or observers_status.st_uid
            != os.geteuid()
            or path_identity(
                observers_status
            ) != staging.observers.identity
            or observers_status.st_dev
            != staging_status.st_dev
            or mode_exceeds(
                observers_status,
                STAGING_MODE,
            )
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: observers divergente",
            )

        registered_modules = {
            entry["module"]
            for entry
            in configuration.registry.document[
                "observers"
            ]
        }

        allowed_reports = {
            f"{module}.json"
            for module in registered_modules
        }

        observer_names = set(
            os.listdir(
                observers_fd
            )
        )

        if not observer_names.issubset(
            allowed_reports
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "limpeza: relatório desconhecido",
            )

        def validate_regular(
            directory_fd: int,
            name: str,
            *,
            role: str,
        ) -> None:
            file_flags = os.O_RDONLY
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

            descriptor = None

            try:
                descriptor = os.open(
                    name,
                    file_flags,
                    dir_fd=directory_fd,
                )

                status_result = os.fstat(
                    descriptor
                )

                if (
                    not stat.S_ISREG(
                        status_result.st_mode
                    )
                    or status_result.st_nlink
                    != 1
                    or status_result.st_uid
                    != os.geteuid()
                    or status_result.st_dev
                    != staging_status.st_dev
                    or mode_exceeds(
                        status_result,
                        STAGING_FILE_MODE,
                    )
                ):
                    fail(
                        EXIT_STRUCTURAL,
                        "STRUCTURAL_FAILURE",
                        f"{role}: objeto inseguro",
                    )

                path_status = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )

                if (
                    stat.S_ISLNK(
                        path_status.st_mode
                    )
                    or path_identity(
                        path_status
                    ) != path_identity(
                        status_result
                    )
                ):
                    fail(
                        EXIT_STRUCTURAL,
                        "STRUCTURAL_FAILURE",
                        f"{role}: identidade divergente",
                    )
            except RunnerFailure:
                raise
            except OSError as error:
                raise RunnerFailure(
                    EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    f"{role}: validação falhou",
                ) from error
            finally:
                if descriptor is not None:
                    try:
                        os.close(
                            descriptor
                        )
                    except OSError:
                        pass

        for name in sorted(
            observer_names
        ):
            validate_regular(
                observers_fd,
                name,
                role="limpeza de relatório",
            )

        if (
            MANIFEST_FILE_NAME
            in root_names
        ):
            validate_regular(
                staging_fd,
                MANIFEST_FILE_NAME,
                role="limpeza de manifesto",
            )

        os.fchmod(
            observers_fd,
            STAGING_MODE,
        )
        os.fchmod(
            staging_fd,
            STAGING_MODE,
        )

        for name in sorted(
            observer_names
        ):
            os.unlink(
                name,
                dir_fd=observers_fd,
            )

        os.fsync(
            observers_fd
        )

        os.close(
            observers_fd
        )
        observers_fd = None

        os.rmdir(
            OBSERVERS_DIRECTORY_NAME,
            dir_fd=staging_fd,
        )

        if (
            MANIFEST_FILE_NAME
            in root_names
        ):
            os.unlink(
                MANIFEST_FILE_NAME,
                dir_fd=staging_fd,
            )

        os.fsync(
            staging_fd
        )

        os.close(
            staging_fd
        )
        staging_fd = None

        os.rmdir(
            expected_name,
            dir_fd=generations_fd,
        )

        os.fsync(
            generations_fd
        )

    except RunnerFailure:
        raise
    except OSError as error:
        raise RunnerFailure(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "limpeza: operação falhou",
        ) from error
    finally:
        for descriptor in (
            observers_fd,
            staging_fd,
            generations_fd,
        ):
            if descriptor is None:
                continue

            try:
                os.close(
                    descriptor
                )
            except OSError:
                pass


def run_cycle(
    state: InvocationState,
    roots: RootsContext,
    configuration: ConfigurationContext,
    lock: LockContext,
    deadline: CycleDeadline,
    renameat2: Any,
) -> tuple[int, str]:
    staging = None

    try:
        revalidate_lock(lock)
        revalidate_roots(roots)
        revalidate_configuration(
            configuration
        )

        registry_entries = (
            configuration
            .registry
            .document[
                "observers"
            ]
        )

        state.facts.declared = len(
            registry_entries
        )

        ensure_minimum_free_space(
            roots.generations.path,
            role="geração",
        )

        cycle = create_cycle_identity(
            state
        )

        staging = create_staging(
            roots,
            cycle,
        )

        captures: list[
            CaptureResultContext
        ] = []

        for entry in registry_entries:
            revalidate_lock(lock)

            capture = (
                invoke_capture_process(
                    roots,
                    staging,
                    configuration,
                    deadline,
                    entry["module"],
                )
            )

            captures.append(
                capture
            )

        reports: list[
            PersistedReportContext
        ] = []

        for capture in captures:
            if capture.outcome != "SUCCESS":
                continue

            report = (
                validate_persisted_report(
                    capture,
                    configuration=configuration,
                    roots=roots,
                    staging=staging,
                    deadline=deadline,
                )
            )

            reports.append(report)

        modules = build_manifest_modules(
            captures,
            reports,
            configuration=configuration,
        )

        successful_modules = [
            capture.module
            for capture in captures
            if capture.outcome == "SUCCESS"
        ]

        failed_modules = [
            capture.module
            for capture in captures
            if capture.outcome == "FAILED"
        ]

        state.facts.successful = len(
            successful_modules
        )
        state.facts.failed = len(
            failed_modules
        )
        state.facts.reports_written = len(
            reports
        )
        state.facts.successful_modules = (
            successful_modules
        )
        state.facts.failed_modules = (
            failed_modules
        )

        completed_at = (
            create_completed_at(
                cycle
            )
        )

        manifest_document = (
            build_manifest_document(
                modules,
                configuration=configuration,
                cycle=cycle,
                completed_at=completed_at,
            )
        )

        state.facts.generation_state = (
            manifest_document[
                "state"
            ]
        )

        ensure_minimum_free_space(
            staging.root.path,
            role="manifesto",
        )

        manifest_content = (
            serialize_manifest_document(
                manifest_document
            )
        )

        manifest_secure = (
            persist_manifest(
                roots,
                staging,
                manifest_content,
                renameat2,
            )
        )

        validate_manifest_official(
            roots,
            staging,
            manifest_secure,
            reports,
            deadline,
        )

        (
            staging,
            manifest_secure,
            reports,
        ) = apply_final_permissions(
            roots,
            staging,
            manifest_secure,
            reports,
            deadline,
        )

        validate_manifest_official(
            roots,
            staging,
            manifest_secure,
            reports,
            deadline,
        )

        synchronize_generation(
            roots,
            staging,
            manifest_secure,
            reports,
            deadline,
        )

        revalidate_lock(lock)

        ensure_minimum_free_space(
            roots.generations.path,
            role="promoção",
        )

        try:
            generation_path = (
                promote_generation(
                    roots,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                    renameat2,
                )
            )
        except RunnerFailure as error:
            if (
                error.exit_code
                == EXIT_UNKNOWN
            ):
                state.facts.generation_promoted = (
                    None
                )

            raise

        state.facts.generation_promoted = True

        revalidate_lock(lock)

        try:
            update_current_generation(
                roots,
                staging,
                generation_path,
                deadline,
            )
        except RunnerFailure as error:
            if (
                error.exit_code
                == EXIT_UNKNOWN
            ):
                state.facts.current_generation_updated = (
                    None
                )

            raise

        state.facts.current_generation_updated = (
            True
        )

        generation_state = (
            state.facts.generation_state
        )

        if generation_state == "COMPLETE":
            return (
                EXIT_SUCCESS,
                "SUCCESS",
            )

        if generation_state == "PARTIAL":
            return (
                EXIT_PARTIAL,
                "GENERATION_PARTIAL",
            )

        if generation_state == "FAILED":
            return (
                EXIT_FAILED,
                "GENERATION_FAILED",
            )

        fail(
            EXIT_INTERNAL,
            "INTERNAL_ERROR",
            "ciclo: estado final inválido",
        )

    except BaseException as error:
        if (
            staging is not None
            and state.facts.generation_promoted
            is False
        ):
            try:
                if path_exists_without_following(
                    staging.root.path,
                    role="staging",
                ):
                    cleanup_owned_staging(
                        roots,
                        staging,
                        configuration,
                    )
            except RunnerFailure as cleanup_error:
                raise cleanup_error from error

        raise


def emit_runner_diagnostic(
    code: str,
    message: str,
) -> None:
    fields = (
        "ERROR",
        sanitize_message(code),
        "runner",
        sanitize_message(message),
    )

    print(
        "\t".join(fields),
        file=sys.stderr,
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    effective_argv = (
        sys.argv[1:]
        if argv is None
        else argv
    )

    state = InvocationState()

    project_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    validator = None
    lock = None
    exit_code = EXIT_INTERNAL

    try:
        arguments = parse_arguments(
            effective_argv
        )

        validator = (
            load_runner_report_validator(
                project_root
            )
        )

        runtime = (
            validate_runtime_root_for_lock(
                arguments.runtime_root
            )
        )

        lock = acquire_lock(
            runtime
        )

        state.facts.lock_acquired = True

        deadline = (
            start_cycle_deadline()
        )

        roots = validate_roots(
            arguments.state_root,
            arguments.runtime_root,
        )

        if (
            roots.runtime.identity
            != runtime.identity
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "RUNTIME_ROOT mudou durante a aquisição do bloqueio",
            )

        revalidate_lock(lock)

        configuration = (
            load_configuration(
                project_root
            )
        )

        renameat2 = (
            load_rename_noreplace()
        )

        (
            exit_code,
            result_code,
        ) = run_cycle(
            state,
            roots,
            configuration,
            lock,
            deadline,
            renameat2,
        )

        apply_invocation_result(
            state,
            exit_code,
            result_code,
        )

    except RunnerFailure as error:
        exit_code = error.exit_code

        if error.exit_code == EXIT_UNKNOWN:
            if (
                state.facts.generation_promoted
                is not True
                and state.facts.generation_promoted
                is not None
            ):
                state.facts.generation_promoted = (
                    None
                )

        apply_invocation_result(
            state,
            exit_code,
            error.code,
            uncertain=(
                error.exit_code
                == EXIT_UNKNOWN
            ),
        )

    except Exception:
        exit_code = EXIT_INTERNAL

        uncertain = (
            state.facts.generation_promoted
            is None
            or state.facts.current_generation_updated
            is None
        )

        apply_invocation_result(
            state,
            exit_code,
            "INTERNAL_ERROR",
            uncertain=uncertain,
        )

    if validator is None:
        try:
            validator = (
                load_runner_report_validator(
                    project_root
                )
            )
        except RunnerFailure:
            if lock is not None:
                try:
                    release_lock(lock)
                except Exception:
                    pass

            emit_runner_diagnostic(
                "RUNNER_REPORT_UNAVAILABLE",
                "não foi possível preparar o relatório final",
            )

            return exit_code
        except Exception:
            if lock is not None:
                try:
                    release_lock(lock)
                except Exception:
                    pass

            emit_runner_diagnostic(
                "RUNNER_REPORT_UNAVAILABLE",
                "não foi possível preparar o relatório final",
            )

            return exit_code

    try:
        report_content = (
            build_validated_runner_report(
                state,
                validator,
            )
        )
    except RunnerFailure as error:
        if lock is not None:
            try:
                release_lock(lock)
            except Exception:
                pass

        emit_runner_diagnostic(
            error.code,
            "não foi possível validar o relatório final",
        )

        return error.exit_code
    except Exception:
        if lock is not None:
            try:
                release_lock(lock)
            except Exception:
                pass

        emit_runner_diagnostic(
            "INTERNAL_ERROR",
            "não foi possível construir o relatório final",
        )

        return EXIT_INTERNAL

    if lock is not None:
        try:
            release_lock(lock)
        except Exception:
            emit_runner_diagnostic(
                "STRUCTURAL_FAILURE",
                "não foi possível libertar o bloqueio",
            )

            return EXIT_STRUCTURAL

    try:
        sys.stdout.buffer.write(
            report_content
        )
        sys.stdout.buffer.flush()
    except Exception:
        emit_runner_diagnostic(
            "STRUCTURAL_FAILURE",
            "não foi possível emitir o relatório final",
        )

        return EXIT_STRUCTURAL

    return exit_code


def serialize_manifest_document(
    document: dict[str, Any],
) -> bytes:
    if not isinstance(document, dict):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: documento inválido",
        )

    try:
        content = (
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode(
            "utf-8",
            errors="strict",
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeEncodeError,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: serialização inválida",
        )

    if len(content) > MANIFEST_MAX_BYTES:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: tamanho excedido",
        )

    return content


def build_manifest_document(
    modules: Sequence[dict[str, Any]],
    *,
    configuration: ConfigurationContext,
    cycle: CycleIdentity,
    completed_at: str,
) -> dict[str, Any]:
    if (
        not isinstance(
            modules,
            Sequence,
        )
        or isinstance(
            modules,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: módulos inválidos",
        )

    if not isinstance(
        configuration,
        ConfigurationContext,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: configuração inválida",
        )

    if not isinstance(
        cycle,
        CycleIdentity,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: ciclo inválido",
        )

    if not isinstance(
        completed_at,
        str,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: conclusão inválida",
        )

    try:
        completed_datetime = (
            datetime.strptime(
                completed_at,
                "%Y-%m-%dT%H:%M:%S.%fZ",
            ).replace(
                tzinfo=timezone.utc
            )
        )
    except ValueError:
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: conclusão inválida",
        )

    if (
        format_manifest_timestamp(
            completed_datetime
        )
        != completed_at
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: conclusão inválida",
        )

    if (
        completed_datetime
        < cycle.started_datetime
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: intervalo UTC inválido",
        )

    if (
        cycle.started_at
        != format_manifest_timestamp(
            cycle.started_datetime
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: início divergente",
        )

    if (
        parse_generation_identifier(
            cycle.generation_id
        )
        != cycle.started_datetime
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: geração divergente",
        )

    registry_document = (
        configuration.registry.document
    )

    if not isinstance(
        registry_document,
        dict,
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: registo inválido",
        )

    registry_version = (
        registry_document.get(
            "registry_version"
        )
    )
    registered = registry_document.get(
        "observers"
    )

    if (
        registry_version != "1.0.0"
        or not isinstance(
            registered,
            list,
        )
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: registo incompatível",
        )

    registry_sha256 = (
        configuration.registry.sha256
    )

    if (
        not isinstance(
            registry_sha256,
            str,
        )
        or re.fullmatch(
            r"[0-9a-f]{64}",
            registry_sha256,
        )
        is None
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: hash do registo inválido",
        )

    declared = len(modules)

    if (
        declared == 0
        or declared != len(registered)
    ):
        fail(
            EXIT_STRUCTURAL,
            "STRUCTURAL_FAILURE",
            "manifesto: quantidade de módulos inválida",
        )

    manifest_modules: list[
        dict[str, Any]
    ] = []
    successful = 0

    for entry in modules:
        if not isinstance(
            entry,
            dict,
        ):
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: entrada de módulo inválida",
            )

        outcome = entry.get(
            "outcome"
        )

        if outcome == "SUCCESS":
            successful += 1
        elif outcome != "FAILED":
            fail(
                EXIT_STRUCTURAL,
                "STRUCTURAL_FAILURE",
                "manifesto: outcome inválido",
            )

        manifest_modules.append(
            dict(entry)
        )

    failed = (
        declared
        - successful
    )

    if successful == declared:
        state = "COMPLETE"
    elif successful == 0:
        state = "FAILED"
    else:
        state = "PARTIAL"

    summary = {
        "declared": declared,
        "successful": successful,
        "failed": failed,
        "reports_written": successful,
    }

    return {
        "manifest_version": "1.0.0",
        "generation_id": (
            cycle.generation_id
        ),
        "started_at": (
            cycle.started_at
        ),
        "completed_at": completed_at,
        "state": state,
        "runner": {
            "module": "observer-runner",
            "version": RUNNER_VERSION,
        },
        "registry": {
            "version": registry_version,
            "hash_algorithm": "sha256",
            "sha256": registry_sha256,
        },
        "summary": summary,
        "modules": manifest_modules,
    }


if __name__ == "__main__":
    raise SystemExit(main())
