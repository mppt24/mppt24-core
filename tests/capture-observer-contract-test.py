#!/usr/bin/python3 -I
"""Testes do Capturador de Observers MPPT24 1.0.0."""

import ast
import importlib.util
import hashlib
import json
import os
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
CAPTURER = ROOT / "core" / "capture-observer.py"
LEGACY_CAPTURER = ROOT / "core" / "capture-observer.sh"
REPORT_VALIDATOR = ROOT / "core" / "validate-report.py"
REGISTRY = ROOT / "config" / "observer-registry.json"
REGISTRY_SCHEMA = (
    ROOT
    / "schemas"
    / "observer-registry"
    / "1.0.0"
    / "observer-registry.schema.json"
)
REPORT_SCHEMA = (
    ROOT
    / "schemas"
    / "report"
    / "2.1.0"
    / "report.schema.json"
)
VALID_REPORT_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "report-2.1.0"
    / "valid-minimal.json"
)

RESULT_SCHEMA = (
    ROOT
    / "schemas"
    / "capture-result"
    / "1.0.0"
    / "capture-result.schema.json"
)

EXPECTED_LEGACY_SHA256 = (
    "721840c8b674ea908c0d6176372b9dbeb"
    "cc77e2d423269fafb0d7c2e9e530add"
)


