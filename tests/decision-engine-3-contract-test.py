#!/usr/bin/python3 -I
"""Testes contratuais do Decision Engine MPPT24 3.0.0."""

import ast
import sys
import unittest
import os
import signal
import time
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent

DECISION_2 = (
    ROOT
    / "decision"
    / "decision-engine.sh"
)

DECISION_3 = (
    ROOT
    / "decision"
    / "decision-engine.py"
)

INPUT_CONTRACT = (
    ROOT
    / "decision"
    / "decision-engine-input-contract-3.0.0.md"
)

VALIDATOR = (
    ROOT
    / "core"
    / "validate-manifest.py"
)

SNAPSHOT_SCHEMA = (
    ROOT
    / "schemas"
    / "validated-generation-snapshot"
    / "1.0.0"
    / "validated-generation-snapshot.schema.json"
)

MANIFEST_SCHEMA = (
    ROOT
    / "schemas"
    / "generation-manifest"
    / "1.0.0"
    / "generation-manifest.schema.json"
)

REPORT_SCHEMA = (
    ROOT
    / "schemas"
    / "report"
    / "2.1.0"
    / "report.schema.json"
)

FIXTURE_ROOT = (
    ROOT
    / "tests"
    / "fixtures"
    / "validated-generation-snapshot-1.0.0"
)

EXPECTED_DECISION_2_SHA256 = (
    "d008c561f2b32054aed42667e5bcb5c8b"
    "600ad38e9b61ac868ec203b26834707"
)

EXPECTED_INPUT_CONTRACT_SHA256 = (
    "46d86bab399e1d5328f23d1693535daf"
    "915142b99d549d7165a1ba0893e548aa"
)

EXPECTED_FIXTURES = (
    "valid-complete",
    "valid-partial",
    "valid-failed",
)


class DecisionEngine3ArchitectureContractTest(
    unittest.TestCase
):
    maxDiff = None

    def test_legacy_decision_engine_exists(
        self,
    ) -> None:
        self.assertTrue(
            DECISION_2.is_file()
        )

    def test_input_contract_exists(
        self,
    ) -> None:
        self.assertTrue(
            INPUT_CONTRACT.is_file()
        )

    def test_validator_exists(
        self,
    ) -> None:
        self.assertTrue(
            VALIDATOR.is_file()
        )

    def test_required_schemas_exist(
        self,
    ) -> None:
        for path in (
            SNAPSHOT_SCHEMA,
            MANIFEST_SCHEMA,
            REPORT_SCHEMA,
        ):
            with self.subTest(path=path):
                self.assertTrue(
                    path.is_file()
                )

    def test_snapshot_fixtures_exist(
        self,
    ) -> None:
        for name in EXPECTED_FIXTURES:
            path = (
                FIXTURE_ROOT
                / name
                / "snapshot.json"
            )
            with self.subTest(fixture=name):
                self.assertTrue(
                    path.is_file()
                )

    def test_candidate_path_is_distinct_from_legacy(
        self,
    ) -> None:
        self.assertNotEqual(
            DECISION_3,
            DECISION_2,
        )

    def test_candidate_uses_python_filename(
        self,
    ) -> None:
        self.assertEqual(
            DECISION_3.name,
            "decision-engine.py",
        )


