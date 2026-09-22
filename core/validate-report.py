#!/usr/bin/python3 -I
"""
MPPT24 CORE
Validador de fronteira para relatórios serializados 2.1.0.
"""

import argparse
import errno
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, NoReturn, Sequence

EXIT_VALID = 0
EXIT_USAGE = 2
EXIT_DEPENDENCY = 3
EXIT_SCHEMA = 4
EXIT_INPUT = 5
EXIT_STRUCTURE = 6
EXIT_SEMANTIC = 7
EXIT_INTERNAL = 8

SCHEMA_MAX_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
DIAGNOSTIC_MESSAGE_LIMIT = 240

MODULE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"[+-][0-9]{4}$"
)


EXPECTED_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_ID = "urn:mppt24:schema:report:2.1.0"


class ValidationFailure(Exception):
    """Falha prevista e controlada pelo contrato."""

    def __init__(
        self,
        exit_code: int,
        code: str,
        location: str,
        message: str,
        reported: bool = False,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.location = location
        self.message = message
        self.reported = reported


class DuplicateKeyError(ValueError):
    """Chave JSON repetida."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class NonFiniteNumberError(ValueError):
    """Constante numérica não pertencente a JSON."""

    def __init__(self, value: str) -> None:
        super().__init__(value)
        self.value = value


def sanitize_diagnostic(value: object) -> str:
    """Remover controlos e limitar texto apresentado ao utilizador."""

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
    location: object,
    message: object,
) -> None:
    """Emitir um diagnóstico contratualmente controlado."""

    fields = (
        "ERROR",
        sanitize_diagnostic(code),
        sanitize_diagnostic(location),
        sanitize_diagnostic(message),
    )
    print("\t".join(fields), file=sys.stderr)


def fail(
    exit_code: int,
    code: str,
    location: str,
    message: str,
) -> NoReturn:
    """Interromper com uma falha contratualmente conhecida."""

    raise ValidationFailure(exit_code, code, location, message)


class ContractArgumentParser(argparse.ArgumentParser):
    """ArgumentParser sem diagnóstico automático não controlado."""

    def error(self, message: str) -> NoReturn:
        fail(EXIT_USAGE, "USAGE_INVALID", "arguments", message)


def positive_integer(value: str) -> int:
    """Converter um argumento decimal estritamente positivo."""

    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError(
            "o valor deve ser um inteiro decimal positivo"
        )
    return int(value)


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    """Validar a interface de linha de comandos."""

    unique_options = {
        "--help",
        "--max-bytes",
        "--max-depth",
        "--expected-module",
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
        prog="validate-report.py",
        description="Validar um relatório serializado MPPT24 2.1.0.",
    )
    parser.add_argument(
        "--max-bytes",
        required=True,
        type=positive_integer,
    )
    parser.add_argument(
        "--max-depth",
        required=True,
        type=positive_integer,
    )
    parser.add_argument(
        "--expected-module",
    )
    parser.add_argument(
        "report",
    )

    arguments = parser.parse_args(argv)

    if (
        arguments.expected_module is not None
        and not MODULE_PATTERN.fullmatch(arguments.expected_module)
    ):
        fail(
            EXIT_USAGE,
            "USAGE_INVALID",
            "--expected-module",
            "nome de módulo esperado inválido",
        )

    return arguments


def load_jsonschema_dependency() -> tuple[Any, Any]:
    """Carregar jsonschema apenas durante a execução efetiva."""

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        fail(
            EXIT_DEPENDENCY,
            "DEPENDENCY_UNAVAILABLE",
            "python3-jsonschema",
            "dependência obrigatória indisponível",
        )

    return Draft202012Validator, SchemaError


def secure_read(
    path: Path,
    maximum_bytes: int,
    role: str,
) -> bytes:
    """Ler um ficheiro regular sem seguir links nem reabrir o caminho."""

    if role == "schema":
        exit_code = EXIT_SCHEMA
        missing_code = "SCHEMA_MISSING"
        unreadable_code = "SCHEMA_UNREADABLE"
        symlink_code = "SCHEMA_SYMLINK"
        regular_code = "SCHEMA_NOT_REGULAR"
        size_code = "SCHEMA_TOO_LARGE"
        changed_code = "SCHEMA_INVALID"
        location = "schema"
    else:
        exit_code = EXIT_INPUT
        missing_code = "INPUT_MISSING"
        unreadable_code = "INPUT_UNREADABLE"
        symlink_code = "INPUT_SYMLINK"
        regular_code = "INPUT_NOT_REGULAR"
        size_code = "INPUT_TOO_LARGE"
        changed_code = "INPUT_CHANGED"
        location = "report"

    try:
        path_status = os.lstat(path)
    except FileNotFoundError:
        fail(exit_code, missing_code, location, "ficheiro inexistente")
    except OSError:
        fail(exit_code, unreadable_code, location, "não foi possível examinar o ficheiro")

    if stat.S_ISLNK(path_status.st_mode):
        fail(exit_code, symlink_code, location, "links simbólicos não são permitidos")

    if not stat.S_ISREG(path_status.st_mode):
        fail(exit_code, regular_code, location, "o caminho não identifica um ficheiro regular")

    if path_status.st_size > maximum_bytes:
        fail(exit_code, size_code, location, "o ficheiro excede o limite permitido")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            fail(exit_code, symlink_code, location, "links simbólicos não são permitidos")
        fail(exit_code, unreadable_code, location, "não foi possível abrir o ficheiro")

    try:
        opened_status = os.fstat(descriptor)

        if not stat.S_ISREG(opened_status.st_mode):
            fail(
                exit_code,
                regular_code,
                location,
                "o descritor não representa um ficheiro regular",
            )

        if (
            opened_status.st_dev != path_status.st_dev
            or opened_status.st_ino != path_status.st_ino
        ):
            fail(exit_code, changed_code, location, "o ficheiro mudou antes da leitura")

        if opened_status.st_size > maximum_bytes:
            fail(exit_code, size_code, location, "o ficheiro excede o limite permitido")

        chunks = []
        total = 0

        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break

            total += len(chunk)
            if total > maximum_bytes:
                fail(exit_code, size_code, location, "o ficheiro excede o limite permitido")

            chunks.append(chunk)

        completed_status = os.fstat(descriptor)
    except ValidationFailure:
        raise
    except OSError:
        fail(exit_code, unreadable_code, location, "falha durante a leitura")
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
        getattr(opened_status, field) != getattr(completed_status, field)
        for field in stable_fields
    ):
        fail(exit_code, changed_code, location, "o ficheiro mudou durante a leitura")

    content = b"".join(chunks)

    if len(content) != completed_status.st_size:
        fail(exit_code, changed_code, location, "a leitura não corresponde ao tamanho final")

    return content


def decode_utf8(content: bytes, role: str) -> str:
    """Descodificar UTF-8 sem substituição de caracteres inválidos."""

    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        if role == "schema":
            fail(
                EXIT_SCHEMA,
                "SCHEMA_INVALID",
                "schema",
                "o schema não contém UTF-8 válido",
            )
        fail(
            EXIT_INPUT,
            "INVALID_UTF8",
            "report",
            "o relatório não contém UTF-8 válido",
        )


def reject_duplicate_keys(
    pairs: Iterable[tuple[str, Any]],
) -> dict[str, Any]:
    """Construir um objeto JSON rejeitando chaves repetidas."""

    result = {}

    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value

    return result


def reject_non_finite(value: str) -> NoReturn:
    """Rejeitar extensões numéricas não pertencentes a JSON."""

    raise NonFiniteNumberError(value)


def parse_json_strict(text: str, role: str) -> Any:
    """Ler exatamente um documento JSON sem extensões permissivas."""

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except DuplicateKeyError:
        if role == "schema":
            fail(
                EXIT_SCHEMA,
                "SCHEMA_INVALID",
                "schema",
                "o schema contém uma chave duplicada",
            )
        fail(
            EXIT_INPUT,
            "DUPLICATE_KEY",
            "report",
            "o relatório contém uma chave duplicada",
        )
    except NonFiniteNumberError:
        if role == "schema":
            fail(
                EXIT_SCHEMA,
                "SCHEMA_INVALID",
                "schema",
                "o schema contém um número não finito",
            )
        fail(
            EXIT_INPUT,
            "NON_FINITE_NUMBER",
            "report",
            "o relatório contém um número não finito",
        )
    except RecursionError:
        if role == "schema":
            fail(
                EXIT_SCHEMA,
                "SCHEMA_INVALID",
                "schema",
                "o schema excede a profundidade suportada",
            )
        fail(
            EXIT_INPUT,
            "DEPTH_LIMIT_EXCEEDED",
            "report",
            "o relatório excede a profundidade suportada",
        )
    except (json.JSONDecodeError, ValueError):
        if role == "schema":
            fail(
                EXIT_SCHEMA,
                "SCHEMA_INVALID",
                "schema",
                "o schema não é JSON válido",
            )
        fail(
            EXIT_INPUT,
            "INVALID_JSON",
            "report",
            "o relatório não é JSON válido",
        )


def enforce_depth(document: Any, maximum_depth: int) -> None:
    """Limitar o aninhamento de objetos e arrays sem recursão."""

    if not isinstance(document, (dict, list)):
        return

    stack = [(document, 1)]

    while stack:
        value, depth = stack.pop()

        if depth > maximum_depth:
            fail(
                EXIT_INPUT,
                "DEPTH_LIMIT_EXCEEDED",
                "report",
                "o relatório excede a profundidade permitida",
            )

        children = value.values() if isinstance(value, dict) else value

        for child in children:
            if isinstance(child, (dict, list)):
                stack.append((child, depth + 1))


def schema_location() -> Path:
    """Obter o schema fixo relativamente ao projeto instalado."""

    project_root = Path(__file__).resolve().parent.parent
    return (
        project_root
        / "schemas"
        / "report"
        / "2.1.0"
        / "report.schema.json"
    )


def reject_external_references(schema: Any) -> None:
    """Rejeitar referências que não sejam fragmentos internos."""

    stack = [schema]

    while stack:
        value = stack.pop()

        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"}:
                    if not isinstance(child, str) or not child.startswith("#"):
                        fail(
                            EXIT_SCHEMA,
                            "SCHEMA_EXTERNAL_REFERENCE",
                            "schema",
                            "o schema contém uma referência externa",
                        )
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)


def load_schema(
    validator_class: Any,
    schema_error_class: Any,
) -> tuple[Any, Any]:
    """Ler, verificar e preparar o schema local."""

    path = schema_location()
    content = secure_read(path, SCHEMA_MAX_BYTES, "schema")
    text = decode_utf8(content, "schema")
    schema = parse_json_strict(text, "schema")

    if (
        not isinstance(schema, dict)
        or schema.get("$schema") != EXPECTED_SCHEMA_DIALECT
        or schema.get("$id") != EXPECTED_SCHEMA_ID
    ):
        fail(
            EXIT_SCHEMA,
            "SCHEMA_INVALID",
            "schema",
            "identidade ou dialecto do schema inválido",
        )
    reject_external_references(schema)

    try:
        validator_class.check_schema(schema)
    except schema_error_class:
        fail(
            EXIT_SCHEMA,
            "SCHEMA_INVALID",
            "schema",
            "o schema não cumpre o dialecto Draft 2020-12",
        )

    return schema, validator_class(schema)


def pointer_component(value: object) -> str:
    """Codificar um componente segundo JSON Pointer."""

    return str(value).replace("~", "~0").replace("/", "~1")


def json_pointer(path: Iterable[object]) -> str:
    """Converter um caminho do validador numa localização determinística."""

    components = [pointer_component(component) for component in path]

    if not components:
        return "/"

    return "/" + "/".join(components)


def validation_error_sort_key(error: Any) -> tuple[Any, ...]:
    """Produzir uma chave comparável mesmo com índices e nomes misturados."""

    instance_path = tuple(
        (type(component).__name__, str(component))
        for component in error.absolute_path
    )
    schema_path = tuple(
        (type(component).__name__, str(component))
        for component in error.absolute_schema_path
    )
    return (
        instance_path,
        schema_path,
        str(error.validator),
    )


def validate_structure(document: Any, validator: Any) -> None:
    """Aplicar todas as regras estruturais e ordenar os diagnósticos."""

    errors = sorted(
        validator.iter_errors(document),
        key=validation_error_sort_key,
    )

    if not errors:
        return

    for error in errors:
        keyword = sanitize_diagnostic(error.validator)
        emit_diagnostic(
            "CONTRACT_VIOLATION",
            json_pointer(error.absolute_path),
            f"violação estrutural: {keyword}",
        )

    raise ValidationFailure(
        EXIT_STRUCTURE,
        "CONTRACT_VIOLATION",
        "/",
        "o relatório viola o contrato estrutural",
        reported=True,
    )


def validate_semantics(
    document: dict[str, Any],
    expected_module: str | None,
) -> None:
    """Aplicar regras semânticas posteriores ao schema."""

    timestamp = document["timestamp"]

    if not TIMESTAMP_PATTERN.fullmatch(timestamp):
        fail(
            EXIT_SEMANTIC,
            "INVALID_TIMESTAMP",
            "/timestamp",
            "timestamp incompatível com o contrato",
        )

    try:
        datetime.strptime(
            timestamp,
            "%Y-%m-%dT%H:%M:%S%z",
        )
    except ValueError:
        fail(
            EXIT_SEMANTIC,
            "INVALID_TIMESTAMP",
            "/timestamp",
            "timestamp semanticamente inválido",
        )

    if (
        expected_module is not None
        and document["module"] != expected_module
    ):
        fail(
            EXIT_SEMANTIC,
            "MODULE_MISMATCH",
            "/module",
            "o módulo não corresponde à identidade esperada",
        )


def execute_validation(arguments: argparse.Namespace) -> int:
    """Executar a sequência integral definida pelo contrato."""

    validator_class, schema_error_class = load_jsonschema_dependency()
    _schema, validator = load_schema(
        validator_class,
        schema_error_class,
    )

    report_path = Path(arguments.report)
    content = secure_read(
        report_path,
        arguments.max_bytes,
        "report",
    )
    text = decode_utf8(content, "report")
    document = parse_json_strict(text, "report")
    enforce_depth(document, arguments.max_depth)
    validate_structure(document, validator)
    validate_semantics(document, arguments.expected_module)

    return EXIT_VALID


def main(argv: Sequence[str] | None = None) -> int:
    """Converter resultados e exceções em interface de processo estável."""

    effective_argv = sys.argv[1:] if argv is None else argv

    try:
        arguments = parse_arguments(effective_argv)
        return execute_validation(arguments)
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
            "validator",
            "falha interna inesperada",
        )
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
