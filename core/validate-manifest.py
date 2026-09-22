#!/usr/bin/python3 -I
"""
MPPT24 CORE
Validador de manifestos e gerações, contrato 1.0.0.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Sequence

sys.dont_write_bytecode = True

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_GENERATION = 4
EXIT_INPUT = 5
EXIT_CONTRACT = 6
EXIT_SEMANTIC = 7
EXIT_MISMATCH = 8
EXIT_INTERNAL = 9

MANIFEST_MAX_BYTES = 262144
SCHEMA_MAX_BYTES = 1024 * 1024
REGISTRY_MAX_BYTES = 65536
MANIFEST_MAX_DEPTH = 32
DIAGNOSTIC_MESSAGE_LIMIT = 240

EXPECTED_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)
EXPECTED_MANIFEST_SCHEMA_ID = (
    "urn:mppt24:schema:generation-manifest:1.0.0"
)
EXPECTED_REGISTRY_SCHEMA_ID = (
    "urn:mppt24:schema:observer-registry:1.0.0"
)

GENERATION_ID_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$"
)
MANIFEST_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}Z$"
)
MODULE_PATTERN = re.compile(
    r"^[a-z0-9]+(-[a-z0-9]+)*$"
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

RECORDABLE_FAILURE_CODES = {
    "EXECUTABLE_MISSING",
    "EXECUTABLE_INVALID",
    "EXECUTION_FAILED",
    "EXECUTION_TIMEOUT",
    "OUTPUT_LIMIT_EXCEEDED",
    "STDERR_LIMIT_EXCEEDED",
    "EMPTY_REPORT",
    "INVALID_JSON",
    "CONTRACT_VIOLATION",
    "MODULE_MISMATCH",
}


class ValidationFailure(Exception):
    """Falha prevista e controlada pelo contrato."""

    def __init__(
        self,
        exit_code: int,
        code: str,
        location: str,
        message: str,
        *,
        reported: bool = False,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.location = location
        self.message = message
        self.reported = reported


def fail(
    exit_code: int,
    code: str,
    location: str,
    message: str,
    *,
    reported: bool = False,
) -> NoReturn:
    raise ValidationFailure(
        exit_code,
        code,
        location,
        message,
        reported=reported,
    )


def sanitize(value: object) -> str:
    text = str(value)
    controlled = "".join(
        " "
        if character in "\t\r\n"
        or ord(character) < 32
        else character
        for character in text
    )
    return controlled[:DIAGNOSTIC_MESSAGE_LIMIT]


def emit_diagnostic(
    code: str,
    location: str,
    message: str,
) -> None:
    print(
        "ERROR",
        code,
        sanitize(location),
        sanitize(message),
        sep="\t",
        file=sys.stderr,
    )


class ContractArgumentParser(argparse.ArgumentParser):
    """ArgumentParser com falhas controladas."""

    def error(self, message: str) -> NoReturn:
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "arguments",
            message,
        )


def parse_arguments(
    argv: Sequence[str],
) -> argparse.Namespace:
    unique_options = {
        "--help",
        "--expected-generation-id",
        "--emit-validated-snapshot",
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
                option,
                "a opção não pode ser repetida",
            )

        seen_options.add(option)

    parser = ContractArgumentParser(
        prog="validate-manifest.py",
        description=(
            "Validar um manifesto e uma geração MPPT24."
        ),
    )
    parser.add_argument(
        "--expected-generation-id",
        required=True,
    )
    parser.add_argument(
        "--emit-validated-snapshot",
        action="store_true",
    )
    parser.add_argument(
        "generation_directory",
    )

    return parser.parse_args(argv)


class DuplicateKeyError(ValueError):
    """Objeto JSON com chave repetida."""


class NonFiniteNumberError(ValueError):
    """Número não finito proibido pelo contrato."""


@dataclass(frozen=True)
class SecureContent:
    content: bytes
    identity: tuple[int, int]
    size: int
    mtime_ns: int
    ctime_ns: int


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
        return 1 + max(
            (
                container_depth(child)
                for child in value.values()
            ),
            default=0,
        )

    if isinstance(value, list):
        return 1 + max(
            (
                container_depth(child)
                for child in value
            ),
            default=0,
        )

    return 0


def parse_json_strict(
    content: bytes,
    *,
    location: str,
    exit_code: int,
    invalid_utf8_code: str,
    invalid_json_code: str,
    duplicate_key_code: str,
    non_finite_code: str,
    depth_code: str,
    maximum_depth: int,
) -> object:
    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        fail(
            exit_code,
            invalid_utf8_code,
            location,
            "conteúdo não é UTF-8 válido",
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
            duplicate_key_code,
            location,
            "objeto contém chave duplicada",
        )
    except NonFiniteNumberError:
        fail(
            exit_code,
            non_finite_code,
            location,
            "documento contém número não finito",
        )
    except json.JSONDecodeError:
        fail(
            exit_code,
            invalid_json_code,
            location,
            "documento JSON inválido",
        )

    if container_depth(document) > maximum_depth:
        fail(
            exit_code,
            depth_code,
            location,
            "documento excede a profundidade máxima",
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


def secure_read_file(
    path: Path,
    maximum_bytes: int,
    *,
    location: str,
    exit_code: int,
    missing_code: str,
    unreadable_code: str,
    too_large_code: str,
    require_single_link: bool,
) -> SecureContent:
    try:
        path_status = os.lstat(path)
    except FileNotFoundError:
        fail(
            exit_code,
            missing_code,
            location,
            "ficheiro ausente",
        )
    except OSError:
        fail(
            exit_code,
            unreadable_code,
            location,
            "não foi possível inspecionar o ficheiro",
        )

    if stat.S_ISLNK(path_status.st_mode):
        fail(
            exit_code,
            unreadable_code,
            location,
            "ficheiro não pode ser link simbólico",
        )

    if not stat.S_ISREG(path_status.st_mode):
        fail(
            exit_code,
            unreadable_code,
            location,
            "objeto não é ficheiro regular",
        )

    if (
        require_single_link
        and path_status.st_nlink != 1
    ):
        fail(
            exit_code,
            unreadable_code,
            location,
            "ficheiro possui ligações adicionais",
        )

    if path_status.st_size > maximum_bytes:
        fail(
            exit_code,
            too_large_code,
            location,
            "ficheiro excede o limite",
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        descriptor = os.open(path, flags)
    except OSError:
        fail(
            exit_code,
            unreadable_code,
            location,
            "não foi possível abrir o ficheiro",
        )

    try:
        opened_status = os.fstat(descriptor)

        if (
            not stat.S_ISREG(opened_status.st_mode)
            or status_signature(opened_status)
            != status_signature(path_status)
        ):
            fail(
                exit_code,
                unreadable_code,
                location,
                "ficheiro mudou durante a abertura",
            )

        chunks = []
        observed = 0

        while True:
            try:
                chunk = os.read(
                    descriptor,
                    min(
                        65536,
                        maximum_bytes + 1 - observed,
                    ),
                )
            except OSError:
                fail(
                    exit_code,
                    unreadable_code,
                    location,
                    "falha durante a leitura",
                )

            if not chunk:
                break

            chunks.append(chunk)
            observed += len(chunk)

            if observed > maximum_bytes:
                fail(
                    exit_code,
                    too_large_code,
                    location,
                    "ficheiro excede o limite",
                )

        completed_status = os.fstat(descriptor)

        if (
            status_signature(completed_status)
            != status_signature(opened_status)
        ):
            fail(
                exit_code,
                unreadable_code,
                location,
                "ficheiro mudou durante a leitura",
            )

        content = b"".join(chunks)

        if len(content) != completed_status.st_size:
            fail(
                exit_code,
                unreadable_code,
                location,
                "leitura incompleta",
            )

        return SecureContent(
            content=content,
            identity=(
                completed_status.st_dev,
                completed_status.st_ino,
            ),
            size=completed_status.st_size,
            mtime_ns=completed_status.st_mtime_ns,
            ctime_ns=completed_status.st_ctime_ns,
        )
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class RegistryContext:
    document: dict[str, Any]
    content: bytes
    sha256: str


def load_jsonschema_dependency() -> tuple[Any, Any]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "dependency",
            "python3-jsonschema indisponível",
        )

    return Draft202012Validator, SchemaError


def external_references(
    document: object,
) -> list[str]:
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


def parse_configuration_json(
    content: bytes,
    *,
    location: str,
    code: str,
) -> object:
    return parse_json_strict(
        content,
        location=location,
        exit_code=EXIT_CONFIGURATION,
        invalid_utf8_code=code,
        invalid_json_code=code,
        duplicate_key_code=code,
        non_finite_code=code,
        depth_code=code,
        maximum_depth=MANIFEST_MAX_DEPTH,
    )


def load_schema(
    path: Path,
    expected_identifier: str,
    *,
    location: str,
    failure_code: str,
    validator_class: Any,
    schema_error_class: Any,
) -> dict[str, Any]:
    secure = secure_read_file(
        path,
        SCHEMA_MAX_BYTES,
        location=location,
        exit_code=EXIT_CONFIGURATION,
        missing_code=failure_code,
        unreadable_code=failure_code,
        too_large_code=failure_code,
        require_single_link=False,
    )
    document = parse_configuration_json(
        secure.content,
        location=location,
        code=failure_code,
    )

    if (
        not isinstance(document, dict)
        or document.get("$schema")
        != EXPECTED_DIALECT
        or document.get("$id")
        != expected_identifier
    ):
        fail(
            EXIT_CONFIGURATION,
            failure_code,
            location,
            "identidade ou dialecto inválido",
        )

    if external_references(document):
        fail(
            EXIT_CONFIGURATION,
            failure_code,
            location,
            "schema contém referência externa",
        )

    try:
        validator_class.check_schema(document)
    except schema_error_class:
        fail(
            EXIT_CONFIGURATION,
            failure_code,
            location,
            "schema local inválido",
        )

    return document


def validate_registry_semantics(
    registry: dict[str, Any],
) -> None:
    modules = [
        entry["module"]
        for entry in registry["observers"]
    ]

    if modules != EXPECTED_MODULES:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registry",
            "lista ou ordem de módulos incompatível",
        )

    if len(modules) != len(set(modules)):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registry",
            "módulos duplicados",
        )

    executables = [
        entry["executable"]
        for entry in registry["observers"]
    ]

    if len(executables) != len(set(executables)):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registry",
            "executáveis duplicados",
        )

    expected_limits = {
        "observer_timeout_seconds": 30,
        "stdout_max_bytes": 262144,
        "stderr_max_bytes": 65536,
        "report_max_bytes": 262144,
        "json_max_depth": 32,
        "max_observers": 32,
    }

    if registry["limits"] != expected_limits:
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registry",
            "limites do registo incompatíveis",
        )

    for entry in registry["observers"]:
        module = entry["module"]

        if entry["required"] is not True:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "registry",
                "Observer deve ser obrigatório",
            )

        if entry["module_versions"] != ["1.0.0"]:
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "registry",
                "versão de módulo incompatível",
            )

        if entry["output_contract"] != "2.1.0":
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "registry",
                "contrato de saída incompatível",
            )

        if (
            entry["executable"]
            != f"observer/{module}.sh"
        ):
            fail(
                EXIT_CONFIGURATION,
                "REGISTRY_INVALID",
                "registry",
                "módulo e executável divergem",
            )


def load_configuration(
    project_root: Path,
) -> tuple[
    Any,
    dict[str, Any],
    RegistryContext,
]:
    validator_class, schema_error_class = (
        load_jsonschema_dependency()
    )

    manifest_schema = load_schema(
        (
            project_root
            / "schemas"
            / "generation-manifest"
            / "1.0.0"
            / "generation-manifest.schema.json"
        ),
        EXPECTED_MANIFEST_SCHEMA_ID,
        location="manifest-schema",
        failure_code="SCHEMA_INVALID",
        validator_class=validator_class,
        schema_error_class=schema_error_class,
    )

    registry_schema = load_schema(
        (
            project_root
            / "schemas"
            / "observer-registry"
            / "1.0.0"
            / "observer-registry.schema.json"
        ),
        EXPECTED_REGISTRY_SCHEMA_ID,
        location="registry-schema",
        failure_code="REGISTRY_INVALID",
        validator_class=validator_class,
        schema_error_class=schema_error_class,
    )

    registry_secure = secure_read_file(
        (
            project_root
            / "config"
            / "observer-registry.json"
        ),
        REGISTRY_MAX_BYTES,
        location="registry",
        exit_code=EXIT_CONFIGURATION,
        missing_code="REGISTRY_INVALID",
        unreadable_code="REGISTRY_INVALID",
        too_large_code="REGISTRY_INVALID",
        require_single_link=False,
    )
    registry = parse_configuration_json(
        registry_secure.content,
        location="registry",
        code="REGISTRY_INVALID",
    )

    errors = list(
        validator_class(
            registry_schema
        ).iter_errors(registry)
    )

    if errors or not isinstance(registry, dict):
        fail(
            EXIT_CONFIGURATION,
            "REGISTRY_INVALID",
            "registry",
            "registo viola o schema",
        )

    validate_registry_semantics(registry)

    registry_context = RegistryContext(
        document=registry,
        content=registry_secure.content,
        sha256=hashlib.sha256(
            registry_secure.content
        ).hexdigest(),
    )

    return (
        validator_class,
        manifest_schema,
        registry_context,
    )


def json_pointer(path: Sequence[object]) -> str:
    if not path:
        return ""

    escaped = [
        str(component)
        .replace("~", "~0")
        .replace("/", "~1")
        for component in path
    ]
    return "/" + "/".join(escaped)


def validate_manifest_schema(
    validator_class: Any,
    schema: dict[str, Any],
    document: object,
) -> None:
    errors = sorted(
        validator_class(schema).iter_errors(
            document
        ),
        key=lambda error: (
            tuple(
                str(component)
                for component in error.absolute_path
            ),
            str(error.validator),
        ),
    )

    if not errors:
        return

    for error in errors:
        rule = str(error.validator)
        emit_diagnostic(
            "CONTRACT_VIOLATION",
            json_pointer(error.absolute_path),
            f"violação da regra {rule}",
        )

    fail(
        EXIT_CONTRACT,
        "CONTRACT_VIOLATION",
        "",
        "manifesto viola o schema",
        reported=True,
    )


def parse_generation_identifier(
    value: str,
) -> datetime:
    if not GENERATION_ID_PATTERN.fullmatch(value):
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation_id",
            "identificador de geração inválido",
        )

    temporal = value.split("-", 1)[0]

    try:
        return datetime.strptime(
            temporal,
            "%Y%m%dT%H%M%S%fZ",
        )
    except ValueError:
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation_id",
            "data do identificador inválida",
        )


def parse_manifest_timestamp(
    value: str,
    location: str,
) -> datetime:
    if not MANIFEST_TIMESTAMP_PATTERN.fullmatch(
        value
    ):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            location,
            "timestamp do manifesto inválido",
        )

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )
    except ValueError:
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            location,
            "timestamp semanticamente inválido",
        )


def expected_state(
    declared: int,
    successful: int,
) -> str:
    if successful == declared:
        return "COMPLETE"

    if successful == 0:
        return "FAILED"

    return "PARTIAL"


def validate_manifest_semantics(
    document: dict[str, Any],
    expected_identifier: str,
    registry: RegistryContext,
) -> None:
    if document["generation_id"] != expected_identifier:
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/generation_id",
            "identificador diverge do esperado",
        )

    identifier_time = parse_generation_identifier(
        document["generation_id"]
    )
    started = parse_manifest_timestamp(
        document["started_at"],
        "/started_at",
    )
    completed = parse_manifest_timestamp(
        document["completed_at"],
        "/completed_at",
    )

    if completed < started:
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/completed_at",
            "conclusão anterior ao início",
        )

    if identifier_time != started:
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/generation_id",
            "identificador não corresponde ao início",
        )

    registry_document = registry.document

    if (
        document["registry"]["version"]
        != registry_document["registry_version"]
    ):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/registry/version",
            "versão do registo divergente",
        )

    if (
        document["registry"]["sha256"]
        != registry.sha256
    ):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/registry/sha256",
            "hash do registo divergente",
        )

    entries = document["modules"]
    registered = registry_document["observers"]
    summary = document["summary"]

    if len(entries) != len(registered):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/modules",
            "quantidade de módulos divergente",
        )

    if (
        len(entries)
        > registry_document["limits"]["max_observers"]
    ):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/modules",
            "quantidade excede o registo",
        )

    modules = [
        entry["module"]
        for entry in entries
    ]

    if len(modules) != len(set(modules)):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/modules",
            "módulo duplicado",
        )

    successful = 0

    for index, (entry, registered_entry) in enumerate(
        zip(entries, registered)
    ):
        prefix = f"/modules/{index}"
        module = registered_entry["module"]

        if entry["module"] != module:
            fail(
                EXIT_SEMANTIC,
                "SEMANTIC_VIOLATION",
                f"{prefix}/module",
                "módulo ou ordem divergente",
            )

        if (
            entry["required"]
            != registered_entry["required"]
        ):
            fail(
                EXIT_SEMANTIC,
                "SEMANTIC_VIOLATION",
                f"{prefix}/required",
                "classificação required divergente",
            )

        if entry["outcome"] == "SUCCESS":
            successful += 1
            report = entry["report"]

            if (
                entry["error_code"] is not None
                or entry["exit_code"] != 0
                or report is None
            ):
                fail(
                    EXIT_SEMANTIC,
                    "SEMANTIC_VIOLATION",
                    prefix,
                    "entrada de sucesso incoerente",
                )

            if (
                report["module"] != module
                or report["path"]
                != f"observers/{module}.json"
            ):
                fail(
                    EXIT_SEMANTIC,
                    "SEMANTIC_VIOLATION",
                    f"{prefix}/report",
                    "descritor não corresponde ao módulo",
                )

            if (
                report["version"]
                not in registered_entry[
                    "module_versions"
                ]
            ):
                fail(
                    EXIT_SEMANTIC,
                    "SEMANTIC_VIOLATION",
                    f"{prefix}/report/version",
                    "versão de módulo incompatível",
                )

            if (
                report["contract_version"]
                != registered_entry[
                    "output_contract"
                ]
            ):
                fail(
                    EXIT_SEMANTIC,
                    "SEMANTIC_VIOLATION",
                    f"{prefix}/report/contract_version",
                    "contrato de relatório incompatível",
                )
        else:
            if (
                entry["error_code"]
                not in RECORDABLE_FAILURE_CODES
                or entry["report"] is not None
            ):
                fail(
                    EXIT_SEMANTIC,
                    "SEMANTIC_VIOLATION",
                    prefix,
                    "entrada de falha incoerente",
                )

    declared = len(entries)
    failed = declared - successful

    expected_summary = {
        "declared": declared,
        "successful": successful,
        "failed": failed,
        "reports_written": successful,
    }

    if summary != expected_summary:
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/summary",
            "contadores incoerentes",
        )

    if (
        document["state"]
        != expected_state(declared, successful)
    ):
        fail(
            EXIT_SEMANTIC,
            "SEMANTIC_VIOLATION",
            "/state",
            "estado da geração incoerente",
        )


@dataclass(frozen=True)
class GenerationContext:
    root: Path
    observers: Path
    expected_identifier: str
    staging: bool
    root_identity: tuple[int, int]
    observers_identity: tuple[int, int]


def ensure_no_symlink_components(
    path: Path,
) -> None:
    current = Path(path.anchor)

    for component in path.parts[1:]:
        current = current / component

        try:
            current_status = os.lstat(current)
        except OSError:
            fail(
                EXIT_GENERATION,
                "GENERATION_INVALID",
                "generation",
                "componente do caminho indisponível",
            )

        if stat.S_ISLNK(current_status.st_mode):
            fail(
                EXIT_GENERATION,
                "GENERATION_INVALID",
                "generation",
                "caminho atravessa link simbólico",
            )


def mode_exceeds(
    status_result: os.stat_result,
    maximum: int,
) -> bool:
    mode = stat.S_IMODE(status_result.st_mode)
    return bool(mode & ~maximum)


def validate_generation_directory(
    value: str,
    expected_identifier: str,
) -> GenerationContext:
    root = Path(value)

    if not root.is_absolute():
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation",
            "diretório deve usar caminho absoluto",
        )

    parse_generation_identifier(
        expected_identifier
    )
    expected_names = {
        expected_identifier,
        f".staging-{expected_identifier}",
    }

    if root.name not in expected_names:
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation",
            "nome do diretório divergente",
        )

    ensure_no_symlink_components(root)

    try:
        root_status = os.lstat(root)
    except OSError:
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation",
            "diretório de geração indisponível",
        )

    if (
        stat.S_ISLNK(root_status.st_mode)
        or not stat.S_ISDIR(root_status.st_mode)
    ):
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation",
            "geração não é diretório seguro",
        )

    staging = root.name.startswith(".staging-")
    root_maximum = 0o750 if staging else 0o550

    if mode_exceeds(root_status, root_maximum):
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "generation",
            "permissões da geração excedem o limite",
        )

    observers = root / "observers"

    try:
        observers_status = os.lstat(observers)
    except OSError:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "observers",
            "diretório observers ausente",
        )

    if (
        stat.S_ISLNK(observers_status.st_mode)
        or not stat.S_ISDIR(
            observers_status.st_mode
        )
    ):
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "observers",
            "observers não é diretório seguro",
        )

    observers_maximum = (
        0o750
        if staging
        else 0o550
    )

    if mode_exceeds(
        observers_status,
        observers_maximum,
    ):
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "observers",
            "permissões de observers excedem o limite",
        )

    return GenerationContext(
        root=root,
        observers=observers,
        expected_identifier=expected_identifier,
        staging=staging,
        root_identity=(
            root_status.st_dev,
            root_status.st_ino,
        ),
        observers_identity=(
            observers_status.st_dev,
            observers_status.st_ino,
        ),
    )


def revalidate_generation(
    context: GenerationContext,
) -> None:
    try:
        root_status = os.lstat(context.root)
        observers_status = os.lstat(
            context.observers
        )
    except OSError:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "generation",
            "geração mudou durante a validação",
        )

    if (
        stat.S_ISLNK(root_status.st_mode)
        or stat.S_ISLNK(observers_status.st_mode)
        or not stat.S_ISDIR(root_status.st_mode)
        or not stat.S_ISDIR(
            observers_status.st_mode
        )
        or (
            root_status.st_dev,
            root_status.st_ino,
        ) != context.root_identity
        or (
            observers_status.st_dev,
            observers_status.st_ino,
        ) != context.observers_identity
    ):
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "generation",
            "identidade da geração mudou",
        )


def read_manifest(
    context: GenerationContext,
) -> tuple[dict[str, Any], SecureContent]:
    secure = secure_read_file(
        context.root / "manifest.json",
        MANIFEST_MAX_BYTES,
        location="manifest.json",
        exit_code=EXIT_INPUT,
        missing_code="MANIFEST_MISSING",
        unreadable_code="MANIFEST_UNREADABLE",
        too_large_code="MANIFEST_TOO_LARGE",
        require_single_link=True,
    )

    maximum_mode = (
        0o640
        if context.staging
        else 0o440
    )

    try:
        manifest_status = os.lstat(
            context.root / "manifest.json"
        )
    except OSError:
        fail(
            EXIT_INPUT,
            "MANIFEST_UNREADABLE",
            "manifest.json",
            "manifesto mudou depois da leitura",
        )

    if mode_exceeds(
        manifest_status,
        maximum_mode,
    ):
        fail(
            EXIT_INPUT,
            "MANIFEST_UNREADABLE",
            "manifest.json",
            "permissões do manifesto excedem o limite",
        )

    document = parse_json_strict(
        secure.content,
        location="manifest.json",
        exit_code=EXIT_INPUT,
        invalid_utf8_code="INVALID_UTF8",
        invalid_json_code="INVALID_JSON",
        duplicate_key_code="DUPLICATE_KEY",
        non_finite_code="NON_FINITE_NUMBER",
        depth_code="DEPTH_LIMIT_EXCEEDED",
        maximum_depth=MANIFEST_MAX_DEPTH,
    )

    if not isinstance(document, dict):
        fail(
            EXIT_CONTRACT,
            "CONTRACT_VIOLATION",
            "",
            "manifesto não é objeto",
        )

    return document, secure


@dataclass(frozen=True)
class ReportValidatorContext:
    module: Any
    validator: Any


def load_report_validator(
    project_root: Path,
) -> ReportValidatorContext:
    validator_path = (
        project_root
        / "core"
        / "validate-report.py"
    )

    try:
        before_status = os.lstat(
            validator_path
        )
    except OSError:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "report-validator",
            "validador de relatórios indisponível",
        )

    if (
        stat.S_ISLNK(before_status.st_mode)
        or not stat.S_ISREG(
            before_status.st_mode
        )
    ):
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "report-validator",
            "validador de relatórios inseguro",
        )

    specification = (
        importlib.util.spec_from_file_location(
            "mppt24_manifest_report_validator",
            validator_path,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "report-validator",
            "validador de relatórios não carregável",
        )

    validator_module = (
        importlib.util.module_from_spec(
            specification
        )
    )

    try:
        specification.loader.exec_module(
            validator_module
        )
        validator_class, schema_error_class = (
            validator_module
            .load_jsonschema_dependency()
        )
        _schema, validator = (
            validator_module.load_schema(
                validator_class,
                schema_error_class,
            )
        )
        after_status = os.lstat(
            validator_path
        )
    except Exception:
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "report-validator",
            "contrato de relatório indisponível",
        )

    before_identity = (
        before_status.st_dev,
        before_status.st_ino,
        before_status.st_size,
        before_status.st_mtime_ns,
        before_status.st_ctime_ns,
    )
    after_identity = (
        after_status.st_dev,
        after_status.st_ino,
        after_status.st_size,
        after_status.st_mtime_ns,
        after_status.st_ctime_ns,
    )

    if (
        stat.S_ISLNK(after_status.st_mode)
        or not stat.S_ISREG(
            after_status.st_mode
        )
        or before_identity != after_identity
    ):
        fail(
            EXIT_CONFIGURATION,
            "DEPENDENCY_UNAVAILABLE",
            "report-validator",
            "validador de relatórios mudou durante a carga",
        )

    return ReportValidatorContext(
        module=validator_module,
        validator=validator,
    )


def validate_report_content(
    context: ReportValidatorContext,
    content: bytes,
    module_name: str,
    maximum_depth: int,
    location: str,
) -> dict[str, Any]:
    validator_module = context.module
    diagnostics = io.StringIO()

    try:
        with contextlib.redirect_stderr(
            diagnostics
        ):
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
                context.validator,
            )
            validator_module.validate_semantics(
                document,
                module_name,
            )
    except validator_module.ValidationFailure:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "relatório rejeitado pelo contrato 2.1.0",
        )
    except Exception:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "falha controlada ao validar relatório",
        )

    if not isinstance(document, dict):
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "relatório validado não é objeto",
        )

    return document


def revalidate_secure_file(
    path: Path,
    secure: SecureContent,
    location: str,
) -> None:
    try:
        current_status = os.lstat(path)
    except OSError:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "ficheiro mudou durante a validação",
        )

    expected_signature = (
        secure.identity[0],
        secure.identity[1],
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
        ) != expected_signature
    ):
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "identidade do ficheiro mudou",
        )


def directory_entry_names(
    directory: Path,
    location: str,
) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            names = {
                entry.name
                for entry in entries
            }
    except OSError:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            location,
            "não foi possível enumerar o diretório",
        )

    return names


def validate_generation_structure(
    context: GenerationContext,
    document: dict[str, Any],
    registry: RegistryContext,
    report_validator: ReportValidatorContext,
    manifest_secure: SecureContent,
) -> dict[str, dict[str, Any]]:
    root_names = directory_entry_names(
        context.root,
        "generation",
    )

    if root_names != {
        "manifest.json",
        "observers",
    }:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "generation",
            "objetos inesperados na raiz da geração",
        )

    successful_entries = [
        entry
        for entry in document["modules"]
        if entry["outcome"] == "SUCCESS"
    ]
    expected_report_names = {
        f"{entry['module']}.json"
        for entry in successful_entries
    }
    actual_report_names = directory_entry_names(
        context.observers,
        "observers",
    )

    if actual_report_names != expected_report_names:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "observers",
            "conjunto de relatórios diverge do manifesto",
        )

    limits = registry.document["limits"]
    report_maximum = limits[
        "report_max_bytes"
    ]
    depth_maximum = limits[
        "json_max_depth"
    ]
    report_mode_maximum = (
        0o640
        if context.staging
        else 0o440
    )
    validated_reports: list[
        tuple[
            Path,
            SecureContent,
            str,
            str,
            dict[str, Any],
        ]
    ] = []

    for entry in successful_entries:
        module = entry["module"]
        descriptor = entry["report"]
        report_name = f"{module}.json"
        relative_path = (
            f"observers/{report_name}"
        )
        report_path = (
            context.observers
            / report_name
        )

        if descriptor["path"] != relative_path:
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                f"/modules/{module}/report/path",
                "caminho do relatório divergente",
            )

        secure = secure_read_file(
            report_path,
            report_maximum,
            location=relative_path,
            exit_code=EXIT_MISMATCH,
            missing_code="GENERATION_MISMATCH",
            unreadable_code="GENERATION_MISMATCH",
            too_large_code="GENERATION_MISMATCH",
            require_single_link=True,
        )

        try:
            report_status = os.lstat(
                report_path
            )
        except OSError:
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                relative_path,
                "relatório mudou depois da leitura",
            )

        if mode_exceeds(
            report_status,
            report_mode_maximum,
        ):
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                relative_path,
                "permissões do relatório excedem o limite",
            )

        if secure.size != descriptor["size_bytes"]:
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                relative_path,
                "tamanho do relatório divergente",
            )

        report_hash = hashlib.sha256(
            secure.content
        ).hexdigest()

        if report_hash != descriptor["sha256"]:
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                relative_path,
                "hash do relatório divergente",
            )

        report_document = validate_report_content(
            report_validator,
            secure.content,
            module,
            depth_maximum,
            relative_path,
        )

        expected_metadata = {
            "module": descriptor["module"],
            "version": descriptor["version"],
            "timestamp": descriptor["timestamp"],
            "status": descriptor["status"],
        }
        actual_metadata = {
            key: report_document.get(key)
            for key in expected_metadata
        }

        if actual_metadata != expected_metadata:
            fail(
                EXIT_MISMATCH,
                "GENERATION_MISMATCH",
                relative_path,
                "metadados do relatório divergentes",
            )

        validated_reports.append(
            (
                report_path,
                secure,
                relative_path,
                module,
                report_document,
            )
        )

    revalidate_generation(context)

    if directory_entry_names(
        context.root,
        "generation",
    ) != root_names:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "generation",
            "raiz mudou durante a validação",
        )

    if directory_entry_names(
        context.observers,
        "observers",
    ) != actual_report_names:
        fail(
            EXIT_MISMATCH,
            "GENERATION_MISMATCH",
            "observers",
            "diretório de relatórios mudou",
        )

    for (
        report_path,
        secure,
        relative_path,
        _module,
        _report_document,
    ) in validated_reports:
        revalidate_secure_file(
            report_path,
            secure,
            relative_path,
        )

    revalidate_secure_file(
        context.root / "manifest.json",
        manifest_secure,
        "manifest.json",
    )

    return {
        module: report_document
        for (
            _report_path,
            _secure,
            _relative_path,
            module,
            report_document,
        ) in validated_reports
    }


def validate_generation(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    project_root = (
        Path(__file__).resolve().parent.parent
    )
    expected_identifier = (
        arguments.expected_generation_id
    )

    load_jsonschema_dependency()
    parse_generation_identifier(
        expected_identifier
    )

    (
        validator_class,
        manifest_schema,
        registry,
    ) = load_configuration(project_root)

    generation = validate_generation_directory(
        arguments.generation_directory,
        expected_identifier,
    )
    document, manifest_secure = (
        read_manifest(generation)
    )

    validate_manifest_schema(
        validator_class,
        manifest_schema,
        document,
    )
    validate_manifest_semantics(
        document,
        expected_identifier,
        registry,
    )

    report_validator = load_report_validator(
        project_root
    )

    reports = validate_generation_structure(
        generation,
        document,
        registry,
        report_validator,
        manifest_secure,
    )

    return {
        "snapshot_version": "1.0.0",
        "generation_id": document["generation_id"],
        "state": document["state"],
        "manifest": document,
        "reports": reports,
    }


def main(
    argv: Sequence[str] | None = None,
) -> int:
    effective_argv = (
        sys.argv[1:]
        if argv is None
        else argv
    )

    try:
        arguments = parse_arguments(
            effective_argv
        )
        snapshot = validate_generation(
            arguments
        )

        if arguments.emit_validated_snapshot:
            serialized = json.dumps(
                snapshot,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            sys.stdout.write(
                serialized + "\n"
            )

        return EXIT_SUCCESS
    except ValidationFailure as error:
        if not error.reported:
            emit_diagnostic(
                error.code,
                error.location,
                error.message,
            )
        return error.exit_code
    except Exception:
        emit_diagnostic(
            "INTERNAL_ERROR",
            "internal",
            "falha interna inesperada",
        )
        return EXIT_INTERNAL




def validate_current_generation_content(
    content: bytes,
) -> str:
    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "current-generation",
            "referência não é UTF-8 válido",
        )

    if (
        not text.endswith("\n")
        or text.count("\n") != 1
    ):
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "current-generation",
            "formato da referência inválido",
        )

    generation_id = text[:-1]

    if (
        not generation_id
        or "\r" in generation_id
    ):
        fail(
            EXIT_GENERATION,
            "GENERATION_INVALID",
            "current-generation",
            "conteúdo da referência inválido",
        )

    parse_generation_identifier(
        generation_id
    )
    return generation_id


if __name__ == "__main__":
    raise SystemExit(main())
