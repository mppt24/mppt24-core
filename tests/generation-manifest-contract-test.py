#!/usr/bin/python3 -I
"""Testes do manifesto e das gerações MPPT24 1.0.0."""

import ast
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "core" / "validate-manifest.py"
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
MANIFEST_SCHEMA = (
    ROOT
    / "schemas"
    / "generation-manifest"
    / "1.0.0"
    / "generation-manifest.schema.json"
)
FIXTURE_ROOT = (
    ROOT
    / "tests"
    / "fixtures"
    / "generation-manifest-1.0.0"
)

EXPECTED_SCHEMA_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)
EXPECTED_SCHEMA_ID = (
    "urn:mppt24:schema:generation-manifest:1.0.0"
)


def load_json(path: Path) -> object:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_module(path: Path):
    specification = importlib.util.spec_from_file_location(
        "mppt24_validate_manifest_contract_test",
        path,
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise RuntimeError(
            "não foi possível carregar o validador"
        )

    module = importlib.util.module_from_spec(
        specification
    )
    specification.loader.exec_module(module)
    return module


validator_module = load_module(VALIDATOR)


class GenerationManifestContractTest(
    unittest.TestCase
):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mppt24-generation-manifest-"
        )
        self.temporary_path = Path(
            self.temporary.name
        )
        self.project_root = (
            self.temporary_path
            / "project"
        )
        self.state_root = (
            self.temporary_path
            / "state"
        )

        self.copy_project_contracts()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_project_contracts(self) -> None:
        paths = [
            VALIDATOR,
            REPORT_VALIDATOR,
            REGISTRY,
            REGISTRY_SCHEMA,
            REPORT_SCHEMA,
            MANIFEST_SCHEMA,
        ]

        for source in paths:
            relative = source.relative_to(ROOT)
            destination = (
                self.project_root
                / relative
            )
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copy2(
                source,
                destination,
            )

        (
            self.project_root
            / "core"
            / "validate-manifest.py"
        ).chmod(0o755)

    def fixture_source(
        self,
        fixture_name: str,
    ) -> Path:
        candidates = list(
            (
                FIXTURE_ROOT
                / fixture_name
            ).iterdir()
        )

        self.assertEqual(
            len(candidates),
            1,
        )
        self.assertTrue(
            candidates[0].is_dir()
        )
        return candidates[0]

    def materialize_fixture(
        self,
        fixture_name: str,
        *,
        staging: bool = False,
    ) -> tuple[Path, str]:
        source = self.fixture_source(
            fixture_name
        )
        generation_id = source.name
        generations = (
            self.state_root
            / "generations"
        )
        generations.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o750,
        )

        directory_name = (
            f".staging-{generation_id}"
            if staging
            else generation_id
        )
        generation = (
            generations
            / directory_name
        )

        shutil.copytree(
            source,
            generation,
        )

        (generation / "observers").mkdir(exist_ok=True, mode=0o750)

        file_mode = (
            0o640
            if staging
            else 0o440
        )
        directory_mode = (
            0o750
            if staging
            else 0o550
        )

        for path in generation.rglob("*"):
            if path.is_file():
                path.chmod(file_mode)
            elif path.is_dir():
                path.chmod(directory_mode)

        generation.chmod(directory_mode)

        return generation, generation_id

    def run_validator(
        self,
        generation: Path,
        generation_id: str,
        *additional_arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            str(
                self.project_root
                / "core"
                / "validate-manifest.py"
            ),
            "--expected-generation-id",
            generation_id,
            str(generation),
            *additional_arguments,
        ]

        return subprocess.run(
            command,
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
        )

    def assert_result(
        self,
        result: subprocess.CompletedProcess[str],
        expected_exit: int,
        expected_code: str,
    ) -> None:
        self.assertEqual(
            result.returncode,
            expected_exit,
            msg=result.stderr,
        )
        self.assertEqual(
            result.stdout,
            "",
        )

        if expected_exit == 0:
            self.assertEqual(
                result.stderr,
                "",
            )
            return

        fields = (
            result.stderr
            .splitlines()[0]
            .split("\t")
        )
        self.assertGreaterEqual(
            len(fields),
            4,
        )
        self.assertEqual(
            fields[0],
            "ERROR",
        )
        self.assertEqual(
            fields[1],
            expected_code,
        )

    def manifest_path(
        self,
        generation: Path,
    ) -> Path:
        return generation / "manifest.json"

    def observers_path(
        self,
        generation: Path,
    ) -> Path:
        return generation / "observers"

    def make_writable(
        self,
        path: Path,
    ) -> None:
        current_mode = stat.S_IMODE(
            os.lstat(path).st_mode
        )
        path.chmod(
            current_mode | stat.S_IWUSR
        )

    def write_manifest(
        self,
        generation: Path,
        document: object,
    ) -> None:
        manifest = self.manifest_path(
            generation
        )
        self.make_writable(manifest)
        manifest.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest.chmod(0o440)



    def test_schema_is_valid_draft_2020_12(
        self,
    ) -> None:
        schema = load_json(MANIFEST_SCHEMA)

        Draft202012Validator.check_schema(
            schema
        )

    def test_schema_identity(self) -> None:
        schema = load_json(MANIFEST_SCHEMA)

        self.assertEqual(
            schema["$schema"],
            EXPECTED_SCHEMA_DIALECT,
        )
        self.assertEqual(
            schema["$id"],
            EXPECTED_SCHEMA_ID,
        )

    def test_schema_has_no_external_references(
        self,
    ) -> None:
        schema = load_json(MANIFEST_SCHEMA)
        references = []
        stack = [schema]

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
                            references.append(child)
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)

        self.assertEqual(
            references,
            [],
        )

    def test_valid_complete_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-complete"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            0,
            "SUCCESS",
        )

    def test_valid_partial_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            0,
            "SUCCESS",
        )

    def test_valid_failed_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            0,
            "SUCCESS",
        )

    def test_valid_staging_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial",
                staging=True,
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            0,
            "SUCCESS",
        )

    def test_duplicate_key_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "invalid-duplicate-key"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "DUPLICATE_KEY",
        )

    def test_impossible_timestamp_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "invalid-impossible-timestamp"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_tampered_report_fixture(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "invalid-tampered-report"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_help(self) -> None:
        result = subprocess.run(
            [
                str(
                    self.project_root
                    / "core"
                    / "validate-manifest.py"
                ),
                "--help",
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(
            result.returncode,
            0,
        )
        self.assertIn(
            "--expected-generation-id",
            result.stdout,
        )
        self.assertEqual(
            result.stderr,
            "",
        )

    def test_unknown_argument(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )

        result = self.run_validator(
            generation,
            generation_id,
            "--unknown",
        )

        self.assert_result(
            result,
            2,
            "USAGE_INVALID",
        )

    def test_repeated_option(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        validator = (
            self.project_root
            / "core"
            / "validate-manifest.py"
        )

        result = subprocess.run(
            [
                str(validator),
                "--expected-generation-id",
                generation_id,
                "--expected-generation-id",
                generation_id,
                str(generation),
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assert_result(
            result,
            2,
            "USAGE_INVALID",
        )

    def test_import_has_no_execution_side_effect(
        self,
    ) -> None:
        validator = (
            self.project_root
            / "core"
            / "validate-manifest.py"
        )
        script = (
            "import importlib.util,sys;"
            "sys.dont_write_bytecode=True;"
            "p=sys.argv[1];"
            "s=importlib.util.spec_from_file_location("
            "'manifest_import_test',p);"
            "m=importlib.util.module_from_spec(s);"
            "s.loader.exec_module(m)"
        )

        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-c",
                script,
                str(validator),
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )
        self.assertEqual(
            result.stdout,
            "",
        )
        self.assertEqual(
            result.stderr,
            "",
        )



    def make_directory_writable(
        self,
        directory: Path,
    ) -> None:
        current_mode = stat.S_IMODE(
            os.lstat(directory).st_mode
        )
        directory.chmod(
            current_mode
            | stat.S_IWUSR
            | stat.S_IXUSR
        )

    def write_manifest_bytes(
        self,
        generation: Path,
        content: bytes,
    ) -> None:
        manifest = self.manifest_path(
            generation
        )
        self.make_writable(manifest)
        manifest.write_bytes(content)
        manifest.chmod(0o440)

    def test_manifest_missing(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.make_directory_writable(
            generation
        )
        self.manifest_path(
            generation
        ).unlink()
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_MISSING",
        )

    def test_manifest_is_directory(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        manifest = self.manifest_path(
            generation
        )
        self.make_directory_writable(
            generation
        )
        manifest.unlink()
        manifest.mkdir(mode=0o550)
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_UNREADABLE",
        )

    def test_manifest_symbolic_link(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        manifest = self.manifest_path(
            generation
        )
        external = (
            self.temporary_path
            / "external-manifest.json"
        )
        external.write_bytes(
            manifest.read_bytes()
        )
        self.make_directory_writable(
            generation
        )
        manifest.unlink()
        manifest.symlink_to(external)
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_UNREADABLE",
        )

    def test_manifest_size_limit(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.write_manifest_bytes(
            generation,
            b" " * (
                validator_module.MANIFEST_MAX_BYTES
                + 1
            ),
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_TOO_LARGE",
        )

    def test_manifest_invalid_utf8(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.write_manifest_bytes(
            generation,
            b"\xff",
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "INVALID_UTF8",
        )

    def test_manifest_empty_json(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.write_manifest_bytes(
            generation,
            b"",
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "INVALID_JSON",
        )

    def test_manifest_whitespace_only(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.write_manifest_bytes(
            generation,
            b"   \n",
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "INVALID_JSON",
        )

    def test_manifest_additional_json_document(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        content = (
            self.manifest_path(
                generation
            ).read_bytes()
            + b"\n{}\n"
        )
        self.write_manifest_bytes(
            generation,
            content,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "INVALID_JSON",
        )

    def test_manifest_non_finite_number(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        content = (
            self.manifest_path(
                generation
            ).read_bytes()
        )
        content = content.replace(
            b'"duration_ms": 10',
            b'"duration_ms": NaN',
            1,
        )
        self.assertIn(
            b"NaN",
            content,
        )
        self.write_manifest_bytes(
            generation,
            content,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "NON_FINITE_NUMBER",
        )

    def test_manifest_depth_limit(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(
                generation
            )
        )
        nested = {}
        cursor = nested

        for _index in range(40):
            child = {}
            cursor["child"] = child
            cursor = child

        document["unexpected"] = nested
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "DEPTH_LIMIT_EXCEEDED",
        )

    def test_unknown_top_level_property(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(
                generation
            )
        )
        document["unexpected"] = True
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_registry_hash_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(
                generation
            )
        )
        document["registry"]["sha256"] = (
            "0" * 64
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_state_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-complete"
            )
        )
        document = load_json(
            self.manifest_path(
                generation
            )
        )
        document["state"] = "PARTIAL"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )



    def test_relative_generation_directory(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        relative = generation.relative_to(
            self.temporary_path
        )
        validator = (
            self.project_root
            / "core"
            / "validate-manifest.py"
        )

        result = subprocess.run(
            [
                str(validator),
                "--expected-generation-id",
                generation_id,
                str(relative),
            ],
            cwd=self.temporary_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_generation_symbolic_link(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        real_generation = (
            generation.parent
            / f"real-{generation_id}"
        )
        generation.rename(
            real_generation
        )
        generation.symlink_to(
            real_generation,
            target_is_directory=True,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_intermediate_symbolic_link(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        linked_parent = (
            self.temporary_path
            / "linked-generations"
        )
        linked_parent.symlink_to(
            generation.parent,
            target_is_directory=True,
        )
        linked_generation = (
            linked_parent
            / generation.name
        )

        result = self.run_validator(
            linked_generation,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_generation_name_mismatch(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        wrong_name = (
            generation.parent
            / (
                "20260816T233310123456Z-"
                "3123456789abcdef0123456789abcdef"
            )
        )
        generation.rename(wrong_name)

        result = self.run_validator(
            wrong_name,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_generation_is_regular_file(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        for path in generation.rglob("*"):
            if path.is_dir():
                path.chmod(0o750)
            elif path.is_file():
                path.chmod(0o640)

        generation.chmod(0o750)
        shutil.rmtree(generation)
        generation.write_bytes(
            b"not-a-directory\n"
        )
        generation.chmod(0o440)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_generation_permissions_exceed_limit(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        generation.chmod(0o750)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            4,
            "GENERATION_INVALID",
        )

    def test_observers_missing(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        observers = self.observers_path(
            generation
        )
        self.make_directory_writable(
            generation
        )
        observers.rmdir()
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_observers_is_regular_file(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        observers = self.observers_path(
            generation
        )
        self.make_directory_writable(
            generation
        )
        observers.rmdir()
        observers.write_bytes(
            b"not-a-directory\n"
        )
        observers.chmod(0o440)
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_observers_symbolic_link(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        observers = self.observers_path(
            generation
        )
        external = (
            self.temporary_path
            / "external-observers"
        )
        external.mkdir(mode=0o550)
        self.make_directory_writable(
            generation
        )
        observers.rmdir()
        observers.symlink_to(
            external,
            target_is_directory=True,
        )
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_unknown_object_in_generation_root(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.make_directory_writable(
            generation
        )
        unknown = generation / "unexpected"
        unknown.write_bytes(b"unexpected\n")
        unknown.chmod(0o440)
        generation.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_unknown_report(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        observers = self.observers_path(
            generation
        )
        self.make_directory_writable(
            observers
        )
        unknown = (
            observers
            / "observer-unregistered.json"
        )
        unknown.write_bytes(b"{}\n")
        unknown.chmod(0o440)
        observers.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_declared_report_missing(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        observers = report.parent
        self.make_directory_writable(
            observers
        )
        report.unlink()
        observers.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_report_symbolic_link(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        external = (
            self.temporary_path
            / "external-report.json"
        )
        external.write_bytes(
            report.read_bytes()
        )
        external.chmod(0o440)
        observers = report.parent
        self.make_directory_writable(
            observers
        )
        report.unlink()
        report.symlink_to(external)
        observers.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_report_hard_link(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        external = (
            self.temporary_path
            / "report-hard-link.json"
        )
        os.link(
            report,
            external,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )



    def test_manifest_permissions_exceed_limit(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.manifest_path(
            generation
        ).chmod(0o640)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_UNREADABLE",
        )

    def test_observers_permissions_exceed_limit(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        self.observers_path(
            generation
        ).chmod(0o750)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_report_permissions_exceed_limit(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        report.chmod(0o640)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_completed_before_started(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["completed_at"] = (
            "2026-08-16T23:33:08.123456Z"
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_manifest_generation_id_mismatch(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["generation_id"] = (
            "20260816T233310123456Z-"
            "3123456789abcdef0123456789abcdef"
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_summary_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["summary"][
            "failed"
        ] = 6
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_modules_reordered(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        modules = document["modules"]
        modules[0], modules[1] = (
            modules[1],
            modules[0],
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_required_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0][
            "required"
        ] = False
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_report_size_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"][
            "size_bytes"
        ] += 1
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_report_hash_mismatch(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"][
            "sha256"
        ] = "0" * 64
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_report_metadata_mismatch(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"][
            "timestamp"
        ] = "2026-08-16T23:31:10+0000"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_contractually_invalid_report(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        report_document = load_json(report)
        report_document["confidence"] = 101
        report.chmod(0o640)
        report.write_text(
            json.dumps(
                report_document,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        report.chmod(0o440)

        report_content = report.read_bytes()
        manifest_document = load_json(
            self.manifest_path(generation)
        )
        descriptor = (
            manifest_document["modules"][0][
                "report"
            ]
        )
        descriptor["size_bytes"] = len(
            report_content
        )
        descriptor["sha256"] = hashlib.sha256(
            report_content
        ).hexdigest()
        self.write_manifest(
            generation,
            manifest_document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )



    def test_current_generation_valid(
        self,
    ) -> None:
        generation_id = (
            "20260816T233109123456Z-"
            "0123456789abcdef0123456789abcdef"
        )

        actual = (
            validator_module
            .validate_current_generation_content(
                (
                    generation_id
                    + "\n"
                ).encode("utf-8")
            )
        )

        self.assertEqual(
            actual,
            generation_id,
        )

    def test_current_generation_missing_newline(
        self,
    ) -> None:
        generation_id = (
            "20260816T233109123456Z-"
            "0123456789abcdef0123456789abcdef"
        )

        with self.assertRaises(
            validator_module.ValidationFailure
        ) as raised:
            (
                validator_module
                .validate_current_generation_content(
                    generation_id.encode(
                        "utf-8"
                    )
                )
            )

        self.assertEqual(
            raised.exception.code,
            "GENERATION_INVALID",
        )

    def test_current_generation_additional_text(
        self,
    ) -> None:
        generation_id = (
            "20260816T233109123456Z-"
            "0123456789abcdef0123456789abcdef"
        )

        with self.assertRaises(
            validator_module.ValidationFailure
        ):
            (
                validator_module
                .validate_current_generation_content(
                    (
                        generation_id
                        + "\nextra\n"
                    ).encode("utf-8")
                )
            )

    def test_current_generation_impossible_date(
        self,
    ) -> None:
        generation_id = (
            "20260230T120000123456Z-"
            "0123456789abcdef0123456789abcdef"
        )

        with self.assertRaises(
            validator_module.ValidationFailure
        ):
            (
                validator_module
                .validate_current_generation_content(
                    (
                        generation_id
                        + "\n"
                    ).encode("utf-8")
                )
            )

    def test_manifest_hard_link(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        manifest = self.manifest_path(
            generation
        )
        external = (
            self.temporary_path
            / "manifest-hard-link.json"
        )
        os.link(
            manifest,
            external,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "MANIFEST_UNREADABLE",
        )

    def test_registry_missing(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        sandbox_registry = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        sandbox_registry.unlink()

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            3,
            "REGISTRY_INVALID",
        )

    def test_registry_symbolic_link(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        sandbox_registry = (
            self.project_root
            / "config"
            / "observer-registry.json"
        )
        external = (
            self.temporary_path
            / "external-registry.json"
        )
        external.write_bytes(
            sandbox_registry.read_bytes()
        )
        sandbox_registry.unlink()
        sandbox_registry.symlink_to(
            external
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            3,
            "REGISTRY_INVALID",
        )

    def test_manifest_schema_identity_mismatch(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        sandbox_schema = (
            self.project_root
            / MANIFEST_SCHEMA.relative_to(ROOT)
        )
        schema = load_json(
            sandbox_schema
        )
        schema["$id"] = (
            "urn:mppt24:schema:wrong:1.0.0"
        )
        sandbox_schema.write_text(
            json.dumps(schema) + "\n",
            encoding="utf-8",
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            3,
            "SCHEMA_INVALID",
        )

    def test_manifest_schema_external_reference(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        sandbox_schema = (
            self.project_root
            / MANIFEST_SCHEMA.relative_to(ROOT)
        )
        schema = load_json(
            sandbox_schema
        )
        schema["unexpected"] = {
            "$ref": "https://example.invalid/schema"
        }
        sandbox_schema.write_text(
            json.dumps(schema) + "\n",
            encoding="utf-8",
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            3,
            "SCHEMA_INVALID",
        )

    def test_report_validator_unavailable(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        sandbox_validator = (
            self.project_root
            / "core"
            / "validate-report.py"
        )
        sandbox_validator.unlink()

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            3,
            "DEPENDENCY_UNAVAILABLE",
        )

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
                validator_module.ValidationFailure
            ) as raised:
                (
                    validator_module
                    .load_jsonschema_dependency()
                )

        self.assertEqual(
            raised.exception.code,
            "DEPENDENCY_UNAVAILABLE",
        )
        self.assertEqual(
            raised.exception.exit_code,
            3,
        )

    def test_no_network_shell_or_component_execution(
        self,
    ) -> None:
        tree = ast.parse(
            VALIDATOR.read_text(
                encoding="utf-8"
            ),
            filename=str(VALIDATOR),
        )
        forbidden_imports = {
            "socket",
            "subprocess",
            "urllib",
            "requests",
            "http",
        }
        imported = set()
        forbidden_calls = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".", 1)[0]
                    for alias in node.names
                )
            elif isinstance(
                node,
                ast.ImportFrom,
            ):
                if node.module:
                    imported.add(
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
                ):
                    qualified = (
                        f"{function.value.id}."
                        f"{function.attr}"
                    )

                    if qualified in {
                        "os.system",
                        "os.popen",
                        "os.spawnl",
                        "os.spawnv",
                        "os.execv",
                        "os.execl",
                    }:
                        forbidden_calls.append(
                            qualified
                        )

        self.assertEqual(
            imported & forbidden_imports,
            set(),
        )
        self.assertEqual(
            forbidden_calls,
            [],
        )



    def test_manifest_truncated_json(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        content = (
            self.manifest_path(generation)
            .read_bytes()
        )
        self.write_manifest_bytes(
            generation,
            content[:-2],
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            5,
            "INVALID_JSON",
        )

    def test_missing_required_field(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        del document["runner"]
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_incorrect_field_type(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["summary"]["declared"] = "7"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_incompatible_runner_version(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["runner"]["version"] = "1.0.0"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_generation_identifier_time_mismatch(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["started_at"] = (
            "2026-08-16T23:33:08.123456Z"
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_zero_modules(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"] = []
        document["summary"] = {
            "declared": 0,
            "successful": 0,
            "failed": 0,
            "reports_written": 0,
        }
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_missing_module(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"].pop()
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_additional_module(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        additional = copy.deepcopy(
            document["modules"][-1]
        )
        additional["module"] = (
            "observer-additional"
        )
        document["modules"].append(
            additional
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_duplicate_module(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][1]["module"] = (
            document["modules"][0]["module"]
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            7,
            "SEMANTIC_VIOLATION",
        )

    def test_invalid_failure_code(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0][
            "error_code"
        ] = "UNKNOWN_FAILURE"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_success_without_report(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"] = None
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_failure_with_report(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        partial_source = self.fixture_source(
            "valid-partial"
        )
        partial_document = load_json(
            partial_source / "manifest.json"
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"] = (
            copy.deepcopy(
                partial_document["modules"][0][
                    "report"
                ]
            )
        )
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_incoherent_exit_code(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0][
            "exit_code"
        ] = 1
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_invalid_report_path(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"][
            "path"
        ] = "../observer-cpu.json"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_incompatible_report_version(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        document["modules"][0]["report"][
            "version"
        ] = "2.0.0"
        self.write_manifest(
            generation,
            document,
        )

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            6,
            "CONTRACT_VIOLATION",
        )

    def test_report_is_directory(self) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        observers = report.parent
        self.make_directory_writable(
            observers
        )
        report.unlink()
        report.mkdir(mode=0o550)
        observers.chmod(0o550)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )



    def test_report_above_registry_limit(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-partial"
            )
        )
        report = (
            self.observers_path(generation)
            / "observer-cpu.json"
        )
        report.chmod(0o640)
        report.write_bytes(
            b"x" * (
                validator_module.REGISTRY_MAX_BYTES
                * 4
                + 1
            )
        )
        report.chmod(0o440)

        result = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            result,
            8,
            "GENERATION_MISMATCH",
        )

    def test_change_during_secure_read(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "changing-manifest.json"
        )
        path.write_bytes(b'{"value":1}\n')
        path.chmod(0o440)

        original_read = (
            validator_module.os.read
        )
        changed = False

        def controlled_read(
            descriptor: int,
            count: int,
        ) -> bytes:
            nonlocal changed

            chunk = original_read(
                descriptor,
                count,
            )

            if not changed and chunk:
                changed = True
                path.chmod(0o640)
                with path.open("ab") as stream:
                    stream.write(b" ")
                path.chmod(0o440)

            return chunk

        with mock.patch.object(
            validator_module.os,
            "read",
            side_effect=controlled_read,
        ):
            with self.assertRaises(
                validator_module.ValidationFailure
            ) as raised:
                validator_module.secure_read_file(
                    path,
                    1024,
                    location="changing",
                    exit_code=5,
                    missing_code="MANIFEST_MISSING",
                    unreadable_code=(
                        "MANIFEST_UNREADABLE"
                    ),
                    too_large_code=(
                        "MANIFEST_TOO_LARGE"
                    ),
                    require_single_link=True,
                )

        self.assertTrue(changed)
        self.assertEqual(
            raised.exception.code,
            "MANIFEST_UNREADABLE",
        )
        self.assertIn(
            "mudou durante a leitura",
            raised.exception.message,
        )

    def test_schema_diagnostics_are_deterministic(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        document = load_json(
            self.manifest_path(generation)
        )
        del document["runner"]["module"]
        document["summary"]["declared"] = (
            "seven"
        )
        document["unexpected"] = True
        self.write_manifest(
            generation,
            document,
        )

        first = self.run_validator(
            generation,
            generation_id,
        )
        second = self.run_validator(
            generation,
            generation_id,
        )

        self.assert_result(
            first,
            6,
            "CONTRACT_VIOLATION",
        )
        self.assert_result(
            second,
            6,
            "CONTRACT_VIOLATION",
        )
        self.assertEqual(
            first.stderr,
            second.stderr,
        )

        lines = first.stderr.splitlines()
        self.assertGreaterEqual(
            len(lines),
            3,
        )
        locations = [
            line.split("\t")[2]
            for line in lines
        ]
        self.assertEqual(
            locations,
            sorted(locations),
        )

    def test_recorded_component_hashes_match(
        self,
    ) -> None:
        expected = {
            "runner/observer-runner.sh": (
                "363fee5967b6bdbfdce0b752fb834d99b"
                "6f33e117fa4bc45c04df0416fad478c"
            ),
            "historian/historian.sh": (
                "cc05b4c8dd86fb59d86f85fc99c381d5"
                "e43f9cc54755ddc1efb2a9a509ecef3a"
            ),
            "MANIFESTO.md": (
                "49df9ddaeafae774bc79cc82f90a1c63"
                "116ecfb4c2b9c1d766effd8455563b3e"
            ),
            "decision/decision-engine.sh": (
                "f1ac43b947c40b7c28f2a6c15b3aad32"
                "a458e8eb811e5ccc3963e9d5c150b98e"
            ),
            "observer/observer-cpu.sh": (
                "f397a9b18005cc4d0542cd231a2a2b2b"
                "ca745109aadaeb4155bad1cde3e7fe6d"
            ),
            "observer/observer-memory.sh": (
                "b496786d8490b61f5ff538ffac4c2c26"
                "2b0ff87ea35f17a52b4d9c0ad73d1072"
            ),
            "observer/observer-network.sh": (
                "37b910c0321cd41ddef49310d45a2eff6"
                "c327de19642c40745db7c879c3d59bd"
            ),
            "observer/observer-services.sh": (
                "99b0c584e19dac48bb49a68b018bf760"
                "eaf6cf7f503d797a2007e91296a576f7"
            ),
            "observer/observer-ssh.sh": (
                "be00f870a85cbf50cfa715b9e5586c44"
                "b11faa2cada7e58796e4c3a52d8e2a72"
            ),
            "observer/observer-storage.sh": (
                "c2600a0a0006ffb4e9d583336da90a79"
                "51389ba94c6c3d0562d445f44bc53cc0"
            ),
            "observer/observer-system.sh": (
                "1b39bf0e44f8aad483f3649064c089ad2"
                "ff8422844fd06d57af4b5e7ee5f12f3"
            ),
        }

        actual = {
            relative: hashlib.sha256(
                (ROOT / relative).read_bytes()
            ).hexdigest()
            for relative in expected
        }

        self.assertEqual(
            actual,
            expected,
        )


    def test_help_advertises_snapshot_interface(
        self,
    ) -> None:
        validator = (
            self.project_root
            / "core"
            / "validate-manifest.py"
        )

        result = subprocess.run(
            [
                str(validator),
                "--help",
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
        )

        self.assertEqual(
            result.returncode,
            0,
        )
        self.assertIn(
            "--emit-validated-snapshot",
            result.stdout,
        )
        self.assertEqual(
            result.stderr,
            "",
        )

    def test_emit_validated_snapshot_fixtures(
        self,
    ) -> None:
        snapshot_root = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
        )

        for fixture_name in (
            "valid-complete",
            "valid-partial",
            "valid-failed",
        ):
            with self.subTest(
                fixture_name=fixture_name
            ):
                generation, generation_id = (
                    self.materialize_fixture(
                        fixture_name
                    )
                )

                result = self.run_validator(
                    generation,
                    generation_id,
                    "--emit-validated-snapshot",
                )

                self.assertEqual(
                    result.returncode,
                    0,
                    msg=result.stderr,
                )
                self.assertEqual(
                    result.stderr,
                    "",
                )

                expected = (
                    snapshot_root
                    / fixture_name
                    / "snapshot.json"
                ).read_text(
                    encoding="utf-8"
                )

                self.assertEqual(
                    result.stdout,
                    expected,
                )

    def test_repeated_snapshot_option(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-failed"
            )
        )
        validator = (
            self.project_root
            / "core"
            / "validate-manifest.py"
        )

        result = subprocess.run(
            [
                str(validator),
                "--emit-validated-snapshot",
                "--emit-validated-snapshot",
                "--expected-generation-id",
                generation_id,
                str(generation),
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
        )

        self.assertEqual(
            result.returncode,
            2,
        )
        self.assertEqual(
            result.stdout,
            "",
        )

        fields = (
            result.stderr
            .splitlines()[0]
            .split("\t")
        )

        self.assertGreaterEqual(
            len(fields),
            4,
        )
        self.assertEqual(
            fields[0],
            "ERROR",
        )
        self.assertEqual(
            fields[1],
            "USAGE_INVALID",
        )
        self.assertEqual(
            fields[2],
            "--emit-validated-snapshot",
        )
        self.assertIn(
            "não pode ser repetida",
            fields[3],
        )

    def test_snapshot_mode_preserves_validation_failure(
        self,
    ) -> None:
        generation, generation_id = (
            self.materialize_fixture(
                "valid-complete"
            )
        )
        manifest = load_json(
            self.manifest_path(
                generation
            )
        )
        manifest["generation_id"] = (
            "20260816T233109123456Z-"
            "ffffffffffffffffffffffffffffffff"
        )
        self.write_manifest(
            generation,
            manifest,
        )

        normal_result = self.run_validator(
            generation,
            generation_id,
        )
        snapshot_result = self.run_validator(
            generation,
            generation_id,
            "--emit-validated-snapshot",
        )

        self.assertEqual(
            normal_result.returncode,
            7,
        )
        self.assertEqual(
            snapshot_result.returncode,
            normal_result.returncode,
        )

        self.assertEqual(
            normal_result.stdout,
            "",
        )
        self.assertEqual(
            snapshot_result.stdout,
            "",
        )
        self.assertEqual(
            snapshot_result.stderr,
            normal_result.stderr,
        )

        fields = (
            snapshot_result.stderr
            .splitlines()[0]
            .split("\t")
        )

        self.assertGreaterEqual(
            len(fields),
            4,
        )
        self.assertEqual(
            fields[0],
            "ERROR",
        )
        self.assertEqual(
            fields[1],
            "SEMANTIC_VIOLATION",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