class DecisionEngine3ImplementationContractTest(
    unittest.TestCase
):
    """Contrato executável da futura implementação 3.0.0."""

    def candidate_source(
        self,
    ) -> str:
        self.assertTrue(
            DECISION_3.is_file(),
            (
                "implementação candidata ainda ausente: "
                "decision/decision-engine.py"
            ),
        )
        return DECISION_3.read_text(
            encoding="utf-8"
        )

    def candidate_tree(
        self,
    ) -> ast.Module:
        return ast.parse(
            self.candidate_source(),
            filename=str(DECISION_3),
        )

    def test_candidate_exists(
        self,
    ) -> None:
        self.assertTrue(
            DECISION_3.is_file(),
            (
                "implementação candidata ainda ausente: "
                "decision/decision-engine.py"
            ),
        )

    def test_candidate_is_valid_python(
        self,
    ) -> None:
        tree = self.candidate_tree()
        self.assertIsInstance(
            tree,
            ast.Module,
        )

    def test_candidate_declares_module_identity(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            '"decision-engine"',
            source,
        )

    def test_candidate_declares_version_3_0_0(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            '"3.0.0"',
            source,
        )

    def test_candidate_mentions_state_root_option(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            "--state-root",
            source,
        )

    def test_candidate_mentions_snapshot_interface(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            "--emit-validated-snapshot",
            source,
        )

    def test_candidate_does_not_invoke_legacy_engine(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertNotIn(
            "decision-engine.sh",
            source,
        )

    def test_import_has_main_guard(
        self,
    ) -> None:
        tree = self.candidate_tree()

        guards = []

        for node in tree.body:
            if not isinstance(node, ast.If):
                continue

            test = node.test

            if not isinstance(
                test,
                ast.Compare,
            ):
                continue

            guards.append(
                ast.unparse(test)
            )

        self.assertIn(
            "__name__ == '__main__'",
            guards,
        )


class DecisionEngine3StateRootContractTest(
    unittest.TestCase
):
    """Contrato da resolução segura da geração promovida."""

    def candidate_source(
        self,
    ) -> str:
        self.assertTrue(
            DECISION_3.is_file(),
            (
                "implementação candidata ainda ausente: "
                "decision/decision-engine.py"
            ),
        )
        return DECISION_3.read_text(
            encoding="utf-8"
        )

    def candidate_tree(
        self,
    ) -> ast.Module:
        return ast.parse(
            self.candidate_source(),
            filename=str(DECISION_3),
        )

    def test_state_root_has_no_implicit_default(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            "--state-root",
            source,
        )

        self.assertNotIn(
            "MPPT24_STATE_ROOT",
            source,
        )

    def test_current_generation_is_named_explicitly(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            '"current-generation"',
            source,
        )

    def test_generations_directory_is_named_explicitly(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            '"generations"',
            source,
        )

    def test_candidate_contains_generation_id_validation(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            "generation_id",
            source,
        )

    def test_candidate_uses_lstat_for_secure_resolution(
        self,
    ) -> None:
        tree = self.candidate_tree()

        attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }

        self.assertIn(
            "lstat",
            attributes,
        )

    def test_candidate_uses_strict_utf8(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertIn(
            '"utf-8"',
            source,
        )
        self.assertIn(
            '"strict"',
            source,
        )

    def test_candidate_checks_regular_file_type(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertTrue(
            (
                "S_ISREG" in source
                or "is_file" in source
            ),
            (
                "resolução deve verificar que "
                "current-generation é ficheiro regular"
            ),
        )

    def test_candidate_checks_symbolic_links(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertTrue(
            (
                "S_ISLNK" in source
                or "is_symlink" in source
                or "O_NOFOLLOW" in source
            ),
            (
                "resolução deve possuir proteção "
                "explícita contra links simbólicos"
            ),
        )

    def test_candidate_has_current_generation_size_limit(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertTrue(
            (
                "CURRENT_GENERATION_MAX" in source
                or "CURRENT_GENERATION_MAX_BYTES" in source
                or "current_generation_max" in source
            ),
            (
                "limite de current-generation "
                "deve ser explícito"
            ),
        )

    def test_candidate_detects_object_change(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertTrue(
            (
                "CURRENT_GENERATION_CHANGED" in source
                and "st_ino" in source
                and "st_dev" in source
            ),
            (
                "mudança do objeto deve ser "
                "detetável deterministicamente"
            ),
        )

    def test_candidate_fixes_generation_before_validator(
        self,
    ) -> None:
        source = self.candidate_source()

        current_position = source.find(
            "current-generation"
        )
        expected_position = source.find(
            "--expected-generation-id"
        )

        self.assertGreaterEqual(
            current_position,
            0,
        )
        self.assertGreaterEqual(
            expected_position,
            0,
        )
        self.assertLess(
            current_position,
            expected_position,
            (
                "a identidade deve ser resolvida "
                "antes da invocação do validador"
            ),
        )

    def test_candidate_has_generation_boundary_check(
        self,
    ) -> None:
        source = self.candidate_source()

        self.assertTrue(
            (
                "commonpath" in source
                or "relative_to" in source
                or "is_relative_to" in source
            ),
            (
                "a geração resolvida deve permanecer "
                "dentro da raiz autorizada"
            ),
        )


class DecisionEngine3StateRootDynamicTest(
    unittest.TestCase
):
    """Testes comportamentais da resolução segura de STATE_ROOT."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def setUp(self) -> None:
        import tempfile

        self._temporary = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self._temporary.name
        )

        self.root.chmod(0o750)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def assert_failure(
        self,
        callable_object,
        expected_code,
        *arguments,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            callable_object(*arguments)

        self.assertEqual(
            context.exception.code,
            expected_code,
        )
        self.assertEqual(
            context.exception.exit_code,
            4,
        )
        self.assertIsInstance(
            context.exception.location,
            str,
        )
        self.assertTrue(
            context.exception.location,
        )
        self.assertIsInstance(
            context.exception.message,
            str,
        )
        self.assertTrue(
            context.exception.message,
        )

    def make_generation(
        self,
        generation_id="20260816T233109123456Z-0123456789abcdef0123456789abcdef",
    ):
        generations = (
            self.root
            / "generations"
        )
        generations.mkdir(
            mode=0o750
        )

        generation = (
            generations
            / generation_id
        )
        generation.mkdir(
            mode=0o750
        )

        return generation

    def write_current(
        self,
        content=b"20260816T233109123456Z-0123456789abcdef0123456789abcdef\n",
        mode=0o640,
    ):
        reference = (
            self.root
            / "current-generation"
        )
        reference.write_bytes(content)
        reference.chmod(mode)
        return reference

    def test_generation_id_accepts_valid_identifier(
        self,
    ) -> None:
        self.assertEqual(
            self.engine.validate_generation_id(
                "20260816T233109123456Z-0123456789abcdef0123456789abcdef"
            ),
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_generation_id_rejects_impossible_date(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_generation_id,
            "CURRENT_GENERATION_INVALID",
            "20260230T120000123456Z-3123456789abcdef0123456789abcdef",
        )

    def test_generation_id_rejects_parent_reference(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_generation_id,
            "CURRENT_GENERATION_INVALID",
            "..",
        )

    def test_generation_id_rejects_path_separator(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_generation_id,
            "CURRENT_GENERATION_INVALID",
            "../generation",
        )

    def test_state_root_accepts_secure_directory(
        self,
    ) -> None:
        resolved = (
            self.engine.validate_state_root(
                str(self.root)
            )
        )

        self.assertEqual(
            resolved,
            self.root.resolve(strict=True),
        )

    def test_state_root_rejects_world_writable_directory(
        self,
    ) -> None:
        self.root.chmod(0o777)

        self.assert_failure(
            self.engine.validate_state_root,
            "STATE_ROOT_INVALID",
            str(self.root),
        )

    def test_state_root_rejects_symbolic_link(
        self,
    ) -> None:
        link = (
            self.root.parent
            / (
                self.root.name
                + "-state-root-link"
            )
        )

        try:
            link.symlink_to(
                self.root,
                target_is_directory=True,
            )

            self.assert_failure(
                self.engine.validate_state_root,
                "STATE_ROOT_INVALID",
                str(link),
            )
        finally:
            link.unlink(missing_ok=True)

    def test_current_generation_content_accepts_contract(
        self,
    ) -> None:
        self.assertEqual(
            self.engine.validate_current_generation_content(
                b"20260816T233109123456Z-0123456789abcdef0123456789abcdef\n"
            ),
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_current_generation_content_rejects_missing_lf(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_current_generation_content,
            "CURRENT_GENERATION_INVALID",
            b"20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_current_generation_content_rejects_crlf(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_current_generation_content,
            "CURRENT_GENERATION_INVALID",
            b"20260816T233109123456Z-0123456789abcdef0123456789abcdef\r\n",
        )

    def test_current_generation_content_rejects_invalid_utf8(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_current_generation_content,
            "CURRENT_GENERATION_INVALID",
            b"\xff\n",
        )

    def test_current_generation_rejects_missing_file(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_MISSING",
            self.root,
        )

    def test_current_generation_accepts_secure_file(
        self,
    ) -> None:
        self.write_current()

        self.assertEqual(
            self.engine.read_current_generation(
                self.root
            ),
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_current_generation_rejects_excessive_permissions(
        self,
    ) -> None:
        self.write_current(
            mode=0o666
        )

        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_INVALID",
            self.root,
        )

    def test_current_generation_rejects_symbolic_link(
        self,
    ) -> None:
        target = (
            self.root
            / "target"
        )
        target.write_bytes(
            b"20260816T233109123456Z-0123456789abcdef0123456789abcdef\n"
        )
        target.chmod(0o640)

        reference = (
            self.root
            / "current-generation"
        )
        reference.symlink_to(target)

        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_INVALID",
            self.root,
        )

    def test_current_generation_rejects_oversize_file(
        self,
    ) -> None:
        self.write_current(
            (
                b"a" * 257
            )
        )

        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_TOO_LARGE",
            self.root,
        )

    def test_resolve_generation_accepts_valid_directory(
        self,
    ) -> None:
        generation = self.make_generation()

        resolved = (
            self.engine.resolve_generation(
                self.root,
                "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
            )
        )

        self.assertEqual(
            resolved,
            generation.resolve(strict=True),
        )

    def test_resolve_generation_rejects_missing_generation(
        self,
    ) -> None:
        (
            self.root
            / "generations"
        ).mkdir(mode=0o750)

        self.assert_failure(
            self.engine.resolve_generation,
            "GENERATION_INVALID",
            self.root,
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_resolve_generation_rejects_generation_symlink(
        self,
    ) -> None:
        generations = (
            self.root
            / "generations"
        )
        generations.mkdir(mode=0o750)

        outside = (
            self.root
            / "outside"
        )
        outside.mkdir(mode=0o750)

        (
            generations
            / "20260816T233109123456Z-0123456789abcdef0123456789abcdef"
        ).symlink_to(
            outside,
            target_is_directory=True,
        )

        self.assert_failure(
            self.engine.resolve_generation,
            "GENERATION_INVALID",
            self.root,
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )

    def test_resolve_input_keeps_single_generation_identity(
        self,
    ) -> None:
        generation = self.make_generation()
        self.write_current()

        (
            state_root,
            generation_id,
            resolved_generation,
        ) = self.engine.resolve_input(
            str(self.root)
        )

        self.assertEqual(
            state_root,
            self.root.resolve(strict=True),
        )
        self.assertEqual(
            generation_id,
            "20260816T233109123456Z-0123456789abcdef0123456789abcdef",
        )
        self.assertEqual(
            resolved_generation,
            generation.resolve(strict=True),
        )


    def test_current_generation_limit_is_contractual(
        self,
    ) -> None:
        self.assertEqual(
            self.engine.CURRENT_GENERATION_MAX_BYTES,
            256,
        )

    def test_state_root_rejects_missing_directory(
        self,
    ) -> None:
        missing = (
            self.root
            / "missing-state-root"
        )

        self.assert_failure(
            self.engine.validate_state_root,
            "STATE_ROOT_INVALID",
            str(missing),
        )

    def test_state_root_rejects_regular_file(
        self,
    ) -> None:
        regular = (
            self.root
            / "state-root-file"
        )
        regular.write_bytes(b"state-root\n")
        regular.chmod(0o640)

        self.assert_failure(
            self.engine.validate_state_root,
            "STATE_ROOT_INVALID",
            str(regular),
        )

    def test_current_generation_content_rejects_empty(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_current_generation_content,
            "CURRENT_GENERATION_INVALID",
            b"",
        )

    def test_current_generation_content_rejects_additional_line(
        self,
    ) -> None:
        self.assert_failure(
            self.engine.validate_current_generation_content,
            "CURRENT_GENERATION_INVALID",
            (
                b"20260816T233109123456Z-"
                b"0123456789abcdef0123456789abcdef\n"
                b"additional\n"
            ),
        )

    def test_current_generation_rejects_directory(
        self,
    ) -> None:
        reference = (
            self.root
            / "current-generation"
        )
        reference.mkdir(mode=0o750)

        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_INVALID",
            self.root,
        )

    def test_current_generation_rejects_mode_0644(
        self,
    ) -> None:
        self.write_current(mode=0o644)

        self.assert_failure(
            self.engine.read_current_generation,
            "CURRENT_GENERATION_INVALID",
            self.root,
        )

    def test_current_generation_rejects_unreadable_file(
        self,
    ) -> None:
        reference = self.write_current(mode=0o000)

        try:
            self.assert_failure(
                self.engine.read_current_generation,
                "CURRENT_GENERATION_UNREADABLE",
                self.root,
            )
        finally:
            reference.chmod(0o640)


    def test_current_generation_change_before_open_is_rejected(
        self,
    ) -> None:
        self.write_current()
        original_fstat = self.engine.os.fstat
        calls = 0

        def controlled_fstat(descriptor):
            nonlocal calls
            calls += 1

            current = original_fstat(
                descriptor
            )

            if calls != 1:
                return current

            return SimpleNamespace(
                st_dev=current.st_dev,
                st_ino=current.st_ino,
                st_mode=current.st_mode,
                st_nlink=current.st_nlink,
                st_size=current.st_size,
                st_mtime_ns=current.st_mtime_ns,
                st_ctime_ns=(
                    current.st_ctime_ns + 1
                ),
            )

        with mock.patch.object(
            self.engine.os,
            "fstat",
            side_effect=controlled_fstat,
        ):
            self.assert_failure(
                self.engine.read_current_generation,
                "CURRENT_GENERATION_CHANGED",
                self.root,
            )

    def test_current_generation_path_replacement_is_rejected(
        self,
    ) -> None:
        reference = self.write_current()
        replacement = (
            self.root
            / "replacement"
        )
        replacement.write_bytes(
            (
                b"20260816T233109123456Z-"
                b"ffffffffffffffffffffffffffffffff\n"
            )
        )
        replacement.chmod(0o640)

        original_read = self.engine.os.read
        replaced = False

        def controlled_read(descriptor, amount):
            nonlocal replaced

            if not replaced:
                replacement.replace(reference)
                replaced = True

            return original_read(
                descriptor,
                amount,
            )

        with mock.patch.object(
            self.engine.os,
            "read",
            side_effect=controlled_read,
        ):
            self.assert_failure(
                self.engine.read_current_generation,
                "CURRENT_GENERATION_CHANGED",
                self.root,
            )

    def test_current_generation_short_reads_are_completed(
        self,
    ) -> None:
        self.write_current()
        original_read = self.engine.os.read

        def controlled_read(descriptor, amount):
            return original_read(
                descriptor,
                min(amount, 8),
            )

        with mock.patch.object(
            self.engine.os,
            "read",
            side_effect=controlled_read,
        ):
            generation_id = (
                self.engine.read_current_generation(
                    self.root
                )
            )

        self.assertEqual(
            generation_id,
            (
                "20260816T233109123456Z-"
                "0123456789abcdef0123456789abcdef"
            ),
        )

    def test_current_generation_ctime_change_is_rejected(
        self,
    ) -> None:
        self.write_current()
        original_fstat = self.engine.os.fstat
        calls = 0

        def controlled_fstat(descriptor):
            nonlocal calls
            calls += 1

            current = original_fstat(
                descriptor
            )

            if calls != 2:
                return current

            return SimpleNamespace(
                st_dev=current.st_dev,
                st_ino=current.st_ino,
                st_mode=current.st_mode,
                st_nlink=current.st_nlink,
                st_size=current.st_size,
                st_mtime_ns=current.st_mtime_ns,
                st_ctime_ns=(
                    current.st_ctime_ns + 1
                ),
            )

        with mock.patch.object(
            self.engine.os,
            "fstat",
            side_effect=controlled_fstat,
        ):
            self.assert_failure(
                self.engine.read_current_generation,
                "CURRENT_GENERATION_CHANGED",
                self.root,
            )


    def test_resolve_generation_rejects_generations_symlink(
        self,
    ) -> None:
        outside = (
            self.root.parent
            / (
                self.root.name
                + "-outside-generations"
            )
        )
        outside.mkdir(mode=0o750)

        generations = (
            self.root
            / "generations"
        )

        try:
            generations.symlink_to(
                outside,
                target_is_directory=True,
            )

            self.assert_failure(
                self.engine.resolve_generation,
                "GENERATION_INVALID",
                self.root,
                (
                    "20260816T233109123456Z-"
                    "0123456789abcdef0123456789abcdef"
                ),
            )
        finally:
            generations.unlink(
                missing_ok=True
            )
            outside.rmdir()

    def test_validator_arguments_keep_fixed_generation(
        self,
    ) -> None:
        generation = self.make_generation()
        reference = self.write_current()

        (
            state_root,
            generation_id,
            resolved_generation,
        ) = self.engine.resolve_input(
            str(self.root)
        )

        reference.write_bytes(
            (
                b"20260816T233109123456Z-"
                b"ffffffffffffffffffffffffffffffff\n"
            )
        )
        reference.chmod(0o640)

        arguments = (
            self.engine.build_validator_arguments(
                generation_id,
                resolved_generation,
            )
        )

        self.assertEqual(
            state_root,
            self.root.resolve(strict=True),
        )
        self.assertEqual(
            generation_id,
            (
                "20260816T233109123456Z-"
                "0123456789abcdef0123456789abcdef"
            ),
        )
        self.assertEqual(
            resolved_generation,
            generation.resolve(strict=True),
        )
        self.assertEqual(
            arguments[-2],
            generation_id,
        )
        self.assertEqual(
            arguments[-1],
            str(resolved_generation),
        )
        self.assertNotIn(
            (
                "20260816T233109123456Z-"
                "ffffffffffffffffffffffffffffffff"
            ),
            arguments,
        )


class DecisionEngine3CaptureContractTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_capture_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def setUp(self) -> None:
        import tempfile

        self._temporary = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self._temporary.name
        )
        self.root.chmod(0o750)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def write_program(
        self,
        name: str,
        source: str,
    ) -> Path:
        program = self.root / name
        program.write_text(
            source,
            encoding="utf-8",
        )
        program.chmod(0o700)
        return program

    def capture(
        self,
        program: Path,
        *,
        timeout_seconds: float = 2.0,
    ):
        return (
            self.engine.capture_validator_process(
                [
                    "/usr/bin/python3",
                    "-I",
                    str(program),
                ],
                self.root,
                timeout_seconds=timeout_seconds,
            )
        )

    def assert_capture_failure(
        self,
        expected_code: str,
        callable_object,
        *arguments,
        **keywords,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            callable_object(
                *arguments,
                **keywords,
            )

        self.assertEqual(
            context.exception.code,
            expected_code,
        )

        expected_exit = {
            "SNAPSHOT_UNREADABLE": 5,
            "SNAPSHOT_TOO_LARGE": 5,
            "VALIDATOR_PROTOCOL_VIOLATION": 8,
        }[expected_code]

        self.assertEqual(
            context.exception.exit_code,
            expected_exit,
        )

    def test_capture_constants_are_contractual(
        self,
    ) -> None:
        self.assertEqual(
            self.engine.SNAPSHOT_MAX_BYTES,
            16777216,
        )
        self.assertEqual(
            self.engine.DIAGNOSTIC_MAX_BYTES,
            4096,
        )
        self.assertEqual(
            self.engine.VALIDATOR_TIMEOUT_SECONDS,
            60,
        )
        self.assertEqual(
            self.engine.TERMINATION_GRACE_SECONDS,
            2,
        )

    def test_child_environment_is_minimal(
        self,
    ) -> None:
        self.assertEqual(
            self.engine.build_child_environment(),
            {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )

    def test_capture_collects_exact_stdout(
        self,
    ) -> None:
        program = self.write_program(
            "stdout.py",
            (
                "import os\n"
                "os.write(1, b"
                "'{"
                '"ok":true'
                "}\\n')\n"
            ),
        )

        result = self.capture(program)

        self.assertEqual(
            result.exit_code,
            0,
        )
        self.assertEqual(
            result.stdout,
            b'{"ok":true}\n',
        )
        self.assertEqual(
            result.stderr,
            b"",
        )

    def test_capture_keeps_streams_separate(
        self,
    ) -> None:
        program = self.write_program(
            "streams.py",
            (
                "import os\n"
                "os.write(1, b'output\\n')\n"
                "os.write(2, b'error\\n')\n"
                "raise SystemExit(7)\n"
            ),
        )

        result = self.capture(program)

        self.assertEqual(
            result.exit_code,
            7,
        )
        self.assertEqual(
            result.stdout,
            b"output\n",
        )
        self.assertEqual(
            result.stderr,
            b"error\n",
        )

    def test_capture_rejects_stdout_above_limit(
        self,
    ) -> None:
        program = self.write_program(
            "large-stdout.py",
            (
                "import os\n"
                "chunk = b'x' * 65536\n"
                "for _ in range(257):\n"
                "    os.write(1, chunk)\n"
                "os.write(1, b'x')\n"
            ),
        )

        self.assert_capture_failure(
            "SNAPSHOT_TOO_LARGE",
            self.capture,
            program,
        )

    def test_capture_rejects_stderr_above_limit(
        self,
    ) -> None:
        program = self.write_program(
            "large-stderr.py",
            (
                "import os\n"
                "os.write(2, b'x' * 4097)\n"
            ),
        )

        self.assert_capture_failure(
            "VALIDATOR_PROTOCOL_VIOLATION",
            self.capture,
            program,
        )

    def test_capture_rejects_timeout(
        self,
    ) -> None:
        program = self.write_program(
            "timeout.py",
            (
                "import time\n"
                "time.sleep(10)\n"
            ),
        )

        self.assert_capture_failure(
            "SNAPSHOT_UNREADABLE",
            self.capture,
            program,
            timeout_seconds=0.05,
        )


    def test_timeout_drains_streams_after_sigterm(
        self,
    ) -> None:
        program = self.write_program(
            "timeout-drain.py",
            (
                "import os\n"
                "import signal\n"
                "import time\n"
                "\n"
                "def write_all(descriptor, content):\n"
                "    offset = 0\n"
                "    while offset < len(content):\n"
                "        offset += os.write(\n"
                "            descriptor,\n"
                "            content[offset:],\n"
                "        )\n"
                "\n"
                "def terminate(_signum, _frame):\n"
                "    write_all(1, b'x' * 1048576)\n"
                "    write_all(2, b'e' * 4096)\n"
                "    with open(\n"
                "        'sigterm-drained',\n"
                "        'wb',\n"
                "    ) as marker:\n"
                "        marker.write(b'complete\\n')\n"
                "    raise SystemExit(0)\n"
                "\n"
                "signal.signal(signal.SIGTERM, terminate)\n"
                "with open('handler-ready', 'wb') as ready:\n"
                "    ready.write(b'ready\\n')\n"
                "time.sleep(10)\n"
            ),
        )

        self.assert_capture_failure(
            "SNAPSHOT_UNREADABLE",
            self.capture,
            program,
            timeout_seconds=0.2,
        )

        self.assertEqual(
            (
                self.root
                / "sigterm-drained"
            ).read_bytes(),
            b"complete\n",
        )

    def test_timeout_terminates_session_descendants(
        self,
    ) -> None:
        program = self.write_program(
            "timeout-descendant.py",
            (
                "import os\n"
                "import signal\n"
                "import time\n"
                "\n"
                "with open('process-group', 'w') as output:\n"
                "    output.write(str(os.getpgrp()))\n"
                "    output.flush()\n"
                "    os.fsync(output.fileno())\n"
                "\n"
                "child = os.fork()\n"
                "\n"
                "if child == 0:\n"
                "    signal.signal(\n"
                "        signal.SIGTERM,\n"
                "        signal.SIG_IGN,\n"
                "    )\n"
                "    while True:\n"
                "        with open(\n"
                "            'descendant-heartbeat',\n"
                "            'ab',\n"
                "        ) as heartbeat:\n"
                "            heartbeat.write(b'x')\n"
                "            heartbeat.flush()\n"
                "            os.fsync(heartbeat.fileno())\n"
                "        time.sleep(0.02)\n"
                "\n"
                "time.sleep(10)\n"
            ),
        )

        process_group_file = (
            self.root
            / "process-group"
        )
        heartbeat = (
            self.root
            / "descendant-heartbeat"
        )

        try:
            self.assert_capture_failure(
                "SNAPSHOT_UNREADABLE",
                self.capture,
                program,
                timeout_seconds=0.2,
            )

            self.assertTrue(
                process_group_file.is_file()
            )
            self.assertTrue(
                heartbeat.is_file()
            )

            size_after_capture = (
                heartbeat.stat().st_size
            )

            time.sleep(0.15)

            self.assertEqual(
                heartbeat.stat().st_size,
                size_after_capture,
            )
        finally:
            if process_group_file.is_file():
                try:
                    process_group = int(
                        process_group_file.read_text(
                            encoding="ascii"
                        )
                    )
                    os.killpg(
                        process_group,
                        signal.SIGKILL,
                    )
                except (
                    ProcessLookupError,
                    PermissionError,
                    ValueError,
                ):
                    pass


class DecisionEngine3ValidatorProtocolTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_protocol_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def result(
        self,
        exit_code: int,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ):
        return self.engine.ValidatorProcessResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )

    def assert_protocol_failure(
        self,
        result,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.validate_validator_result(
                result
            )

        self.assertEqual(
            context.exception.code,
            "VALIDATOR_PROTOCOL_VIOLATION",
        )
        self.assertEqual(
            context.exception.exit_code,
            8,
        )

    def test_protocol_accepts_success_snapshot(
        self,
    ) -> None:
        snapshot = b'{"snapshot_version":"1.0.0"}\n'

        self.assertEqual(
            self.engine.validate_validator_result(
                self.result(
                    0,
                    stdout=snapshot,
                )
            ),
            snapshot,
        )

    def test_protocol_rejects_missing_snapshot(
        self,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.validate_validator_result(
                self.result(0)
            )

        self.assertEqual(
            context.exception.code,
            "SNAPSHOT_MISSING",
        )
        self.assertEqual(
            context.exception.exit_code,
            5,
        )

    def test_protocol_rejects_stderr_on_success(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                0,
                stdout=b"{}\n",
                stderr=b"unexpected\n",
            )
        )

    def test_protocol_propagates_valid_failures(
        self,
    ) -> None:
        valid_pairs = {
            3: (
                "DEPENDENCY_UNAVAILABLE",
                "REGISTRY_INVALID",
                "SCHEMA_INVALID",
            ),
            4: (
                "GENERATION_INVALID",
            ),
            5: (
                "MANIFEST_MISSING",
                "MANIFEST_UNREADABLE",
                "MANIFEST_TOO_LARGE",
                "INVALID_UTF8",
                "INVALID_JSON",
                "DUPLICATE_KEY",
                "NON_FINITE_NUMBER",
                "DEPTH_LIMIT_EXCEEDED",
            ),
            6: (
                "CONTRACT_VIOLATION",
            ),
            7: (
                "SEMANTIC_VIOLATION",
            ),
            8: (
                "GENERATION_MISMATCH",
            ),
            9: (
                "INTERNAL_ERROR",
            ),
        }

        for exit_code, codes in valid_pairs.items():
            for code in codes:
                with self.subTest(
                    exit_code=exit_code,
                    code=code,
                ):
                    diagnostic = (
                        "ERROR\t"
                        + code
                        + "\tlocation\tmessage\n"
                    ).encode("utf-8")

                    with self.assertRaises(
                        self.engine.DecisionFailure
                    ) as context:
                        (
                            self.engine
                            .validate_validator_result(
                                self.result(
                                    exit_code,
                                    stderr=diagnostic,
                                )
                            )
                        )

                    self.assertEqual(
                        context.exception.exit_code,
                        exit_code,
                    )
                    self.assertEqual(
                        context.exception.code,
                        code,
                    )
                    self.assertEqual(
                        context.exception.location,
                        "location",
                    )
                    self.assertEqual(
                        context.exception.message,
                        "message",
                    )

    def test_protocol_converts_validator_usage_error(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                2,
                stderr=(
                    b"ERROR\tUSAGE_INVALID\t"
                    b"arguments\tinvalid\n"
                ),
            )
        )

    def test_protocol_rejects_stdout_on_failure(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stdout=b"unexpected\n",
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\tinvalid\n"
                ),
            )
        )

    def test_protocol_rejects_unknown_exit_code(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                1,
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\tinvalid\n"
                ),
            )
        )

    def test_protocol_rejects_unknown_textual_code(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stderr=(
                    b"ERROR\tUNKNOWN_CODE\t"
                    b"generation\tinvalid\n"
                ),
            )
        )

    def test_protocol_rejects_mismatched_code_category(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                7,
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\tinvalid\n"
                ),
            )
        )

    def test_protocol_rejects_invalid_utf8(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stderr=b"\xff\n",
            )
        )

    def test_protocol_rejects_wrong_field_count(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\n"
                ),
            )
        )

    def test_protocol_rejects_missing_final_lf(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\tinvalid"
                ),
            )
        )

    def test_protocol_rejects_additional_line(
        self,
    ) -> None:
        self.assert_protocol_failure(
            self.result(
                4,
                stderr=(
                    b"ERROR\tGENERATION_INVALID\t"
                    b"generation\tinvalid\n"
                    b"additional\n"
                ),
            )
        )

    def test_protocol_rejects_location_above_limit(
        self,
    ) -> None:
        diagnostic = (
            "ERROR\tGENERATION_INVALID\t"
            + ("x" * 241)
            + "\tinvalid\n"
        ).encode("utf-8")

        self.assert_protocol_failure(
            self.result(
                4,
                stderr=diagnostic,
            )
        )

    def test_protocol_rejects_message_above_limit(
        self,
    ) -> None:
        diagnostic = (
            "ERROR\tGENERATION_INVALID\t"
            "generation\t"
            + ("x" * 241)
            + "\n"
        ).encode("utf-8")

        self.assert_protocol_failure(
            self.result(
                4,
                stderr=diagnostic,
            )
        )

    def test_protocol_resanitizes_control_characters(
        self,
    ) -> None:
        diagnostic = (
            b"ERROR\tGENERATION_INVALID\t"
            b"loc\x01ation\tmes\x7fsage\n"
        )

        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.validate_validator_result(
                self.result(
                    4,
                    stderr=diagnostic,
                )
            )

        self.assertEqual(
            context.exception.exit_code,
            4,
        )
        self.assertEqual(
            context.exception.code,
            "GENERATION_INVALID",
        )
        self.assertEqual(
            context.exception.location,
            "loc?ation",
        )
        self.assertEqual(
            context.exception.message,
            "mes?sage",
        )


class DecisionEngine3SnapshotSerializationTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_serialization_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def assert_snapshot_invalid(
        self,
        content: bytes,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.parse_snapshot_serialization(
                content
            )

        self.assertEqual(
            context.exception.code,
            "SNAPSHOT_INVALID",
        )
        self.assertEqual(
            context.exception.exit_code,
            6,
        )

    def test_serialization_accepts_compact_utf8_object(
        self,
    ) -> None:
        content = (
            '{"message":"ação\\nlinha","value":1}\n'
        ).encode("utf-8")

        document = (
            self.engine.parse_snapshot_serialization(
                content
            )
        )

        self.assertEqual(
            document,
            {
                "message": "ação\nlinha",
                "value": 1,
            },
        )

    def test_serialization_rejects_empty_input(
        self,
    ) -> None:
        self.assert_snapshot_invalid(b"")

    def test_serialization_rejects_missing_final_lf(
        self,
    ) -> None:
        self.assert_snapshot_invalid(b'{"value":1}')

    def test_serialization_rejects_crlf(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":1}\r\n'
        )

    def test_serialization_rejects_additional_lf(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":1}\n\n'
        )

    def test_serialization_rejects_utf8_bom(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b"\xef\xbb\xbf"
            b'{"value":1}\n'
        )

    def test_serialization_rejects_invalid_utf8(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":"\xff"}\n'
        )

    def test_serialization_rejects_truncated_json(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":\n'
        )

    def test_serialization_rejects_trailing_content(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":1}unexpected\n'
        )

    def test_serialization_rejects_duplicate_key(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":1,"value":2}\n'
        )

    def test_serialization_rejects_non_finite_number(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":NaN}\n'
        )

    def test_serialization_rejects_depth_above_40(
        self,
    ) -> None:
        content = (
            (b"[" * 41)
            + b"0"
            + (b"]" * 41)
            + b"\n"
        )

        self.assert_snapshot_invalid(content)

    def test_serialization_rejects_non_object_top_level(
        self,
    ) -> None:
        self.assert_snapshot_invalid(b"[]\n")

    def test_serialization_rejects_noncompact_json(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value": 1}\n'
        )

    def test_serialization_rejects_escaped_unicode(
        self,
    ) -> None:
        self.assert_snapshot_invalid(
            b'{"value":"\\u00e7"}\n'
        )


class DecisionEngine3SnapshotSchemasTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_schemas_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def setUp(self) -> None:
        import shutil
        import tempfile

        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(
            self.temporary.name
        )

        shutil.copytree(
            ROOT / "schemas",
            self.project_root / "schemas",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def parse_test_json(
        self,
        content: bytes,
    ) -> object:
        import json

        return json.loads(
            content.decode(
                "utf-8",
                errors="strict",
            )
        )

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        content = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        ).read_bytes()

        document = self.parse_test_json(content)

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def assert_configuration_invalid(
        self,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.load_snapshot_schemas(
                self.project_root
            )

        self.assertEqual(
            context.exception.code,
            "CONFIGURATION_INVALID",
        )
        self.assertEqual(
            context.exception.exit_code,
            3,
        )

    def assert_snapshot_invalid(
        self,
        snapshot: dict[str, object],
    ) -> None:
        schemas = self.engine.load_snapshot_schemas(
            self.project_root
        )

        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.validate_snapshot_documents(
                snapshot,
                schemas,
            )

        self.assertEqual(
            context.exception.code,
            "SNAPSHOT_INVALID",
        )
        self.assertEqual(
            context.exception.exit_code,
            6,
        )

    def schema_path(
        self,
        family: str,
        version: str,
        filename: str,
    ) -> Path:
        return (
            self.project_root
            / "schemas"
            / family
            / version
            / filename
        )

    def rewrite_json(
        self,
        path: Path,
        document: object,
    ) -> None:
        import json

        path.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_schema_loader_accepts_official_schemas(
        self,
    ) -> None:
        schemas = self.engine.load_snapshot_schemas(
            self.project_root
        )

        self.assertIsNotNone(schemas)

    def test_schema_validation_accepts_complete_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        schemas = self.engine.load_snapshot_schemas(
            self.project_root
        )

        self.assertEqual(
            self.engine.validate_snapshot_documents(
                snapshot,
                schemas,
            ),
            snapshot,
        )

    def test_schema_validation_accepts_partial_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )
        schemas = self.engine.load_snapshot_schemas(
            self.project_root
        )

        self.assertEqual(
            self.engine.validate_snapshot_documents(
                snapshot,
                schemas,
            ),
            snapshot,
        )

    def test_schema_validation_accepts_failed_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-failed"
        )
        schemas = self.engine.load_snapshot_schemas(
            self.project_root
        )

        self.assertEqual(
            self.engine.validate_snapshot_documents(
                snapshot,
                schemas,
            ),
            snapshot,
        )

    def test_schema_validation_rejects_invalid_envelope(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        snapshot["unexpected"] = True

        self.assert_snapshot_invalid(snapshot)

    def test_schema_validation_rejects_invalid_manifest(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        manifest = snapshot["manifest"]

        if not isinstance(manifest, dict):
            raise TypeError("manifesto inválido")

        manifest["unexpected"] = True

        self.assert_snapshot_invalid(snapshot)

    def test_schema_validation_rejects_invalid_report(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise TypeError("reports inválido")

        first_report = next(iter(reports.values()))

        if not isinstance(first_report, dict):
            raise TypeError("relatório inválido")

        first_report["unexpected"] = True

        self.assert_snapshot_invalid(snapshot)

    def test_schema_loader_rejects_missing_schema(
        self,
    ) -> None:
        path = self.schema_path(
            "validated-generation-snapshot",
            "1.0.0",
            "validated-generation-snapshot.schema.json",
        )
        path.unlink()

        self.assert_configuration_invalid()

    def test_schema_loader_rejects_symbolic_link(
        self,
    ) -> None:
        path = self.schema_path(
            "validated-generation-snapshot",
            "1.0.0",
            "validated-generation-snapshot.schema.json",
        )
        replacement = path.with_name(
            "replacement.schema.json"
        )

        path.rename(replacement)
        path.symlink_to(replacement.name)

        self.assert_configuration_invalid()

    def test_schema_loader_rejects_wrong_identity(
        self,
    ) -> None:
        path = self.schema_path(
            "validated-generation-snapshot",
            "1.0.0",
            "validated-generation-snapshot.schema.json",
        )
        document = self.parse_test_json(
            path.read_bytes()
        )

        if not isinstance(document, dict):
            raise TypeError("schema inválido")

        document["$id"] = "urn:unexpected"
        self.rewrite_json(path, document)

        self.assert_configuration_invalid()

    def test_schema_loader_rejects_external_reference(
        self,
    ) -> None:
        path = self.schema_path(
            "validated-generation-snapshot",
            "1.0.0",
            "validated-generation-snapshot.schema.json",
        )
        document = self.parse_test_json(
            path.read_bytes()
        )

        if not isinstance(document, dict):
            raise TypeError("schema inválido")

        document["unexpected"] = {
            "$ref": "https://example.invalid/schema"
        }
        self.rewrite_json(path, document)

        self.assert_configuration_invalid()

    def test_schema_loader_rejects_invalid_schema(
        self,
    ) -> None:
        path = self.schema_path(
            "validated-generation-snapshot",
            "1.0.0",
            "validated-generation-snapshot.schema.json",
        )
        document = self.parse_test_json(
            path.read_bytes()
        )

        if not isinstance(document, dict):
            raise TypeError("schema inválido")

        document["type"] = 7
        self.rewrite_json(path, document)

        self.assert_configuration_invalid()


class DecisionEngine3SnapshotSemanticsTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_semantics_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def validate(
        self,
        snapshot: dict[str, object],
    ) -> dict[str, object]:
        generation_id = snapshot["generation_id"]

        if not isinstance(generation_id, str):
            raise TypeError(
                "generation_id inválida"
            )

        return self.engine.validate_snapshot_semantics(
            snapshot,
            generation_id,
        )

    def assert_semantic_violation(
        self,
        snapshot: dict[str, object],
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.validate(snapshot)

        self.assertEqual(
            context.exception.code,
            "SNAPSHOT_SEMANTIC_VIOLATION",
        )
        self.assertEqual(
            context.exception.exit_code,
            7,
        )

    def test_semantics_accepts_complete_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertIs(
            self.validate(snapshot),
            snapshot,
        )

    def test_semantics_accepts_partial_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertIs(
            self.validate(snapshot),
            snapshot,
        )

    def test_semantics_accepts_failed_snapshot(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-failed"
        )

        self.assertIs(
            self.validate(snapshot),
            snapshot,
        )

    def test_semantics_rejects_requested_generation_mismatch(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.validate_snapshot_semantics(
                snapshot,
                (
                    "20260816T233209123456Z-"
                    "1123456789abcdef0123456789abcdef"
                ),
            )

        self.assertEqual(
            context.exception.code,
            "SNAPSHOT_MISMATCH",
        )
        self.assertEqual(
            context.exception.exit_code,
            8,
        )

    def test_semantics_rejects_internal_generation_mismatch(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        snapshot["generation_id"] = (
            "20260816T233209123456Z-"
            "1123456789abcdef0123456789abcdef"
        )

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_state_mismatch(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        snapshot["state"] = "PARTIAL"

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_summary_mismatch(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        manifest = snapshot["manifest"]

        if not isinstance(manifest, dict):
            raise TypeError("manifesto inválido")

        summary = manifest["summary"]

        if not isinstance(summary, dict):
            raise TypeError("resumo inválido")

        summary["reports_written"] = 6

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_missing_report(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise TypeError("reports inválido")

        reports.pop("observer-cpu")

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_additional_report(
        self,
    ) -> None:
        import copy

        snapshot = self.load_fixture(
            "valid-complete"
        )
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise TypeError("reports inválido")

        reports["observer-extra"] = copy.deepcopy(
            reports["observer-cpu"]
        )

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_report_key_mismatch(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise TypeError("reports inválido")

        report = reports.pop("observer-cpu")
        reports["observer-extra"] = report

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_descriptor_mismatch(
        self,
    ) -> None:
        mutations = {
            "module": "observer-memory",
            "version": "1.0.1",
            "timestamp": (
                "2026-08-16T23:31:10+0000"
            ),
            "status": "WARNING",
        }

        for field, value in mutations.items():
            with self.subTest(
                field=field,
                value=value,
            ):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                reports = snapshot["reports"]

                if not isinstance(reports, dict):
                    raise TypeError(
                        "reports inválido"
                    )

                report = reports["observer-cpu"]

                if not isinstance(report, dict):
                    raise TypeError(
                        "relatório inválido"
                    )

                report[field] = value

                self.assert_semantic_violation(
                    snapshot
                )

    def test_semantics_rejects_complete_with_failure(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )
        snapshot["state"] = "COMPLETE"

        manifest = snapshot["manifest"]

        if not isinstance(manifest, dict):
            raise TypeError("manifesto inválido")

        manifest["state"] = "COMPLETE"

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_partial_without_failure(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        snapshot["state"] = "PARTIAL"

        manifest = snapshot["manifest"]

        if not isinstance(manifest, dict):
            raise TypeError("manifesto inválido")

        manifest["state"] = "PARTIAL"

        self.assert_semantic_violation(snapshot)

    def test_semantics_rejects_failed_with_success(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        snapshot["state"] = "FAILED"

        manifest = snapshot["manifest"]

        if not isinstance(manifest, dict):
            raise TypeError("manifesto inválido")

        manifest["state"] = "FAILED"

        self.assert_semantic_violation(snapshot)


class DecisionEngine3SnapshotOrchestrationTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_orchestration_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def capture_result(
        self,
        fixture_name: str,
    ):
        import json

        snapshot = self.load_fixture(
            fixture_name
        )

        serialized = (
            json.dumps(
                snapshot,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        return self.engine.ValidatorProcessResult(
            stdout=serialized,
            stderr=b"",
            exit_code=0,
        )

    def run_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        from unittest import mock

        result = self.capture_result(
            fixture_name
        )
        snapshot = self.load_fixture(
            fixture_name
        )
        generation_id = snapshot["generation_id"]

        if not isinstance(generation_id, str):
            raise TypeError(
                "generation_id inválida"
            )

        generation = (
            ROOT
            / "state"
            / "generations"
            / generation_id
        )

        with mock.patch.object(
            self.engine,
            "capture_validator_process",
            return_value=result,
        ):
            return self.engine.obtain_validated_snapshot(
                generation_id,
                generation,
            )

    def failure(
        self,
        exit_code: int,
        code: str,
    ):
        return self.engine.DecisionFailure(
            exit_code,
            code,
            "test",
            "falha controlada",
        )

    def test_orchestration_accepts_complete_snapshot(
        self,
    ) -> None:
        snapshot = self.run_fixture(
            "valid-complete"
        )

        self.assertEqual(
            snapshot["state"],
            "COMPLETE",
        )

    def test_orchestration_accepts_partial_snapshot(
        self,
    ) -> None:
        snapshot = self.run_fixture(
            "valid-partial"
        )

        self.assertEqual(
            snapshot["state"],
            "PARTIAL",
        )

    def test_orchestration_rejects_failed_generation(
        self,
    ) -> None:
        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.run_fixture(
                "valid-failed"
            )

        self.assertEqual(
            context.exception.code,
            "GENERATION_FAILED",
        )
        self.assertEqual(
            context.exception.exit_code,
            6,
        )

    def test_orchestration_uses_fixed_arguments_and_cwd(
        self,
    ) -> None:
        from unittest import mock

        result = self.capture_result(
            "valid-complete"
        )
        snapshot = self.load_fixture(
            "valid-complete"
        )
        generation_id = snapshot["generation_id"]

        if not isinstance(generation_id, str):
            raise TypeError(
                "generation_id inválida"
            )

        generation = (
            ROOT
            / "state"
            / "generations"
            / generation_id
        )

        expected_arguments = (
            self.engine.build_validator_arguments(
                generation_id,
                generation,
            )
        )

        with mock.patch.object(
            self.engine,
            "capture_validator_process",
            return_value=result,
        ) as capture:
            self.engine.obtain_validated_snapshot(
                generation_id,
                generation,
            )

        capture.assert_called_once_with(
            expected_arguments,
            ROOT,
        )

    def test_orchestration_stops_after_protocol_failure(
        self,
    ) -> None:
        from unittest import mock

        failure = self.failure(
            8,
            "VALIDATOR_PROTOCOL_VIOLATION",
        )

        with (
            mock.patch.object(
                self.engine,
                "capture_validator_process",
                return_value=object(),
            ),
            mock.patch.object(
                self.engine,
                "validate_validator_result",
                side_effect=failure,
            ),
            mock.patch.object(
                self.engine,
                "parse_snapshot_serialization",
            ) as parser,
        ):
            with self.assertRaises(
                self.engine.DecisionFailure
            ) as context:
                self.engine.obtain_validated_snapshot(
                    "generation",
                    Path("/generation"),
                )

        self.assertIs(
            context.exception,
            failure,
        )
        parser.assert_not_called()

    def test_orchestration_stops_after_serialization_failure(
        self,
    ) -> None:
        from unittest import mock

        failure = self.failure(
            6,
            "SNAPSHOT_INVALID",
        )

        with (
            mock.patch.object(
                self.engine,
                "capture_validator_process",
                return_value=object(),
            ),
            mock.patch.object(
                self.engine,
                "validate_validator_result",
                return_value=b"snapshot",
            ),
            mock.patch.object(
                self.engine,
                "parse_snapshot_serialization",
                side_effect=failure,
            ),
            mock.patch.object(
                self.engine,
                "load_snapshot_schemas",
            ) as loader,
        ):
            with self.assertRaises(
                self.engine.DecisionFailure
            ) as context:
                self.engine.obtain_validated_snapshot(
                    "generation",
                    Path("/generation"),
                )

        self.assertIs(
            context.exception,
            failure,
        )
        loader.assert_not_called()

    def test_orchestration_stops_after_schema_failure(
        self,
    ) -> None:
        from unittest import mock

        failure = self.failure(
            3,
            "CONFIGURATION_INVALID",
        )

        with (
            mock.patch.object(
                self.engine,
                "capture_validator_process",
                return_value=object(),
            ),
            mock.patch.object(
                self.engine,
                "validate_validator_result",
                return_value=b"snapshot",
            ),
            mock.patch.object(
                self.engine,
                "parse_snapshot_serialization",
                return_value={},
            ),
            mock.patch.object(
                self.engine,
                "load_snapshot_schemas",
                side_effect=failure,
            ),
            mock.patch.object(
                self.engine,
                "validate_snapshot_documents",
            ) as validator,
        ):
            with self.assertRaises(
                self.engine.DecisionFailure
            ) as context:
                self.engine.obtain_validated_snapshot(
                    "generation",
                    Path("/generation"),
                )

        self.assertIs(
            context.exception,
            failure,
        )
        validator.assert_not_called()

    def test_orchestration_propagates_semantic_failure(
        self,
    ) -> None:
        from unittest import mock

        failure = self.failure(
            7,
            "SNAPSHOT_SEMANTIC_VIOLATION",
        )

        with (
            mock.patch.object(
                self.engine,
                "capture_validator_process",
                return_value=object(),
            ),
            mock.patch.object(
                self.engine,
                "validate_validator_result",
                return_value=b"snapshot",
            ),
            mock.patch.object(
                self.engine,
                "parse_snapshot_serialization",
                return_value={},
            ),
            mock.patch.object(
                self.engine,
                "load_snapshot_schemas",
                return_value=object(),
            ),
            mock.patch.object(
                self.engine,
                "validate_snapshot_documents",
                return_value={},
            ),
            mock.patch.object(
                self.engine,
                "validate_snapshot_semantics",
                side_effect=failure,
            ),
        ):
            with self.assertRaises(
                self.engine.DecisionFailure
            ) as context:
                self.engine.obtain_validated_snapshot(
                    "generation",
                    Path("/generation"),
                )

        self.assertIs(
            context.exception,
            failure,
        )


class DecisionEngine3OverallHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_overall_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_report_status(
        self,
        snapshot: dict[str, object],
        module: str,
        status: str,
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports[module]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = status

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module") == module
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = status
                return

        raise KeyError(module)

    def set_all_report_statuses(
        self,
        snapshot: dict[str, object],
        status: str,
    ) -> None:
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise TypeError("reports inválido")

        for module in list(reports):
            self.set_report_status(
                snapshot,
                module,
                status,
            )

    def test_overall_complete_all_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "OK",
        )

    def test_overall_complete_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_all_report_statuses(
            snapshot,
            "OK",
        )
        self.set_report_status(
            snapshot,
            "observer-cpu",
            "UNKNOWN",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_overall_complete_warning_over_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_all_report_statuses(
            snapshot,
            "OK",
        )
        self.set_report_status(
            snapshot,
            "observer-cpu",
            "UNKNOWN",
        )
        self.set_report_status(
            snapshot,
            "observer-memory",
            "WARNING",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "WARNING",
        )

    def test_overall_complete_error_over_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_all_report_statuses(
            snapshot,
            "OK",
        )
        self.set_report_status(
            snapshot,
            "observer-cpu",
            "WARNING",
        )
        self.set_report_status(
            snapshot,
            "observer-memory",
            "ERROR",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "ERROR",
        )

    def test_overall_partial_ok_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )
        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_overall_partial_unknown_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_overall_partial_warning_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )
        self.set_all_report_statuses(
            snapshot,
            "WARNING",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_overall_partial_error_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )
        self.set_all_report_statuses(
            snapshot,
            "ERROR",
        )

        self.assertEqual(
            self.engine.evaluate_overall_health(
                snapshot
            ),
            "ERROR",
        )

    def test_overall_rejects_failed_generation(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-failed"
        )

        with self.assertRaises(
            self.engine.DecisionFailure
        ) as context:
            self.engine.evaluate_overall_health(
                snapshot
            )

        self.assertEqual(
            context.exception.code,
            "GENERATION_FAILED",
        )
        self.assertEqual(
            context.exception.exit_code,
            6,
        )


class DecisionEngine3SystemHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_system_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_system(
        self,
        snapshot: dict[str, object],
        status: str,
        facts: dict[str, object],
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports["observer-system"]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = status
        report["facts"] = facts

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module")
                == "observer-system"
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = status
                return

        raise KeyError("observer-system")

    def test_system_failed_module_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_system_unknown_report_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_system_error_report_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_system(
            snapshot,
            "ERROR",
            {},
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "ERROR",
        )

    def test_system_warning_report_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_system(
            snapshot,
            "WARNING",
            {},
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "WARNING",
        )

    def test_system_ok_with_missing_fact_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_system(
            snapshot,
            "OK",
            {
                "time_available": True,
                "ntp_enabled": True,
            },
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_system_ok_with_invalid_fact_is_unknown(
        self,
    ) -> None:
        invalid_facts = (
            {
                "time_available": "true",
                "ntp_enabled": True,
                "ntp_synchronized": True,
            },
            {
                "time_available": True,
                "ntp_enabled": 1,
                "ntp_synchronized": True,
            },
            {
                "time_available": True,
                "ntp_enabled": True,
                "ntp_synchronized": "false",
            },
        )

        for facts in invalid_facts:
            with self.subTest(facts=facts):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                self.set_system(
                    snapshot,
                    "OK",
                    facts,
                )

                self.assertEqual(
                    self.engine.evaluate_system_health(
                        snapshot
                    ),
                    "UNKNOWN",
                )

    def test_system_time_unavailable_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_system(
            snapshot,
            "OK",
            {
                "time_available": False,
                "ntp_enabled": True,
                "ntp_synchronized": True,
            },
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_system_ntp_false_is_warning(
        self,
    ) -> None:
        ntp_values = (
            (False, True),
            (True, False),
            (False, False),
        )

        for enabled, synchronized in ntp_values:
            with self.subTest(
                enabled=enabled,
                synchronized=synchronized,
            ):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                self.set_system(
                    snapshot,
                    "OK",
                    {
                        "time_available": True,
                        "ntp_enabled": enabled,
                        "ntp_synchronized": synchronized,
                    },
                )

                self.assertEqual(
                    self.engine.evaluate_system_health(
                        snapshot
                    ),
                    "WARNING",
                )

    def test_system_all_determinants_true_is_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_system(
            snapshot,
            "OK",
            {
                "time_available": True,
                "ntp_enabled": True,
                "ntp_synchronized": True,
            },
        )

        self.assertEqual(
            self.engine.evaluate_system_health(
                snapshot
            ),
            "OK",
        )


class DecisionEngine3SecurityHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_security_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_ssh(
        self,
        snapshot: dict[str, object],
        status: str,
        facts: dict[str, object],
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports["observer-ssh"]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = status
        report["facts"] = facts

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module")
                == "observer-ssh"
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = status
                return

        raise KeyError("observer-ssh")

    def test_security_failed_module_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_security_unknown_report_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_security_missing_journal_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_ssh(
            snapshot,
            "OK",
            {
                "failed_password_events_24h": 0,
            },
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_security_false_journal_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_ssh(
            snapshot,
            "OK",
            {
                "journal_available": False,
                "failed_password_events_24h": 0,
            },
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_security_invalid_journal_is_unknown(
        self,
    ) -> None:
        invalid_values = (
            "true",
            1,
            None,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                self.set_ssh(
                    snapshot,
                    "OK",
                    {
                        "journal_available": value,
                        "failed_password_events_24h": 0,
                    },
                )

                self.assertEqual(
                    self.engine.evaluate_security_health(
                        snapshot
                    ),
                    "UNKNOWN",
                )

    def test_security_missing_failed_count_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_ssh(
            snapshot,
            "OK",
            {
                "journal_available": True,
            },
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_security_invalid_failed_count_is_unknown(
        self,
    ) -> None:
        invalid_values = (
            True,
            -1,
            "0",
            0.0,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                self.set_ssh(
                    snapshot,
                    "OK",
                    {
                        "journal_available": True,
                        "failed_password_events_24h":
                            value,
                    },
                )

                self.assertEqual(
                    self.engine.evaluate_security_health(
                        snapshot
                    ),
                    "UNKNOWN",
                )

    def test_security_zero_failed_count_is_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )
        self.set_ssh(
            snapshot,
            "OK",
            {
                "journal_available": True,
                "failed_password_events_24h": 0,
            },
        )

        self.assertEqual(
            self.engine.evaluate_security_health(
                snapshot
            ),
            "OK",
        )

    def test_security_positive_failed_count_is_warning(
        self,
    ) -> None:
        supplementary_values = (
            {},
            {
                "invalid_user_events_24h": "invalid",
                "accepted_publickey_events_24h": -1,
            },
            {
                "invalid_user_events_24h": 4,
                "accepted_publickey_events_24h": 2,
            },
        )

        for supplementary in supplementary_values:
            with self.subTest(
                supplementary=supplementary
            ):
                snapshot = self.load_fixture(
                    "valid-complete"
                )
                facts = {
                    "journal_available": True,
                    "failed_password_events_24h": 3,
                }
                facts.update(supplementary)

                self.set_ssh(
                    snapshot,
                    "OK",
                    facts,
                )

                self.assertEqual(
                    self.engine.evaluate_security_health(
                        snapshot
                    ),
                    "WARNING",
                )


class DecisionEngine3ResourcesHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        spec = importlib.util.spec_from_file_location(
            "decision_engine_3_resources_under_test",
            implementation,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_module_report(
        self,
        snapshot: dict[str, object],
        module_name: str,
        facts: dict[str, object],
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports[module_name]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = "OK"
        report["facts"] = facts

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module")
                == module_name
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = "OK"
                return

        raise KeyError(module_name)

    def set_resources(
        self,
        snapshot: dict[str, object],
        *,
        cpu_count: object = 4,
        load_15min: object = 1.0,
        mem_total: object = 100,
        mem_available: object = 50,
        swap_total: object = 100,
        swap_free: object = 100,
    ) -> None:
        self.set_module_report(
            snapshot,
            "observer-cpu",
            {
                "cpu_count": cpu_count,
                "load_15min": load_15min,
            },
        )

        self.set_module_report(
            snapshot,
            "observer-memory",
            {
                "memory": {
                    "MemTotal": mem_total,
                    "MemAvailable": mem_available,
                    "SwapTotal": swap_total,
                    "SwapFree": swap_free,
                },
            },
        )

    def test_resources_failed_cpu_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-failed"
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_resources_failed_memory_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_resources_missing_facts_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_resources_invalid_facts_are_unknown(
        self,
    ) -> None:
        invalid_cases = (
            {
                "cpu_count": True,
            },
            {
                "cpu_count": 0,
            },
            {
                "cpu_count": 4.0,
            },
            {
                "load_15min": True,
            },
            {
                "load_15min": -0.1,
            },
            {
                "mem_total": True,
            },
            {
                "mem_total": 0,
            },
            {
                "mem_available": -1,
            },
            {
                "swap_total": -1,
            },
            {
                "swap_free": "0",
            },
        )

        for changes in invalid_cases:
            with self.subTest(changes=changes):
                snapshot = self.load_fixture(
                    "valid-complete"
                )

                self.set_resources(
                    snapshot,
                    **changes,
                )

                self.assertEqual(
                    self.engine.evaluate_resources_health(
                        snapshot
                    ),
                    "UNKNOWN",
                )

    def test_resources_cpu_critical_boundary_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            cpu_count=4,
            load_15min=8.0,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "ERROR",
        )

    def test_resources_memory_below_five_percent_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            mem_total=100,
            mem_available=4,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "ERROR",
        )

    def test_resources_cpu_warning_boundary_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            cpu_count=4,
            load_15min=4.0,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "WARNING",
        )

    def test_resources_memory_five_percent_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            mem_total=100,
            mem_available=5,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "WARNING",
        )

    def test_resources_swap_seventy_five_percent_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            swap_total=100,
            swap_free=25,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "WARNING",
        )

    def test_resources_zero_swap_total_does_not_warn(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            swap_total=0,
            swap_free=0,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "OK",
        )

    def test_resources_memory_fifteen_percent_is_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_resources(
            snapshot,
            mem_total=100,
            mem_available=15,
        )

        self.assertEqual(
            self.engine.evaluate_resources_health(
                snapshot
            ),
            "OK",
        )


class DecisionEngine3ConnectivityHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        from importlib.machinery import SourceFileLoader

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        loader = SourceFileLoader(
            "decision_engine_3_connectivity_under_test",
            str(implementation),
        )

        spec = importlib.util.spec_from_loader(
            "decision_engine_3_connectivity_under_test",
            loader,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_module_report(
        self,
        snapshot: dict[str, object],
        module_name: str,
        facts: dict[str, object],
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports[module_name]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = "OK"
        report["facts"] = facts

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module")
                == module_name
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = "OK"
                return

        raise KeyError(module_name)

    def set_network(
        self,
        snapshot: dict[str, object],
        *,
        interfaces: object = None,
        default_routes: object = None,
    ) -> None:
        if interfaces is None:
            interfaces = [
                {
                    "ifname": "enp8s0",
                    "flags": [
                        "BROADCAST",
                        "MULTICAST",
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "POINTOPOINT",
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "POINTOPOINT",
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ]

        if default_routes is None:
            default_routes = [
                {
                    "gateway": "192.0.2.1",
                    "dev": "enp8s0",
                },
            ]

        self.set_module_report(
            snapshot,
            "observer-network",
            {
                "interfaces": interfaces,
                "default_routes": default_routes,
            },
        )

    def test_connectivity_failed_network_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_connectivity_missing_structures_are_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_connectivity_invalid_structure_types_are_unknown(
        self,
    ) -> None:
        invalid_cases = (
            {
                "interfaces": {},
                "default_routes": [],
            },
            {
                "interfaces": [],
                "default_routes": {},
            },
            {
                "interfaces": "invalid",
                "default_routes": [],
            },
            {
                "interfaces": [],
                "default_routes": "invalid",
            },
        )

        for facts in invalid_cases:
            with self.subTest(facts=facts):
                snapshot = self.load_fixture(
                    "valid-complete"
                )

                self.set_module_report(
                    snapshot,
                    "observer-network",
                    facts,
                )

                self.assertEqual(
                    self.engine.evaluate_connectivity_health(
                        snapshot
                    ),
                    "UNKNOWN",
                )

    def test_connectivity_present_malformed_interface_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "enp8s0",
                    "flags": "UP",
                },
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_connectivity_missing_lan_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "ERROR",
        )

    def test_connectivity_lan_without_required_flags_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "enp8s0",
                    "flags": [
                        "UP",
                    ],
                },
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "ERROR",
        )

    def test_connectivity_missing_default_route_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            default_routes=[],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "ERROR",
        )

    def test_connectivity_missing_gateway_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            default_routes=[
                {
                    "dev": "enp8s0",
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "ERROR",
        )

    def test_connectivity_wrong_default_route_device_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            default_routes=[
                {
                    "gateway": "192.0.2.1",
                    "dev": "tailscale0",
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "ERROR",
        )

    def test_connectivity_missing_tailscale_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "enp8s0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "WARNING",
        )

    def test_connectivity_wireguard_not_operational_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "enp8s0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "WARNING",
        )

    def test_connectivity_operational_with_extra_interface_is_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_network(
            snapshot,
            interfaces=[
                {
                    "ifname": "wg0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "docker0",
                    "flags": [
                        "BROADCAST",
                        "MULTICAST",
                    ],
                },
                {
                    "ifname": "enp8s0",
                    "flags": [
                        "BROADCAST",
                        "MULTICAST",
                        "UP",
                        "LOWER_UP",
                    ],
                },
                {
                    "ifname": "tailscale0",
                    "flags": [
                        "UP",
                        "LOWER_UP",
                    ],
                },
            ],
        )

        self.assertEqual(
            self.engine.evaluate_connectivity_health(
                snapshot
            ),
            "OK",
        )


class DecisionEngine3ServicesHealthTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        from importlib.machinery import SourceFileLoader

        implementation = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        loader = SourceFileLoader(
            "decision_engine_3_services_under_test",
            str(implementation),
        )

        spec = importlib.util.spec_from_loader(
            "decision_engine_3_services_under_test",
            loader,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)
        cls.engine = module

    def load_fixture(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        import json

        path = (
            ROOT
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / fixture_name
            / "snapshot.json"
        )

        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(document, dict):
            raise TypeError(
                "fixture de snapshot não é objeto"
            )

        return document

    def set_services(
        self,
        snapshot: dict[str, object],
        facts: object,
    ) -> None:
        reports = snapshot["reports"]
        manifest = snapshot["manifest"]

        if (
            not isinstance(reports, dict)
            or not isinstance(manifest, dict)
        ):
            raise TypeError("snapshot inválido")

        report = reports["observer-services"]
        modules = manifest["modules"]

        if (
            not isinstance(report, dict)
            or not isinstance(modules, list)
        ):
            raise TypeError("snapshot inválido")

        report["status"] = "OK"
        report["facts"] = facts

        for entry in modules:
            if (
                isinstance(entry, dict)
                and entry.get("module")
                == "observer-services"
            ):
                descriptor = entry.get("report")

                if not isinstance(descriptor, dict):
                    raise TypeError(
                        "descritor inválido"
                    )

                descriptor["status"] = "OK"
                return

        raise KeyError("observer-services")

    def operational_facts(
        self,
    ) -> dict[str, object]:
        return {
            "ssh.service": "active",
            "tailscaled.service": "active",
            "fail2ban.service": "active",
            "AdGuardHome.service": "active",
        }

    def test_services_failed_module_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_services_missing_facts_are_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_services_invalid_facts_type_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_services(
            snapshot,
            [],
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_services_missing_determinant_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        del facts["fail2ban.service"]

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_services_invalid_determinant_type_is_unknown(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        facts["tailscaled.service"] = True

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "UNKNOWN",
        )

    def test_services_ssh_not_active_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        facts["ssh.service"] = "inactive"

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "ERROR",
        )

    def test_services_adguard_not_active_is_error(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        facts["AdGuardHome.service"] = "failed"

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "ERROR",
        )

    def test_services_tailscale_not_active_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        facts["tailscaled.service"] = "inactive"

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "WARNING",
        )

    def test_services_fail2ban_not_active_is_warning(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        facts = self.operational_facts()
        facts["fail2ban.service"] = "failed"

        self.set_services(
            snapshot,
            facts,
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "WARNING",
        )

    def test_services_all_active_is_ok(
        self,
    ) -> None:
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_services(
            snapshot,
            self.operational_facts(),
        )

        self.assertEqual(
            self.engine.evaluate_services_health(
                snapshot
            ),
            "OK",
        )




class DecisionEngine3HealthAggregateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        cls.repo_root = Path(__file__).resolve().parents[1]

        implementation = (
            cls.repo_root
            / "decision"
            / "decision-engine.py"
        )

        loader = SourceFileLoader(
            "decision_engine_3_health_aggregate_under_test",
            str(implementation),
        )

        spec = importlib.util.spec_from_loader(
            "decision_engine_3_health_aggregate_under_test",
            loader,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "não foi possível carregar Decision Engine 3"
            )

        module = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(module)

        cls.module = module

    def load_fixture(
        self,
        name: str,
    ) -> dict[str, object]:
        import json

        path = (
            self.repo_root
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / name
            / "snapshot.json"
        )

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)

    @staticmethod
    def set_all_report_statuses(
        snapshot: dict[str, object],
        status: str,
    ) -> None:
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise AssertionError(
                "reports não é objeto"
            )

        for report in reports.values():
            if not isinstance(report, dict):
                raise AssertionError(
                    "report não é objeto"
                )

            report["status"] = status

    @staticmethod
    def reports(
        snapshot: dict[str, object],
    ) -> list[dict[str, object]]:
        reports = snapshot["reports"]

        if not isinstance(reports, dict):
            raise AssertionError(
                "reports não é objeto"
            )

        result = []

        for report in reports.values():
            if not isinstance(report, dict):
                raise AssertionError(
                    "report não é objeto"
                )

            result.append(report)

        return result

    def test_health_aggregate_complete_all_ok_is_ok(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "OK",
        )

    def test_health_aggregate_complete_warning_is_warning(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        reports = self.reports(snapshot)
        reports[0]["status"] = "WARNING"

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "WARNING",
        )

    def test_health_aggregate_complete_unknown_is_unknown(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        reports = self.reports(snapshot)
        reports[0]["status"] = "UNKNOWN"

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "UNKNOWN",
        )

    def test_health_aggregate_complete_error_is_error(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        reports = self.reports(snapshot)
        reports[0]["status"] = "ERROR"

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "ERROR",
        )

    def test_health_aggregate_error_has_priority_over_warning(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        reports = self.reports(snapshot)

        self.assertGreaterEqual(
            len(reports),
            2,
        )

        reports[0]["status"] = "WARNING"
        reports[1]["status"] = "ERROR"

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "ERROR",
        )

    def test_health_aggregate_warning_has_priority_over_unknown(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        reports = self.reports(snapshot)

        self.assertGreaterEqual(
            len(reports),
            2,
        )

        reports[0]["status"] = "UNKNOWN"
        reports[1]["status"] = "WARNING"

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "WARNING",
        )

    def test_health_aggregate_partial_ok_cannot_be_ok(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.set_all_report_statuses(
            snapshot,
            "OK",
        )

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "UNKNOWN",
        )

    def test_health_aggregate_partial_warning_remains_overall_unknown(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.set_all_report_statuses(
            snapshot,
            "WARNING",
        )

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "UNKNOWN",
        )

    def test_health_aggregate_partial_error_is_error(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-partial"
        )

        self.set_all_report_statuses(
            snapshot,
            "ERROR",
        )

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            health["overall"]["status"],
            "ERROR",
        )

    def test_health_aggregate_has_exactly_six_domains(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        health = self.module.build_health(
            snapshot
        )

        self.assertEqual(
            set(health),
            {
                "overall",
                "system",
                "security",
                "resources",
                "connectivity",
                "services",
            },
        )

    def test_health_aggregate_every_domain_contains_status(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-complete"
        )

        health = self.module.build_health(
            snapshot
        )

        for domain in (
            "overall",
            "system",
            "security",
            "resources",
            "connectivity",
            "services",
        ):
            with self.subTest(
                domain=domain
            ):
                self.assertIsInstance(
                    health[domain],
                    dict,
                )

                self.assertIn(
                    "status",
                    health[domain],
                )

    def test_health_aggregate_specific_domains_use_validated_evaluators(
        self,
    ):
        from unittest.mock import patch

        snapshot = self.load_fixture(
            "valid-complete"
        )

        expected = {
            "system": "OK",
            "security": "WARNING",
            "resources": "ERROR",
            "connectivity": "UNKNOWN",
            "services": "OK",
        }

        with (
            patch.object(
                self.module,
                "evaluate_system_health",
                return_value=expected["system"],
            ),
            patch.object(
                self.module,
                "evaluate_security_health",
                return_value=expected["security"],
            ),
            patch.object(
                self.module,
                "evaluate_resources_health",
                return_value=expected["resources"],
            ),
            patch.object(
                self.module,
                "evaluate_connectivity_health",
                return_value=expected["connectivity"],
            ),
            patch.object(
                self.module,
                "evaluate_services_health",
                return_value=expected["services"],
            ),
        ):
            health = self.module.build_health(
                snapshot
            )

        for domain, status in expected.items():
            with self.subTest(
                domain=domain
            ):
                self.assertEqual(
                    health[domain]["status"],
                    status,
                )

    def test_health_aggregate_overall_matches_overall_evaluator(
        self,
    ):
        from unittest.mock import patch

        snapshot = self.load_fixture(
            "valid-complete"
        )

        with patch.object(
            self.module,
            "evaluate_overall_health",
            return_value="WARNING",
        ):
            health = self.module.build_health(
                snapshot
            )

        self.assertEqual(
            health["overall"]["status"],
            "WARNING",
        )

    def test_health_aggregate_rejects_failed_generation_defensively(
        self,
    ):
        snapshot = self.load_fixture(
            "valid-failed"
        )

        with self.assertRaises(
            self.module.DecisionFailure
        ):
            self.module.build_health(
                snapshot
            )



import copy as _v25_copy
import importlib.machinery as _v25_machinery
import importlib.util as _v25_util
import json as _v25_json
from pathlib import Path as _V25Path
from unittest import mock as _v25_mock


class DecisionEngineInterpretationV25Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = _V25Path(__file__).resolve().parents[1]

        target = (
            cls.root
            / "decision"
            / "decision-engine.py"
        )

        loader = _v25_machinery.SourceFileLoader(
            "decision_engine_interpretation_v25_target",
            str(target),
        )

        spec = _v25_util.spec_from_loader(
            loader.name,
            loader,
        )

        if spec is None:
            raise RuntimeError("não foi possível criar spec V25")

        module = _v25_util.module_from_spec(spec)
        loader.exec_module(module)

        cls.engine = module

        fixture_root = (
            cls.root
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
        )

        cls.complete_path = (
            fixture_root
            / "valid-complete"
            / "snapshot.json"
        )

        cls.partial_path = (
            fixture_root
            / "valid-partial"
            / "snapshot.json"
        )

        cls.failed_path = (
            fixture_root
            / "valid-failed"
            / "snapshot.json"
        )

    def _load(self, path):
        return _v25_json.loads(
            path.read_text(encoding="utf-8")
        )

    def _complete(self):
        snapshot = self._load(self.complete_path)

        for report in snapshot["reports"].values():
            report["status"] = "OK"

        return snapshot

    def _partial(self):
        return self._load(self.partial_path)

    def _failed(self):
        return self._load(self.failed_path)

    def _interpret(self, snapshot):
        health = self.engine.build_health(snapshot)

        return self.engine.build_interpretation(
            snapshot,
            health,
        )

    def _all_text(self, result):
        values = []

        for field in (
            "analysis",
            "summary",
            "conclusions",
            "recommendations",
            "warnings",
            "errors",
        ):
            values.extend(result[field])

        return "\n".join(values)

    def test_interpretation_complete_all_ok(self):
        snapshot = self._complete()
        result = self._interpret(snapshot)

        self.assertIn(
            "recommendations",
            result,
        )

        self.assertNotEqual(
            result["recommendations"],
            [],
        )

    def test_interpretation_complete_warning_preserved(self):
        snapshot = self._complete()
        snapshot["reports"]["observer-system"]["status"] = "WARNING"

        result = self._interpret(snapshot)

        self.assertIn(
            "WARNING",
            self._all_text(result),
        )

    def test_interpretation_complete_error_preserved(self):
        snapshot = self._complete()
        snapshot["reports"]["observer-system"]["status"] = "ERROR"

        result = self._interpret(snapshot)

        self.assertIn(
            "ERROR",
            self._all_text(result),
        )

    def test_interpretation_partial_without_error_overall_unknown(self):
        snapshot = self._partial()
        result = self._interpret(snapshot)

        self.assertIn(
            "UNKNOWN",
            self._all_text(result),
        )

    def test_interpretation_partial_error_remains_error(self):
        snapshot = self._partial()

        first_report = next(
            iter(snapshot["reports"].values())
        )
        first_report["status"] = "ERROR"

        result = self._interpret(snapshot)

        self.assertIn(
            "ERROR",
            self._all_text(result),
        )

    def test_interpretation_partial_identifies_failed_module(self):
        snapshot = self._partial()

        failed = next(
            item
            for item in snapshot["manifest"]["modules"]
            if item["outcome"] == "FAILED"
        )

        result = self._interpret(snapshot)

        self.assertIn(
            failed["module"],
            self._all_text(result),
        )

    def test_interpretation_partial_exposes_failure_codes(self):
        snapshot = self._partial()

        failed = next(
            item
            for item in snapshot["manifest"]["modules"]
            if item["outcome"] == "FAILED"
        )

        result = self._interpret(snapshot)
        text = self._all_text(result)

        self.assertIn(
            str(failed["error_code"]),
            text,
        )

        self.assertIn(
            str(failed["exit_code"]),
            text,
        )

    def test_interpretation_partial_states_observation_incomplete(self):
        snapshot = self._partial()
        result = self._interpret(snapshot)

        text = self._all_text(result).lower()

        self.assertTrue(
            "não foi integralmente observado" in text
            or "observação incompleta" in text
            or "observado parcialmente" in text
        )

    def test_interpretation_partial_identifies_unknown_health_domains(self):
        snapshot = self._partial()
        health = self.engine.build_health(snapshot)

        expected = {
            name
            for name, value in health.items()
            if value["status"] == "UNKNOWN"
        }

        result = self.engine.build_interpretation(
            snapshot,
            health,
        )

        text = self._all_text(result)

        for domain in expected:
            self.assertIn(
                domain,
                text,
            )

    def test_interpretation_missing_determinant_not_invented_as_normal(self):
        snapshot = self._partial()
        result = self._interpret(snapshot)

        text = self._all_text(result)

        self.assertNotIn(
            "Sistema base operacional.",
            text,
        )

    def test_interpretation_security_invalid_users_supplemental(self):
        snapshot = self._complete()

        facts = snapshot["reports"]["observer-ssh"]["facts"]
        facts["journal_available"] = True
        facts["failed_password_events_24h"] = 0
        facts["invalid_user_events_24h"] = 7

        result = self._interpret(snapshot)

        self.assertIn(
            "7",
            self._all_text(result),
        )

    def test_interpretation_security_missing_supplemental_not_invented(self):
        snapshot = self._complete()

        facts = snapshot["reports"]["observer-ssh"]["facts"]
        facts["journal_available"] = True
        facts["failed_password_events_24h"] = 0
        facts.pop(
            "invalid_user_events_24h",
            None,
        )

        result = self._interpret(snapshot)

        self.assertNotIn(
            "utilizadores inválidos",
            self._all_text(result).lower(),
        )

    def test_interpretation_security_publickey_supplemental(self):
        snapshot = self._complete()

        facts = snapshot["reports"]["observer-ssh"]["facts"]
        facts["journal_available"] = True
        facts["failed_password_events_24h"] = 0
        facts["accepted_publickey_events_24h"] = 3

        result = self._interpret(snapshot)

        self.assertIn(
            "chave pública",
            self._all_text(result).lower(),
        )

    def test_interpretation_services_only_explicit_active_conclusions(self):
        snapshot = self._complete()

        facts = snapshot["reports"]["observer-services"]["facts"]
        facts.update(
            {
                "ssh.service": "active",
                "tailscaled.service": "inactive",
                "fail2ban.service": "active",
                "AdGuardHome.service": "active",
            }
        )

        result = self._interpret(snapshot)
        text = self._all_text(result)

        self.assertIn(
            "SSH operacional",
            text,
        )

        self.assertNotIn(
            "Tailscale operacional",
            text,
        )

    def test_interpretation_text_arrays_have_no_empty_strings(self):
        snapshot = self._complete()
        result = self._interpret(snapshot)

        for field in (
            "analysis",
            "summary",
            "conclusions",
            "recommendations",
            "warnings",
            "errors",
        ):
            self.assertTrue(
                all(
                    isinstance(value, str)
                    and len(value) > 0
                    for value in result[field]
                )
            )

    def test_interpretation_text_arrays_have_unique_items(self):
        snapshot = self._complete()
        result = self._interpret(snapshot)

        for field in (
            "analysis",
            "summary",
            "conclusions",
            "recommendations",
            "warnings",
            "errors",
        ):
            self.assertEqual(
                len(result[field]),
                len(set(result[field])),
            )

    def test_interpretation_does_not_mutate_snapshot(self):
        snapshot = self._complete()
        before = _v25_copy.deepcopy(snapshot)

        self._interpret(snapshot)

        self.assertEqual(
            snapshot,
            before,
        )

    def test_interpretation_does_not_mutate_health(self):
        snapshot = self._complete()
        health = self.engine.build_health(snapshot)
        before = _v25_copy.deepcopy(health)

        self.engine.build_interpretation(
            snapshot,
            health,
        )

        self.assertEqual(
            health,
            before,
        )

    def test_interpretation_does_not_reopen_generation_files(self):
        snapshot = self._complete()
        health = self.engine.build_health(snapshot)

        with _v25_mock.patch(
            "builtins.open",
            side_effect=AssertionError(
                "interpretação tentou abrir ficheiro"
            ),
        ):
            self.engine.build_interpretation(
                snapshot,
                health,
            )

    def test_interpretation_is_deterministic_from_snapshot_and_health(self):
        snapshot = self._complete()
        health = self.engine.build_health(snapshot)

        first = self.engine.build_interpretation(
            _v25_copy.deepcopy(snapshot),
            _v25_copy.deepcopy(health),
        )

        second = self.engine.build_interpretation(
            _v25_copy.deepcopy(snapshot),
            _v25_copy.deepcopy(health),
        )

        self.assertEqual(
            first,
            second,
        )


    def test_interpretation_partial_exposes_generation_identity_and_state(self):
        snapshot = self._partial()

        result = self._interpret(snapshot)
        text = self._all_text(result)

        self.assertIn(
            snapshot["generation_id"],
            text,
        )

        self.assertIn(
            "PARTIAL",
            text,
        )

    def test_interpretation_partial_exposes_exact_coverage_counters(self):
        snapshot = self._partial()

        modules = snapshot["manifest"]["modules"]

        declared = len(modules)

        successful = sum(
            1
            for item in modules
            if item["outcome"] == "SUCCESS"
        )

        failed = sum(
            1
            for item in modules
            if item["outcome"] == "FAILED"
        )

        result = self._interpret(snapshot)
        text = self._all_text(result)

        self.assertIn(
            str(declared),
            text,
        )

        self.assertIn(
            f"sucesso={successful}",
            text,
        )

        self.assertIn(
            f"falha={failed}",
            text,
        )

    def test_interpretation_partial_exposes_unavailable_facts_and_conclusions(self):
        snapshot = self._partial()

        result = self._interpret(snapshot)
        text = self._all_text(result).lower()

        self.assertIn(
            "factos",
            text,
        )

        self.assertIn(
            "conclusões",
            text,
        )

        self.assertTrue(
            (
                "não puderam ser produzidos" in text
                or "não puderam ser produzidas" in text
                or "indisponíveis" in text
                or "insuficientes" in text
            ),
            text,
        )

    def test_interpretation_missing_gateway_does_not_invent_gateway_value(self):
        snapshot = self._complete()

        network = snapshot["reports"]["observer-network"]
        facts = network["facts"]

        facts.pop(
            "default_gateway",
            None,
        )

        facts.pop(
            "gateway",
            None,
        )

        health = self.engine.build_health(snapshot)

        result = self.engine.build_interpretation(
            snapshot,
            health,
        )

        text = self._all_text(result).lower()

        self.assertNotIn(
            "gateway desconhecido",
            text,
        )

        self.assertNotIn(
            "gateway: desconhecido",
            text,
        )

        self.assertNotIn(
            "gateway=desconhecido",
            text,
        )

    def test_interpretation_complete_unknown_does_not_recommend_all_ok(self):
        snapshot = self._complete()

        health = self.engine.build_health(snapshot)

        health["overall"]["status"] = "UNKNOWN"

        result = self.engine.build_interpretation(
            snapshot,
            health,
        )

        recommendations = "\n".join(
            result["recommendations"]
        ).lower()

        self.assertNotIn(
            "todos os observers estão em estado ok",
            recommendations,
        )

        self.assertNotIn(
            "nenhuma ação recomendada",
            recommendations,
        )

    def test_interpretation_partial_preserves_known_warning_when_overall_unknown(self):
        snapshot = self._partial()

        successful_module = next(
            item
            for item in snapshot["manifest"]["modules"]
            if item["outcome"] == "SUCCESS"
        )

        module_name = successful_module["module"]

        report = snapshot["reports"][module_name]
        report["status"] = "WARNING"

        health = self.engine.build_health(snapshot)

        self.assertEqual(
            health["overall"]["status"],
            "UNKNOWN",
        )

        result = self.engine.build_interpretation(
            snapshot,
            health,
        )

        warnings = "\n".join(
            result["warnings"]
        )

        self.assertIn(
            module_name,
            warnings,
        )

        self.assertIn(
            "WARNING",
            warnings,
        )


class DecisionEngineFinalReportV27Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = _V25Path(__file__).resolve().parents[1]

        target = (
            cls.root
            / "decision"
            / "decision-engine.py"
        )

        loader = _v25_machinery.SourceFileLoader(
            "decision_engine_final_report_v27_target",
            str(target),
        )

        spec = _v25_util.spec_from_loader(
            loader.name,
            loader,
        )

        if spec is None:
            raise RuntimeError(
                "não foi possível criar spec V27"
            )

        module = _v25_util.module_from_spec(spec)
        loader.exec_module(module)

        cls.engine = module

        cls.complete_path = (
            cls.root
            / "tests"
            / "fixtures"
            / "validated-generation-snapshot-1.0.0"
            / "valid-complete"
            / "snapshot.json"
        )

        cls.timestamp = "2026-09-12T00:45:00+0100"

    def _complete(self):
        snapshot = _v25_json.loads(
            self.complete_path.read_text(
                encoding="utf-8"
            )
        )

        for report in snapshot["reports"].values():
            report["status"] = "OK"

        return snapshot

    def _inputs(self):
        snapshot = self._complete()

        health = self.engine.build_health(
            snapshot
        )

        interpretation = (
            self.engine.build_interpretation(
                snapshot,
                health,
            )
        )

        return (
            snapshot,
            health,
            interpretation,
        )

    def _build(self):
        (
            snapshot,
            health,
            interpretation,
        ) = self._inputs()

        report = self.engine.build_final_report(
            snapshot,
            health,
            interpretation,
            self.timestamp,
        )

        return (
            snapshot,
            health,
            interpretation,
            report,
        )

    def test_final_report_has_exact_top_level_contract(self):
        *_, report = self._build()

        self.assertEqual(
            set(report),
            {
                "module",
                "version",
                "timestamp",
                "status",
                "confidence",
                "facts",
                "analysis",
                "conclusions",
                "health",
                "summary",
                "recommendations",
                "warnings",
                "errors",
            },
        )

    def test_final_report_metadata_is_explicit(self):
        *_, report = self._build()

        self.assertEqual(
            report["module"],
            "decision-engine",
        )

        self.assertEqual(
            report["version"],
            "3.0.0",
        )

        self.assertEqual(
            report["timestamp"],
            self.timestamp,
        )

    def test_final_report_status_uses_health_authority(self):
        (
            snapshot,
            health,
            interpretation,
        ) = self._inputs()

        report = self.engine.build_final_report(
            snapshot,
            health,
            interpretation,
            self.timestamp,
        )

        self.assertEqual(
            report["status"],
            health["overall"]["status"],
        )

    def test_final_report_complete_preserves_23_counter_facts(self):
        *_, report = self._build()

        self.assertEqual(
            report["confidence"],
            100,
        )

        self.assertEqual(
            report["facts"]["observer_reports"],
            7,
        )

        self.assertEqual(
            report["facts"]["ok"],
            7,
        )

        self.assertEqual(
            report["facts"]["warning"],
            0,
        )

        self.assertEqual(
            report["facts"]["error"],
            0,
        )

        self.assertEqual(
            report["facts"]["unknown"],
            0,
        )

    def test_final_report_copies_health_and_interpretation(self):
        (
            _snapshot,
            health,
            interpretation,
            report,
        ) = self._build()

        self.assertEqual(
            report["health"],
            health,
        )

        for field in (
            "analysis",
            "conclusions",
            "summary",
            "recommendations",
            "warnings",
            "errors",
        ):
            self.assertEqual(
                report[field],
                interpretation[field],
            )

    def test_final_report_does_not_mutate_inputs(self):
        (
            snapshot,
            health,
            interpretation,
        ) = self._inputs()

        before_snapshot = _v25_copy.deepcopy(
            snapshot
        )
        before_health = _v25_copy.deepcopy(
            health
        )
        before_interpretation = _v25_copy.deepcopy(
            interpretation
        )

        self.engine.build_final_report(
            snapshot,
            health,
            interpretation,
            self.timestamp,
        )

        self.assertEqual(
            snapshot,
            before_snapshot,
        )

        self.assertEqual(
            health,
            before_health,
        )

        self.assertEqual(
            interpretation,
            before_interpretation,
        )

    def test_final_report_does_not_perform_external_io(self):
        (
            snapshot,
            health,
            interpretation,
        ) = self._inputs()

        with (
            _v25_mock.patch(
                "builtins.open",
                side_effect=AssertionError(
                    "build_final_report tentou abrir ficheiro"
                ),
            ),
            _v25_mock.patch.object(
                self.engine.os,
                "open",
                side_effect=AssertionError(
                    "build_final_report tentou os.open"
                ),
            ),
            _v25_mock.patch.object(
                self.engine.subprocess,
                "Popen",
                side_effect=AssertionError(
                    "build_final_report tentou subprocesso"
                ),
            ),
            _v25_mock.patch.object(
                self.engine.subprocess,
                "run",
                side_effect=AssertionError(
                    "build_final_report tentou subprocess.run"
                ),
            ),
        ):
            self.engine.build_final_report(
                snapshot,
                health,
                interpretation,
                self.timestamp,
            )

    def test_final_report_is_deterministic_for_identical_inputs(self):
        (
            snapshot,
            health,
            interpretation,
        ) = self._inputs()

        first = self.engine.build_final_report(
            _v25_copy.deepcopy(snapshot),
            _v25_copy.deepcopy(health),
            _v25_copy.deepcopy(interpretation),
            self.timestamp,
        )

        second = self.engine.build_final_report(
            _v25_copy.deepcopy(snapshot),
            _v25_copy.deepcopy(health),
            _v25_copy.deepcopy(interpretation),
            self.timestamp,
        )

        self.assertEqual(
            first,
            second,
        )


import io as _v28_io
import json as _v28_json


class DecisionEngineFinalOutputV28Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = _V25Path(__file__).resolve().parents[1]

        target = (
            cls.root
            / "decision"
            / "decision-engine.py"
        )

        loader = _v25_machinery.SourceFileLoader(
            "decision_engine_final_output_v28_target",
            str(target),
        )

        spec = _v25_util.spec_from_loader(
            loader.name,
            loader,
        )

        if spec is None:
            raise RuntimeError(
                "não foi possível criar spec V28"
            )

        module = _v25_util.module_from_spec(spec)
        loader.exec_module(module)

        cls.engine = module

    def _valid_report(self):
        return {
            "module": "decision-engine",
            "version": "3.0.0",
            "timestamp": "2026-09-13T03:00:00+0100",
            "status": "OK",
            "confidence": 100,
            "facts": {},
            "analysis": [],
            "conclusions": [],
            "health": {
                "overall": {"status": "OK"},
                "system": {"status": "OK"},
                "security": {"status": "OK"},
                "resources": {"status": "OK"},
                "connectivity": {"status": "OK"},
                "services": {"status": "OK"},
            },
            "summary": [],
            "recommendations": [],
            "warnings": [],
            "errors": [],
        }

    def test_main_executes_complete_validated_pipeline_and_emits_once(self):
        snapshot = {"state": "COMPLETE"}
        health = {"overall": {"status": "OK"}}
        interpretation = {
            "analysis": [],
            "conclusions": [],
            "summary": [],
            "recommendations": [],
            "warnings": [],
            "errors": [],
        }
        report = self._valid_report()

        stdout = _v28_io.StringIO()
        stderr = _v28_io.StringIO()

        with (
            _v25_mock.patch.object(
                self.engine,
                "parse_arguments",
                return_value=SimpleNamespace(
                    state_root="/state"
                ),
            ),
            _v25_mock.patch.object(
                self.engine,
                "resolve_input",
                return_value=(
                    _V25Path("/state"),
                    "20260913T020000000000Z-"
                    "0123456789abcdef0123456789abcdef",
                    _V25Path("/generation"),
                ),
            ),
            _v25_mock.patch.object(
                self.engine,
                "obtain_validated_snapshot",
                return_value=snapshot,
            ) as obtain,
            _v25_mock.patch.object(
                self.engine,
                "build_health",
                return_value=health,
            ) as build_health,
            _v25_mock.patch.object(
                self.engine,
                "build_interpretation",
                return_value=interpretation,
            ) as build_interpretation,
            _v25_mock.patch.object(
                self.engine,
                "build_final_report",
                return_value=report,
            ) as build_report,
            _v25_mock.patch.object(
                self.engine.sys,
                "stdout",
                stdout,
            ),
            _v25_mock.patch.object(
                self.engine.sys,
                "stderr",
                stderr,
            ),
        ):
            rc = self.engine.main(
                ["--state-root", "/state"]
            )

        self.assertEqual(rc, 0)

        obtain.assert_called_once()
        build_health.assert_called_once_with(snapshot)
        build_interpretation.assert_called_once_with(
            snapshot,
            health,
        )
        build_report.assert_called_once()

        timestamp = build_report.call_args.args[3]

        self.assertRegex(
            timestamp,
            (
                r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"[+-][0-9]{4}$"
            ),
        )

        expected = (
            _v28_json.dumps(
                report,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        self.assertEqual(
            stdout.getvalue(),
            expected,
        )

    def test_main_rejects_invalid_final_report_without_stdout(self):
        stdout = _v28_io.StringIO()
        stderr = _v28_io.StringIO()

        with (
            _v25_mock.patch.object(
                self.engine,
                "parse_arguments",
                return_value=SimpleNamespace(
                    state_root="/state"
                ),
            ),
            _v25_mock.patch.object(
                self.engine,
                "resolve_input",
                return_value=(
                    _V25Path("/state"),
                    "20260913T020000000000Z-"
                    "0123456789abcdef0123456789abcdef",
                    _V25Path("/generation"),
                ),
            ),
            _v25_mock.patch.object(
                self.engine,
                "obtain_validated_snapshot",
                return_value={"state": "COMPLETE"},
            ),
            _v25_mock.patch.object(
                self.engine,
                "build_health",
                return_value={
                    "overall": {"status": "OK"}
                },
            ),
            _v25_mock.patch.object(
                self.engine,
                "build_interpretation",
                return_value={
                    "analysis": [],
                    "conclusions": [],
                    "summary": [],
                    "recommendations": [],
                    "warnings": [],
                    "errors": [],
                },
            ),
            _v25_mock.patch.object(
                self.engine,
                "build_final_report",
                return_value={
                    "module": "decision-engine"
                },
            ),
            _v25_mock.patch.object(
                self.engine.sys,
                "stdout",
                stdout,
            ),
            _v25_mock.patch.object(
                self.engine.sys,
                "stderr",
                stderr,
            ),
        ):
            rc = self.engine.main(
                ["--state-root", "/state"]
            )

        self.assertNotEqual(rc, 0)
        self.assertEqual(
            stdout.getvalue(),
            "",
        )

class DecisionEngineResourcesStringLoadV29Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = (
            ROOT
            / "decision"
            / "decision-engine.py"
        )

        loader = _v25_machinery.SourceFileLoader(
            "decision_engine_resources_string_load_v29",
            str(target),
        )

        spec = _v25_util.spec_from_loader(
            loader.name,
            loader,
        )

        module = _v25_util.module_from_spec(spec)
        loader.exec_module(module)
        cls.module = module

    def test_resources_accepts_observer_cpu_decimal_string_load(self):
        snapshot = {
            "manifest": {
                "modules": [
                    {
                        "module": "observer-cpu",
                        "outcome": "SUCCESS",
                    },
                    {
                        "module": "observer-memory",
                        "outcome": "SUCCESS",
                    },
                ],
            },
            "reports": {
                "observer-cpu": {
                    "status": "OK",
                    "facts": {
                        "cpu_count": 4,
                        "load_15min": "0.62",
                    },
                },
                "observer-memory": {
                    "status": "OK",
                    "facts": {
                        "memory": {
                            "MemTotal": 8050000,
                            "MemAvailable": 6002828,
                            "SwapTotal": 4194300,
                            "SwapFree": 4194300,
                        },
                    },
                },
            },
        }

        self.assertEqual(
            self.module.evaluate_resources_health(snapshot),
            "OK",
        )


if __name__ == "__main__":
    unittest.main()