def load_module(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise RuntimeError(f"não foi possível carregar {path}")

    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


capturer_module = load_module(
    CAPTURER,
    "mppt24_capture_observer_test",
)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class CaptureObserverContractTest(unittest.TestCase):
    """Validar o capturador sem usar staging operacional."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mppt24-capturer-contract-"
        )
        self.temp_path = Path(self.temporary.name)
        self.project_root = self.temp_path / "project"
        self.state_root = self.temp_path / "state"
        self.staging = (
            self.state_root
            / "generations"
            / ".staging-contract-test"
        )
        self.observers_staging = (
            self.staging
            / "observers"
        )

        self.result_schema = load_json(RESULT_SCHEMA)
        Draft202012Validator.check_schema(
            self.result_schema
        )
        self.result_validator = Draft202012Validator(
            self.result_schema
        )

        self.registry = load_json(REGISTRY)
        self.prepare_project()
        self.prepare_staging()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_project_file(
        self,
        relative: str,
        *,
        executable: bool = False,
    ) -> Path:
        source = ROOT / relative
        target = self.project_root / relative
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copyfile(source, target)
        target.chmod(0o755 if executable else 0o644)
        return target

    def prepare_project(self) -> None:
        self.copy_project_file(
            "core/capture-observer.py",
            executable=True,
        )
        self.copy_project_file(
            "core/validate-report.py",
            executable=True,
        )
        self.copy_project_file(
            "config/observer-registry.json",
        )
        self.copy_project_file(
            (
                "schemas/observer-registry/1.0.0/"
                "observer-registry.schema.json"
            ),
        )
        self.copy_project_file(
            "schemas/report/2.1.0/report.schema.json",
        )
        self.copy_project_file(
            (
                "schemas/capture-result/1.0.0/"
                "capture-result.schema.json"
            ),
        )

        for entry in self.registry["observers"]:
            self.copy_project_file(
                entry["executable"],
                executable=True,
            )

    def prepare_staging(self) -> None:
        self.observers_staging.mkdir(
            parents=True,
            mode=0o750,
        )

    @property
    def sandbox_capturer(self) -> Path:
        return (
            self.project_root
            / "core"
            / "capture-observer.py"
        )

    def report_path(
        self,
        module: str = "observer-cpu",
    ) -> Path:
        return (
            self.observers_staging
            / f"{module}.json"
        )

    def valid_report(
        self,
        module: str = "observer-cpu",
        version: str = "1.0.0",
    ) -> dict[str, object]:
        document = load_json(VALID_REPORT_FIXTURE)
        document["module"] = module
        document["version"] = version
        return document

    def write_fake_observer(
        self,
        body: str,
        *,
        module: str = "observer-cpu",
        declared_module: str | None = None,
        declared_version: str = "1.0.0",
    ) -> Path:
        declaration = (
            module
            if declared_module is None
            else declared_module
        )
        path = (
            self.project_root
            / "observer"
            / f"{module}.sh"
        )
        content = (
            "#!/usr/bin/env bash\n"
            "set -u\n"
            f'readonly MODULE_NAME="{declaration}"\n'
            f'readonly MODULE_VERSION="{declared_version}"\n'
            f"{body}\n"
        )
        path.write_text(
            content,
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def write_success_observer(
        self,
        *,
        module: str = "observer-cpu",
        document: dict[str, object] | None = None,
        stderr_text: str = "",
    ) -> Path:
        report = (
            self.valid_report(module)
            if document is None
            else document
        )
        serialized = json.dumps(
            report,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        commands = []

        if stderr_text:
            commands.append(
                "printf '%s' "
                f"{shlex.quote(stderr_text)} >&2"
            )

        commands.append(
            "printf '%s\\n' "
            f"{shlex.quote(serialized)}"
        )

        return self.write_fake_observer(
            "\n".join(commands),
            module=module,
        )

    def run_capture(
        self,
        module: str = "observer-cpu",
        *,
        staging: Path | None = None,
        timeout: int = 10,
        extra_arguments: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        selected_staging = (
            self.staging
            if staging is None
            else staging
        )
        arguments = [
            str(self.sandbox_capturer),
            "--staging-dir",
            str(selected_staging),
        ]

        if extra_arguments:
            arguments.extend(extra_arguments)

        arguments.append(module)

        return subprocess.run(
            arguments,
            cwd=self.project_root,
            env={
                "PATH": (
                    "/usr/local/sbin:/usr/local/bin:"
                    "/usr/sbin:/usr/bin:/sbin:/bin"
                ),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def parse_result(
        self,
        result: subprocess.CompletedProcess[str],
    ) -> dict[str, object]:
        document = json.loads(result.stdout)
        errors = list(
            self.result_validator.iter_errors(document)
        )
        self.assertEqual(
            errors,
            [],
            msg="\n".join(
                error.message
                for error in errors
            ),
        )
        return document

    def assert_capture_result(
        self,
        result: subprocess.CompletedProcess[str],
        exit_code: int,
        code: str,
        *,
        module: str | None = "observer-cpu",
        outcome: str = "FAILED",
    ) -> dict[str, object]:
        self.assertEqual(
            result.returncode,
            exit_code,
            msg=result.stderr,
        )
        document = self.parse_result(result)
        self.assertEqual(document["capture_contract"], "1.0.0")
        self.assertEqual(document["module"], module)
        self.assertEqual(document["outcome"], outcome)
        self.assertEqual(document["code"], code)

        if outcome == "FAILED":
            self.assertIsNone(document["report"])
            self.assertNotEqual(result.stderr, "")
            self.assertNotIn("Traceback", result.stderr)

        return document

    def assert_no_report(
        self,
        module: str = "observer-cpu",
    ) -> None:
        self.assertFalse(
            self.report_path(module).exists()
        )

    def test_result_schema_is_valid(self) -> None:
        Draft202012Validator.check_schema(
            self.result_schema
        )

    def test_result_schema_identity(self) -> None:
        self.assertEqual(
            self.result_schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(
            self.result_schema["$id"],
            "urn:mppt24:schema:capture-result:1.0.0",
        )

    def test_legacy_capturer_is_unchanged(self) -> None:
        digest = hashlib.sha256(
            LEGACY_CAPTURER.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest,
            EXPECTED_LEGACY_SHA256,
        )

    def test_help(self) -> None:
        result = subprocess.run(
            [
                str(self.sandbox_capturer),
                "--help",
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assert_no_report()

    def test_repeated_option(self) -> None:
        result = self.run_capture(
            extra_arguments=[
                "--staging-dir",
                str(self.staging),
            ],
        )

        self.assert_capture_result(
            result,
            2,
            "USAGE_INVALID",
            module=None,
        )
        self.assert_no_report()

    def test_unknown_argument(self) -> None:
        result = self.run_capture(
            extra_arguments=["--unknown"],
        )

        self.assert_capture_result(
            result,
            2,
            "USAGE_INVALID",
            module=None,
        )
        self.assert_no_report()

    def test_unauthorized_module(self) -> None:
        result = self.run_capture(
            "observer-unregistered"
        )

        self.assert_capture_result(
            result,
            4,
            "MODULE_NOT_AUTHORIZED",
            module="observer-unregistered",
        )
        self.assert_no_report(
            "observer-unregistered"
        )

    def test_success(self) -> None:
        expected = self.valid_report()
        self.write_success_observer(
            document=expected
        )

        result = self.run_capture()
        document = self.assert_capture_result(
            result,
            0,
            "SUCCESS",
            outcome="SUCCESS",
        )

        report = self.report_path()
        report_status = os.lstat(report)

        self.assertEqual(result.stderr, "")
        self.assertEqual(
            document["observer_exit_code"],
            0,
        )
        self.assertEqual(
            document["report"],
            "observers/observer-cpu.json",
        )
        self.assertGreater(
            document["stdout_bytes"],
            0,
        )
        self.assertEqual(
            document["stderr_bytes"],
            0,
        )
        self.assertTrue(
            stat.S_ISREG(report_status.st_mode)
        )
        self.assertFalse(
            stat.S_ISLNK(report_status.st_mode)
        )
        self.assertEqual(
            stat.S_IMODE(report_status.st_mode),
            0o640,
        )
        self.assertEqual(
            report_status.st_nlink,
            1,
        )
        self.assertEqual(
            load_json(report),
            expected,
        )
        self.assertEqual(
            list(
                self.observers_staging.glob(
                    ".*.tmp.*"
                )
            ),
            [],
        )

    def test_success_records_stderr_size(self) -> None:
        self.write_success_observer(
            stderr_text="diagnóstico controlado"
        )

        result = self.run_capture()
        document = self.assert_capture_result(
            result,
            0,
            "SUCCESS",
            outcome="SUCCESS",
        )

        self.assertEqual(result.stderr, "")
        self.assertEqual(
            document["stderr_bytes"],
            len(
                "diagnóstico controlado".encode(
                    "utf-8"
                )
            ),
        )
        self.assertNotIn(
            "diagnóstico controlado",
            result.stdout,
        )

    def test_relative_staging_is_rejected(self) -> None:
        result = self.run_capture(
            staging=Path(".staging-relative")
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )
        self.assert_no_report()

    def test_invalid_staging_name(self) -> None:
        invalid = (
            self.state_root
            / "generation-without-prefix"
        )
        invalid.mkdir(
            parents=True,
        )
        (invalid / "observers").mkdir()

        result = self.run_capture(
            staging=invalid
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_missing_staging(self) -> None:
        missing = (
            self.state_root
            / ".staging-missing"
        )

        result = self.run_capture(
            staging=missing
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_missing_observers_directory(self) -> None:
        missing = (
            self.state_root
            / ".staging-without-observers"
        )
        missing.mkdir(
            parents=True,
        )

        result = self.run_capture(
            staging=missing
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_existing_destination_is_rejected(self) -> None:
        original = b"existing-report\n"
        self.report_path().write_bytes(original)

        result = self.run_capture()

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )
        self.assertEqual(
            self.report_path().read_bytes(),
            original,
        )

    def test_staging_symbolic_link(self) -> None:
        real_staging = (
            self.state_root
            / ".staging-real"
        )
        (real_staging / "observers").mkdir(
            parents=True
        )

        linked_staging = (
            self.state_root
            / ".staging-linked"
        )
        linked_staging.symlink_to(
            real_staging,
            target_is_directory=True,
        )

        result = self.run_capture(
            staging=linked_staging
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_intermediate_staging_symlink(self) -> None:
        real_parent = self.temp_path / "real-state"
        linked_parent = self.temp_path / "linked-state"
        staging = (
            linked_parent
            / ".staging-intermediate-link"
        )

        (
            real_parent
            / ".staging-intermediate-link"
            / "observers"
        ).mkdir(parents=True)
        linked_parent.symlink_to(
            real_parent,
            target_is_directory=True,
        )

        result = self.run_capture(
            staging=staging
        )

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_observers_directory_symlink(self) -> None:
        shutil.rmtree(self.observers_staging)
        real_observers = self.temp_path / "real-observers"
        real_observers.mkdir()
        self.observers_staging.symlink_to(
            real_observers,
            target_is_directory=True,
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )

    def test_destination_symbolic_link(self) -> None:
        external = self.temp_path / "external-report"
        external.write_bytes(b"preserve\n")
        self.report_path().symlink_to(external)

        result = self.run_capture()

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )
        self.assertEqual(
            external.read_bytes(),
            b"preserve\n",
        )

    def test_executable_missing(self) -> None:
        (
            self.project_root
            / "observer"
            / "observer-cpu.sh"
        ).unlink()

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_MISSING",
        )
        self.assert_no_report()

    def test_executable_is_directory(self) -> None:
        executable = (
            self.project_root
            / "observer"
            / "observer-cpu.sh"
        )
        executable.unlink()
        executable.mkdir()

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_INVALID",
        )
        self.assert_no_report()

    def test_executable_symbolic_link(self) -> None:
        executable = (
            self.project_root
            / "observer"
            / "observer-cpu.sh"
        )
        external = self.temp_path / "external-observer.sh"
        external.write_text(
            "#!/usr/bin/env bash\nexit 99\n",
            encoding="utf-8",
        )
        external.chmod(0o755)
        executable.unlink()
        executable.symlink_to(external)

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_INVALID",
        )
        self.assert_no_report()

    def test_executable_without_permission(self) -> None:
        executable = self.write_success_observer()
        executable.chmod(0o644)

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_INVALID",
        )
        self.assert_no_report()

    def test_declared_module_mismatch(self) -> None:
        self.write_fake_observer(
            "exit 0",
            declared_module="observer-memory",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_INVALID",
        )
        self.assert_no_report()

    def test_declared_version_mismatch(self) -> None:
        self.write_fake_observer(
            "exit 0",
            declared_version="9.9.9",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            4,
            "EXECUTABLE_INVALID",
        )
        self.assert_no_report()

    def test_execution_failure(self) -> None:
        self.write_fake_observer(
            "printf '%s' 'ignored' >&2\n"
            "exit 23"
        )

        result = self.run_capture()
        document = self.assert_capture_result(
            result,
            6,
            "EXECUTION_FAILED",
        )

        self.assertEqual(
            document["observer_exit_code"],
            23,
        )
        self.assertEqual(
            document["stderr_bytes"],
            len(b"ignored"),
        )
        self.assert_no_report()

    def test_empty_report(self) -> None:
        self.write_fake_observer("exit 0")

        result = self.run_capture()
        document = self.assert_capture_result(
            result,
            6,
            "EMPTY_REPORT",
        )

        self.assertEqual(
            document["observer_exit_code"],
            0,
        )
        self.assertEqual(
            document["stdout_bytes"],
            0,
        )
        self.assert_no_report()

    def test_invalid_utf8_report(self) -> None:
        self.write_fake_observer(
            "printf '\\377'"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "INVALID_JSON",
        )
        self.assert_no_report()

    def test_invalid_json_report(self) -> None:
        self.write_fake_observer(
            "printf '%s' '{'"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "INVALID_JSON",
        )
        self.assert_no_report()

    def test_additional_json_document(self) -> None:
        self.write_fake_observer(
            "printf '%s' '{} {}'"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "INVALID_JSON",
        )
        self.assert_no_report()

    def test_duplicate_json_key(self) -> None:
        self.write_fake_observer(
            "printf '%s' "
            "'{\"module\":\"observer-cpu\","
            "\"module\":\"observer-memory\"}'"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "INVALID_JSON",
        )
        self.assert_no_report()

    def test_non_finite_numbers(self) -> None:
        for value in (
            "NaN",
            "Infinity",
            "-Infinity",
        ):
            with self.subTest(value=value):
                if self.report_path().exists():
                    self.report_path().unlink()

                self.write_fake_observer(
                    "printf '%s' "
                    f"'{{\"value\":{value}}}'"
                )

                result = self.run_capture()

                self.assert_capture_result(
                    result,
                    7,
                    "INVALID_JSON",
                )
                self.assert_no_report()

    def test_contract_violation(self) -> None:
        document = self.valid_report()
        document.pop("facts")
        self.write_success_observer(
            document=document
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "CONTRACT_VIOLATION",
        )
        self.assert_no_report()

    def test_semantically_invalid_timestamp(self) -> None:
        document = self.valid_report()
        document["timestamp"] = (
            "2026-02-30T12:00:00+0000"
        )
        self.write_success_observer(
            document=document
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "CONTRACT_VIOLATION",
        )
        self.assert_no_report()

    def test_report_module_mismatch(self) -> None:
        document = self.valid_report(
            module="observer-memory"
        )
        self.write_success_observer(
            document=document
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "MODULE_MISMATCH",
        )
        self.assert_no_report()

    def test_report_version_mismatch(self) -> None:
        document = self.valid_report(
            version="1.1.0"
        )
        self.write_success_observer(
            document=document
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "CONTRACT_VIOLATION",
        )
        self.assert_no_report()

    def test_report_depth_limit(self) -> None:
        document = self.valid_report()
        document["facts"] = {
            "nested": {
                "level": {
                    "value": True
                }
            }
        }
        self.write_success_observer(
            document=document
        )

        registry_path = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        registry = load_json(registry_path)
        registry["limits"]["json_max_depth"] = 2
        registry_path.write_text(
            json.dumps(registry) + "\n",
            encoding="utf-8",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_report_bytes_are_preserved(self) -> None:
        document = self.valid_report()
        serialized = (
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        self.write_fake_observer(
            "printf '%s' "
            f"{shlex.quote(serialized.decode('utf-8'))}"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            0,
            "SUCCESS",
            outcome="SUCCESS",
        )
        self.assertEqual(
            self.report_path().read_bytes(),
            serialized,
        )

    def execution_limits(
        self,
        *,
        timeout: float = 2,
        stdout: int = 4096,
        stderr: int = 4096,
    ) -> dict[str, int | float]:
        return {
            "observer_timeout_seconds": timeout,
            "stdout_max_bytes": stdout,
            "stderr_max_bytes": stderr,
            "report_max_bytes": stdout,
            "json_max_depth": 32,
            "max_observers": 32,
        }

    def test_stdout_limit_during_execution(self) -> None:
        executable = self.write_fake_observer(
            "printf '%0100d' 0"
        )

        execution = capturer_module.execute_observer(
            executable,
            self.execution_limits(stdout=32),
            "observer-cpu",
        )

        self.assertEqual(
            execution.failure_code,
            "OUTPUT_LIMIT_EXCEEDED",
        )
        self.assertGreater(
            execution.stdout_bytes,
            32,
        )
        self.assertEqual(
            execution.exit_code,
            0,
        )
        self.assert_no_report()

    def test_stderr_limit_during_execution(self) -> None:
        executable = self.write_fake_observer(
            "printf '%0100d' 0 >&2"
        )

        execution = capturer_module.execute_observer(
            executable,
            self.execution_limits(stderr=32),
            "observer-cpu",
        )

        self.assertEqual(
            execution.failure_code,
            "STDERR_LIMIT_EXCEEDED",
        )
        self.assertGreater(
            execution.stderr_bytes,
            32,
        )
        self.assertEqual(
            execution.exit_code,
            0,
        )
        self.assert_no_report()

    def test_simultaneous_pipe_output(self) -> None:
        executable = self.write_fake_observer(
            "index=0\n"
            "while [ \"$index\" -lt 100 ]; do\n"
            "    printf '%08d' \"$index\"\n"
            "    printf '%08d' \"$index\" >&2\n"
            "    index=$((index + 1))\n"
            "done"
        )

        execution = capturer_module.execute_observer(
            executable,
            self.execution_limits(
                stdout=128,
                stderr=128,
            ),
            "observer-cpu",
        )

        self.assertIn(
            execution.failure_code,
            {
                "OUTPUT_LIMIT_EXCEEDED",
                "STDERR_LIMIT_EXCEEDED",
            },
        )
        self.assertTrue(
            execution.stdout_bytes > 128
            or execution.stderr_bytes > 128
        )
        self.assert_no_report()

    def test_execution_timeout(self) -> None:
        executable = self.write_fake_observer(
            "/usr/bin/sleep 10"
        )

        started = time.monotonic()

        with mock.patch.object(
            capturer_module,
            "TERMINATION_GRACE_SECONDS",
            0.1,
        ):
            execution = capturer_module.execute_observer(
                executable,
                self.execution_limits(timeout=0.2),
                "observer-cpu",
            )

        elapsed = time.monotonic() - started

        self.assertEqual(
            execution.failure_code,
            "EXECUTION_TIMEOUT",
        )
        self.assertLess(elapsed, 2)
        self.assertIn(
            execution.exit_code,
            {
                -signal.SIGTERM,
                -signal.SIGKILL,
            },
        )
        self.assert_no_report()

    def test_timeout_terminates_descendant(self) -> None:
        child_file = self.temp_path / "descendant.pid"
        body = (
            "(\n"
            "    trap '' TERM\n"
            "    /usr/bin/sleep 30\n"
            ") &\n"
            "child=$!\n"
            "printf '%s' \"$child\" > "
            f"{shlex.quote(str(child_file))}\n"
            "/usr/bin/sleep 30"
        )
        executable = self.write_fake_observer(body)

        with mock.patch.object(
            capturer_module,
            "TERMINATION_GRACE_SECONDS",
            0.1,
        ):
            execution = capturer_module.execute_observer(
                executable,
                self.execution_limits(timeout=0.3),
                "observer-cpu",
            )

        self.assertEqual(
            execution.failure_code,
            "EXECUTION_TIMEOUT",
        )
        child_pid = int(
            child_file.read_text(encoding="ascii")
        )

        deadline = time.monotonic() + 2

        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            self.fail(
                "processo descendente permaneceu ativo"
            )

        self.assert_no_report()

    def test_registry_missing(self) -> None:
        (
            self.project_root
            / "config"
            / "observer-registry.json"
        ).unlink()

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_registry_symbolic_link(self) -> None:
        registry_path = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        external = self.temp_path / "registry.json"
        external.write_bytes(
            registry_path.read_bytes()
        )
        registry_path.unlink()
        registry_path.symlink_to(external)

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_registry_duplicate_key(self) -> None:
        registry_path = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        registry_path.write_text(
            (
                '{"registry_version":"1.0.0",'
                '"registry_version":"9.9.9"}'
            ),
            encoding="utf-8",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_registry_schema_external_reference(
        self,
    ) -> None:
        schema_path = (
            self.project_root
            / "schemas"
            / "observer-registry"
            / "1.0.0"
            / "observer-registry.schema.json"
        )
        schema = load_json(schema_path)
        schema["$defs"]["external"] = {
            "$ref": "https://example.invalid/schema.json"
        }
        schema_path.write_text(
            json.dumps(schema) + "\n",
            encoding="utf-8",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_registry_schema_identity_mismatch(
        self,
    ) -> None:
        schema_path = (
            self.project_root
            / "schemas"
            / "observer-registry"
            / "1.0.0"
            / "observer-registry.schema.json"
        )
        schema = load_json(schema_path)
        schema["$id"] = (
            "urn:mppt24:schema:"
            "observer-registry:9.9.9"
        )
        schema_path.write_text(
            json.dumps(schema) + "\n",
            encoding="utf-8",
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def staging_context(self):
        return capturer_module.validate_staging(
            str(self.staging),
            "observer-cpu",
        )

    def assert_no_capture_temporaries(self) -> None:
        self.assertEqual(
            list(
                self.observers_staging.glob(
                    ".observer-cpu.json.tmp.*"
                )
            ),
            [],
        )

    def test_publish_rejects_late_destination(
        self,
    ) -> None:
        context = self.staging_context()
        original = b"late-destination\n"
        self.report_path().write_bytes(original)

        with self.assertRaisesRegex(
            capturer_module.CaptureFailure,
            "destino passou a existir",
        ) as failure:
            capturer_module.publish_report(
                context,
                "observer-cpu",
                b"validated-report\n",
                capturer_module.load_rename_noreplace(),
            )

        self.assertEqual(
            failure.exception.code,
            "TEMPORARY_PERSISTENCE_FAILED",
        )
        self.assertEqual(
            self.report_path().read_bytes(),
            original,
        )
        self.assert_no_capture_temporaries()

    def test_temporary_creation_failure(self) -> None:
        context = self.staging_context()
        original_open = capturer_module.os.open

        def fail_temporary_open(
            path,
            flags,
            mode=0o777,
            *,
            dir_fd=None,
        ):
            if dir_fd is not None:
                raise PermissionError(
                    "temporary creation denied"
                )
            return original_open(path, flags, mode)

        with mock.patch.object(
            capturer_module.os,
            "open",
            side_effect=fail_temporary_open,
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                capturer_module.publish_report(
                    context,
                    "observer-cpu",
                    b"validated-report\n",
                    capturer_module.load_rename_noreplace(),
                )

        self.assertEqual(
            failure.exception.code,
            "TEMPORARY_PERSISTENCE_FAILED",
        )
        self.assert_no_report()
        self.assert_no_capture_temporaries()

    def test_temporary_write_failure(self) -> None:
        context = self.staging_context()

        with mock.patch.object(
            capturer_module.os,
            "write",
            return_value=0,
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                capturer_module.publish_report(
                    context,
                    "observer-cpu",
                    b"validated-report\n",
                    capturer_module.load_rename_noreplace(),
                )

        self.assertEqual(
            failure.exception.code,
            "TEMPORARY_PERSISTENCE_FAILED",
        )
        self.assert_no_report()
        self.assert_no_capture_temporaries()

    def test_temporary_fsync_failure(self) -> None:
        context = self.staging_context()

        with mock.patch.object(
            capturer_module.os,
            "fsync",
            side_effect=OSError("fsync failed"),
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                capturer_module.publish_report(
                    context,
                    "observer-cpu",
                    b"validated-report\n",
                    capturer_module.load_rename_noreplace(),
                )

        self.assertEqual(
            failure.exception.code,
            "TEMPORARY_PERSISTENCE_FAILED",
        )
        self.assert_no_report()
        self.assert_no_capture_temporaries()

    def test_atomic_publication_failure(self) -> None:
        context = self.staging_context()

        with mock.patch.object(
            capturer_module,
            "rename_noreplace",
            side_effect=OSError("rename failed"),
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                capturer_module.publish_report(
                    context,
                    "observer-cpu",
                    b"validated-report\n",
                    object(),
                )

        self.assertEqual(
            failure.exception.code,
            "TEMPORARY_PERSISTENCE_FAILED",
        )
        self.assert_no_report()
        self.assert_no_capture_temporaries()

    def test_registry_size_limit(self) -> None:
        registry_path = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        registry_path.write_bytes(
            b" " * (
                capturer_module.REGISTRY_MAX_BYTES
                + 1
            )
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            3,
            "REGISTRY_INVALID",
        )
        self.assert_no_report()

    def test_jsonschema_dependency_unavailable(
        self,
    ) -> None:
        original_import = __import__

        def controlled_import(
            name,
            globals=None,
            locals=None,
            fromlist=(),
            level=0,
        ):
            if name == "jsonschema":
                raise ImportError("unavailable")
            return original_import(
                name,
                globals,
                locals,
                fromlist,
                level,
            )

        with mock.patch(
            "builtins.__import__",
            side_effect=controlled_import,
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                (
                    capturer_module
                    .load_jsonschema_dependency()
                )

        self.assertEqual(
            failure.exception.code,
            "DEPENDENCY_UNAVAILABLE",
        )
        self.assertEqual(
            failure.exception.exit_code,
            3,
        )

    def test_renameat2_dependency_unavailable(
        self,
    ) -> None:
        library = object()

        with mock.patch.object(
            capturer_module.ctypes,
            "CDLL",
            return_value=library,
        ):
            with self.assertRaises(
                capturer_module.CaptureFailure
            ) as failure:
                capturer_module.load_rename_noreplace()

        self.assertEqual(
            failure.exception.code,
            "DEPENDENCY_UNAVAILABLE",
        )
        self.assertEqual(
            failure.exception.exit_code,
            3,
        )

    def test_controlled_environment(self) -> None:
        executable = self.write_fake_observer(
            "printf '%s\\n' "
            "\"$PATH|$LANG|$LC_ALL|$TZ|${HOME-unset}\""
        )

        execution = capturer_module.execute_observer(
            executable,
            self.execution_limits(),
            "observer-cpu",
        )

        self.assertEqual(
            execution.failure_code,
            None,
        )
        self.assertEqual(
            execution.exit_code,
            0,
        )
        self.assertEqual(
            execution.stdout.decode("utf-8").strip(),
            (
                "/usr/local/sbin:/usr/local/bin:"
                "/usr/sbin:/usr/bin:/sbin:/bin"
                "|C.UTF-8|C.UTF-8|UTC|unset"
            ),
        )

    def test_standard_input_is_disabled(self) -> None:
        report = json.dumps(
            self.valid_report(),
            separators=(",", ":"),
        )
        executable = self.write_fake_observer(
            "if read -r value; then\n"
            "    exit 44\n"
            "fi\n"
            "printf '%s\\n' "
            f"{shlex.quote(report)}"
        )

        execution = capturer_module.execute_observer(
            executable,
            self.execution_limits(),
            "observer-cpu",
        )

        self.assertEqual(execution.exit_code, 0)
        self.assertEqual(
            execution.failure_code,
            None,
        )

    def test_diagnostic_sanitization(self) -> None:
        sanitized = (
            capturer_module.sanitize_diagnostic(
                "line1\tline2\nline3\r\x00"
            )
        )

        self.assertNotIn("\t", sanitized)
        self.assertNotIn("\n", sanitized)
        self.assertNotIn("\r", sanitized)
        self.assertNotIn("\x00", sanitized)
        self.assertLessEqual(
            len(sanitized),
            (
                capturer_module
                .DIAGNOSTIC_MESSAGE_LIMIT
            ),
        )

    def test_result_schema_rejects_incoherence(
        self,
    ) -> None:
        success = capturer_module.make_result(
            module="observer-cpu",
            outcome="SUCCESS",
            code="SUCCESS",
            observer_exit_code=0,
            report="observers/observer-cpu.json",
            stdout_bytes=100,
            stderr_bytes=0,
            duration_ms=10,
        )
        failure = dict(success)
        failure["outcome"] = "FAILED"
        failure["report"] = None

        self.assertEqual(
            list(
                self.result_validator.iter_errors(
                    success
                )
            ),
            [],
        )
        self.assertNotEqual(
            list(
                self.result_validator.iter_errors(
                    failure
                )
            ),
            [],
        )

    def test_import_has_no_side_effect(self) -> None:
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-c",
                (
                    "import runpy,sys;"
                    "runpy.run_path(sys.argv[1],"
                    "run_name='capture_import_test')"
                ),
                str(CAPTURER),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_official_observers_through_capturer(
        self,
    ) -> None:
        self.copy_project_file(
            "core/common.sh",
        )
        self.copy_project_file(
            "core/report.sh",
        )
        self.copy_project_file(
            "config/core.conf",
        )

        for entry in self.registry["observers"]:
            module = entry["module"]

            with self.subTest(module=module):
                result = self.run_capture(
                    module,
                    timeout=35,
                )
                document = self.assert_capture_result(
                    result,
                    0,
                    "SUCCESS",
                    module=module,
                    outcome="SUCCESS",
                )
                report = self.report_path(module)

                self.assertEqual(result.stderr, "")
                self.assertEqual(
                    document["report"],
                    f"observers/{module}.json",
                )
                self.assertTrue(report.is_file())

                validation = subprocess.run(
                    [
                        str(
                            self.project_root
                            / "core"
                            / "validate-report.py"
                        ),
                        "--max-bytes",
                        "262144",
                        "--max-depth",
                        "32",
                        "--expected-module",
                        module,
                        str(report),
                    ],
                    cwd=self.project_root,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                self.assertEqual(
                    validation.returncode,
                    0,
                    msg=validation.stderr,
                )

    def test_no_operational_report_writes(self) -> None:
        before = {
            path: (
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in (
                ROOT
                / "data"
                / "observer"
            ).glob("*.json")
        }

        self.write_success_observer()
        result = self.run_capture()

        self.assert_capture_result(
            result,
            0,
            "SUCCESS",
            outcome="SUCCESS",
        )

        after = {
            path: (
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in (
                ROOT
                / "data"
                / "observer"
            ).glob("*.json")
        }

        self.assertEqual(after, before)



    def test_staging_is_regular_file(self) -> None:
        shutil.rmtree(self.staging)
        self.staging.write_bytes(b"not-a-directory\n")

        result = self.run_capture()

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )
        self.assert_no_report()

    def test_observers_is_regular_file(self) -> None:
        shutil.rmtree(self.observers_staging)
        self.observers_staging.write_bytes(
            b"not-a-directory\n"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            5,
            "STAGING_INVALID",
        )
        self.assert_no_report()

    def test_whitespace_only_json_document(self) -> None:
        self.write_fake_observer(
            "printf '%s' '   '"
        )

        result = self.run_capture()

        self.assert_capture_result(
            result,
            7,
            "INVALID_JSON",
        )
        self.assert_no_report()

    def test_report_validator_unavailable(self) -> None:
        self.write_success_observer()
        (
            self.project_root
            / "core"
            / "validate-report.py"
        ).unlink()

        result = self.run_capture()
        document = self.assert_capture_result(
            result,
            3,
            "DEPENDENCY_UNAVAILABLE",
        )

        self.assertGreater(
            document["stdout_bytes"],
            0,
        )
        self.assertEqual(
            document["observer_exit_code"],
            0,
        )
        self.assert_no_report()



    def test_output_limit_terminates_descendant(
        self,
    ) -> None:
        child_file = self.temp_path / "output-descendant.pid"
        body = (
            "(\n"
            "    trap '' TERM\n"
            "    /usr/bin/sleep 30\n"
            ") &\n"
            "child=$!\n"
            "printf '%s' \"$child\" > "
            f"{shlex.quote(str(child_file))}\n"
            "printf '%01000d' 0\n"
            "/usr/bin/sleep 30"
        )
        executable = self.write_fake_observer(body)

        with mock.patch.object(
            capturer_module,
            "TERMINATION_GRACE_SECONDS",
            0.1,
        ):
            execution = capturer_module.execute_observer(
                executable,
                self.execution_limits(
                    timeout=3,
                    stdout=32,
                ),
                "observer-cpu",
            )

        self.assertEqual(
            execution.failure_code,
            "OUTPUT_LIMIT_EXCEEDED",
        )
        child_pid = int(
            child_file.read_text(encoding="ascii")
        )

        deadline = time.monotonic() + 2

        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            self.fail(
                "descendente de excesso permaneceu ativo"
            )

        self.assert_no_report()

    def test_no_network_or_shell_execution(
        self,
    ) -> None:
        tree = ast.parse(
            CAPTURER.read_text(encoding="utf-8"),
            filename=str(CAPTURER),
        )
        forbidden_modules = {
            "aiohttp",
            "ftplib",
            "http",
            "requests",
            "socket",
            "urllib",
        }
        imported_roots = set()
        forbidden_calls = []
        shell_enabled = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0]
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(
                        node.module.split(".", 1)[0]
                    )
            elif isinstance(node, ast.Call):
                function = node.func

                if (
                    isinstance(function, ast.Attribute)
                    and isinstance(
                        function.value,
                        ast.Name,
                    )
                    and function.value.id == "os"
                    and function.attr in {
                        "system",
                        "popen",
                    }
                ):
                    forbidden_calls.append(
                        f"os.{function.attr}"
                    )

                if (
                    isinstance(function, ast.Attribute)
                    and isinstance(
                        function.value,
                        ast.Name,
                    )
                    and function.value.id == "subprocess"
                    and function.attr == "Popen"
                ):
                    for keyword in node.keywords:
                        if (
                            keyword.arg == "shell"
                            and not (
                                isinstance(
                                    keyword.value,
                                    ast.Constant,
                                )
                                and keyword.value.value
                                is False
                            )
                        ):
                            shell_enabled.append(
                                ast.unparse(keyword.value)
                            )

        self.assertEqual(
            imported_roots & forbidden_modules,
            set(),
        )
        self.assertEqual(forbidden_calls, [])
        self.assertEqual(shell_enabled, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
