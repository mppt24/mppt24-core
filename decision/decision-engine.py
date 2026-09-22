#!/usr/bin/python3 -I
"""Decision Engine MPPT24 3.0.0 — implementação candidata."""

import argparse
import copy
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Sequence

sys.dont_write_bytecode = True

MODULE_NAME = "decision-engine"
MODULE_VERSION = "3.0.0"
REPORT_CONTRACT_VERSION = "2.1.0"

CURRENT_GENERATION_NAME = "current-generation"
GENERATIONS_DIRECTORY_NAME = "generations"

CURRENT_GENERATION_MAX_BYTES = 256

SNAPSHOT_MAX_BYTES = 16777216
DIAGNOSTIC_MAX_BYTES = 4096
VALIDATOR_TIMEOUT_SECONDS = 60
TERMINATION_GRACE_SECONDS = 2
CHILD_READ_CHUNK_BYTES = 16384

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_STATE = 4
EXIT_INTERNAL = 9

GENERATION_ID_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$"
)


class DecisionFailure(Exception):
    """Falha contratual prevista."""

    def __init__(
        self,
        exit_code: int,
        code: str,
        location: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.location = location
        self.message = message


def fail(
    exit_code: int,
    code: str,
    location: str,
    message: str,
) -> NoReturn:
    raise DecisionFailure(
        exit_code,
        code,
        location,
        message,
    )


def sanitize(value: str) -> str:
    result = []

    for character in value:
        codepoint = ord(character)

        if (
            character in "\t\r\n"
            or codepoint < 32
            or codepoint == 127
        ):
            result.append("?")
        else:
            result.append(character)

    return "".join(result)[:240]


def emit_diagnostic(
    code: str,
    location: str,
    message: str,
) -> None:
    print(
        "ERROR",
        sanitize(code),
        sanitize(location),
        sanitize(message),
        sep="\t",
        file=sys.stderr,
    )


class ContractArgumentParser(argparse.ArgumentParser):
    """ArgumentParser com diagnóstico contratual."""

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
    seen_state_root = False

    for token in argv:
        option = token.split("=", 1)[0]

        if option != "--state-root":
            continue

        if seen_state_root:
            fail(
                EXIT_USAGE,
                "USAGE_INVALID",
                "--state-root",
                "a opção não pode ser repetida",
            )

        seen_state_root = True

    parser = ContractArgumentParser(
        prog="decision-engine.py",
        description="Decision Engine MPPT24 3.0.0.",
    )
    parser.add_argument(
        "--state-root",
        required=True,
    )

    return parser.parse_args(argv)


def validate_generation_id(
    generation_id: str,
) -> str:
    if not GENERATION_ID_PATTERN.fullmatch(
        generation_id
    ):
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "identificador de geração inválido",
        )

    temporal = generation_id.split("-", 1)[0]

    try:
        datetime.strptime(
            temporal,
            "%Y%m%dT%H%M%S%fZ",
        )
    except ValueError:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "data do identificador inválida",
        )

    return generation_id


def validate_state_root(
    supplied: str,
) -> Path:
    if not supplied:
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT vazia",
        )

    path = Path(supplied)

    try:
        metadata = path.lstat()
    except OSError:
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT indisponível",
        )

    if stat.S_ISLNK(metadata.st_mode):
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT não pode ser link simbólico",
        )

    if not stat.S_ISDIR(metadata.st_mode):
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT não é diretório",
        )

    if metadata.st_mode & 0o022:
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT possui permissões excessivas",
        )

    try:
        resolved = path.resolve(strict=True)
    except OSError:
        fail(
            EXIT_STATE,
            "STATE_ROOT_INVALID",
            "state-root",
            "STATE_ROOT não pôde ser resolvida",
        )

    return resolved


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
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "referência não é UTF-8 válido",
        )

    if (
        not text.endswith("\n")
        or text.count("\n") != 1
    ):
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "formato da referência inválido",
        )

    generation_id = text[:-1]

    if (
        not generation_id
        or "\r" in generation_id
    ):
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "conteúdo da referência inválido",
        )

    return validate_generation_id(
        generation_id
    )


def current_generation_signature(
    status_result: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        status_result.st_dev,
        status_result.st_ino,
        status_result.st_mode,
        status_result.st_nlink,
        status_result.st_size,
        status_result.st_mtime_ns,
        status_result.st_ctime_ns,
    )


def read_current_generation(
    state_root: Path,
) -> str:
    reference = (
        state_root
        / CURRENT_GENERATION_NAME
    )

    try:
        before = reference.lstat()
    except FileNotFoundError:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_MISSING",
            CURRENT_GENERATION_NAME,
            "referência atual ausente",
        )
    except OSError:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_UNREADABLE",
            CURRENT_GENERATION_NAME,
            "referência atual ilegível",
        )

    if stat.S_ISLNK(before.st_mode):
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "referência não pode ser link simbólico",
        )

    if not stat.S_ISREG(before.st_mode):
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "referência não é ficheiro regular",
        )

    if before.st_mode & 0o027:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_INVALID",
            CURRENT_GENERATION_NAME,
            "referência possui permissões excessivas",
        )

    if before.st_size > CURRENT_GENERATION_MAX_BYTES:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_TOO_LARGE",
            CURRENT_GENERATION_NAME,
            "referência excede o limite",
        )

    flags = os.O_RDONLY

    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(
            reference,
            flags,
        )
    except OSError:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_UNREADABLE",
            CURRENT_GENERATION_NAME,
            "referência não pôde ser aberta",
        )

    try:
        try:
            opened = os.fstat(descriptor)
        except OSError:
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "referência mudou durante a abertura",
            )

        if (
            not stat.S_ISREG(opened.st_mode)
            or current_generation_signature(opened)
            != current_generation_signature(before)
        ):
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "objeto mudou durante a resolução",
            )

        chunks = []
        remaining = (
            CURRENT_GENERATION_MAX_BYTES + 1
        )

        while remaining > 0:
            try:
                chunk = os.read(
                    descriptor,
                    remaining,
                )
            except OSError:
                fail(
                    EXIT_STATE,
                    "CURRENT_GENERATION_UNREADABLE",
                    CURRENT_GENERATION_NAME,
                    "referência não pôde ser lida",
                )

            if not chunk:
                break

            chunks.append(chunk)
            remaining -= len(chunk)

        content = b"".join(chunks)

        try:
            after = os.fstat(descriptor)
        except OSError:
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "referência mudou durante a leitura",
            )

        if (
            current_generation_signature(after)
            != current_generation_signature(opened)
        ):
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "objeto mudou durante a leitura",
            )

        try:
            final = reference.lstat()
        except OSError:
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "referência mudou depois da leitura",
            )

        if (
            stat.S_ISLNK(final.st_mode)
            or not stat.S_ISREG(final.st_mode)
            or current_generation_signature(final)
            != current_generation_signature(opened)
        ):
            fail(
                EXIT_STATE,
                "CURRENT_GENERATION_CHANGED",
                CURRENT_GENERATION_NAME,
                "identidade da referência mudou",
            )
    finally:
        os.close(descriptor)

    if len(content) > CURRENT_GENERATION_MAX_BYTES:
        fail(
            EXIT_STATE,
            "CURRENT_GENERATION_TOO_LARGE",
            CURRENT_GENERATION_NAME,
            "referência excede o limite",
        )

    return validate_current_generation_content(
        content
    )


