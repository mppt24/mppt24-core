#!/usr/bin/python3 -I
"""Testes do contrato serializado de relatórios MPPT24 2.1.0."""

import ast
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "core" / "validate-report.py"
SCHEMA = ROOT / "schemas" / "report" / "2.1.0" / "report.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "report-2.1.0"

spec = importlib.util.spec_from_file_location(
    "mppt24_validate_report",
    VALIDATOR,
)
if spec is None or spec.loader is None:
    raise RuntimeError("não foi possível carregar o validador")

validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)


class SerializedReportContractTest(unittest.TestCase):
    """Validar a interface completa através de ficheiros temporários."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mppt24-report-contract-"
        )
        self.temp_path = Path(self.temporary.name)

        with (FIXTURES / "valid-minimal.json").open(
            encoding="utf-8"
        ) as handle:
            self.base_report = json.load(handle)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(
        self,
        document: object,
        name: str = "report.json",
    ) -> Path:
        path = self.temp_path / name
        path.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def write_bytes(
        self,
        content: bytes,
        name: str = "report.json",
    ) -> Path:
        path = self.temp_path / name
        path.write_bytes(content)
        return path

    def run_validator(
        self,
        report: Path,
        *,
        expected_module: str = "observer-example",
        max_bytes: int = 1048576,
        max_depth: int = 64,
        validator: Path = VALIDATOR,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(validator),
                "--max-bytes",
                str(max_bytes),
                "--max-depth",
                str(max_depth),
                "--expected-module",
                expected_module,
                str(report),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def assert_result(
        self,
        result: subprocess.CompletedProcess[str],
        exit_code: int,
        diagnostic_code: str | None = None,
    ) -> None:
        self.assertEqual(result.returncode, exit_code)
        self.assertEqual(result.stdout, "")

        if exit_code == 0:
            self.assertEqual(result.stderr, "")
            return

        lines = result.stderr.splitlines()
        self.assertGreaterEqual(len(lines), 1)

        for line in lines:
            fields = line.split("\t")
            self.assertEqual(len(fields), 4)
            self.assertEqual(fields[0], "ERROR")

        if diagnostic_code is not None:
            self.assertIn(
                diagnostic_code,
                [line.split("\t")[1] for line in lines],
            )

    def make_sandbox(self) -> tuple[Path, Path]:
        root = self.temp_path / "sandbox"
        validator = root / "core" / "validate-report.py"
        schema = (
            root
            / "schemas"
            / "report"
            / "2.1.0"
            / "report.schema.json"
        )

        validator.parent.mkdir(parents=True)
        schema.parent.mkdir(parents=True)
        shutil.copy2(VALIDATOR, validator)
        shutil.copy2(SCHEMA, schema)

        return validator, schema

    def test_schema_is_valid(self) -> None:
        validator_class, schema_error = (
            validator_module.load_jsonschema_dependency()
        )
        schema, validator = validator_module.load_schema(
            validator_class,
            schema_error,
        )

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIsNotNone(validator)

    def test_valid_minimal_fixture(self) -> None:
        result = self.run_validator(
            FIXTURES / "valid-minimal.json"
        )
        self.assert_result(result, 0)

    def test_valid_complete_fixture(self) -> None:
        result = self.run_validator(
            FIXTURES / "valid-complete.json",
            expected_module="decision-example",
        )
        self.assert_result(result, 0)

    def test_expected_module_match(self) -> None:
        report = self.write_json(self.base_report)
        result = self.run_validator(report)

        self.assert_result(result, 0)

    def test_expected_module_mismatch(self) -> None:
        report = self.write_json(self.base_report)
        result = self.run_validator(
            report,
            expected_module="observer-other",
        )

        self.assert_result(result, 7, "MODULE_MISMATCH")

    def test_invalid_usage(self) -> None:
        result = subprocess.run(
            [str(VALIDATOR)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assert_result(result, 2, "USAGE_INVALID")

    def test_invalid_expected_module_argument(self) -> None:
        report = self.write_json(self.base_report)
        result = self.run_validator(
            report,
            expected_module="Invalid Module",
        )

        self.assert_result(result, 2, "USAGE_INVALID")

    def test_dependency_unavailable(self) -> None:
        report = self.write_json(self.base_report)
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-S",
                str(VALIDATOR),
                "--max-bytes",
                "1048576",
                "--max-depth",
                "64",
                str(report),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assert_result(
            result,
            3,
            "DEPENDENCY_UNAVAILABLE",
        )

    def test_import_has_no_execution_side_effect(self) -> None:
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-c",
                (
                    "import runpy,sys;"
                    "runpy.run_path(sys.argv[1],"
                    "run_name='contract_import_test')"
                ),
                str(VALIDATOR),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_schema_missing(self) -> None:
        validator, schema = self.make_sandbox()
        schema.unlink()
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(result, 4, "SCHEMA_MISSING")

    def test_schema_not_regular(self) -> None:
        validator, schema = self.make_sandbox()
        schema.unlink()
        schema.mkdir()
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(
            result,
            4,
            "SCHEMA_NOT_REGULAR",
        )

    def test_schema_symlink(self) -> None:
        validator, schema = self.make_sandbox()
        schema.unlink()
        schema.symlink_to(SCHEMA)
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(result, 4, "SCHEMA_SYMLINK")

    def test_schema_too_large(self) -> None:
        validator, schema = self.make_sandbox()
        schema.write_bytes(
            b"{" + b" " * validator_module.SCHEMA_MAX_BYTES
        )
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(result, 4, "SCHEMA_TOO_LARGE")

    def test_schema_invalid(self) -> None:
        validator, schema = self.make_sandbox()
        schema.write_text("{", encoding="utf-8")
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(result, 4, "SCHEMA_INVALID")

    def test_schema_external_reference(self) -> None:
        validator, schema = self.make_sandbox()

        with schema.open(encoding="utf-8") as handle:
            document = json.load(handle)

        document["$defs"]["external"] = {
            "$ref": "https://example.invalid/schema.json"
        }
        schema.write_text(
            json.dumps(document) + "\n",
            encoding="utf-8",
        )
        report = self.write_json(self.base_report)

        result = self.run_validator(
            report,
            validator=validator,
        )

        self.assert_result(
            result,
            4,
            "SCHEMA_EXTERNAL_REFERENCE",
        )

    def test_input_missing(self) -> None:
        result = self.run_validator(
            self.temp_path / "missing.json"
        )
        self.assert_result(result, 5, "INPUT_MISSING")

    def test_input_not_regular(self) -> None:
        result = self.run_validator(self.temp_path)
        self.assert_result(
            result,
            5,
            "INPUT_NOT_REGULAR",
        )

    def test_input_symlink(self) -> None:
        target = self.write_json(self.base_report)
        link = self.temp_path / "report-link.json"
        link.symlink_to(target)

        result = self.run_validator(link)

        self.assert_result(result, 5, "INPUT_SYMLINK")

    def test_input_too_large(self) -> None:
        report = self.write_json(self.base_report)
        result = self.run_validator(
            report,
            max_bytes=report.stat().st_size - 1,
        )

        self.assert_result(result, 5, "INPUT_TOO_LARGE")

    def test_invalid_utf8(self) -> None:
        report = self.write_bytes(b"\xff\xfe")
        result = self.run_validator(report)

        self.assert_result(result, 5, "INVALID_UTF8")

    def test_invalid_json_documents(self) -> None:
        cases = {
            "empty": b"",
            "truncated": b'{"module":',
            "additional": b"{} {}",
        }

        for name, content in cases.items():
            with self.subTest(name=name):
                report = self.write_bytes(
                    content,
                    name=f"{name}.json",
                )
                result = self.run_validator(report)

                self.assert_result(
                    result,
                    5,
                    "INVALID_JSON",
                )

    def test_duplicate_key_fixture(self) -> None:
        result = self.run_validator(
            FIXTURES / "invalid-duplicate-key.json"
        )

        self.assert_result(result, 5, "DUPLICATE_KEY")

    def test_non_finite_numbers(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                content = json.dumps(self.base_report)
                content = content.replace(
                    '"confidence": 100',
                    f'"confidence": {constant}',
                )
                report = self.write_bytes(
                    content.encode("utf-8"),
                    name=f"{constant}.json",
                )
                result = self.run_validator(report)

                self.assert_result(
                    result,
                    5,
                    "NON_FINITE_NUMBER",
                )

    def test_depth_limit(self) -> None:
        report_document = copy.deepcopy(self.base_report)
        report_document["facts"] = {
            "level-one": {
                "level-two": {
                    "value": True
                }
            }
        }
        report = self.write_json(report_document)
        result = self.run_validator(
            report,
            max_depth=3,
        )

        self.assert_result(
            result,
            5,
            "DEPTH_LIMIT_EXCEEDED",
        )

    def test_required_field_missing(self) -> None:
        document = copy.deepcopy(self.base_report)
        document.pop("module")
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_unknown_top_level_property(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["unexpected"] = True
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_wrong_top_level_type(self) -> None:
        report = self.write_json([])
        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_module_name(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["module"] = "Invalid Module"
        report = self.write_json(document)

        result = self.run_validator(
            report,
            expected_module="observer-example",
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_semver(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["version"] = "1.0.0-01"
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_status(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["status"] = "INVALID"
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_confidence_values(self) -> None:
        for value in (-1, 101, 50.5, True):
            with self.subTest(value=value):
                document = copy.deepcopy(self.base_report)
                document["confidence"] = value
                report = self.write_json(
                    document,
                    name=f"confidence-{value}.json",
                )

                result = self.run_validator(report)

                self.assert_result(
                    result,
                    6,
                    "CONTRACT_VIOLATION",
                )

    def test_empty_fact_key(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["facts"] = {"": 1}
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_text_arrays(self) -> None:
        fields = (
            "analysis",
            "conclusions",
            "summary",
            "recommendations",
            "warnings",
            "errors",
        )

        for field in fields:
            for value in ([""], ["duplicate", "duplicate"]):
                with self.subTest(field=field, value=value):
                    document = copy.deepcopy(self.base_report)
                    document[field] = value
                    report = self.write_json(
                        document,
                        name=f"{field}-{len(value)}.json",
                    )

                    result = self.run_validator(report)

                    self.assert_result(
                        result,
                        6,
                        "CONTRACT_VIOLATION",
                    )

    def test_invalid_health_domain(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["health"] = {
            "Invalid Domain": {
                "status": "OK"
            }
        }
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_health_missing_status(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["health"] = {"system": {}}
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_health_invalid_status(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["health"] = {
            "system": {
                "status": "INVALID"
            }
        }
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_health_additional_properties(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["health"] = {
            "system": {
                "status": "OK",
                "confidence": 95,
                "details": {
                    "source": "observer-system"
                },
            }
        }
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(result, 0)

    def test_timestamp_wrong_format(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["timestamp"] = "2026-08-16T12:30:45+01:00"
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_timestamp_semantically_invalid(self) -> None:
        result = self.run_validator(
            FIXTURES / "invalid-impossible-timestamp.json"
        )

        self.assert_result(result, 7, "INVALID_TIMESTAMP")

    def test_diagnostic_order(self) -> None:
        document = copy.deepcopy(self.base_report)
        document["analysis"] = [1]
        document["facts"] = []
        document["warnings"] = [1]
        report = self.write_json(document)

        result = self.run_validator(report)

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

        locations = [
            line.split("\t")[2]
            for line in result.stderr.splitlines()
        ]
        self.assertEqual(
            locations,
            [
                "/analysis/0",
                "/facts",
                "/warnings/0",
            ],
        )

    def test_input_unreadable(self) -> None:
        report = self.write_json(self.base_report)

        with mock.patch.object(
            validator_module.os,
            "open",
            side_effect=PermissionError,
        ):
            with self.assertRaises(
                validator_module.ValidationFailure
            ) as context:
                validator_module.secure_read(
                    report,
                    1048576,
                    "report",
                )

        self.assertEqual(
            context.exception.code,
            "INPUT_UNREADABLE",
        )

    def test_input_changed_during_read(self) -> None:
        report = self.write_json(self.base_report)
        status_result = report.stat()

        opened = SimpleNamespace(
            st_mode=status_result.st_mode,
            st_dev=status_result.st_dev,
            st_ino=status_result.st_ino,
            st_size=status_result.st_size,
            st_mtime_ns=status_result.st_mtime_ns,
            st_ctime_ns=status_result.st_ctime_ns,
        )
        completed = SimpleNamespace(
            st_mode=status_result.st_mode,
            st_dev=status_result.st_dev,
            st_ino=status_result.st_ino,
            st_size=status_result.st_size,
            st_mtime_ns=status_result.st_mtime_ns + 1,
            st_ctime_ns=status_result.st_ctime_ns,
        )

        with mock.patch.object(
            validator_module.os,
            "fstat",
            side_effect=[opened, completed],
        ):
            with self.assertRaises(
                validator_module.ValidationFailure
            ) as context:
                validator_module.secure_read(
                    report,
                    1048576,
                    "report",
                )

        self.assertEqual(
            context.exception.code,
            "INPUT_CHANGED",
        )

    def test_validator_has_no_network_or_process_imports(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0]
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])

        forbidden = {
            "http",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        self.assertEqual(imported & forbidden, set())

    def test_official_producers(self) -> None:
        programs = [
            (
                path,
                path.stem,
            )
            for path in sorted(
                (ROOT / "observer").glob("observer-*.sh")
            )
        ]
        programs.append(
            (
                ROOT / "decision" / "decision-engine.sh",
                "decision-engine",
            )
        )

        for program, module in programs:
            with self.subTest(module=module):
                produced = subprocess.run(
                    ["/usr/bin/bash", str(program)],
                    check=False,
                    capture_output=True,
                    env=(
                        {
                            **os.environ,
                            "MPPT24_REPORT_DIR": str(self.temp_path),
                        }
                        if module == "decision-engine"
                        else None
                    ),
                    timeout=30,
                )
                self.assertEqual(
                    produced.returncode,
                    0,
                    produced.stderr.decode(
                        "utf-8",
                        errors="replace",
                    ),
                )

                report = self.write_bytes(
                    produced.stdout,
                    name=f"{module}.json",
                )
                result = self.run_validator(
                    report,
                    expected_module=module,
                )

                self.assert_result(result, 0)

    def test_network_observer_reports_collection_failure(self) -> None:
        ip = self.temp_path / "ip"
        ip.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        ip.chmod(0o755)

        result = subprocess.run(
            ["/usr/bin/bash", str(ROOT / "observer" / "observer-network.sh")],
            env={**os.environ, "PATH": f"{self.temp_path}:{os.environ['PATH']}"},
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["confidence"], 0)
        self.assertEqual(report["facts"], {})
        self.assertTrue(report["errors"])
        path = self.write_bytes(result.stdout.encode("utf-8"))
        self.assert_result(
            self.run_validator(path, expected_module="observer-network"),
            0,
        )

    def test_legacy_decision_reports_unknown_without_network_facts(self) -> None:
        self.write_json(
            {**self.base_report, "module": "observer-cpu"},
            name="observer-cpu.json",
        )
        result = subprocess.run(
            ["/usr/bin/bash", str(ROOT / "decision" / "decision-engine.sh")],
            env={**os.environ, "MPPT24_REPORT_DIR": str(self.temp_path)},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["health"]["connectivity"]["status"], "UNKNOWN")
        path = self.write_bytes(result.stdout.encode("utf-8"))
        self.assert_result(
            self.run_validator(path, expected_module="decision-engine"),
            0,
        )

    def test_schema_unreadable(self) -> None:
        _validator, schema = self.make_sandbox()

        with mock.patch.object(
            validator_module.os,
            "open",
            side_effect=PermissionError,
        ):
            with self.assertRaises(
                validator_module.ValidationFailure
            ) as context:
                validator_module.secure_read(
                    schema,
                    validator_module.SCHEMA_MAX_BYTES,
                    "schema",
                )

        self.assertEqual(
            context.exception.code,
            "SCHEMA_UNREADABLE",
        )


    def test_help(self) -> None:
        result = subprocess.run(
            [str(VALIDATOR), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_repeated_option(self) -> None:
        report = self.write_json(self.base_report)
        result = subprocess.run(
            [
                str(VALIDATOR),
                "--max-bytes",
                "1048576",
                "--max-bytes",
                "2048",
                "--max-depth",
                "64",
                str(report),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assert_result(result, 2, "USAGE_INVALID")

    def test_schema_identity_and_dialect(self) -> None:
        cases = {
            "identity": (
                "$id",
                "urn:mppt24:schema:report:9.9.9",
            ),
            "dialect": (
                "$schema",
                "http://json-schema.org/draft-07/schema#",
            ),
        }

        for name, (field, value) in cases.items():
            with self.subTest(name=name):
                validator, schema = self.make_sandbox()

                with schema.open(encoding="utf-8") as handle:
                    document = json.load(handle)

                document[field] = value
                schema.write_text(
                    json.dumps(document) + "\n",
                    encoding="utf-8",
                )
                report = self.write_json(
                    self.base_report,
                    name=f"{name}.json",
                )

                result = self.run_validator(
                    report,
                    validator=validator,
                )

                self.assert_result(
                    result,
                    4,
                    "SCHEMA_INVALID",
                )

                shutil.rmtree(validator.parent.parent)

    def test_exact_depth_limit_is_accepted(self) -> None:
        report = self.write_json(self.base_report)
        result = self.run_validator(
            report,
            max_depth=2,
        )

        self.assert_result(result, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