def resolve_generation(
    state_root: Path,
    generation_id: str,
) -> Path:
    generations = (
        state_root
        / GENERATIONS_DIRECTORY_NAME
    )

    try:
        generations_metadata = generations.lstat()
    except OSError:
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generations",
            "diretório de gerações indisponível",
        )

    if (
        stat.S_ISLNK(generations_metadata.st_mode)
        or not stat.S_ISDIR(
            generations_metadata.st_mode
        )
    ):
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generations",
            "diretório de gerações inseguro",
        )

    generation = (
        generations
        / generation_id
    )

    try:
        metadata = generation.lstat()
    except OSError:
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generation",
            "geração indisponível",
        )

    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generation",
            "geração insegura",
        )

    try:
        resolved_generations = (
            generations.resolve(strict=True)
        )
        resolved_generation = (
            generation.resolve(strict=True)
        )
    except OSError:
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generation",
            "geração não pôde ser resolvida",
        )

    try:
        common = Path(
            os.path.commonpath(
                (
                    str(resolved_generations),
                    str(resolved_generation),
                )
            )
        )
    except ValueError:
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generation",
            "geração fora da raiz autorizada",
        )

    if common != resolved_generations:
        fail(
            EXIT_STATE,
            "GENERATION_INVALID",
            "generation",
            "geração fora da raiz autorizada",
        )

    return resolved_generation


@dataclass(frozen=True)
class ValidatorProcessResult:
    stdout: bytes
    stderr: bytes
    exit_code: int


def build_child_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def signal_process_group(
    process: subprocess.Popen[bytes],
    signal_number: int,
) -> None:
    try:
        os.killpg(
            process.pid,
            signal_number,
        )
    except ProcessLookupError:
        pass
    except OSError:
        fail(
            5,
            "SNAPSHOT_UNREADABLE",
            "validator",
            "grupo do validador não pôde ser terminado",
        )


def capture_validator_process(
    arguments: Sequence[str],
    working_directory: Path,
    *,
    timeout_seconds: float = VALIDATOR_TIMEOUT_SECONDS,
) -> ValidatorProcessResult:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(
            timeout_seconds,
            (int, float),
        )
        or timeout_seconds <= 0
    ):
        fail(
            5,
            "SNAPSHOT_UNREADABLE",
            "validator",
            "tempo limite do validador inválido",
        )

    try:
        process = subprocess.Popen(
            list(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_directory,
            env=build_child_environment(),
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        fail(
            5,
            "SNAPSHOT_UNREADABLE",
            "validator",
            "validador não pôde ser iniciado",
        )

    if (
        process.stdout is None
        or process.stderr is None
    ):
        signal_process_group(
            process,
            signal.SIGKILL,
        )
        fail(
            5,
            "SNAPSHOT_UNREADABLE",
            "validator",
            "pipes do validador indisponíveis",
        )

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()

    selector = selectors.DefaultSelector()

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

    started = time.monotonic()
    execution_deadline = (
        started + float(timeout_seconds)
    )

    failure_code = None
    failure_exit = None
    failure_message = None

    termination_started = None
    kill_sent = False

    try:
        for descriptor, (
            stream_name,
            _stream,
        ) in streams.items():
            os.set_blocking(
                descriptor,
                False,
            )
            selector.register(
                descriptor,
                selectors.EVENT_READ,
                data=stream_name,
            )

        while (
            selector.get_map()
            or process.poll() is None
        ):
            current = time.monotonic()

            if (
                failure_code is None
                and current >= execution_deadline
            ):
                failure_code = (
                    "SNAPSHOT_UNREADABLE"
                )
                failure_exit = 5
                failure_message = (
                    "execução do validador expirou"
                )

            if (
                failure_code is not None
                and termination_started is None
            ):
                signal_process_group(
                    process,
                    signal.SIGTERM,
                )
                termination_started = current

            if (
                termination_started is not None
                and not kill_sent
                and current
                >= (
                    termination_started
                    + TERMINATION_GRACE_SECONDS
                )
            ):
                signal_process_group(
                    process,
                    signal.SIGKILL,
                )
                kill_sent = True

            wait_seconds = 0.05

            if failure_code is None:
                wait_seconds = max(
                    0.0,
                    min(
                        wait_seconds,
                        execution_deadline - current,
                    ),
                )
            elif (
                termination_started is not None
                and not kill_sent
            ):
                wait_seconds = max(
                    0.0,
                    min(
                        wait_seconds,
                        (
                            termination_started
                            + TERMINATION_GRACE_SECONDS
                            - current
                        ),
                    ),
                )

            try:
                events = selector.select(
                    wait_seconds
                )
            except OSError:
                if failure_code is None:
                    failure_code = (
                        "SNAPSHOT_UNREADABLE"
                    )
                    failure_exit = 5
                    failure_message = (
                        "captura do validador falhou"
                    )
                continue

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
                    if failure_code is None:
                        failure_code = (
                            "SNAPSHOT_UNREADABLE"
                        )
                        failure_exit = 5
                        failure_message = (
                            "saída do validador não pôde ser lida"
                        )
                    continue

                if not chunk:
                    try:
                        selector.unregister(
                            descriptor
                        )
                    except KeyError:
                        pass
                    continue

                if stream_name == "stdout":
                    stdout_buffer.extend(chunk)

                    if (
                        len(stdout_buffer)
                        > SNAPSHOT_MAX_BYTES
                        and failure_code is None
                    ):
                        failure_code = (
                            "SNAPSHOT_TOO_LARGE"
                        )
                        failure_exit = 5
                        failure_message = (
                            "snapshot excedeu o limite"
                        )
                else:
                    stderr_buffer.extend(chunk)

                    if (
                        len(stderr_buffer)
                        > DIAGNOSTIC_MAX_BYTES
                        and failure_code is None
                    ):
                        failure_code = (
                            "VALIDATOR_PROTOCOL_VIOLATION"
                        )
                        failure_exit = 8
                        failure_message = (
                            "diagnóstico excedeu o limite"
                        )

            if (
                kill_sent
                and process.poll() is not None
                and not selector.get_map()
            ):
                break

        if process.poll() is None:
            if failure_code is None:
                failure_code = (
                    "SNAPSHOT_UNREADABLE"
                )
                failure_exit = 5
                failure_message = (
                    "estado final do validador indisponível"
                )

            signal_process_group(
                process,
                signal.SIGKILL,
            )

        try:
            process.wait(
                timeout=TERMINATION_GRACE_SECONDS
            )
        except subprocess.TimeoutExpired:
            signal_process_group(
                process,
                signal.SIGKILL,
            )

            try:
                process.wait(
                    timeout=TERMINATION_GRACE_SECONDS
                )
            except subprocess.TimeoutExpired:
                fail(
                    5,
                    "SNAPSHOT_UNREADABLE",
                    "validator",
                    "validador não terminou",
                )
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()

    if failure_code is not None:
        fail(
            failure_exit,
            failure_code,
            "validator",
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
            5,
            "SNAPSHOT_UNREADABLE",
            "validator",
            "código final do validador indisponível",
        )

    return ValidatorProcessResult(
        stdout=bytes(stdout_buffer),
        stderr=bytes(stderr_buffer),
        exit_code=process.returncode,
    )


SNAPSHOT_MAX_DEPTH = 40


class SnapshotDuplicateKeyError(ValueError):
    """Snapshot com chave JSON duplicada."""


class SnapshotNonFiniteNumberError(ValueError):
    """Snapshot com número JSON não finito."""


def snapshot_invalid(
    message: str,
) -> NoReturn:
    fail(
        6,
        "SNAPSHOT_INVALID",
        "snapshot",
        message,
    )


def reject_snapshot_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document = {}

    for key, value in pairs:
        if key in document:
            raise SnapshotDuplicateKeyError(
                key
            )

        document[key] = value

    return document


def reject_snapshot_non_finite(
    value: str,
) -> NoReturn:
    raise SnapshotNonFiniteNumberError(value)


def snapshot_container_depth(
    value: object,
) -> int:
    if isinstance(value, dict):
        return 1 + max(
            (
                snapshot_container_depth(child)
                for child in value.values()
            ),
            default=0,
        )

    if isinstance(value, list):
        return 1 + max(
            (
                snapshot_container_depth(child)
                for child in value
            ),
            default=0,
        )

    return 0


def parse_snapshot_serialization(
    content: bytes,
) -> dict[str, object]:
    if not isinstance(content, bytes):
        snapshot_invalid(
            "snapshot não é sequência de bytes"
        )

    if len(content) > SNAPSHOT_MAX_BYTES:
        fail(
            5,
            "SNAPSHOT_TOO_LARGE",
            "snapshot",
            "snapshot excedeu o limite",
        )

    if not content:
        snapshot_invalid(
            "snapshot vazio"
        )

    if content.startswith(
        b"\xef\xbb\xbf"
    ):
        snapshot_invalid(
            "snapshot contém BOM"
        )

    if (
        not content.endswith(b"\n")
        or content.count(b"\n") != 1
        or b"\r" in content
    ):
        snapshot_invalid(
            "terminação do snapshot inválida"
        )

    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        snapshot_invalid(
            "snapshot não é UTF-8 válido"
        )

    try:
        document = json.loads(
            text[:-1],
            object_pairs_hook=(
                reject_snapshot_duplicate_keys
            ),
            parse_constant=(
                reject_snapshot_non_finite
            ),
        )
    except SnapshotDuplicateKeyError:
        snapshot_invalid(
            "snapshot contém chave duplicada"
        )
    except SnapshotNonFiniteNumberError:
        snapshot_invalid(
            "snapshot contém número não finito"
        )
    except (
        json.JSONDecodeError,
        RecursionError,
    ):
        snapshot_invalid(
            "snapshot contém JSON inválido"
        )

    if not isinstance(document, dict):
        snapshot_invalid(
            "snapshot não é objeto JSON"
        )

    try:
        depth = snapshot_container_depth(
            document
        )
    except RecursionError:
        snapshot_invalid(
            "snapshot excede a profundidade máxima"
        )

    if depth > SNAPSHOT_MAX_DEPTH:
        snapshot_invalid(
            "snapshot excede a profundidade máxima"
        )

    try:
        canonical = (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (
        TypeError,
        ValueError,
        RecursionError,
    ):
        snapshot_invalid(
            "snapshot não pode ser serializado"
        )

    if canonical != content:
        snapshot_invalid(
            "serialização do snapshot não é canónica"
        )

    return document


SNAPSHOT_SCHEMA_MAX_BYTES = 1048576
SNAPSHOT_SCHEMA_MAX_DEPTH = 40

JSON_SCHEMA_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)

SNAPSHOT_SCHEMA_IDENTIFIER = (
    "urn:mppt24:schema:"
    "validated-generation-snapshot:1.0.0"
)

MANIFEST_SCHEMA_IDENTIFIER = (
    "urn:mppt24:schema:"
    "generation-manifest:1.0.0"
)

REPORT_SCHEMA_IDENTIFIER = (
    "urn:mppt24:schema:report:2.1.0"
)


@dataclass(frozen=True)
class SnapshotSchemas:
    envelope: object
    manifest: object
    report: object


def configuration_invalid(
    location: str,
    message: str,
) -> NoReturn:
    fail(
        3,
        "CONFIGURATION_INVALID",
        location,
        message,
    )


def snapshot_schema_signature(
    status_result: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        status_result.st_dev,
        status_result.st_ino,
        status_result.st_mode,
        status_result.st_size,
        status_result.st_mtime_ns,
        status_result.st_ctime_ns,
    )


def secure_read_snapshot_schema(
    path: Path,
    location: str,
) -> bytes:
    try:
        initial_status = os.lstat(path)
    except OSError:
        configuration_invalid(
            location,
            "schema local ausente ou inacessível",
        )

    if (
        stat.S_ISLNK(initial_status.st_mode)
        or not stat.S_ISREG(initial_status.st_mode)
    ):
        configuration_invalid(
            location,
            "schema local não é ficheiro regular seguro",
        )

    if initial_status.st_size > SNAPSHOT_SCHEMA_MAX_BYTES:
        configuration_invalid(
            location,
            "schema local excedeu o limite",
        )

    flags = os.O_RDONLY | os.O_CLOEXEC

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(
            path,
            flags,
        )
    except OSError:
        configuration_invalid(
            location,
            "schema local não pôde ser aberto",
        )

    try:
        try:
            opened_status = os.fstat(descriptor)
        except OSError:
            configuration_invalid(
                location,
                "schema local não pôde ser inspecionado",
            )

        if (
            not stat.S_ISREG(opened_status.st_mode)
            or snapshot_schema_signature(
                opened_status
            )
            != snapshot_schema_signature(
                initial_status
            )
        ):
            configuration_invalid(
                location,
                "schema local mudou durante a abertura",
            )

        content = bytearray()

        while True:
            try:
                chunk = os.read(
                    descriptor,
                    16384,
                )
            except OSError:
                configuration_invalid(
                    location,
                    "schema local não pôde ser lido",
                )

            if not chunk:
                break

            content.extend(chunk)

            if len(content) > SNAPSHOT_SCHEMA_MAX_BYTES:
                configuration_invalid(
                    location,
                    "schema local excedeu o limite",
                )

        try:
            completed_status = os.fstat(descriptor)
        except OSError:
            configuration_invalid(
                location,
                "schema local não pôde ser reinspecionado",
            )

        if (
            snapshot_schema_signature(
                completed_status
            )
            != snapshot_schema_signature(
                opened_status
            )
            or len(content) != completed_status.st_size
        ):
            configuration_invalid(
                location,
                "schema local mudou durante a leitura",
            )

        return bytes(content)
    finally:
        os.close(descriptor)


def snapshot_schema_external_references(
    document: object,
) -> list[str]:
    external = []
    pending = [document]

    while pending:
        value = pending.pop()

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
                        external.append(str(child))

                pending.append(child)

        elif isinstance(value, list):
            pending.extend(value)

    return external


def parse_snapshot_schema_document(
    content: bytes,
    location: str,
) -> dict[str, object]:
    try:
        text = content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        configuration_invalid(
            location,
            "schema local não é UTF-8 válido",
        )

    try:
        document = json.loads(
            text,
            object_pairs_hook=(
                reject_snapshot_duplicate_keys
            ),
            parse_constant=(
                reject_snapshot_non_finite
            ),
        )
    except (
        SnapshotDuplicateKeyError,
        SnapshotNonFiniteNumberError,
        json.JSONDecodeError,
        RecursionError,
    ):
        configuration_invalid(
            location,
            "schema local contém JSON inválido",
        )

    if not isinstance(document, dict):
        configuration_invalid(
            location,
            "schema local não é objeto JSON",
        )

    try:
        depth = snapshot_container_depth(
            document
        )
    except RecursionError:
        configuration_invalid(
            location,
            "schema local excede a profundidade máxima",
        )

    if depth > SNAPSHOT_SCHEMA_MAX_DEPTH:
        configuration_invalid(
            location,
            "schema local excede a profundidade máxima",
        )

    return document


def load_snapshot_schema_validator(
    path: Path,
    expected_identifier: str,
    *,
    location: str,
    validator_class: object,
    schema_error_class: type[Exception],
) -> object:
    content = secure_read_snapshot_schema(
        path,
        location,
    )

    document = parse_snapshot_schema_document(
        content,
        location,
    )

    if (
        document.get("$schema")
        != JSON_SCHEMA_DIALECT
        or document.get("$id")
        != expected_identifier
    ):
        configuration_invalid(
            location,
            "identidade ou dialecto do schema inválido",
        )

    if snapshot_schema_external_references(
        document
    ):
        configuration_invalid(
            location,
            "schema local contém referência externa",
        )

    try:
        validator_class.check_schema(document)
    except schema_error_class:
        configuration_invalid(
            location,
            "schema local inválido",
        )

    return validator_class(document)


def load_snapshot_schemas(
    project_root: Path,
) -> SnapshotSchemas:
    if not isinstance(project_root, Path):
        configuration_invalid(
            "schemas",
            "raiz local dos schemas inválida",
        )

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        fail(
            3,
            "DEPENDENCY_UNAVAILABLE",
            "dependency",
            "python3-jsonschema indisponível",
        )

    envelope = load_snapshot_schema_validator(
        (
            project_root
            / "schemas"
            / "validated-generation-snapshot"
            / "1.0.0"
            / "validated-generation-snapshot.schema.json"
        ),
        SNAPSHOT_SCHEMA_IDENTIFIER,
        location="snapshot-schema",
        validator_class=Draft202012Validator,
        schema_error_class=SchemaError,
    )

    manifest = load_snapshot_schema_validator(
        (
            project_root
            / "schemas"
            / "generation-manifest"
            / "1.0.0"
            / "generation-manifest.schema.json"
        ),
        MANIFEST_SCHEMA_IDENTIFIER,
        location="manifest-schema",
        validator_class=Draft202012Validator,
        schema_error_class=SchemaError,
    )

    report = load_snapshot_schema_validator(
        (
            project_root
            / "schemas"
            / "report"
            / "2.1.0"
            / "report.schema.json"
        ),
        REPORT_SCHEMA_IDENTIFIER,
        location="report-schema",
        validator_class=Draft202012Validator,
        schema_error_class=SchemaError,
    )

    return SnapshotSchemas(
        envelope=envelope,
        manifest=manifest,
        report=report,
    )


def snapshot_document_errors(
    validator: object,
    document: object,
) -> list[object]:
    try:
        return list(
            validator.iter_errors(document)
        )
    except Exception:
        snapshot_invalid(
            "documento incorporado não pôde ser validado"
        )


def validate_snapshot_documents(
    snapshot: dict[str, object],
    schemas: SnapshotSchemas,
) -> dict[str, object]:
    if (
        not isinstance(snapshot, dict)
        or not isinstance(
            schemas,
            SnapshotSchemas,
        )
    ):
        snapshot_invalid(
            "estrutura de validação do snapshot inválida"
        )

    if snapshot_document_errors(
        schemas.envelope,
        snapshot,
    ):
        snapshot_invalid(
            "envelope do snapshot viola o schema"
        )

    manifest = snapshot["manifest"]
    reports = snapshot["reports"]

    if snapshot_document_errors(
        schemas.manifest,
        manifest,
    ):
        snapshot_invalid(
            "manifesto incorporado viola o schema"
        )

    if not isinstance(reports, dict):
        snapshot_invalid(
            "coleção de relatórios inválida"
        )

    for report in reports.values():
        if snapshot_document_errors(
            schemas.report,
            report,
        ):
            snapshot_invalid(
                "relatório incorporado viola o schema"
            )

    return snapshot


def snapshot_semantic_violation(
    message: str,
) -> NoReturn:
    fail(
        7,
        "SNAPSHOT_SEMANTIC_VIOLATION",
        "snapshot",
        message,
    )


def snapshot_mismatch(
    message: str,
) -> NoReturn:
    fail(
        8,
        "SNAPSHOT_MISMATCH",
        "snapshot",
        message,
    )


def validate_snapshot_semantics(
    snapshot: dict[str, object],
    expected_generation_id: str,
) -> dict[str, object]:
    if (
        not isinstance(snapshot, dict)
        or not isinstance(
            expected_generation_id,
            str,
        )
        or not expected_generation_id
    ):
        snapshot_semantic_violation(
            "entrada semântica do snapshot inválida"
        )

    snapshot_generation_id = snapshot.get(
        "generation_id"
    )

    if (
        snapshot_generation_id
        != expected_generation_id
    ):
        snapshot_mismatch(
            "snapshot diverge da geração solicitada"
        )

    manifest = snapshot.get("manifest")
    reports = snapshot.get("reports")
    snapshot_state = snapshot.get("state")

    if (
        not isinstance(manifest, dict)
        or not isinstance(reports, dict)
    ):
        snapshot_semantic_violation(
            "estrutura interna do snapshot inválida"
        )

    if (
        manifest.get("generation_id")
        != snapshot_generation_id
    ):
        snapshot_semantic_violation(
            "identificador interno da geração diverge"
        )

    manifest_state = manifest.get("state")

    if manifest_state != snapshot_state:
        snapshot_semantic_violation(
            "estado do envelope diverge do manifesto"
        )

    modules = manifest.get("modules")
    summary = manifest.get("summary")

    if (
        not isinstance(modules, list)
        or not isinstance(summary, dict)
    ):
        snapshot_semantic_violation(
            "estrutura do manifesto incorporado inválida"
        )

    successful_entries = []
    failed_entries = []
    module_names = []

    for entry in modules:
        if not isinstance(entry, dict):
            snapshot_semantic_violation(
                "entrada de módulo inválida"
            )

        module = entry.get("module")
        outcome = entry.get("outcome")

        if not isinstance(module, str):
            snapshot_semantic_violation(
                "nome de módulo inválido"
            )

        module_names.append(module)

        if outcome == "SUCCESS":
            successful_entries.append(entry)
        elif outcome == "FAILED":
            failed_entries.append(entry)
        else:
            snapshot_semantic_violation(
                "resultado de módulo inválido"
            )

    if len(module_names) != len(set(module_names)):
        snapshot_semantic_violation(
            "manifesto contém módulos duplicados"
        )

    expected_summary = {
        "declared": len(modules),
        "successful": len(successful_entries),
        "failed": len(failed_entries),
        "reports_written": len(successful_entries),
    }

    if summary != expected_summary:
        snapshot_semantic_violation(
            "resumo do manifesto é incoerente"
        )

    if (
        len(reports)
        != summary["successful"]
        or len(reports)
        != summary["reports_written"]
    ):
        snapshot_semantic_violation(
            "quantidade de relatórios é incoerente"
        )

    successful_modules = {
        entry["module"]
        for entry in successful_entries
    }

    if set(reports) != successful_modules:
        snapshot_semantic_violation(
            "conjunto de relatórios é incoerente"
        )

    descriptor_fields = (
        "module",
        "version",
        "timestamp",
        "status",
    )

    for entry in successful_entries:
        module = entry["module"]
        descriptor = entry.get("report")
        report = reports.get(module)

        if (
            not isinstance(descriptor, dict)
            or not isinstance(report, dict)
        ):
            snapshot_semantic_violation(
                "relatório de módulo bem-sucedido ausente"
            )

        if report.get("module") != module:
            snapshot_semantic_violation(
                "chave e módulo do relatório divergem"
            )

        for field in descriptor_fields:
            if (
                descriptor.get(field)
                != report.get(field)
            ):
                snapshot_semantic_violation(
                    "relatório diverge do descritor"
                )

    for entry in failed_entries:
        module = entry["module"]
        error_code = entry.get("error_code")
        exit_code = entry.get("exit_code")

        if (
            entry.get("report") is not None
            or module in reports
            or not isinstance(error_code, str)
            or not error_code
            or isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or exit_code == 0
        ):
            snapshot_semantic_violation(
                "entrada de módulo falhado incoerente"
            )

    if snapshot_state == "COMPLETE":
        if (
            not modules
            or failed_entries
            or len(successful_entries) != len(modules)
        ):
            snapshot_semantic_violation(
                "estado COMPLETE incoerente"
            )

    elif snapshot_state == "PARTIAL":
        if (
            not successful_entries
            or not failed_entries
        ):
            snapshot_semantic_violation(
                "estado PARTIAL incoerente"
            )

    elif snapshot_state == "FAILED":
        if (
            not modules
            or successful_entries
            or len(failed_entries) != len(modules)
            or reports
        ):
            snapshot_semantic_violation(
                "estado FAILED incoerente"
            )

    else:
        snapshot_semantic_violation(
            "estado da geração inválido"
        )

    return snapshot


VALIDATOR_FAILURE_CODES = {
    3: {
        "DEPENDENCY_UNAVAILABLE",
        "REGISTRY_INVALID",
        "SCHEMA_INVALID",
    },
    4: {
        "GENERATION_INVALID",
    },
    5: {
        "MANIFEST_MISSING",
        "MANIFEST_UNREADABLE",
        "MANIFEST_TOO_LARGE",
        "INVALID_UTF8",
        "INVALID_JSON",
        "DUPLICATE_KEY",
        "NON_FINITE_NUMBER",
        "DEPTH_LIMIT_EXCEEDED",
    },
    6: {
        "CONTRACT_VIOLATION",
    },
    7: {
        "SEMANTIC_VIOLATION",
    },
    8: {
        "GENERATION_MISMATCH",
    },
    9: {
        "INTERNAL_ERROR",
    },
}


def validator_protocol_violation(
    message: str,
) -> NoReturn:
    fail(
        8,
        "VALIDATOR_PROTOCOL_VIOLATION",
        "validator",
        message,
    )


def validate_validator_result(
    result: ValidatorProcessResult,
) -> bytes:
    if not isinstance(
        result,
        ValidatorProcessResult,
    ):
        validator_protocol_violation(
            "resultado do validador inválido"
        )

    if (
        isinstance(result.exit_code, bool)
        or not isinstance(
            result.exit_code,
            int,
        )
        or not isinstance(result.stdout, bytes)
        or not isinstance(result.stderr, bytes)
    ):
        validator_protocol_violation(
            "tipos do resultado do validador inválidos"
        )

    if len(result.stdout) > SNAPSHOT_MAX_BYTES:
        fail(
            5,
            "SNAPSHOT_TOO_LARGE",
            "validator",
            "snapshot excedeu o limite",
        )

    if len(result.stderr) > DIAGNOSTIC_MAX_BYTES:
        validator_protocol_violation(
            "diagnóstico excedeu o limite"
        )

    if result.exit_code == 0:
        if result.stderr:
            validator_protocol_violation(
                "validador produziu stderr com sucesso"
            )

        if not result.stdout:
            fail(
                5,
                "SNAPSHOT_MISSING",
                "validator",
                "validador terminou sem snapshot",
            )

        return result.stdout

    if result.stdout:
        validator_protocol_violation(
            "validador produziu stdout durante falha"
        )

    if result.exit_code == 2:
        validator_protocol_violation(
            "validador rejeitou argumentos internos"
        )

    accepted_codes = VALIDATOR_FAILURE_CODES.get(
        result.exit_code
    )

    if accepted_codes is None:
        validator_protocol_violation(
            "código de processo do validador inválido"
        )

    if not result.stderr:
        validator_protocol_violation(
            "diagnóstico do validador ausente"
        )

    try:
        diagnostic = result.stderr.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError:
        validator_protocol_violation(
            "diagnóstico do validador não é UTF-8"
        )

    if (
        not diagnostic.endswith("\n")
        or diagnostic.count("\n") != 1
        or "\r" in diagnostic
    ):
        validator_protocol_violation(
            "terminação do diagnóstico inválida"
        )

    fields = diagnostic[:-1].split("\t")

    if len(fields) != 4:
        validator_protocol_violation(
            "estrutura do diagnóstico inválida"
        )

    marker, code, location, message = fields

    if marker != "ERROR":
        validator_protocol_violation(
            "marcador do diagnóstico inválido"
        )

    if code not in accepted_codes:
        validator_protocol_violation(
            "código textual do validador incoerente"
        )

    if (
        len(location) > 240
        or len(message) > 240
    ):
        validator_protocol_violation(
            "campos do diagnóstico excedem o limite"
        )

    fail(
        result.exit_code,
        code,
        sanitize(location),
        sanitize(message),
    )


def build_validator_arguments(
    generation_id: str,
    generation: Path,
) -> list[str]:
    validator = (
        Path(__file__).resolve().parent.parent
        / "core"
        / "validate-manifest.py"
    )

    return [
        "/usr/bin/python3",
        "-I",
        str(validator),
        "--emit-validated-snapshot",
        "--expected-generation-id",
        generation_id,
        str(generation),
    ]


def snapshot_module_outcome(
    snapshot: dict[str, object],
    module_name: str,
) -> str | None:
    manifest = snapshot.get("manifest")

    if not isinstance(manifest, dict):
        return None

    modules = manifest.get("modules")

    if not isinstance(modules, list):
        return None

    for entry in modules:
        if (
            isinstance(entry, dict)
            and entry.get("module") == module_name
        ):
            outcome = entry.get("outcome")

            if isinstance(outcome, str):
                return outcome

            return None

    return None


def snapshot_module_report(
    snapshot: dict[str, object],
    module_name: str,
) -> dict[str, object] | None:
    if (
        snapshot_module_outcome(
            snapshot,
            module_name,
        )
        != "SUCCESS"
    ):
        return None

    reports = snapshot.get("reports")

    if not isinstance(reports, dict):
        return None

    report = reports.get(module_name)

    if not isinstance(report, dict):
        return None

    return report


def evaluate_resources_health(
    snapshot: dict[str, object],
) -> str:
    import math

    if not isinstance(snapshot, dict):
        return "UNKNOWN"

    cpu_report = snapshot_module_report(
        snapshot,
        "observer-cpu",
    )
    memory_report = snapshot_module_report(
        snapshot,
        "observer-memory",
    )

    if (
        cpu_report is None
        or memory_report is None
    ):
        return "UNKNOWN"

    cpu_facts = cpu_report.get("facts")
    memory_facts = memory_report.get("facts")

    if (
        not isinstance(cpu_facts, dict)
        or not isinstance(memory_facts, dict)
    ):
        return "UNKNOWN"

    memory = memory_facts.get("memory")

    if not isinstance(memory, dict):
        return "UNKNOWN"

    cpu_count = cpu_facts.get("cpu_count")
    load_15min = cpu_facts.get("load_15min")
    mem_total = memory.get("MemTotal")
    mem_available = memory.get("MemAvailable")
    swap_total = memory.get("SwapTotal")
    swap_free = memory.get("SwapFree")

    if (
        type(cpu_count) is not int
        or cpu_count <= 0
        or type(load_15min) not in {
            int,
            float,
            str,
        }
        or type(mem_total) is not int
        or mem_total <= 0
        or type(mem_available) is not int
        or mem_available < 0
        or type(swap_total) is not int
        or swap_total < 0
        or type(swap_free) is not int
        or swap_free < 0
    ):
        return "UNKNOWN"

    if isinstance(load_15min, str):
        if not re.fullmatch(
            r"[0-9]+(?:\.[0-9]+)?",
            load_15min,
        ):
            return "UNKNOWN"

        try:
            load_15min = float(
                load_15min
            )
        except ValueError:
            return "UNKNOWN"

    if (
        type(load_15min) not in {
            int,
            float,
        }
        or not math.isfinite(load_15min)
        or load_15min < 0
    ):
        return "UNKNOWN"

    if (
        load_15min >= cpu_count * 2
        or mem_available * 100
        < mem_total * 5
    ):
        return "ERROR"

    if (
        load_15min >= cpu_count
        or mem_available * 100
        < mem_total * 15
        or (
            swap_total > 0
            and (
                swap_total - swap_free
            )
            * 100
            >= swap_total * 75
        )
    ):
        return "WARNING"

    return "OK"



def evaluate_connectivity_health(
    snapshot: dict[str, object],
) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"

    report = snapshot_module_report(
        snapshot,
        "observer-network",
    )

    if report is None:
        return "UNKNOWN"

    facts = report.get("facts")

    if not isinstance(facts, dict):
        return "UNKNOWN"

    interfaces = facts.get("interfaces")
    default_routes = facts.get(
        "default_routes"
    )

    if (
        not isinstance(interfaces, list)
        or not isinstance(default_routes, list)
    ):
        return "UNKNOWN"

    expected_interfaces = {
        "enp8s0": None,
        "tailscale0": None,
        "wg0": None,
    }

    for interface in interfaces:
        if not isinstance(interface, dict):
            return "UNKNOWN"

        ifname = interface.get("ifname")

        if not isinstance(ifname, str):
            return "UNKNOWN"

        if ifname not in expected_interfaces:
            continue

        flags = interface.get("flags")

        if (
            not isinstance(flags, list)
            or not all(
                isinstance(flag, str)
                for flag in flags
            )
        ):
            return "UNKNOWN"

        expected_interfaces[ifname] = (
            "UP" in flags
            and "LOWER_UP" in flags
        )

    lan = expected_interfaces["enp8s0"]
    tailscale = expected_interfaces["tailscale0"]
    wireguard = expected_interfaces["wg0"]

    if lan is None:
        return "ERROR"

    if lan is not True:
        return "ERROR"

    if not default_routes:
        return "ERROR"

    first_route = default_routes[0]

    if not isinstance(first_route, dict):
        return "UNKNOWN"

    gateway = first_route.get("gateway")
    device = first_route.get("dev")

    if (
        device is not None
        and not isinstance(device, str)
    ):
        return "UNKNOWN"

    if (
        gateway is not None
        and not isinstance(gateway, str)
    ):
        return "UNKNOWN"

    if (
        not isinstance(gateway, str)
        or not gateway
    ):
        return "ERROR"

    if not isinstance(device, str):
        return "UNKNOWN"

    if device != "enp8s0":
        return "ERROR"

    if (
        tailscale is not True
        or wireguard is not True
    ):
        return "WARNING"

    return "OK"


def evaluate_services_health(
    snapshot: dict[str, object],
) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"

    report = snapshot_module_report(
        snapshot,
        "observer-services",
    )

    if report is None:
        return "UNKNOWN"

    facts = report.get("facts")

    if not isinstance(facts, dict):
        return "UNKNOWN"

    service_names = (
        "ssh.service",
        "tailscaled.service",
        "fail2ban.service",
        "AdGuardHome.service",
    )

    states: dict[str, str] = {}

    for service_name in service_names:
        state = facts.get(service_name)

        if not isinstance(state, str):
            return "UNKNOWN"

        states[service_name] = state

    if (
        states["ssh.service"] != "active"
        or states["AdGuardHome.service"] != "active"
    ):
        return "ERROR"

    if (
        states["tailscaled.service"] != "active"
        or states["fail2ban.service"] != "active"
    ):
        return "WARNING"

    return "OK"


def evaluate_security_health(
    snapshot: dict[str, object],
) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"

    report = snapshot_module_report(
        snapshot,
        "observer-ssh",
    )

    if report is None:
        return "UNKNOWN"

    facts = report.get("facts")

    if not isinstance(facts, dict):
        return "UNKNOWN"

    journal_available = facts.get(
        "journal_available"
    )
    failed_password_events = facts.get(
        "failed_password_events_24h"
    )

    if journal_available is not True:
        return "UNKNOWN"

    if (
        isinstance(
            failed_password_events,
            bool,
        )
        or not isinstance(
            failed_password_events,
            int,
        )
        or failed_password_events < 0
    ):
        return "UNKNOWN"

    if failed_password_events > 0:
        return "WARNING"

    return "OK"


def evaluate_system_health(
    snapshot: dict[str, object],
) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"

    report = snapshot_module_report(
        snapshot,
        "observer-system",
    )

    if report is None:
        return "UNKNOWN"

    status = report.get("status")

    if status == "ERROR":
        return "ERROR"

    if status == "WARNING":
        return "WARNING"

    if status != "OK":
        return "UNKNOWN"

    facts = report.get("facts")

    if not isinstance(facts, dict):
        return "UNKNOWN"

    time_available = facts.get(
        "time_available"
    )
    ntp_enabled = facts.get(
        "ntp_enabled"
    )
    ntp_synchronized = facts.get(
        "ntp_synchronized"
    )

    if (
        type(time_available) is not bool
        or type(ntp_enabled) is not bool
        or type(ntp_synchronized) is not bool
    ):
        return "UNKNOWN"

    if time_available is not True:
        return "UNKNOWN"

    if (
        ntp_enabled is not True
        or ntp_synchronized is not True
    ):
        return "WARNING"

    return "OK"


def evaluate_overall_health(
    snapshot: dict[str, object],
) -> str:
    if not isinstance(snapshot, dict):
        snapshot_semantic_violation(
            "snapshot indisponível para interpretação"
        )

    state = snapshot.get("state")
    reports = snapshot.get("reports")

    if state == "FAILED":
        fail(
            6,
            "GENERATION_FAILED",
            "generation",
            "geração válida sem módulos bem-sucedidos",
        )

    if (
        state not in {
            "COMPLETE",
            "PARTIAL",
        }
        or not isinstance(reports, dict)
    ):
        snapshot_semantic_violation(
            "estado ou relatórios indisponíveis"
        )

    statuses = []

    for report in reports.values():
        if not isinstance(report, dict):
            snapshot_semantic_violation(
                "relatório indisponível para interpretação"
            )

        status = report.get("status")

        if status not in {
            "OK",
            "WARNING",
            "ERROR",
            "UNKNOWN",
        }:
            snapshot_semantic_violation(
                "estado de relatório inválido"
            )

        statuses.append(status)

    if not statuses:
        snapshot_semantic_violation(
            "nenhum relatório disponível para interpretação"
        )

    if "ERROR" in statuses:
        return "ERROR"

    if state == "PARTIAL":
        return "UNKNOWN"

    if "WARNING" in statuses:
        return "WARNING"

    if "UNKNOWN" in statuses:
        return "UNKNOWN"

    return "OK"


def build_health(
    snapshot: dict[str, object],
) -> dict[str, dict[str, str]]:
    overall = evaluate_overall_health(
        snapshot
    )

    return {
        "overall": {
            "status": overall,
        },
        "system": {
            "status": evaluate_system_health(
                snapshot
            ),
        },
        "security": {
            "status": evaluate_security_health(
                snapshot
            ),
        },
        "resources": {
            "status": evaluate_resources_health(
                snapshot
            ),
        },
        "connectivity": {
            "status": evaluate_connectivity_health(
                snapshot
            ),
        },
        "services": {
            "status": evaluate_services_health(
                snapshot
            ),
        },
    }


def obtain_validated_snapshot(
    generation_id: str,
    generation: Path,
) -> dict[str, object]:
    project_root = (
        Path(__file__).resolve().parent.parent
    )

    arguments = build_validator_arguments(
        generation_id,
        generation,
    )

    process_result = capture_validator_process(
        arguments,
        project_root,
    )

    serialized = validate_validator_result(
        process_result
    )

    snapshot = parse_snapshot_serialization(
        serialized
    )

    schemas = load_snapshot_schemas(
        project_root
    )

    validated_snapshot = (
        validate_snapshot_documents(
            snapshot,
            schemas,
        )
    )

    validated_snapshot = (
        validate_snapshot_semantics(
            validated_snapshot,
            generation_id,
        )
    )

    if validated_snapshot["state"] == "FAILED":
        fail(
            6,
            "GENERATION_FAILED",
            "generation",
            "geração válida sem módulos bem-sucedidos",
        )

    return validated_snapshot


def resolve_input(
    supplied_state_root: str,
) -> tuple[Path, str, Path]:
    state_root = validate_state_root(
        supplied_state_root
    )
    generation_id = read_current_generation(
        state_root
    )
    generation = resolve_generation(
        state_root,
        generation_id,
    )

    return (
        state_root,
        generation_id,
        generation,
    )



def build_interpretation(
    snapshot: dict[str, object],
    health: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    analysis: list[str] = []
    summary: list[str] = []
    conclusions: list[str] = []
    recommendations: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    def add_unique(
        target: list[str],
        text: str,
    ) -> None:
        if text and text not in target:
            target.append(text)

    state = snapshot.get("state")
    generation_id = snapshot.get("generation_id")

    manifest = snapshot.get("manifest")
    reports = snapshot.get("reports")

    modules: list[object] = []

    if isinstance(manifest, dict):
        raw_modules = manifest.get("modules")

        if isinstance(raw_modules, list):
            modules = raw_modules

    if not isinstance(reports, dict):
        reports = {}

    declared = len(modules)
    successful = 0
    failed = 0

    failed_modules: list[dict[str, object]] = []

    for item in modules:
        if not isinstance(item, dict):
            continue

        outcome = item.get("outcome")

        if outcome == "SUCCESS":
            successful += 1

        elif outcome == "FAILED":
            failed += 1
            failed_modules.append(item)

    if isinstance(generation_id, str) and generation_id:
        add_unique(
            analysis,
            f"Geração validada: {generation_id}.",
        )

    if isinstance(state, str) and state:
        add_unique(
            analysis,
            f"Estado da geração: {state}.",
        )

    add_unique(
        analysis,
        (
            "Cobertura declarada: "
            f"{declared} módulos; "
            f"sucesso={successful}; "
            f"falha={failed}."
        ),
    )

    overall_status = "UNKNOWN"

    overall = health.get("overall")

    if isinstance(overall, dict):
        value = overall.get("status")

        if isinstance(value, str):
            overall_status = value

    if overall_status == "ERROR":
        add_unique(
            summary,
            "Estado global crítico.",
        )
        add_unique(
            analysis,
            "Estado global: ERROR.",
        )
        add_unique(
            conclusions,
            "Estado global: ERROR.",
        )
        add_unique(
            recommendations,
            (
                "Existem condições em estado ERROR. "
                "Rever os dados validados antes de qualquer intervenção."
            ),
        )

    elif overall_status == "WARNING":
        add_unique(
            summary,
            "Estado global requer atenção.",
        )
        add_unique(
            analysis,
            "Estado global: WARNING.",
        )
        add_unique(
            conclusions,
            "Estado global: WARNING.",
        )
        add_unique(
            recommendations,
            (
                "Existem condições em estado WARNING. "
                "Recomenda-se análise antes de alterações."
            ),
        )

    elif overall_status == "OK":
        add_unique(
            summary,
            "Estado global operacional.",
        )
        add_unique(
            analysis,
            "Estado global: OK.",
        )
        add_unique(
            conclusions,
            "Estado global: OK.",
        )
        add_unique(
            recommendations,
            "Nenhuma ação recomendada.",
        )

    else:
        add_unique(
            summary,
            "Estado global desconhecido.",
        )
        add_unique(
            analysis,
            "Estado global: UNKNOWN.",
        )
        add_unique(
            conclusions,
            "Estado global: UNKNOWN.",
        )
        add_unique(
            recommendations,
            (
                "O estado global não pôde ser determinado integralmente. "
                "Rever os dados disponíveis antes de alterações."
            ),
        )

    for module_name in sorted(reports):
        report = reports.get(module_name)

        if not isinstance(report, dict):
            continue

        status = report.get("status")

        if status == "WARNING":
            add_unique(
                warnings,
                f"{module_name}: estado WARNING.",
            )

        elif status == "ERROR":
            add_unique(
                errors,
                f"{module_name}: estado ERROR.",
            )

    if state == "PARTIAL":
        add_unique(
            warnings,
            (
                "Observação incompleta: "
                "o sistema não foi integralmente observado."
            ),
        )

        add_unique(
            conclusions,
            (
                "A geração foi observada parcialmente; "
                "existem factos e conclusões que não puderam ser produzidos."
            ),
        )

        add_unique(
            recommendations,
            (
                "A geração é PARTIAL. "
                "Não interpretar ausência de dados como estado normal."
            ),
        )

        unknown_domains = []

        for name in (
            "overall",
            "system",
            "security",
            "resources",
            "connectivity",
            "services",
        ):
            domain = health.get(name)

            if (
                isinstance(domain, dict)
                and domain.get("status") == "UNKNOWN"
            ):
                unknown_domains.append(name)

        if unknown_domains:
            add_unique(
                analysis,
                (
                    "Domínios health com avaliação incompleta: "
                    + ", ".join(unknown_domains)
                    + "."
                ),
            )

        for item in failed_modules:
            module_name = item.get("module")
            error_code = item.get("error_code")
            exit_code = item.get("exit_code")

            add_unique(
                errors,
                (
                    f"Módulo {module_name}: FAILED; "
                    f"error_code={error_code}; "
                    f"exit_code={exit_code}."
                ),
            )

    system = health.get("system")

    if isinstance(system, dict):
        system_status = system.get("status")

        if system_status == "OK":
            add_unique(
                summary,
                "Sistema base operacional.",
            )
            add_unique(
                conclusions,
                (
                    "Sistema: fontes determinantes disponíveis "
                    "e estado operacional."
                ),
            )

        elif system_status == "WARNING":
            add_unique(
                summary,
                "Sistema base requer atenção.",
            )

        elif system_status == "ERROR":
            add_unique(
                summary,
                "Sistema base em estado crítico.",
            )

        else:
            add_unique(
                summary,
                "Estado do sistema base desconhecido.",
            )
            add_unique(
                conclusions,
                (
                    "Sistema: dados determinantes insuficientes "
                    "para uma conclusão operacional."
                ),
            )

    ssh_report = reports.get("observer-ssh")

    if isinstance(ssh_report, dict):
        facts = ssh_report.get("facts")

        if isinstance(facts, dict):
            invalid_users = facts.get(
                "invalid_user_events_24h"
            )

            if (
                isinstance(invalid_users, int)
                and not isinstance(invalid_users, bool)
                and invalid_users > 0
            ):
                add_unique(
                    conclusions,
                    (
                        "Segurança: observadas "
                        f"{invalid_users} tentativas de utilizadores inválidos "
                        "nas últimas 24 horas."
                    ),
                )

            publickey = facts.get(
                "accepted_publickey_events_24h"
            )

            if (
                isinstance(publickey, int)
                and not isinstance(publickey, bool)
                and publickey > 0
            ):
                add_unique(
                    conclusions,
                    (
                        "Segurança: autenticação por chave pública "
                        "em utilização."
                    ),
                )

    services_report = reports.get(
        "observer-services"
    )

    if isinstance(services_report, dict):
        facts = services_report.get("facts")

        if isinstance(facts, dict):
            service_conclusions = (
                (
                    "ssh.service",
                    "Serviços: SSH operacional.",
                ),
                (
                    "tailscaled.service",
                    "Serviços: Tailscale operacional.",
                ),
                (
                    "fail2ban.service",
                    "Serviços: Fail2Ban operacional.",
                ),
                (
                    "AdGuardHome.service",
                    "Serviços: AdGuardHome operacional.",
                ),
            )

            for key, text in service_conclusions:
                if facts.get(key) == "active":
                    add_unique(
                        conclusions,
                        text,
                    )

    return {
        "analysis": analysis,
        "summary": summary,
        "conclusions": conclusions,
        "recommendations": recommendations,
        "warnings": warnings,
        "errors": errors,
    }


def build_final_report(
    snapshot: dict[str, object],
    health: dict[str, object],
    interpretation: dict[str, object],
    timestamp: str,
) -> dict[str, object]:
    reports = snapshot["reports"]

    if not isinstance(reports, dict):
        raise TypeError("snapshot reports must be an object")

    counts = {
        "OK": 0,
        "WARNING": 0,
        "ERROR": 0,
        "UNKNOWN": 0,
    }

    for report in reports.values():
        status = "UNKNOWN"

        if isinstance(report, dict):
            value = report.get("status")

            if value in counts:
                status = value

        counts[status] += 1

    overall = health["overall"]

    if not isinstance(overall, dict):
        raise TypeError("health overall must be an object")

    status = overall["status"]

    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "timestamp": timestamp,
        "status": status,
        "confidence": 100,
        "facts": {
            "observer_reports": len(reports),
            "ok": counts["OK"],
            "warning": counts["WARNING"],
            "error": counts["ERROR"],
            "unknown": counts["UNKNOWN"],
        },
        "analysis": copy.deepcopy(
            interpretation["analysis"]
        ),
        "conclusions": copy.deepcopy(
            interpretation["conclusions"]
        ),
        "health": copy.deepcopy(
            health
        ),
        "summary": copy.deepcopy(
            interpretation["summary"]
        ),
        "recommendations": copy.deepcopy(
            interpretation["recommendations"]
        ),
        "warnings": copy.deepcopy(
            interpretation["warnings"]
        ),
        "errors": copy.deepcopy(
            interpretation["errors"]
        ),
    }


def final_report_invalid(
    message: str,
) -> NoReturn:
    fail(
        EXIT_INTERNAL,
        "FINAL_REPORT_INVALID",
        "final-report",
        message,
    )


def validate_final_report(
    report: dict[str, object],
    validator: object,
) -> dict[str, object]:
    if not isinstance(report, dict):
        final_report_invalid(
            "relatório final não é um objeto"
        )

    try:
        errors = list(
            validator.iter_errors(report)
        )
    except Exception:
        final_report_invalid(
            "relatório final não pôde ser validado"
        )

    if errors:
        final_report_invalid(
            "relatório final viola o schema 2.1.0"
        )

    return report


def serialize_final_report(
    report: dict[str, object],
) -> str:
    try:
        serialized = json.dumps(
            report,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        final_report_invalid(
            "relatório final não é serializável"
        )

    return serialized + "\n"


def current_report_timestamp() -> str:
    return (
        datetime.now()
        .astimezone()
        .strftime("%Y-%m-%dT%H:%M:%S%z")
    )


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

        (
            _state_root,
            generation_id,
            generation,
        ) = resolve_input(
            arguments.state_root
        )

        snapshot = obtain_validated_snapshot(
            generation_id,
            generation,
        )

        health = build_health(
            snapshot
        )

        interpretation = build_interpretation(
            snapshot,
            health,
        )

        report = build_final_report(
            snapshot,
            health,
            interpretation,
            current_report_timestamp(),
        )

        project_root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        schemas = load_snapshot_schemas(
            project_root
        )

        validate_final_report(
            report,
            schemas.report,
        )

        output = serialize_final_report(
            report
        )

        sys.stdout.write(
            output
        )

        return EXIT_SUCCESS

    except DecisionFailure as error:
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


if __name__ == "__main__":
    raise SystemExit(main())
