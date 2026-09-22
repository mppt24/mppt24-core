#!/usr/bin/python3 -I
"""Testes contratuais do Runner MPPT24 2.0.0."""

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
RUNNER_NEW = (
    ROOT
    / "runner"
    / "observer-runner.py"
)


def load_runner():
    module_name = "mppt24_observer_runner_test"
    loader = (
        importlib.machinery.SourceFileLoader(
            module_name,
            str(RUNNER_NEW),
        )
    )
    specification = (
        importlib.util.spec_from_loader(
            module_name,
            loader,
        )
    )

    if specification is None:
        raise RuntimeError(
            "Runner não carregável"
        )

    module = importlib.util.module_from_spec(
        specification
    )
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


runner_module = load_runner()


class ObserverRunnerContractTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary_path = Path(
            tempfile.mkdtemp(
                prefix="mppt24-runner-contract-"
            )
        )

    def tearDown(self) -> None:
        shutil.rmtree(
            self.temporary_path,
            ignore_errors=False,
        )

    def test_contract_constants(self) -> None:
        self.assertEqual(
            runner_module.RUNNER_MODULE,
            "observer-runner",
        )
        self.assertEqual(
            runner_module.RUNNER_VERSION,
            "2.0.0",
        )
        self.assertEqual(
            runner_module.TOTAL_CYCLE_TIMEOUT_SECONDS,
            1200,
        )
        self.assertEqual(
            runner_module.MINIMUM_FREE_BYTES,
            16777216,
        )
        self.assertEqual(
            runner_module.EXTERNAL_TERMINATION_GRACE_SECONDS,
            1.0,
        )

    def test_valid_arguments(self) -> None:
        arguments = (
            runner_module.parse_arguments(
                [
                    "--state-root",
                    "/state",
                    "--runtime-root",
                    "/runtime",
                ]
            )
        )

        self.assertEqual(
            arguments.state_root,
            "/state",
        )
        self.assertEqual(
            arguments.runtime_root,
            "/runtime",
        )

    def assert_usage_failure(
        self,
        arguments: list[str],
    ) -> None:
        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.parse_arguments(
                arguments
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_USAGE,
        )
        self.assertEqual(
            captured.exception.code,
            "USAGE_INVALID",
        )

    def test_missing_arguments(self) -> None:
        self.assert_usage_failure([])

    def test_unknown_argument(self) -> None:
        self.assert_usage_failure(
            [
                "--state-root",
                "/state",
                "--runtime-root",
                "/runtime",
                "--unknown",
            ]
        )

    def test_repeated_option(self) -> None:
        self.assert_usage_failure(
            [
                "--state-root",
                "/state",
                "--state-root",
                "/other",
                "--runtime-root",
                "/runtime",
            ]
        )

    def test_additional_positional_argument(
        self,
    ) -> None:
        self.assert_usage_failure(
            [
                "--state-root",
                "/state",
                "--runtime-root",
                "/runtime",
                "additional",
            ]
        )

    def test_help(self) -> None:
        output = io.StringIO()

        with (
            contextlib.redirect_stdout(output),
            self.assertRaises(SystemExit)
            as captured,
        ):
            runner_module.parse_arguments(
                ["--help"]
            )

        self.assertEqual(
            captured.exception.code,
            0,
        )
        self.assertIn(
            "--state-root",
            output.getvalue(),
        )
        self.assertIn(
            "--runtime-root",
            output.getvalue(),
        )

    def parse_json(
        self,
        content: bytes,
        maximum_depth: int = 8,
    ):
        return runner_module.parse_json_strict(
            content,
            role="test",
            maximum_depth=maximum_depth,
            exit_code=7,
            failure_code="STRUCTURAL_FAILURE",
        )

    def assert_json_rejected(
        self,
        content: bytes,
        maximum_depth: int = 8,
    ) -> None:
        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.parse_json(
                content,
                maximum_depth,
            )

    def test_valid_strict_json(self) -> None:
        self.assertEqual(
            self.parse_json(
                b'{"value":[1,2,3]}'
            ),
            {
                "value": [
                    1,
                    2,
                    3,
                ]
            },
        )

    def test_duplicate_json_key(self) -> None:
        self.assert_json_rejected(
            b'{"value":1,"value":2}'
        )

    def test_non_finite_json_number(
        self,
    ) -> None:
        self.assert_json_rejected(
            b'{"value":NaN}'
        )

    def test_invalid_utf8(self) -> None:
        self.assert_json_rejected(
            b'{"value":"\xff"}'
        )

    def test_additional_json_document(
        self,
    ) -> None:
        self.assert_json_rejected(
            b'{} {}'
        )

    def test_json_depth_limit(self) -> None:
        self.assert_json_rejected(
            b'[[[[[0]]]]]',
            maximum_depth=4,
        )

    def write_secure_file(
        self,
        name: str,
        content: bytes = b"content\n",
    ) -> Path:
        path = self.temporary_path / name
        path.write_bytes(content)
        path.chmod(0o640)
        return path

    def secure_read(
        self,
        path: Path,
        maximum_bytes: int = 1024,
    ):
        return runner_module.secure_read_file(
            path,
            maximum_bytes,
            role="test",
            exit_code=7,
            missing_code="STRUCTURAL_FAILURE",
            unsafe_code="STRUCTURAL_FAILURE",
        )

    def test_secure_read_success(self) -> None:
        path = self.write_secure_file(
            "document.json"
        )
        secure = self.secure_read(path)

        self.assertEqual(
            secure.content,
            b"content\n",
        )
        self.assertEqual(
            secure.size,
            8,
        )

    def test_secure_read_missing(self) -> None:
        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.secure_read(
                self.temporary_path
                / "missing.json"
            )

    def test_secure_read_symbolic_link(
        self,
    ) -> None:
        target = self.write_secure_file(
            "target.json"
        )
        symbolic = (
            self.temporary_path
            / "symbolic.json"
        )
        symbolic.symlink_to(target)

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.secure_read(symbolic)

    def test_secure_read_hard_link(
        self,
    ) -> None:
        target = self.write_secure_file(
            "target.json"
        )
        hard_link = (
            self.temporary_path
            / "hard-link.json"
        )
        os.link(
            target,
            hard_link,
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.secure_read(target)

    def test_secure_read_size_limit(
        self,
    ) -> None:
        path = self.write_secure_file(
            "large.json",
            b"x" * 17,
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.secure_read(
                path,
                maximum_bytes=16,
            )

    def test_revalidate_secure_file(
        self,
    ) -> None:
        path = self.write_secure_file(
            "document.json"
        )
        secure = self.secure_read(path)
        path.write_bytes(
            b"changed-content\n"
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.revalidate_secure_file(
                path,
                secure,
                role="test",
                exit_code=7,
                failure_code=(
                    "STRUCTURAL_FAILURE"
                ),
            )

    def test_import_has_no_side_effects(
        self,
    ) -> None:
        script = r'''
import importlib.machinery
import importlib.util
import sys

sys.dont_write_bytecode = True

name = "mppt24_runner_import_check"
path = sys.argv[1]
loader = importlib.machinery.SourceFileLoader(
    name,
    path,
)
specification = importlib.util.spec_from_loader(
    name,
    loader,
)

if specification is None:
    raise SystemExit(2)

module = importlib.util.module_from_spec(
    specification
)
sys.modules[name] = module
loader.exec_module(module)
'''
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-",
                str(RUNNER_NEW),
            ],
            input=script,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr,
        )
        self.assertEqual(
            result.stdout,
            "",
        )
        self.assertEqual(
            result.stderr,
            "",
        )



    def test_external_schema_reference(
        self,
    ) -> None:
        document = {
            "$ref": "https://example.invalid/schema"
        }

        self.assertEqual(
            runner_module.external_references(
                document
            ),
            [
                "https://example.invalid/schema"
            ],
        )

    def test_internal_schema_reference(
        self,
    ) -> None:
        document = {
            "$ref": "#/$defs/value"
        }

        self.assertEqual(
            runner_module.external_references(
                document
            ),
            [],
        )

    def test_load_official_configuration(
        self,
    ) -> None:
        context = (
            runner_module.load_configuration(
                ROOT
            )
        )

        self.assertEqual(
            context.registry.document[
                "registry_version"
            ],
            "1.0.0",
        )
        self.assertEqual(
            len(
                context.registry.document[
                    "observers"
                ]
            ),
            7,
        )
        self.assertEqual(
            len(context.registry.sha256),
            64,
        )

        runner_module.revalidate_configuration(
            context
        )

    def test_registry_duplicate_module(
        self,
    ) -> None:
        context = (
            runner_module.load_configuration(
                ROOT
            )
        )
        document = json.loads(
            json.dumps(
                context.registry.document
            )
        )
        document["observers"][1]["module"] = (
            document["observers"][0]["module"]
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.validate_registry_semantics(
                document
            )

    def test_registry_zero_modules(
        self,
    ) -> None:
        context = (
            runner_module.load_configuration(
                ROOT
            )
        )
        document = json.loads(
            json.dumps(
                context.registry.document
            )
        )
        document["observers"] = []

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.validate_registry_semantics(
                document
            )



    def make_roots(
        self,
    ) -> tuple[Path, Path]:
        state = self.temporary_path / "state"
        runtime = self.temporary_path / "runtime"

        state.mkdir(mode=0o750)
        runtime.mkdir(mode=0o750)
        (
            state
            / "generations"
        ).mkdir(mode=0o750)

        return state, runtime

    def test_valid_roots(self) -> None:
        state, runtime = self.make_roots()
        context = runner_module.validate_roots(
            str(state),
            str(runtime),
        )

        self.assertEqual(
            context.state.path,
            state,
        )
        self.assertIsNone(
            context.reference
        )
        runner_module.revalidate_roots(
            context
        )

    def assert_roots_rejected(
        self,
        state: Path | str,
        runtime: Path | str,
    ) -> None:
        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.validate_roots(
                str(state),
                str(runtime),
            )

    def test_relative_state_root(self) -> None:
        _state, runtime = self.make_roots()
        self.assert_roots_rejected(
            "relative-state",
            runtime,
        )

    def test_same_roots(self) -> None:
        state, _runtime = self.make_roots()
        self.assert_roots_rejected(
            state,
            state,
        )

    def test_nested_roots(self) -> None:
        state, _runtime = self.make_roots()
        runtime = state / "runtime"
        runtime.mkdir(mode=0o750)

        self.assert_roots_rejected(
            state,
            runtime,
        )

    def test_state_root_symbolic_link(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        symbolic = (
            self.temporary_path
            / "state-link"
        )
        symbolic.symlink_to(
            state,
            target_is_directory=True,
        )

        self.assert_roots_rejected(
            symbolic,
            runtime,
        )

    def test_unknown_state_object(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        (
            state
            / "unknown"
        ).write_text(
            "unknown\n",
            encoding="utf-8",
        )

        self.assert_roots_rejected(
            state,
            runtime,
        )

    def test_missing_generations(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        (
            state
            / "generations"
        ).rmdir()

        self.assert_roots_rejected(
            state,
            runtime,
        )

    def test_root_permissions_excessive(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        state.chmod(0o751)

        self.assert_roots_rejected(
            state,
            runtime,
        )

    def test_valid_current_reference(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        generation_id = (
            "20260818T010203123456Z-"
            "0123456789abcdef0123456789abcdef"
        )
        generation = (
            state
            / "generations"
            / generation_id
        )
        generation.mkdir(mode=0o550)
        reference = (
            state
            / "current-generation"
        )
        reference.write_text(
            generation_id + "\n",
            encoding="utf-8",
        )
        reference.chmod(0o640)

        context = runner_module.validate_roots(
            str(state),
            str(runtime),
        )

        self.assertEqual(
            context.reference.generation_id,
            generation_id,
        )

    def test_current_reference_missing_target(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        generation_id = (
            "20260818T010203123456Z-"
            "0123456789abcdef0123456789abcdef"
        )
        reference = (
            state
            / "current-generation"
        )
        reference.write_text(
            generation_id + "\n",
            encoding="utf-8",
        )
        reference.chmod(0o640)

        self.assert_roots_rejected(
            state,
            runtime,
        )



    def test_lock_acquisition(self) -> None:
        state, runtime = self.make_roots()
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )
        lock = runner_module.acquire_lock(
            roots.runtime
        )

        try:
            self.assertTrue(lock.locked)
            runner_module.revalidate_lock(
                lock
            )
            lock_status = os.lstat(
                runtime
                / runner_module.LOCK_FILE_NAME
            )
            self.assertEqual(
                stat.S_IMODE(
                    lock_status.st_mode
                ),
                0o640,
            )
        finally:
            runner_module.release_lock(
                lock
            )

        self.assertTrue(
            (
                runtime
                / runner_module.LOCK_FILE_NAME
            ).is_file()
        )

    def test_lock_busy(self) -> None:
        state, runtime = self.make_roots()
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )
        first = runner_module.acquire_lock(
            roots.runtime
        )

        try:
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                runner_module.acquire_lock(
                    roots.runtime
                )

            self.assertEqual(
                captured.exception.exit_code,
                runner_module.EXIT_LOCK_BUSY,
            )
            self.assertEqual(
                captured.exception.code,
                "LOCK_BUSY",
            )
        finally:
            runner_module.release_lock(
                first
            )

    def test_lock_symbolic_link(self) -> None:
        state, runtime = self.make_roots()
        external = (
            self.temporary_path
            / "external-lock"
        )
        external.write_bytes(b"")
        external.chmod(0o640)
        (
            runtime
            / runner_module.LOCK_FILE_NAME
        ).symlink_to(external)
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.acquire_lock(
                roots.runtime
            )

    def test_lock_hard_link(self) -> None:
        state, runtime = self.make_roots()
        lock_path = (
            runtime
            / runner_module.LOCK_FILE_NAME
        )
        lock_path.write_bytes(b"")
        lock_path.chmod(0o640)
        os.link(
            lock_path,
            self.temporary_path
            / "lock-hard-link",
        )
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.acquire_lock(
                roots.runtime
            )

    def test_lock_is_directory(self) -> None:
        state, runtime = self.make_roots()
        (
            runtime
            / runner_module.LOCK_FILE_NAME
        ).mkdir(mode=0o750)
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.acquire_lock(
                roots.runtime
            )

    def test_release_lock_is_idempotent(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )
        lock = runner_module.acquire_lock(
            roots.runtime
        )

        runner_module.release_lock(lock)
        runner_module.release_lock(lock)

        self.assertFalse(lock.locked)



    def test_lock_creation_race(
        self,
    ) -> None:
        state, runtime = self.make_roots()
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )
        lock_path = (
            runtime
            / runner_module.LOCK_FILE_NAME
        )
        original_lstat = os.lstat
        race_created = False

        def racing_lstat(path):
            nonlocal race_created

            if (
                Path(path) == lock_path
                and not race_created
            ):
                race_created = True
                lock_path.write_bytes(b"")
                lock_path.chmod(0o640)
                raise FileNotFoundError(
                    runner_module.errno.ENOENT,
                    "simulated creation race",
                    str(lock_path),
                )

            return original_lstat(path)

        with mock.patch.object(
            runner_module.os,
            "lstat",
            side_effect=racing_lstat,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                runner_module.acquire_lock(
                    roots.runtime
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_CONFIGURATION,
        )
        self.assertEqual(
            captured.exception.code,
            "CONFIGURATION_INVALID",
        )
        self.assertTrue(lock_path.is_file())
        self.assertEqual(
            stat.S_IMODE(
                original_lstat(
                    lock_path
                ).st_mode
            ),
            0o640,
        )

        lock_path.unlink()



    def test_cycle_identity(self) -> None:
        state = runner_module.InvocationState()

        with mock.patch.object(
            runner_module.secrets,
            "token_hex",
            return_value="a" * 32,
        ) as token_hex:
            cycle = (
                runner_module
                .create_cycle_identity(
                    state
                )
            )

        token_hex.assert_called_once_with(16)
        self.assertRegex(
            cycle.generation_id,
            (
                r"^[0-9]{8}T"
                r"[0-9]{12}Z-"
                r"a{32}$"
            ),
        )
        self.assertEqual(
            runner_module
            .parse_generation_identifier(
                cycle.generation_id
            ),
            cycle.started_datetime,
        )
        self.assertEqual(
            cycle.started_at,
            runner_module
            .format_manifest_timestamp(
                cycle.started_datetime
            ),
        )
        self.assertTrue(
            state.facts.cycle_started
        )
        self.assertEqual(
            state.facts.generation_id,
            cycle.generation_id,
        )

    def test_cycle_identity_is_single_use(
        self,
    ) -> None:
        state = runner_module.InvocationState()

        runner_module.create_cycle_identity(
            state
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.create_cycle_identity(
                state
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_cycle_entropy_is_128_bits(
        self,
    ) -> None:
        state = runner_module.InvocationState()

        with mock.patch.object(
            runner_module.secrets,
            "token_hex",
            return_value="b" * 32,
        ) as token_hex:
            cycle = (
                runner_module
                .create_cycle_identity(
                    state
                )
            )

        token_hex.assert_called_once_with(16)
        self.assertEqual(
            cycle.generation_id.rsplit(
                "-",
                1,
            )[1],
            "b" * 32,
        )



    def test_free_space_available(
        self,
    ) -> None:
        filesystem = mock.Mock(
            f_bavail=4096,
            f_frsize=4096,
        )

        with mock.patch.object(
            runner_module.os,
            "statvfs",
            return_value=filesystem,
        ) as statvfs:
            available = (
                runner_module
                .ensure_minimum_free_space(
                    self.temporary_path,
                    role="test",
                )
            )

        statvfs.assert_called_once_with(
            self.temporary_path
        )
        self.assertEqual(
            available,
            runner_module.MINIMUM_FREE_BYTES,
        )

    def test_free_space_insufficient(
        self,
    ) -> None:
        filesystem = mock.Mock(
            f_bavail=4095,
            f_frsize=4096,
        )

        with mock.patch.object(
            runner_module.os,
            "statvfs",
            return_value=filesystem,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .ensure_minimum_free_space(
                        self.temporary_path,
                        role="test",
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_free_space_unavailable(
        self,
    ) -> None:
        with mock.patch.object(
            runner_module.os,
            "statvfs",
            side_effect=OSError(
                "simulated statvfs failure"
            ),
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .ensure_minimum_free_space(
                        self.temporary_path,
                        role="test",
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )



    def test_transient_directory_creation(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "transient"
        )
        context = (
            runner_module
            .create_transient_directory(
                path,
                role="test",
            )
        )

        status_result = os.lstat(path)

        self.assertTrue(
            stat.S_ISDIR(
                status_result.st_mode
            )
        )
        self.assertEqual(
            stat.S_IMODE(
                status_result.st_mode
            ),
            0o750,
        )
        self.assertEqual(
            context.identity,
            runner_module.path_identity(
                status_result
            ),
        )

        runner_module.revalidate_directory(
            context,
            role="test",
            maximum_mode=(
                runner_module.STAGING_MODE
            ),
        )
        (
            runner_module
            .cleanup_empty_transient_directory(
                context,
                role="test",
            )
        )

        self.assertFalse(path.exists())

    def test_transient_directory_collision(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "transient"
        )
        path.mkdir(mode=0o750)

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            (
                runner_module
                .create_transient_directory(
                    path,
                    role="test",
                )
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(path.is_dir())

    def test_transient_directory_nonempty_cleanup(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "transient"
        )
        context = (
            runner_module
            .create_transient_directory(
                path,
                role="test",
            )
        )
        marker = path / "marker"
        marker.write_bytes(b"preserve\n")

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            (
                runner_module
                .cleanup_empty_transient_directory(
                    context,
                    role="test",
                )
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(path.is_dir())
        self.assertEqual(
            marker.read_bytes(),
            b"preserve\n",
        )



    def test_transient_directory_identity_change(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "transient"
        )
        preserved = (
            self.temporary_path
            / "preserved-transient"
        )
        context = (
            runner_module
            .create_transient_directory(
                path,
                role="test",
            )
        )

        path.rename(preserved)
        path.mkdir(mode=0o750)

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            (
                runner_module
                .cleanup_empty_transient_directory(
                    context,
                    role="test",
                )
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(path.is_dir())
        self.assertTrue(preserved.is_dir())
        self.assertNotEqual(
            runner_module.path_identity(
                os.lstat(path)
            ),
            runner_module.path_identity(
                os.lstat(preserved)
            ),
        )

    def test_transient_directory_chmod_failure_cleanup(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "transient"
        )

        with mock.patch.object(
            runner_module.os,
            "chmod",
            side_effect=OSError(
                "simulated chmod failure"
            ),
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .create_transient_directory(
                        path,
                        role="test",
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertFalse(path.exists())



    def test_path_exists_without_following_absent(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "absent"
        )

        self.assertFalse(
            (
                runner_module
                .path_exists_without_following(
                    path,
                    role="test",
                )
            )
        )

    def test_path_exists_without_following_symlink(
        self,
    ) -> None:
        target = (
            self.temporary_path
            / "target"
        )
        link = (
            self.temporary_path
            / "link"
        )
        target.write_bytes(b"target\n")
        link.symlink_to(target)

        self.assertTrue(
            (
                runner_module
                .path_exists_without_following(
                    link,
                    role="test",
                )
            )
        )

    def test_path_exists_without_following_error(
        self,
    ) -> None:
        path = (
            self.temporary_path
            / "object"
        )

        with mock.patch.object(
            runner_module.os,
            "lstat",
            side_effect=PermissionError(
                "simulated lstat failure"
            ),
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .path_exists_without_following(
                        path,
                        role="test",
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )



    def test_cycle_identity_validation_valid(
        self,
    ) -> None:
        state = runner_module.InvocationState()
        cycle = (
            runner_module
            .create_cycle_identity(
                state
            )
        )

        runner_module.validate_cycle_identity(
            cycle
        )

    def test_cycle_identity_validation_identifier(
        self,
    ) -> None:
        cycle = runner_module.CycleIdentity(
            generation_id="../invalid",
            started_at=(
                "2026-08-18T01:00:00.000000Z"
            ),
            started_datetime=(
                runner_module.datetime(
                    2026,
                    8,
                    18,
                    1,
                    0,
                    0,
                    tzinfo=(
                        runner_module.timezone.utc
                    ),
                )
            ),
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.validate_cycle_identity(
                cycle
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_cycle_identity_validation_timestamp(
        self,
    ) -> None:
        state = runner_module.InvocationState()
        valid = (
            runner_module
            .create_cycle_identity(
                state
            )
        )
        forged = runner_module.CycleIdentity(
            generation_id=(
                valid.generation_id
            ),
            started_at=(
                "2026-08-18T00:00:00.000000Z"
            ),
            started_datetime=(
                valid.started_datetime
            ),
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.validate_cycle_identity(
                forged
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )



    def make_staging_inputs(self):
        state, runtime = self.make_roots()
        roots = runner_module.validate_roots(
            str(state),
            str(runtime),
        )
        invocation = (
            runner_module.InvocationState()
        )
        cycle = (
            runner_module
            .create_cycle_identity(
                invocation
            )
        )
        return roots, cycle

    def test_staging_creation(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging = runner_module.create_staging(
            roots,
            cycle,
        )

        self.assertEqual(
            staging.root.path,
            (
                roots.generations.path
                / (
                    ".staging-"
                    + cycle.generation_id
                )
            ),
        )
        self.assertEqual(
            staging.observers.path,
            (
                staging.root.path
                / runner_module
                .OBSERVERS_DIRECTORY_NAME
            ),
        )
        self.assertEqual(
            stat.S_IMODE(
                os.lstat(
                    staging.root.path
                ).st_mode
            ),
            runner_module.STAGING_MODE,
        )
        self.assertEqual(
            stat.S_IMODE(
                os.lstat(
                    staging.observers.path
                ).st_mode
            ),
            runner_module.STAGING_MODE,
        )
        self.assertEqual(
            staging.root.identity.device,
            roots.generations.identity.device,
        )
        self.assertEqual(
            staging.observers.identity.device,
            staging.root.identity.device,
        )

        (
            runner_module
            .cleanup_empty_transient_directory(
                staging.observers,
                role="observers",
            )
        )
        (
            runner_module
            .cleanup_empty_transient_directory(
                staging.root,
                role="staging",
            )
        )

    def test_staging_name_collision(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        collision = (
            roots.generations.path
            / (
                ".staging-"
                + cycle.generation_id
            )
        )
        collision.mkdir(mode=0o750)

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.create_staging(
                roots,
                cycle,
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(collision.is_dir())

    def test_staging_generation_collision(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        collision = (
            roots.generations.path
            / cycle.generation_id
        )
        collision.mkdir(mode=0o550)

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.create_staging(
                roots,
                cycle,
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(collision.is_dir())



    def test_revalidate_staging_valid(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging = runner_module.create_staging(
            roots,
            cycle,
        )

        runner_module.revalidate_staging(
            roots,
            staging,
        )

        (
            runner_module
            .cleanup_empty_transient_directory(
                staging.observers,
                role="observers",
            )
        )
        (
            runner_module
            .cleanup_empty_transient_directory(
                staging.root,
                role="staging",
            )
        )

    def test_revalidate_staging_root_identity(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging = runner_module.create_staging(
            roots,
            cycle,
        )
        preserved = (
            roots.generations.path
            / "preserved-staging"
        )

        staging.root.path.rename(preserved)
        staging.root.path.mkdir(mode=0o750)
        (
            staging.root.path
            / runner_module
            .OBSERVERS_DIRECTORY_NAME
        ).mkdir(mode=0o750)

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.revalidate_staging(
                roots,
                staging,
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(preserved.is_dir())
        self.assertTrue(
            staging.root.path.is_dir()
        )

    def test_revalidate_staging_observers_identity(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging = runner_module.create_staging(
            roots,
            cycle,
        )
        preserved = (
            staging.root.path
            / "preserved-observers"
        )

        staging.observers.path.rename(
            preserved
        )
        staging.observers.path.mkdir(
            mode=0o750
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.revalidate_staging(
                roots,
                staging,
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(preserved.is_dir())
        self.assertTrue(
            staging.observers.path.is_dir()
        )



    def test_observers_creation_failure_cleanup(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging_path = (
            roots.generations.path
            / (
                ".staging-"
                + cycle.generation_id
            )
        )
        original_mkdir = os.mkdir

        def controlled_mkdir(
            path,
            mode=0o777,
            *,
            dir_fd=None,
        ):
            if (
                Path(path).name
                == runner_module
                .OBSERVERS_DIRECTORY_NAME
            ):
                raise OSError(
                    "simulated observers failure"
                )

            return original_mkdir(
                path,
                mode,
                dir_fd=dir_fd,
            )

        with mock.patch.object(
            runner_module.os,
            "mkdir",
            side_effect=controlled_mkdir,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                runner_module.create_staging(
                    roots,
                    cycle,
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertFalse(
            staging_path.exists()
        )

    def test_observers_creation_unsafe_preserved(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging_path = (
            roots.generations.path
            / (
                ".staging-"
                + cycle.generation_id
            )
        )
        observers_path = (
            staging_path
            / runner_module
            .OBSERVERS_DIRECTORY_NAME
        )
        original_mkdir = os.mkdir

        def racing_mkdir(
            path,
            mode=0o777,
            *,
            dir_fd=None,
        ):
            if Path(path) == observers_path:
                observers_path.write_bytes(
                    b"unexpected-object\n"
                )
                raise FileExistsError(
                    "simulated observers race"
                )

            return original_mkdir(
                path,
                mode,
                dir_fd=dir_fd,
            )

        with mock.patch.object(
            runner_module.os,
            "mkdir",
            side_effect=racing_mkdir,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                runner_module.create_staging(
                    roots,
                    cycle,
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertTrue(
            staging_path.is_dir()
        )
        self.assertTrue(
            observers_path.is_file()
        )
        self.assertEqual(
            observers_path.read_bytes(),
            b"unexpected-object\n",
        )



    def test_staging_insufficient_space(
        self,
    ) -> None:
        roots, cycle = (
            self.make_staging_inputs()
        )
        filesystem = mock.Mock(
            f_bavail=4095,
            f_frsize=4096,
        )

        with mock.patch.object(
            runner_module.os,
            "statvfs",
            return_value=filesystem,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                runner_module.create_staging(
                    roots,
                    cycle,
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertEqual(
            {
                path.name
                for path
                in roots.generations.path
                .iterdir()
            },
            set(),
        )



    def test_cycle_deadline_remaining(
        self,
    ) -> None:
        with mock.patch.object(
            runner_module.time,
            "monotonic",
            side_effect=[
                100.0,
                101.5,
            ],
        ):
            deadline = (
                runner_module
                .start_cycle_deadline()
            )
            remaining = (
                runner_module
                .remaining_cycle_seconds(
                    deadline
                )
            )

        self.assertEqual(
            deadline.started_monotonic,
            100.0,
        )
        self.assertEqual(
            deadline.deadline_monotonic,
            1300.0,
        )
        self.assertEqual(
            remaining,
            1198.5,
        )

    def test_cycle_deadline_expired(
        self,
    ) -> None:
        with mock.patch.object(
            runner_module.time,
            "monotonic",
            side_effect=[
                100.0,
                1300.0,
            ],
        ):
            deadline = (
                runner_module
                .start_cycle_deadline()
            )

            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .check_cycle_deadline(
                        deadline
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_cycle_deadline_clock_reversal(
        self,
    ) -> None:
        with mock.patch.object(
            runner_module.time,
            "monotonic",
            side_effect=[
                100.0,
                99.0,
            ],
        ):
            deadline = (
                runner_module
                .start_cycle_deadline()
            )

            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .remaining_cycle_seconds(
                        deadline
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )



    def test_cycle_deadline_tampered_context(
        self,
    ) -> None:
        deadline = runner_module.CycleDeadline(
            started_monotonic=100.0,
            deadline_monotonic=1299.0,
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            (
                runner_module
                .remaining_cycle_seconds(
                    deadline
                )
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_cycle_deadline_non_finite_start(
        self,
    ) -> None:
        with mock.patch.object(
            runner_module.time,
            "monotonic",
            return_value=float("inf"),
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .start_cycle_deadline()
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_INTERNAL,
        )
        self.assertEqual(
            captured.exception.code,
            "INTERNAL_ERROR",
        )



    def make_capture_result_document(
        self,
    ) -> dict[str, object]:
        return {
            "capture_contract": "1.0.0",
            "module": "observer-cpu",
            "outcome": "SUCCESS",
            "code": "SUCCESS",
            "observer_exit_code": 0,
            "report": (
                "observers/observer-cpu.json"
            ),
            "stdout_bytes": 128,
            "stderr_bytes": 0,
            "duration_ms": 25,
        }

    def validate_capture_document(
        self,
        document: dict[str, object],
        *,
        process_exit_code: int,
    ):
        configuration = (
            runner_module.load_configuration(
                ROOT
            )
        )
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return (
            runner_module
            .validate_capture_result(
                content,
                process_exit_code=(
                    process_exit_code
                ),
                expected_module=(
                    "observer-cpu"
                ),
                configuration=configuration,
            )
        )

    def assert_structural_capture_failure(
        self,
        document: dict[str, object],
        *,
        process_exit_code: int,
    ) -> None:
        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            self.validate_capture_document(
                document,
                process_exit_code=(
                    process_exit_code
                ),
            )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_capture_result_success(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        result = self.validate_capture_document(
            document,
            process_exit_code=0,
        )

        self.assertEqual(
            result.outcome,
            "SUCCESS",
        )
        self.assertEqual(
            result.module,
            "observer-cpu",
        )
        self.assertEqual(
            result.report,
            "observers/observer-cpu.json",
        )

    def test_capture_result_normal_failure(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        document.update(
            {
                "outcome": "FAILED",
                "code": "EXECUTION_TIMEOUT",
                "observer_exit_code": None,
                "report": None,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "duration_ms": 30000,
            }
        )
        result = self.validate_capture_document(
            document,
            process_exit_code=6,
        )

        self.assertEqual(
            result.outcome,
            "FAILED",
        )
        self.assertEqual(
            result.code,
            "EXECUTION_TIMEOUT",
        )
        self.assertIsNone(result.report)

    def test_capture_result_schema_violation(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        del document["duration_ms"]

        self.assert_structural_capture_failure(
            document,
            process_exit_code=0,
        )

    def test_capture_result_module_mismatch(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        document["module"] = (
            "observer-memory"
        )

        self.assert_structural_capture_failure(
            document,
            process_exit_code=0,
        )

    def test_capture_result_exit_mismatch(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )

        self.assert_structural_capture_failure(
            document,
            process_exit_code=6,
        )

    def test_capture_result_report_mismatch(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        document["report"] = (
            "observers/observer-memory.json"
        )

        self.assert_structural_capture_failure(
            document,
            process_exit_code=0,
        )

    def test_capture_result_structural_failure(
        self,
    ) -> None:
        document = (
            self.make_capture_result_document()
        )
        document.update(
            {
                "outcome": "FAILED",
                "code": (
                    "DEPENDENCY_UNAVAILABLE"
                ),
                "observer_exit_code": None,
                "report": None,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "duration_ms": 0,
            }
        )

        self.assert_structural_capture_failure(
            document,
            process_exit_code=3,
        )



    def start_controlled_process(
        self,
        source: str,
    ):
        return subprocess.Popen(
            [
                "/usr/bin/python3",
                "-I",
                "-c",
                source,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.temporary_path,
            env=(
                runner_module
                .build_child_environment()
            ),
            close_fds=True,
            start_new_session=True,
        )

    def test_capture_process_environment(
        self,
    ) -> None:
        first = (
            runner_module
            .build_child_environment()
        )
        second = (
            runner_module
            .build_child_environment()
        )

        self.assertEqual(
            first,
            {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.assertIsNot(first, second)

        first["UNEXPECTED"] = "value"

        self.assertNotIn(
            "UNEXPECTED",
            second,
        )

    def test_capture_process_external_timeout(
        self,
    ) -> None:
        configuration = (
            runner_module.load_configuration(
                ROOT
            )
        )
        deadline = runner_module.CycleDeadline(
            started_monotonic=100.0,
            deadline_monotonic=1300.0,
        )

        with mock.patch.object(
            runner_module.time,
            "monotonic",
            return_value=101.0,
        ):
            timeout = (
                runner_module
                .capture_external_timeout(
                    configuration,
                    deadline,
                )
            )

        self.assertEqual(timeout, 40.0)

        with mock.patch.object(
            runner_module.time,
            "monotonic",
            return_value=1280.0,
        ):
            timeout = (
                runner_module
                .capture_external_timeout(
                    configuration,
                    deadline,
                )
            )

        self.assertEqual(timeout, 20.0)

    def test_capture_process_collection(
        self,
    ) -> None:
        process = self.start_controlled_process(
            (
                "import os;"
                "os.write(1,b'{\"ok\":true}\\n');"
                "os.write(2,b'warning')"
            )
        )
        result = (
            runner_module
            .collect_capture_process(
                process,
                timeout_seconds=2.0,
            )
        )

        self.assertEqual(
            result.stdout,
            b'{"ok":true}\n',
        )
        self.assertEqual(
            result.stdout_bytes,
            12,
        )
        self.assertEqual(
            result.stderr_bytes,
            7,
        )
        self.assertEqual(
            result.exit_code,
            0,
        )
        self.assertGreaterEqual(
            result.duration_ms,
            0,
        )

    def test_capture_process_stdout_limit(
        self,
    ) -> None:
        process = self.start_controlled_process(
            (
                "import os;"
                "os.write(1,b'x'*70000)"
            )
        )

        with mock.patch.object(
            runner_module,
            "EXTERNAL_TERMINATION_GRACE_SECONDS",
            0.05,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .collect_capture_process(
                        process,
                        timeout_seconds=2.0,
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertIsNotNone(
            process.returncode
        )

    def test_capture_process_stderr_limit(
        self,
    ) -> None:
        process = self.start_controlled_process(
            (
                "import os;"
                "os.write(2,b'x'*70000)"
            )
        )

        with mock.patch.object(
            runner_module,
            "EXTERNAL_TERMINATION_GRACE_SECONDS",
            0.05,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .collect_capture_process(
                        process,
                        timeout_seconds=2.0,
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertIsNotNone(
            process.returncode
        )

    def test_capture_process_timeout(
        self,
    ) -> None:
        process = self.start_controlled_process(
            (
                "import time;"
                "time.sleep(5)"
            )
        )

        with mock.patch.object(
            runner_module,
            "EXTERNAL_TERMINATION_GRACE_SECONDS",
            0.05,
        ):
            with self.assertRaises(
                runner_module.RunnerFailure
            ) as captured:
                (
                    runner_module
                    .collect_capture_process(
                        process,
                        timeout_seconds=0.05,
                    )
                )

        self.assertEqual(
            captured.exception.exit_code,
            runner_module.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertIsNotNone(
            process.returncode
        )

    def test_capture_process_invocation(
        self,
    ) -> None:
        state_path, runtime_path = (
            self.make_roots()
        )
        roots = runner_module.validate_roots(
            str(state_path),
            str(runtime_path),
        )
        invocation = (
            runner_module.InvocationState()
        )
        cycle = (
            runner_module
            .create_cycle_identity(
                invocation
            )
        )
        staging = (
            runner_module.create_staging(
                roots,
                cycle,
            )
        )
        configuration = (
            runner_module.load_configuration(
                ROOT
            )
        )
        started = (
            runner_module.time.monotonic()
        )
        deadline = runner_module.CycleDeadline(
            started_monotonic=started,
            deadline_monotonic=(
                started
                + runner_module
                .TOTAL_CYCLE_TIMEOUT_SECONDS
            ),
        )
        document = (
            self.make_capture_result_document()
        )
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        process = mock.Mock()

        with mock.patch.object(
            runner_module.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            with mock.patch.object(
                runner_module,
                "collect_capture_process",
                return_value=(
                    runner_module
                    .CaptureProcessResult(
                        stdout=content,
                        stdout_bytes=len(content),
                        stderr_bytes=0,
                        exit_code=0,
                        duration_ms=10,
                    )
                ),
            ) as collect:
                result = (
                    runner_module
                    .invoke_capture_process(
                        roots,
                        staging,
                        configuration,
                        deadline,
                        "observer-cpu",
                    )
                )

        expected_capture = (
            ROOT
            / "core"
            / "capture-observer.py"
        )

        popen.assert_called_once_with(
            [
                "/usr/bin/python3",
                "-I",
                str(expected_capture),
                "--staging-dir",
                str(staging.root.path),
                "observer-cpu",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT,
            env=(
                runner_module
                .build_child_environment()
            ),
            close_fds=True,
            start_new_session=True,
        )
        collect.assert_called_once_with(
            process,
            timeout_seconds=40.0,
        )
        self.assertEqual(
            result.outcome,
            "SUCCESS",
        )



    def make_persisted_report_inputs(
        self,
    ):
        configuration = (
            runner_module.load_configuration(
                ROOT
            )
        )
        roots, cycle = (
            self.make_staging_inputs()
        )
        staging = runner_module.create_staging(
            roots,
            cycle,
        )
        deadline = (
            runner_module
            .start_cycle_deadline()
        )
        capture = (
            self.validate_capture_document(
                self.make_capture_result_document(),
                process_exit_code=0,
            )
        )
        fixture_root = (
            ROOT
            / "tests"
            / "fixtures"
            / "generation-manifest-1.0.0"
            / "valid-complete"
        )
        fixture_reports = list(
            fixture_root.glob(
                "*/observers/observer-cpu.json"
            )
        )

        self.assertEqual(
            len(fixture_reports),
            1,
        )

        report_path = (
            staging.observers.path
            / "observer-cpu.json"
        )
        report_content = (
            fixture_reports[0].read_bytes()
        )
        report_path.write_bytes(
            report_content
        )
        report_path.chmod(0o640)

        return (
            configuration,
            roots,
            staging,
            deadline,
            capture,
            report_path,
            report_content,
        )

    def validate_persisted_inputs(
        self,
        values,
    ):
        (
            configuration,
            roots,
            staging,
            deadline,
            capture,
            _report_path,
            _report_content,
        ) = values

        return (
            runner_module
            .validate_persisted_report(
                capture,
                configuration=configuration,
                roots=roots,
                staging=staging,
                deadline=deadline,
            )
        )

    def test_persisted_report_success(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        context = (
            self.validate_persisted_inputs(
                values
            )
        )
        report_content = values[6]

        self.assertEqual(
            context.descriptor["path"],
            "observers/observer-cpu.json",
        )
        self.assertEqual(
            context.descriptor["module"],
            "observer-cpu",
        )
        self.assertEqual(
            context.descriptor[
                "contract_version"
            ],
            "2.1.0",
        )
        self.assertEqual(
            context.descriptor["version"],
            "1.0.0",
        )
        self.assertEqual(
            context.descriptor["size_bytes"],
            len(report_content),
        )
        self.assertEqual(
            context.descriptor["sha256"],
            hashlib.sha256(
                report_content
            ).hexdigest(),
        )
        self.assertEqual(
            context.document["status"],
            context.descriptor["status"],
        )

    def test_persisted_report_missing(
        self,
    ) -> None:
        values = list(
            self.make_persisted_report_inputs()
        )
        values[5].unlink()

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_symbolic_link(
        self,
    ) -> None:
        values = list(
            self.make_persisted_report_inputs()
        )
        report_path = values[5]
        report_path.unlink()
        fixture_report = next(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "generation-manifest-1.0.0"
                / "valid-complete"
            ).glob(
                "*/observers/observer-cpu.json"
            )
        )
        report_path.symlink_to(
            fixture_report
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_hard_link(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        report_path = values[5]
        os.link(
            report_path,
            self.temporary_path
            / "report-hard-link.json",
        )

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_permissions(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        values[5].chmod(0o660)

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_invalid_contract(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        values[5].write_bytes(
            b"{}\n"
        )
        values[5].chmod(0o640)

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_version_rejected(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        report_path = values[5]
        document = json.loads(
            report_path.read_text(
                encoding="utf-8"
            )
        )
        document["version"] = "9.9.9"
        report_path.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        report_path.chmod(0o640)

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_failed_capture(
        self,
    ) -> None:
        values = list(
            self.make_persisted_report_inputs()
        )
        document = (
            self.make_capture_result_document()
        )
        document.update(
            {
                "outcome": "FAILED",
                "code": "EXECUTION_FAILED",
                "observer_exit_code": 1,
                "report": None,
            }
        )
        values[4] = (
            self.validate_capture_document(
                document,
                process_exit_code=6,
            )
        )
        values[5].unlink()

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            self.validate_persisted_inputs(
                values
            )

    def test_persisted_report_validator_output(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        process = mock.Mock()
        result = (
            runner_module.CaptureProcessResult(
                stdout=b"unexpected\n",
                stdout_bytes=11,
                stderr_bytes=0,
                exit_code=0,
                duration_ms=1,
            )
        )

        with mock.patch.object(
            runner_module.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            with mock.patch.object(
                runner_module,
                "collect_capture_process",
                return_value=result,
            ):
                with self.assertRaises(
                    runner_module.RunnerFailure
                ):
                    self.validate_persisted_inputs(
                        values
                    )

        popen.assert_called_once()

    def test_persisted_report_changed_during_validation(
        self,
    ) -> None:
        values = (
            self.make_persisted_report_inputs()
        )
        report_path = values[5]
        process = mock.Mock()
        result = (
            runner_module.CaptureProcessResult(
                stdout=b"",
                stdout_bytes=0,
                stderr_bytes=0,
                exit_code=0,
                duration_ms=1,
            )
        )

        def alter_report(
            _process,
            *,
            timeout_seconds,
        ):
            self.assertGreater(
                timeout_seconds,
                0,
            )
            report_path.write_bytes(
                b"{}\n"
            )
            report_path.chmod(0o640)
            return result

        with mock.patch.object(
            runner_module.subprocess,
            "Popen",
            return_value=process,
        ):
            with mock.patch.object(
                runner_module,
                "collect_capture_process",
                side_effect=alter_report,
            ):
                with self.assertRaises(
                    runner_module.RunnerFailure
                ):
                    self.validate_persisted_inputs(
                        values
                    )


    def make_manifest_modules_configuration(
        self,
    ):
        registry_path = (
            ROOT
            / "config"
            / "observer-registry.json"
        )
        registry_document = json.loads(
            registry_path.read_text(
                encoding="utf-8"
            )
        )

        registry = runner_module.RegistryContext(
            path=registry_path,
            document=registry_document,
            secure=mock.Mock(),
            sha256="0" * 64,
        )

        return runner_module.ConfigurationContext(
            validator_class=mock.Mock(),
            registry_schema=mock.Mock(),
            capture_schema=mock.Mock(),
            report_schema=mock.Mock(),
            registry=registry,
        )

    def make_manifest_capture(
        self,
        module,
        *,
        outcome="SUCCESS",
        code="SUCCESS",
        observer_exit_code=0,
        process_exit_code=0,
    ):
        return runner_module.CaptureResultContext(
            document={},
            process_exit_code=process_exit_code,
            module=module,
            outcome=outcome,
            code=code,
            observer_exit_code=observer_exit_code,
            report=(
                f"observers/{module}.json"
                if outcome == "SUCCESS"
                else None
            ),
            stdout_bytes=17,
            stderr_bytes=3,
            duration_ms=11,
        )

    def make_manifest_report(
        self,
        module,
    ):
        descriptor = {
            "path": f"observers/{module}.json",
            "module": module,
            "contract_version": "2.1.0",
            "version": "1.0.0",
            "timestamp": (
                "2026-08-19T18:00:00+0000"
            ),
            "status": "UNKNOWN",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }

        return runner_module.PersistedReportContext(
            path=(
                self.temporary_path
                / f"{module}.json"
            ),
            secure=mock.Mock(),
            document={
                "module": module,
            },
            descriptor=descriptor,
        )

    def test_manifest_modules_success(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )
        registry_entries[1]["required"] = False

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in registry_entries
        ]
        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in registry_entries
        ]

        modules = (
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )
        )

        self.assertEqual(
            [
                entry["module"]
                for entry in modules
            ],
            [
                entry["module"]
                for entry in registry_entries
            ],
        )
        self.assertTrue(
            modules[0]["required"]
        )
        self.assertFalse(
            modules[1]["required"]
        )
        self.assertEqual(
            modules[0]["outcome"],
            "SUCCESS",
        )
        self.assertIsNone(
            modules[0]["error_code"]
        )
        self.assertEqual(
            modules[0]["exit_code"],
            0,
        )
        self.assertEqual(
            modules[0]["report"]["module"],
            modules[0]["module"],
        )

    def test_manifest_modules_failure_preserves_observer_exit(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = []
        reports = []

        for index, entry in enumerate(
            registry_entries
        ):
            module = entry["module"]

            if index == 0:
                captures.append(
                    self.make_manifest_capture(
                        module
                    )
                )
                reports.append(
                    self.make_manifest_report(
                        module
                    )
                )
            else:
                captures.append(
                    self.make_manifest_capture(
                        module,
                        outcome="FAILED",
                        code="EXECUTION_FAILED",
                        observer_exit_code=23,
                        process_exit_code=6,
                    )
                )

        modules = (
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )
        )

        failed = modules[1]

        self.assertEqual(
            failed["outcome"],
            "FAILED",
        )
        self.assertEqual(
            failed["error_code"],
            "EXECUTION_FAILED",
        )
        self.assertEqual(
            failed["exit_code"],
            23,
        )
        self.assertIsNone(
            failed["report"]
        )

    def test_manifest_modules_registry_order(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in reversed(
                registry_entries
            )
        ]
        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in reversed(
                registry_entries
            )
        ]

        modules = (
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )
        )

        self.assertEqual(
            [
                entry["module"]
                for entry in modules
            ],
            [
                entry["module"]
                for entry in registry_entries
            ],
        )

    def test_manifest_modules_missing_capture(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in registry_entries[:-1]
        ]
        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in registry_entries[:-1]
        ]

        with self.assertRaises(
            runner_module.RunnerFailure
        ) as captured:
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )

        self.assertEqual(
            captured.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_manifest_modules_duplicate_capture(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in registry_entries
        ]
        captures[-1] = captures[0]

        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in registry_entries
        ]

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )

    def test_manifest_modules_success_without_report(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in registry_entries
        ]
        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in registry_entries[:-1]
        ]

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )

    def test_manifest_modules_failure_with_report(
        self,
    ) -> None:
        configuration = (
            self.make_manifest_modules_configuration()
        )
        registry_entries = (
            configuration.registry.document[
                "observers"
            ]
        )

        captures = [
            self.make_manifest_capture(
                entry["module"]
            )
            for entry in registry_entries
        ]

        failed_module = (
            registry_entries[-1]["module"]
        )
        captures[-1] = (
            self.make_manifest_capture(
                failed_module,
                outcome="FAILED",
                code="EXECUTION_FAILED",
                observer_exit_code=1,
                process_exit_code=6,
            )
        )

        reports = [
            self.make_manifest_report(
                entry["module"]
            )
            for entry in registry_entries
        ]

        with self.assertRaises(
            runner_module.RunnerFailure
        ):
            runner_module.build_manifest_modules(
                captures,
                reports,
                configuration=configuration,
            )



class ObserverRunnerManifestDocumentTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        from importlib.machinery import (
            SourceFileLoader,
        )
        import sys

        runner_path = (
            Path(__file__).resolve()
            .parent.parent
            / "runner"
            / "observer-runner.py"
        )

        module_name = (
            "observer_runner_manifest_document_test"
        )

        loader = SourceFileLoader(
            module_name,
            str(runner_path),
        )

        specification = (
            importlib.util.spec_from_loader(
                module_name,
                loader,
            )
        )

        if specification is None:
            raise RuntimeError(
                "runner import failed"
            )

        module = (
            importlib.util.module_from_spec(
                specification
            )
        )

        sys.modules[
            module_name
        ] = module

        loader.exec_module(
            module
        )

        cls.runner = module

    def setUp(self) -> None:
        self.temporary_path = Path(
            tempfile.mkdtemp(
                prefix=(
                    "mppt24-runner-manifest-"
                )
            )
        )

    def tearDown(self) -> None:
        shutil.rmtree(
            self.temporary_path,
            ignore_errors=False,
        )

    def make_manifest_staging(self):
        state = (
            self.temporary_path
            / "state"
        )
        runtime = (
            self.temporary_path
            / "runtime"
        )

        state.mkdir(mode=0o750)
        runtime.mkdir(mode=0o750)
        (
            state
            / "generations"
        ).mkdir(mode=0o750)

        roots = self.runner.validate_roots(
            str(state),
            str(runtime),
        )

        invocation = (
            self.runner.InvocationState()
        )
        cycle = (
            self.runner
            .create_cycle_identity(
                invocation
            )
        )
        staging = (
            self.runner.create_staging(
                roots,
                cycle,
            )
        )

        return roots, cycle, staging

    def persist_manifest_sample(
        self,
        content=b'{"manifest":"test"}\n',
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        secure = (
            self.runner.persist_manifest(
                roots,
                staging,
                content,
                (
                    self.runner
                    .load_rename_noreplace()
                ),
            )
        )

        return (
            roots,
            cycle,
            staging,
            secure,
        )

    def make_cycle(
        self,
        moment,
    ):
        return self.runner.CycleIdentity(
            generation_id=(
                moment.strftime(
                    "%Y%m%dT%H%M%S%fZ"
                )
                + "-"
                + ("ab" * 16)
            ),
            started_at=(
                self.runner
                .format_manifest_timestamp(
                    moment
                )
            ),
            started_datetime=moment,
        )

    def make_configuration(
        self,
        modules,
    ):
        registry = (
            self.runner.RegistryContext(
                path=Path(
                    "observer-registry.json"
                ),
                document={
                    "registry_version": "1.0.0",
                    "observers": [
                        {
                            "module": module,
                            "required": True,
                        }
                        for module in modules
                    ],
                },
                secure=None,
                sha256=("cd" * 32),
            )
        )

        return (
            self.runner.ConfigurationContext(
                validator_class=None,
                registry_schema=None,
                capture_schema=None,
                report_schema=None,
                registry=registry,
            )
        )

    def make_module(
        self,
        module,
        outcome,
    ):
        if outcome == "SUCCESS":
            return {
                "module": module,
                "required": True,
                "outcome": "SUCCESS",
                "error_code": None,
                "exit_code": 0,
                "stdout_bytes": 10,
                "stderr_bytes": 0,
                "duration_ms": 5,
                "report": {
                    "path": (
                        f"observers/{module}.json"
                    ),
                    "module": module,
                    "contract_version": "2.1.0",
                    "version": "1.0.0",
                    "timestamp": (
                        "2026-08-19T19:00:00+0000"
                    ),
                    "status": "OK",
                    "size_bytes": 100,
                    "sha256": ("ef" * 32),
                },
            }

        return {
            "module": module,
            "required": True,
            "outcome": "FAILED",
            "error_code": "EXECUTION_FAILED",
            "exit_code": 1,
            "stdout_bytes": 0,
            "stderr_bytes": 10,
            "duration_ms": 5,
            "report": None,
        }

    def test_completed_at_after_start(
        self,
    ):
        from datetime import (
            datetime,
            timedelta,
            timezone,
        )

        started = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        completed = (
            started
            + timedelta(
                microseconds=1
            )
        )
        cycle = self.make_cycle(
            started
        )
        original = self.runner.datetime

        class FixedDateTime(datetime):
            @classmethod
            def now(
                cls,
                tz=None,
            ):
                return completed

        self.runner.datetime = (
            FixedDateTime
        )

        try:
            value = (
                self.runner
                .create_completed_at(
                    cycle
                )
            )
        finally:
            self.runner.datetime = (
                original
            )

        self.assertEqual(
            value,
            self.runner
            .format_manifest_timestamp(
                completed
            ),
        )

    def test_completed_at_equal_start(
        self,
    ):
        from datetime import (
            datetime,
            timezone,
        )

        started = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        cycle = self.make_cycle(
            started
        )
        original = self.runner.datetime

        class FixedDateTime(datetime):
            @classmethod
            def now(
                cls,
                tz=None,
            ):
                return started

        self.runner.datetime = (
            FixedDateTime
        )

        try:
            value = (
                self.runner
                .create_completed_at(
                    cycle
                )
            )
        finally:
            self.runner.datetime = (
                original
            )

        self.assertEqual(
            value,
            cycle.started_at,
        )

    def test_completed_at_clock_reversal(
        self,
    ):
        from datetime import (
            datetime,
            timedelta,
            timezone,
        )

        started = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        completed = (
            started
            - timedelta(
                microseconds=1
            )
        )
        cycle = self.make_cycle(
            started
        )
        original = self.runner.datetime

        class FixedDateTime(datetime):
            @classmethod
            def now(
                cls,
                tz=None,
            ):
                return completed

        self.runner.datetime = (
            FixedDateTime
        )

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.create_completed_at(
                    cycle
                )
        finally:
            self.runner.datetime = (
                original
            )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            caught.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_manifest_document_complete(
        self,
    ):
        from datetime import (
            datetime,
            timezone,
        )

        moment = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        cycle = self.make_cycle(
            moment
        )
        configuration = (
            self.make_configuration(
                ["cpu", "memory"]
            )
        )
        modules = [
            self.make_module(
                "cpu",
                "SUCCESS",
            ),
            self.make_module(
                "memory",
                "SUCCESS",
            ),
        ]

        document = (
            self.runner
            .build_manifest_document(
                modules,
                configuration=configuration,
                cycle=cycle,
                completed_at=cycle.started_at,
            )
        )

        self.assertEqual(
            document["state"],
            "COMPLETE",
        )
        self.assertEqual(
            document["summary"],
            {
                "declared": 2,
                "successful": 2,
                "failed": 0,
                "reports_written": 2,
            },
        )

    def test_manifest_document_partial(
        self,
    ):
        from datetime import (
            datetime,
            timezone,
        )

        moment = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        cycle = self.make_cycle(
            moment
        )
        configuration = (
            self.make_configuration(
                ["cpu", "memory"]
            )
        )
        modules = [
            self.make_module(
                "cpu",
                "SUCCESS",
            ),
            self.make_module(
                "memory",
                "FAILED",
            ),
        ]

        document = (
            self.runner
            .build_manifest_document(
                modules,
                configuration=configuration,
                cycle=cycle,
                completed_at=cycle.started_at,
            )
        )

        self.assertEqual(
            document["state"],
            "PARTIAL",
        )
        self.assertEqual(
            document["summary"],
            {
                "declared": 2,
                "successful": 1,
                "failed": 1,
                "reports_written": 1,
            },
        )

    def test_manifest_document_failed(
        self,
    ):
        from datetime import (
            datetime,
            timezone,
        )

        moment = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        cycle = self.make_cycle(
            moment
        )
        configuration = (
            self.make_configuration(
                ["cpu", "memory"]
            )
        )
        modules = [
            self.make_module(
                "cpu",
                "FAILED",
            ),
            self.make_module(
                "memory",
                "FAILED",
            ),
        ]

        document = (
            self.runner
            .build_manifest_document(
                modules,
                configuration=configuration,
                cycle=cycle,
                completed_at=cycle.started_at,
            )
        )

        self.assertEqual(
            document["state"],
            "FAILED",
        )
        self.assertEqual(
            document["summary"],
            {
                "declared": 2,
                "successful": 0,
                "failed": 2,
                "reports_written": 0,
            },
        )

    def test_manifest_document_preserves_module_order_and_identity(
        self,
    ):
        from datetime import (
            datetime,
            timezone,
        )

        moment = datetime(
            2026,
            8,
            19,
            19,
            0,
            0,
            tzinfo=timezone.utc,
        )
        cycle = self.make_cycle(
            moment
        )
        configuration = (
            self.make_configuration(
                ["cpu", "memory"]
            )
        )
        modules = [
            self.make_module(
                "cpu",
                "SUCCESS",
            ),
            self.make_module(
                "memory",
                "FAILED",
            ),
        ]

        document = (
            self.runner
            .build_manifest_document(
                modules,
                configuration=configuration,
                cycle=cycle,
                completed_at=cycle.started_at,
            )
        )

        self.assertEqual(
            document[
                "manifest_version"
            ],
            "1.0.0",
        )
        self.assertEqual(
            document[
                "generation_id"
            ],
            cycle.generation_id,
        )
        self.assertEqual(
            document["started_at"],
            cycle.started_at,
        )
        self.assertEqual(
            document[
                "completed_at"
            ],
            cycle.started_at,
        )
        self.assertEqual(
            document["runner"],
            {
                "module": "observer-runner",
                "version": "2.0.0",
            },
        )
        self.assertEqual(
            document["registry"],
            {
                "version": "1.0.0",
                "hash_algorithm": "sha256",
                "sha256": ("cd" * 32),
            },
        )
        self.assertEqual(
            [
                entry["module"]
                for entry
                in document["modules"]
            ],
            [
                "cpu",
                "memory",
            ],
        )



    def make_official_validation_inputs(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        report_path = (
            staging.observers.path
            / "observer-cpu.json"
        )
        report_content = b'{"test":"report"}\n'

        report_path.write_bytes(
            report_content
        )
        os.chmod(
            report_path,
            self.runner.STAGING_FILE_MODE,
        )

        report_status = os.lstat(
            report_path
        )
        report_secure = (
            self.runner.SecureContent(
                content=report_content,
                identity=self.runner.path_identity(
                    report_status
                ),
                size=report_status.st_size,
                mtime_ns=report_status.st_mtime_ns,
                ctime_ns=report_status.st_ctime_ns,
            )
        )

        report = (
            self.runner.PersistedReportContext(
                path=report_path,
                secure=report_secure,
                document={
                    "module": "observer-cpu",
                },
                descriptor={
                    "path": (
                        "observers/"
                        "observer-cpu.json"
                    ),
                    "module": "observer-cpu",
                    "contract_version": "2.1.0",
                },
            )
        )

        manifest_content = (
            b'{"manifest":"validation"}\n'
        )

        manifest_secure = (
            self.runner.persist_manifest(
                roots,
                staging,
                manifest_content,
                self.runner.load_rename_noreplace(),
            )
        )

        deadline = (
            self.runner.start_cycle_deadline()
        )

        return (
            roots,
            cycle,
            staging,
            manifest_secure,
            [report],
            deadline,
        )

    def run_official_validation_mocked(
        self,
        values,
        *,
        result=None,
    ):
        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        if result is None:
            result = (
                self.runner.CaptureProcessResult(
                    stdout=b"",
                    stdout_bytes=0,
                    stderr_bytes=0,
                    exit_code=0,
                    duration_ms=1,
                )
            )

        process = mock.Mock()

        with mock.patch.object(
            self.runner.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            with mock.patch.object(
                self.runner,
                "collect_capture_process",
                return_value=result,
            ) as collector:
                self.runner.validate_manifest_official(
                    roots,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                )

        return popen, collector

    def test_manifest_official_validation_success(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        self.run_official_validation_mocked(
            values
        )

    def test_manifest_official_validation_arguments(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        popen, collector = (
            self.run_official_validation_mocked(
                values
            )
        )

        arguments = popen.call_args.args[0]

        project_root = (
            Path(
                self.runner.__file__
            ).resolve().parent.parent
        )
        validator_path = (
            project_root
            / "core"
            / "validate-manifest.py"
        )

        self.assertEqual(
            arguments,
            [
                "/usr/bin/python3",
                "-I",
                str(validator_path),
                "--expected-generation-id",
                cycle.generation_id,
                str(staging.root.path),
            ],
        )

        collector.assert_called_once()

    def test_manifest_official_validation_process_contract(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        popen, collector = (
            self.run_official_validation_mocked(
                values
            )
        )

        kwargs = popen.call_args.kwargs

        self.assertIs(
            kwargs["stdin"],
            self.runner.subprocess.DEVNULL,
        )
        self.assertIs(
            kwargs["stdout"],
            self.runner.subprocess.PIPE,
        )
        self.assertIs(
            kwargs["stderr"],
            self.runner.subprocess.PIPE,
        )
        self.assertTrue(
            kwargs["close_fds"]
        )
        self.assertTrue(
            kwargs["start_new_session"]
        )

    def test_manifest_official_validation_environment(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        expected_environment = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
        }

        with mock.patch.object(
            self.runner,
            "build_child_environment",
            return_value=expected_environment,
        ):
            popen, collector = (
                self.run_official_validation_mocked(
                    values
                )
            )

        self.assertEqual(
            popen.call_args.kwargs["env"],
            expected_environment,
        )

    def test_manifest_official_validation_nonzero_exit(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        result = (
            self.runner.CaptureProcessResult(
                stdout=b"",
                stdout_bytes=0,
                stderr_bytes=0,
                exit_code=6,
                duration_ms=1,
            )
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ) as raised:
            self.run_official_validation_mocked(
                values,
                result=result,
            )

        self.assertEqual(
            raised.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            raised.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_manifest_official_validation_stdout(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        result = (
            self.runner.CaptureProcessResult(
                stdout=b"unexpected\n",
                stdout_bytes=11,
                stderr_bytes=0,
                exit_code=0,
                duration_ms=1,
            )
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.run_official_validation_mocked(
                values,
                result=result,
            )

    def test_manifest_official_validation_stderr(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        result = (
            self.runner.CaptureProcessResult(
                stdout=b"",
                stdout_bytes=0,
                stderr_bytes=11,
                exit_code=0,
                duration_ms=1,
            )
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.run_official_validation_mocked(
                values,
                result=result,
            )

    def test_manifest_official_validation_start_failure(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        with mock.patch.object(
            self.runner.subprocess,
            "Popen",
            side_effect=OSError,
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as raised:
                self.runner.validate_manifest_official(
                    roots,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                )

        self.assertEqual(
            raised.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )

    def test_manifest_official_validation_validator_changed(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        original = (
            self.runner.revalidate_secure_file
        )

        calls = {
            "validator": 0,
        }

        def changed(
            path,
            secure,
            *,
            role,
            exit_code,
            failure_code,
        ):
            if role == "Validador de Manifestos":
                calls["validator"] += 1
                raise self.runner.RunnerFailure(
                    self.runner.EXIT_STRUCTURAL,
                    "STRUCTURAL_FAILURE",
                    "validator changed",
                )

            return original(
                path,
                secure,
                role=role,
                exit_code=exit_code,
                failure_code=failure_code,
            )

        with mock.patch.object(
            self.runner,
            "revalidate_secure_file",
            side_effect=changed,
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ):
                self.run_official_validation_mocked(
                    values
                )

        self.assertEqual(
            calls["validator"],
            1,
        )

    def test_manifest_official_validation_manifest_changed(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        manifest_path = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        result = (
            self.runner.CaptureProcessResult(
                stdout=b"",
                stdout_bytes=0,
                stderr_bytes=0,
                exit_code=0,
                duration_ms=1,
            )
        )

        process = mock.Mock()

        def collect(*args, **kwargs):
            manifest_path.write_bytes(
                b'{"changed":true}\n'
            )
            return result

        with mock.patch.object(
            self.runner.subprocess,
            "Popen",
            return_value=process,
        ):
            with mock.patch.object(
                self.runner,
                "collect_capture_process",
                side_effect=collect,
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ):
                    self.runner.validate_manifest_official(
                        roots,
                        staging,
                        manifest_secure,
                        reports,
                        deadline,
                    )

    def test_manifest_official_validation_report_changed(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        report_path = reports[0].path

        result = (
            self.runner.CaptureProcessResult(
                stdout=b"",
                stdout_bytes=0,
                stderr_bytes=0,
                exit_code=0,
                duration_ms=1,
            )
        )

        process = mock.Mock()

        def collect(*args, **kwargs):
            report_path.write_bytes(
                b'{"changed":true}\n'
            )
            return result

        with mock.patch.object(
            self.runner.subprocess,
            "Popen",
            return_value=process,
        ):
            with mock.patch.object(
                self.runner,
                "collect_capture_process",
                side_effect=collect,
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ):
                    self.runner.validate_manifest_official(
                        roots,
                        staging,
                        manifest_secure,
                        reports,
                        deadline,
                    )

    def test_manifest_official_validation_staging_changed(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        original_identity = (
            staging.root.identity
        )

        staging.root.path.rename(
            staging.root.path.with_name(
                staging.root.path.name
                + ".moved"
            )
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.runner.validate_manifest_official(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

    def test_manifest_official_validation_extra_staging_object(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        (
            staging.root.path
            / "unexpected"
        ).write_text(
            "x",
            encoding="utf-8",
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.runner.validate_manifest_official(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

    def test_manifest_official_validation_extra_observer_object(
        self,
    ) -> None:
        values = (
            self.make_official_validation_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        (
            staging.observers.path
            / "unexpected.json"
        ).write_text(
            "{}\n",
            encoding="utf-8",
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.runner.validate_manifest_official(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

    def make_final_permissions_inputs(
        self,
    ):
        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = self.make_official_validation_inputs()

        report = reports[0]
        descriptor = dict(
            report.descriptor
        )
        descriptor["sha256"] = (
            hashlib.sha256(
                report.secure.content
            ).hexdigest()
        )

        updated_report = (
            self.runner.PersistedReportContext(
                path=report.path,
                secure=report.secure,
                document=report.document,
                descriptor=descriptor,
            )
        )

        return (
            roots,
            cycle,
            staging,
            manifest_secure,
            [updated_report],
            deadline,
        )

    def reset_manifest_fixture_tree(
        self,
    ) -> None:
        for child in list(
            self.temporary_path.iterdir()
        ):
            if child.is_dir():
                shutil.rmtree(
                    child,
                    ignore_errors=False,
                )
            else:
                child.unlink()


    def restore_final_permissions_fixture(
        self,
        staging,
    ) -> None:
        for directory in (
            staging.root.path,
            staging.observers.path,
        ):
            try:
                os.chmod(
                    directory,
                    self.runner.STAGING_MODE,
                )
            except OSError:
                pass

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        try:
            os.chmod(
                manifest,
                self.runner.STAGING_FILE_MODE,
            )
        except OSError:
            pass

        try:
            entries = list(
                staging.observers.path.iterdir()
            )
        except OSError:
            entries = []

        for entry in entries:
            try:
                os.chmod(
                    entry,
                    self.runner.STAGING_FILE_MODE,
                )
            except OSError:
                pass

    def test_final_permissions_success_modes(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        try:
            (
                updated_staging,
                updated_manifest,
                updated_reports,
            ) = self.runner.apply_final_permissions(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        updated_staging.root.path
                    ).st_mode
                ),
                self.runner.PROMOTED_DIRECTORY_MODE,
            )
            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        updated_staging.observers.path
                    ).st_mode
                ),
                self.runner.PROMOTED_DIRECTORY_MODE,
            )
            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        staging.root.path
                        / self.runner.MANIFEST_FILE_NAME
                    ).st_mode
                ),
                self.runner.PROMOTED_FILE_MODE,
            )
            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        updated_reports[0].path
                    ).st_mode
                ),
                self.runner.PROMOTED_FILE_MODE,
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_preserve_file_integrity(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        old_report = reports[0]

        try:
            (
                updated_staging,
                updated_manifest,
                updated_reports,
            ) = self.runner.apply_final_permissions(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

            updated_report = (
                updated_reports[0]
            )

            self.assertEqual(
                updated_manifest.identity,
                manifest_secure.identity,
            )
            self.assertEqual(
                updated_manifest.content,
                manifest_secure.content,
            )
            self.assertEqual(
                updated_manifest.size,
                manifest_secure.size,
            )
            self.assertEqual(
                updated_manifest.mtime_ns,
                manifest_secure.mtime_ns,
            )

            self.assertEqual(
                updated_report.secure.identity,
                old_report.secure.identity,
            )
            self.assertEqual(
                updated_report.secure.content,
                old_report.secure.content,
            )
            self.assertEqual(
                updated_report.secure.size,
                old_report.secure.size,
            )
            self.assertEqual(
                updated_report.secure.mtime_ns,
                old_report.secure.mtime_ns,
            )
            self.assertEqual(
                hashlib.sha256(
                    updated_report.secure.content
                ).hexdigest(),
                old_report.descriptor[
                    "sha256"
                ],
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_refresh_secure_contexts(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        try:
            (
                updated_staging,
                updated_manifest,
                updated_reports,
            ) = self.runner.apply_final_permissions(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

            manifest_path = (
                staging.root.path
                / self.runner.MANIFEST_FILE_NAME
            )

            self.assertEqual(
                updated_manifest.ctime_ns,
                os.lstat(
                    manifest_path
                ).st_ctime_ns,
            )
            self.assertEqual(
                updated_reports[0]
                .secure.ctime_ns,
                os.lstat(
                    updated_reports[0].path
                ).st_ctime_ns,
            )

            self.runner.revalidate_secure_file(
                manifest_path,
                updated_manifest,
                role="manifesto",
                exit_code=(
                    self.runner.EXIT_STRUCTURAL
                ),
                failure_code=(
                    "STRUCTURAL_FAILURE"
                ),
            )

            self.runner.revalidate_secure_file(
                updated_reports[0].path,
                updated_reports[0].secure,
                role="relatório persistido",
                exit_code=(
                    self.runner.EXIT_STRUCTURAL
                ),
                failure_code=(
                    "STRUCTURAL_FAILURE"
                ),
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_preserve_directory_identity(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        try:
            (
                updated_staging,
                updated_manifest,
                updated_reports,
            ) = self.runner.apply_final_permissions(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

            self.assertEqual(
                updated_staging.root.identity,
                staging.root.identity,
            )
            self.assertEqual(
                updated_staging.observers.identity,
                staging.observers.identity,
            )
            self.assertEqual(
                updated_staging.root.mode,
                self.runner.PROMOTED_DIRECTORY_MODE,
            )
            self.assertEqual(
                updated_staging.observers.mode,
                self.runner.PROMOTED_DIRECTORY_MODE,
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_second_validation_compatible(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        try:
            (
                updated_staging,
                updated_manifest,
                updated_reports,
            ) = self.runner.apply_final_permissions(
                roots,
                staging,
                manifest_secure,
                reports,
                deadline,
            )

            second_values = (
                roots,
                cycle,
                updated_staging,
                updated_manifest,
                updated_reports,
                deadline,
            )

            self.run_official_validation_mocked(
                second_values
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_fchmod_order(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        original = os.fchmod
        calls = []

        def recording(
            descriptor,
            mode,
        ):
            calls.append(
                (
                    Path(
                        os.readlink(
                            "/proc/self/fd/"
                            + str(descriptor)
                        )
                    ),
                    mode,
                )
            )
            return original(
                descriptor,
                mode,
            )

        try:
            with mock.patch.object(
                self.runner.os,
                "fchmod",
                side_effect=recording,
            ):
                self.runner.apply_final_permissions(
                    roots,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                )

            self.assertEqual(
                calls,
                [
                    (
                        reports[0].path,
                        self.runner
                        .PROMOTED_FILE_MODE,
                    ),
                    (
                        staging.root.path
                        / self.runner
                        .MANIFEST_FILE_NAME,
                        self.runner
                        .PROMOTED_FILE_MODE,
                    ),
                    (
                        staging.observers.path,
                        self.runner
                        .PROMOTED_DIRECTORY_MODE,
                    ),
                    (
                        staging.root.path,
                        self.runner
                        .PROMOTED_DIRECTORY_MODE,
                    ),
                ],
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_fchmod_failures(
        self,
    ) -> None:
        for failure_call in (
            1,
            2,
            3,
            4,
        ):
            with self.subTest(
                failure_call=failure_call
            ):
                values = (
                    self.make_final_permissions_inputs()
                )

                (
                    roots,
                    cycle,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                ) = values

                original = os.fchmod
                counter = {
                    "value": 0,
                }

                def controlled(
                    descriptor,
                    mode,
                ):
                    counter["value"] += 1

                    if (
                        counter["value"]
                        == failure_call
                    ):
                        raise OSError(
                            "simulated chmod failure"
                        )

                    return original(
                        descriptor,
                        mode,
                    )

                try:
                    with mock.patch.object(
                        self.runner.os,
                        "fchmod",
                        side_effect=controlled,
                    ):
                        with self.assertRaises(
                            self.runner.RunnerFailure
                        ) as raised:
                            self.runner.apply_final_permissions(
                                roots,
                                staging,
                                manifest_secure,
                                reports,
                                deadline,
                            )

                    self.assertEqual(
                        raised.exception.exit_code,
                        self.runner.EXIT_STRUCTURAL,
                    )
                    self.assertEqual(
                        raised.exception.code,
                        "STRUCTURAL_FAILURE",
                    )
                finally:
                    self.restore_final_permissions_fixture(
                        staging
                    )
                    self.reset_manifest_fixture_tree()

    def test_final_permissions_confirmation_failure(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        original = os.fchmod
        counter = {
            "value": 0,
        }

        def divergent(
            descriptor,
            mode,
        ):
            counter["value"] += 1

            result = original(
                descriptor,
                mode,
            )

            if counter["value"] == 1:
                original(
                    descriptor,
                    self.runner.STAGING_FILE_MODE,
                )

            return result

        try:
            with mock.patch.object(
                self.runner.os,
                "fchmod",
                side_effect=divergent,
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ) as raised:
                    self.runner.apply_final_permissions(
                        roots,
                        staging,
                        manifest_secure,
                        reports,
                        deadline,
                    )

            self.assertEqual(
                raised.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_final_permissions_extra_objects_rejected(
        self,
    ) -> None:
        for location in (
            "staging",
            "observers",
        ):
            with self.subTest(
                location=location
            ):
                values = (
                    self.make_final_permissions_inputs()
                )

                (
                    roots,
                    cycle,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                ) = values

                if location == "staging":
                    unexpected = (
                        staging.root.path
                        / "unexpected"
                    )
                else:
                    unexpected = (
                        staging.observers.path
                        / "unexpected.json"
                    )

                unexpected.write_bytes(
                    b"x"
                )

                try:
                    with self.assertRaises(
                        self.runner.RunnerFailure
                    ):
                        self.runner.apply_final_permissions(
                            roots,
                            staging,
                            manifest_secure,
                            reports,
                            deadline,
                        )
                finally:
                    try:
                        unexpected.unlink()
                    except OSError:
                        pass

                    self.restore_final_permissions_fixture(
                        staging
                    )
                    self.reset_manifest_fixture_tree()

    def test_final_permissions_hash_mismatch(
        self,
    ) -> None:
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        reports[0].descriptor[
            "sha256"
        ] = "0" * 64

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as raised:
                self.runner.apply_final_permissions(
                    roots,
                    staging,
                    manifest_secure,
                    reports,
                    deadline,
                )

            self.assertEqual(
                raised.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )
            self.assertEqual(
                raised.exception.code,
                "STRUCTURAL_FAILURE",
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def make_generation_sync_inputs(
        self,
    ):
        values = (
            self.make_final_permissions_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest_secure,
            reports,
            deadline,
        ) = values

        (
            updated_staging,
            updated_manifest,
            updated_reports,
        ) = self.runner.apply_final_permissions(
            roots,
            staging,
            manifest_secure,
            reports,
            deadline,
        )

        return (
            roots,
            cycle,
            updated_staging,
            updated_manifest,
            updated_reports,
            deadline,
        )

    def test_generation_sync_success(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        try:
            self.runner.synchronize_generation(
                roots,
                staging,
                manifest,
                reports,
                deadline,
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_order(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        original = os.fsync
        calls = []

        def recording(descriptor):
            calls.append(
                Path(
                    os.readlink(
                        "/proc/self/fd/"
                        + str(descriptor)
                    )
                )
            )
            return original(descriptor)

        try:
            with mock.patch.object(
                self.runner.os,
                "fsync",
                side_effect=recording,
            ):
                self.runner.synchronize_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                )

            self.assertEqual(
                calls,
                [
                    reports[0].path,
                    staging.root.path
                    / self.runner.MANIFEST_FILE_NAME,
                    staging.observers.path,
                    staging.root.path,
                    roots.generations.path,
                ],
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_fsync_failures(
        self,
    ) -> None:
        for failure_call in range(1, 6):
            with self.subTest(
                failure_call=failure_call
            ):
                values = (
                    self.make_generation_sync_inputs()
                )

                (
                    roots,
                    cycle,
                    staging,
                    manifest,
                    reports,
                    deadline,
                ) = values

                original = os.fsync
                calls = {
                    "value": 0,
                }

                def controlled(descriptor):
                    calls["value"] += 1

                    if (
                        calls["value"]
                        == failure_call
                    ):
                        raise OSError(
                            "forced fsync failure"
                        )

                    return original(
                        descriptor
                    )

                try:
                    with mock.patch.object(
                        self.runner.os,
                        "fsync",
                        side_effect=controlled,
                    ):
                        with self.assertRaises(
                            self.runner.RunnerFailure
                        ) as caught:
                            self.runner.synchronize_generation(
                                roots,
                                staging,
                                manifest,
                                reports,
                                deadline,
                            )

                    self.assertEqual(
                        caught.exception.exit_code,
                        self.runner.EXIT_STRUCTURAL,
                    )
                    self.assertEqual(
                        caught.exception.code,
                        "STRUCTURAL_FAILURE",
                    )
                finally:
                    self.restore_final_permissions_fixture(
                        staging
                    )
                    self.reset_manifest_fixture_tree()

    def test_generation_sync_report_change_rejected(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        report = reports[0].path

        try:
            os.chmod(
                report,
                self.runner.STAGING_FILE_MODE,
            )
            report.write_bytes(
                b'{"changed":true}\n'
            )
            os.chmod(
                report,
                self.runner.PROMOTED_FILE_MODE,
            )

            with self.assertRaises(
                self.runner.RunnerFailure
            ):
                self.runner.synchronize_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_manifest_change_rejected(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        manifest_path = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        try:
            os.chmod(
                manifest_path,
                self.runner.STAGING_FILE_MODE,
            )
            manifest_path.write_bytes(
                b'{"changed":true}\n'
            )
            os.chmod(
                manifest_path,
                self.runner.PROMOTED_FILE_MODE,
            )

            with self.assertRaises(
                self.runner.RunnerFailure
            ):
                self.runner.synchronize_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_extra_object_rejected(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        unexpected = (
            staging.root.path
            / "unexpected"
        )

        try:
            os.chmod(
                staging.root.path,
                self.runner.STAGING_MODE,
            )
            unexpected.write_bytes(b"x")
            os.chmod(
                staging.root.path,
                self.runner.PROMOTED_DIRECTORY_MODE,
            )

            with self.assertRaises(
                self.runner.RunnerFailure
            ):
                self.runner.synchronize_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                )
        finally:
            try:
                os.chmod(
                    staging.root.path,
                    self.runner.STAGING_MODE,
                )
                unexpected.unlink()
            except OSError:
                pass

            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_wrong_modes_rejected(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        try:
            os.chmod(
                reports[0].path,
                self.runner.STAGING_FILE_MODE,
            )

            with self.assertRaises(
                self.runner.RunnerFailure
            ):
                self.runner.synchronize_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_sync_preserves_identity(
        self,
    ) -> None:
        values = (
            self.make_generation_sync_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        identities = (
            reports[0].secure.identity,
            manifest.identity,
            staging.observers.identity,
            staging.root.identity,
            roots.generations.identity,
        )

        try:
            self.runner.synchronize_generation(
                roots,
                staging,
                manifest,
                reports,
                deadline,
            )

            self.assertEqual(
                identities,
                (
                    reports[0].secure.identity,
                    manifest.identity,
                    staging.observers.identity,
                    staging.root.identity,
                    roots.generations.identity,
                ),
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )


    def make_generation_promotion_inputs(
        self,
    ):
        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = self.make_generation_sync_inputs()

        self.runner.synchronize_generation(
            roots,
            staging,
            manifest,
            reports,
            deadline,
        )

        return (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        )

    def restore_promoted_fixture(
        self,
        roots,
        staging,
    ) -> None:
        final_path = (
            roots.generations.path
            / staging.cycle.generation_id
        )

        if final_path.exists():
            os.rename(
                final_path,
                staging.root.path,
            )

        self.restore_final_permissions_fixture(
            staging
        )

    def test_generation_promotion_success(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        original_identity = (
            staging.root.identity
        )

        try:
            final_path = (
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    self.runner.load_rename_noreplace(),
                )
            )

            self.assertEqual(
                final_path,
                (
                    roots.generations.path
                    / cycle.generation_id
                ),
            )

            self.assertFalse(
                staging.root.path.exists()
            )

            status = os.lstat(
                final_path
            )

            self.assertEqual(
                self.runner.path_identity(
                    status
                ),
                original_identity,
            )
        finally:
            self.restore_promoted_fixture(
                roots,
                staging,
            )

    def test_generation_promotion_preserves_structure(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        try:
            final_path = (
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    self.runner.load_rename_noreplace(),
                )
            )

            self.assertEqual(
                {
                    item.name
                    for item
                    in final_path.iterdir()
                },
                {
                    self.runner.MANIFEST_FILE_NAME,
                    self.runner.OBSERVERS_DIRECTORY_NAME,
                },
            )

            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        final_path
                    ).st_mode
                ),
                self.runner.PROMOTED_DIRECTORY_MODE,
            )

            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        final_path
                        / self.runner.OBSERVERS_DIRECTORY_NAME
                    ).st_mode
                ),
                self.runner.PROMOTED_DIRECTORY_MODE,
            )
        finally:
            self.restore_promoted_fixture(
                roots,
                staging,
            )

    def test_generation_promotion_destination_collision(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        final_path = (
            roots.generations.path
            / cycle.generation_id
        )

        final_path.mkdir()

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    self.runner.load_rename_noreplace(),
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertTrue(
                staging.root.path.exists()
            )
        finally:
            final_path.rmdir()
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_promotion_extra_object_rejected(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        unexpected = (
            staging.root.path
            / "unexpected"
        )

        try:
            os.chmod(
                staging.root.path,
                self.runner.STAGING_MODE,
            )
            unexpected.write_bytes(b"x")
            os.chmod(
                staging.root.path,
                self.runner.PROMOTED_DIRECTORY_MODE,
            )

            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    self.runner.load_rename_noreplace(),
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertTrue(
                staging.root.path.exists()
            )
        finally:
            try:
                os.chmod(
                    staging.root.path,
                    self.runner.STAGING_MODE,
                )
                unexpected.unlink()
            except OSError:
                pass

            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_promotion_rename_failure_is_structural(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        def failing_rename(*args):
            self.runner.ctypes.set_errno(
                self.runner.errno.EIO
            )
            return -1

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    failing_rename,
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertEqual(
                caught.exception.code,
                "STRUCTURAL_FAILURE",
            )

            self.assertTrue(
                staging.root.path.exists()
            )
        finally:
            self.restore_final_permissions_fixture(
                staging
            )

    def test_generation_promotion_fsync_failure_is_unknown(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        original_fsync = (
            self.runner.os.fsync
        )

        def failing_fsync(descriptor):
            target = os.readlink(
                "/proc/self/fd/"
                + str(descriptor)
            )

            if (
                Path(target)
                == roots.generations.path
            ):
                raise OSError(
                    self.runner.errno.EIO,
                    "forced",
                )

            return original_fsync(
                descriptor
            )

        try:
            with mock.patch.object(
                self.runner.os,
                "fsync",
                side_effect=failing_fsync,
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ) as caught:
                    self.runner.promote_generation(
                        roots,
                        staging,
                        manifest,
                        reports,
                        deadline,
                        self.runner.load_rename_noreplace(),
                    )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_UNKNOWN,
            )

            self.assertEqual(
                caught.exception.code,
                "OUTCOME_UNKNOWN",
            )

            self.assertFalse(
                staging.root.path.exists()
            )

            self.assertTrue(
                (
                    roots.generations.path
                    / cycle.generation_id
                ).exists()
            )
        finally:
            self.restore_promoted_fixture(
                roots,
                staging,
            )

    def test_generation_promotion_uses_noreplace_names(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        real_rename = (
            self.runner.load_rename_noreplace()
        )

        calls = []

        def recording_rename(
            source_fd,
            source_name,
            destination_fd,
            destination_name,
            flags,
        ):
            calls.append(
                (
                    source_fd,
                    os.fsdecode(source_name),
                    destination_fd,
                    os.fsdecode(destination_name),
                    flags,
                )
            )

            return real_rename(
                source_fd,
                source_name,
                destination_fd,
                destination_name,
                flags,
            )

        try:
            self.runner.promote_generation(
                roots,
                staging,
                manifest,
                reports,
                deadline,
                recording_rename,
            )

            self.assertEqual(
                len(calls),
                1,
            )

            self.assertEqual(
                calls[0][1],
                (
                    ".staging-"
                    + cycle.generation_id
                ),
            )

            self.assertEqual(
                calls[0][3],
                cycle.generation_id,
            )

            self.assertEqual(
                calls[0][4],
                self.runner.RENAME_NOREPLACE,
            )

            self.assertEqual(
                calls[0][0],
                calls[0][2],
            )
        finally:
            self.restore_promoted_fixture(
                roots,
                staging,
            )

    def test_generation_promotion_files_unchanged(
        self,
    ) -> None:
        values = (
            self.make_generation_promotion_inputs()
        )

        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = values

        report_content = (
            reports[0].secure.content
        )

        manifest_content = (
            manifest.content
        )

        try:
            final_path = (
                self.runner.promote_generation(
                    roots,
                    staging,
                    manifest,
                    reports,
                    deadline,
                    self.runner.load_rename_noreplace(),
                )
            )

            self.assertEqual(
                (
                    final_path
                    / self.runner.MANIFEST_FILE_NAME
                ).read_bytes(),
                manifest_content,
            )

            self.assertEqual(
                (
                    final_path
                    / self.runner.OBSERVERS_DIRECTORY_NAME
                    / reports[0].path.name
                ).read_bytes(),
                report_content,
            )
        finally:
            self.restore_promoted_fixture(
                roots,
                staging,
            )


    def make_current_generation_inputs(
        self,
    ):
        (
            roots,
            cycle,
            staging,
            manifest,
            reports,
            deadline,
        ) = self.make_generation_promotion_inputs()

        generation_path = (
            self.runner.promote_generation(
                roots,
                staging,
                manifest,
                reports,
                deadline,
                self.runner.load_rename_noreplace(),
            )
        )

        return (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        )

    def install_previous_reference(
        self,
        roots,
    ):
        generation_id = (
            "20000101T000000000000Z-"
            + ("0" * 32)
        )

        generation_path = (
            roots.generations.path
            / generation_id
        )

        generation_path.mkdir(
            mode=self.runner
            .PROMOTED_DIRECTORY_MODE
        )

        os.chmod(
            generation_path,
            self.runner
            .PROMOTED_DIRECTORY_MODE,
        )

        reference_path = (
            roots.state.path
            / self.runner
            .REFERENCE_FILE_NAME
        )

        reference_path.write_bytes(
            (
                generation_id
                + "\n"
            ).encode("utf-8")
        )

        os.chmod(
            reference_path,
            self.runner.REFERENCE_MODE,
        )

        reference = (
            self.runner
            .validate_current_reference(
                roots.state,
                roots.generations,
            )
        )

        updated_roots = (
            self.runner.RootsContext(
                state=roots.state,
                runtime=roots.runtime,
                generations=roots.generations,
                reference=reference,
            )
        )

        return (
            updated_roots,
            generation_path,
            reference_path,
        )

    def cleanup_current_generation_fixture(
        self,
        roots,
        staging,
        previous_generation=None,
    ) -> None:
        reference_path = (
            roots.state.path
            / self.runner
            .REFERENCE_FILE_NAME
        )

        try:
            reference_path.unlink()
        except FileNotFoundError:
            pass

        if (
            previous_generation is not None
            and previous_generation.exists()
        ):
            previous_generation.rmdir()

        self.restore_promoted_fixture(
            roots,
            staging,
        )

    def test_current_generation_update_success(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        try:
            reference = (
                self.runner
                .update_current_generation(
                    roots,
                    staging,
                    generation_path,
                    deadline,
                )
            )

            self.assertEqual(
                reference.generation_id,
                cycle.generation_id,
            )

            self.assertEqual(
                reference.generation_path,
                generation_path,
            )

            self.assertEqual(
                reference.secure.content,
                (
                    cycle.generation_id
                    + "\n"
                ).encode("utf-8"),
            )

            self.assertEqual(
                stat.S_IMODE(
                    os.lstat(
                        reference.path
                    ).st_mode
                ),
                self.runner.REFERENCE_MODE,
            )

            self.assertFalse(
                (
                    roots.state.path
                    / (
                        ".current-generation-"
                        + cycle.generation_id
                        + ".tmp"
                    )
                ).exists()
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )

    def test_current_generation_replaces_previous(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        (
            roots,
            previous_generation,
            reference_path,
        ) = self.install_previous_reference(
            roots
        )

        try:
            reference = (
                self.runner
                .update_current_generation(
                    roots,
                    staging,
                    generation_path,
                    deadline,
                )
            )

            self.assertEqual(
                reference.generation_id,
                cycle.generation_id,
            )

            self.assertTrue(
                previous_generation.exists()
            )

            self.assertEqual(
                reference_path.read_bytes(),
                (
                    cycle.generation_id
                    + "\n"
                ).encode("utf-8"),
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
                previous_generation,
            )

    def test_current_generation_absent_race_rejected(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        reference_path = (
            roots.state.path
            / self.runner
            .REFERENCE_FILE_NAME
        )

        reference_path.write_bytes(
            (
                cycle.generation_id
                + "\n"
            ).encode("utf-8")
        )

        os.chmod(
            reference_path,
            self.runner.REFERENCE_MODE,
        )

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.update_current_generation(
                    roots,
                    staging,
                    generation_path,
                    deadline,
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )

    def test_current_generation_previous_changed_rejected(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        (
            roots,
            previous_generation,
            reference_path,
        ) = self.install_previous_reference(
            roots
        )

        previous_identity = (
            roots.reference.secure.identity
        )

        replacement_path = (
            reference_path.parent
            / ".current-generation-test-replacement"
        )

        replacement_path.write_bytes(
            reference_path.read_bytes()
        )

        os.chmod(
            replacement_path,
            self.runner.REFERENCE_MODE,
        )

        os.replace(
            replacement_path,
            reference_path,
        )

        replacement_status = os.lstat(
            reference_path
        )

        self.assertNotEqual(
            (
                replacement_status.st_dev,
                replacement_status.st_ino,
            ),
            (
                previous_identity.device,
                previous_identity.inode,
            ),
        )

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.update_current_generation(
                    roots,
                    staging,
                    generation_path,
                    deadline,
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
                previous_generation,
            )

    def test_current_generation_temporary_collision(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        temporary = (
            roots.state.path
            / (
                ".current-generation-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        temporary.write_bytes(b"x")

        try:
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.update_current_generation(
                    roots,
                    staging,
                    generation_path,
                    deadline,
                )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertFalse(
                (
                    roots.state.path
                    / self.runner
                    .REFERENCE_FILE_NAME
                ).exists()
            )
        finally:
            temporary.unlink()
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )

    def test_current_generation_rename_failure_structural(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        temporary = (
            roots.state.path
            / (
                ".current-generation-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        try:
            with mock.patch.object(
                self.runner.os,
                "rename",
                side_effect=OSError(
                    self.runner.errno.EIO,
                    "forced",
                ),
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ) as caught:
                    self.runner.update_current_generation(
                        roots,
                        staging,
                        generation_path,
                        deadline,
                    )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertFalse(
                temporary.exists()
            )

            self.assertFalse(
                (
                    roots.state.path
                    / self.runner
                    .REFERENCE_FILE_NAME
                ).exists()
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )

    def test_current_generation_temporary_fsync_failure(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        temporary = (
            roots.state.path
            / (
                ".current-generation-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        try:
            with mock.patch.object(
                self.runner.os,
                "fsync",
                side_effect=OSError(
                    self.runner.errno.EIO,
                    "forced",
                ),
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ) as caught:
                    self.runner.update_current_generation(
                        roots,
                        staging,
                        generation_path,
                        deadline,
                    )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_STRUCTURAL,
            )

            self.assertFalse(
                temporary.exists()
            )

            self.assertFalse(
                (
                    roots.state.path
                    / self.runner
                    .REFERENCE_FILE_NAME
                ).exists()
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )

    def test_current_generation_state_fsync_failure_unknown(
        self,
    ) -> None:
        (
            roots,
            cycle,
            staging,
            generation_path,
            deadline,
        ) = self.make_current_generation_inputs()

        original_fsync = (
            self.runner.os.fsync
        )

        calls = {
            "value": 0,
        }

        def controlled_fsync(
            descriptor,
        ):
            calls["value"] += 1

            if calls["value"] == 2:
                raise OSError(
                    self.runner.errno.EIO,
                    "forced",
                )

            return original_fsync(
                descriptor
            )

        reference_path = (
            roots.state.path
            / self.runner
            .REFERENCE_FILE_NAME
        )

        try:
            with mock.patch.object(
                self.runner.os,
                "fsync",
                side_effect=controlled_fsync,
            ):
                with self.assertRaises(
                    self.runner.RunnerFailure
                ) as caught:
                    self.runner.update_current_generation(
                        roots,
                        staging,
                        generation_path,
                        deadline,
                    )

            self.assertEqual(
                caught.exception.exit_code,
                self.runner.EXIT_UNKNOWN,
            )

            self.assertEqual(
                caught.exception.code,
                "OUTCOME_UNKNOWN",
            )

            self.assertTrue(
                reference_path.exists()
            )

            self.assertEqual(
                reference_path.read_bytes(),
                (
                    cycle.generation_id
                    + "\n"
                ).encode("utf-8"),
            )
        finally:
            self.cleanup_current_generation_fixture(
                roots,
                staging,
            )


    def test_runner_report_success(
        self,
    ) -> None:
        state = (
            self.runner.InvocationState()
        )

        state.facts.lock_acquired = True
        state.facts.cycle_started = True
        state.facts.generation_id = (
            "20260820T000000000000Z-"
            + ("1" * 32)
        )
        state.facts.generation_state = (
            "COMPLETE"
        )
        state.facts.declared = 1
        state.facts.successful = 1
        state.facts.failed = 0
        state.facts.reports_written = 1
        state.facts.successful_modules = [
            "cpu"
        ]
        state.facts.failed_modules = []
        state.facts.generation_promoted = (
            True
        )
        state.facts.current_generation_updated = (
            True
        )

        self.runner.apply_invocation_result(
            state,
            self.runner.EXIT_SUCCESS,
            "SUCCESS",
        )

        project_root = (
            Path(
                self.runner.__file__
            ).resolve().parent.parent
        )

        validator = (
            self.runner
            .load_runner_report_validator(
                project_root
            )
        )

        content = (
            self.runner
            .build_validated_runner_report(
                state,
                validator,
            )
        )

        document = json.loads(
            content.decode("utf-8")
        )

        self.assertEqual(
            document["module"],
            "observer-runner",
        )

        self.assertEqual(
            document["version"],
            "2.0.0",
        )

        self.assertEqual(
            document["status"],
            "OK",
        )

        self.assertEqual(
            document["confidence"],
            100,
        )

        self.assertEqual(
            document["facts"][
                "result_code"
            ],
            "SUCCESS",
        )

        self.assertTrue(
            content.endswith(b"\n")
        )

    def test_runner_report_partial(
        self,
    ) -> None:
        state = (
            self.runner.InvocationState()
        )

        state.facts.generation_state = (
            "PARTIAL"
        )
        state.facts.generation_promoted = (
            True
        )
        state.facts.current_generation_updated = (
            True
        )

        self.runner.apply_invocation_result(
            state,
            self.runner.EXIT_PARTIAL,
            "GENERATION_PARTIAL",
        )

        document = (
            self.runner
            .build_runner_report_document(
                state
            )
        )

        self.assertEqual(
            document["status"],
            "WARNING",
        )

        self.assertEqual(
            document["confidence"],
            100,
        )

        self.assertEqual(
            document["facts"][
                "result_code"
            ],
            "GENERATION_PARTIAL",
        )

    def test_runner_report_unknown(
        self,
    ) -> None:
        state = (
            self.runner.InvocationState()
        )

        state.facts.generation_promoted = (
            True
        )
        state.facts.current_generation_updated = (
            None
        )

        self.runner.apply_invocation_result(
            state,
            self.runner.EXIT_UNKNOWN,
            "OUTCOME_UNKNOWN",
            uncertain=True,
        )

        document = (
            self.runner
            .build_runner_report_document(
                state
            )
        )

        self.assertEqual(
            document["status"],
            "UNKNOWN",
        )

        self.assertEqual(
            document["confidence"],
            0,
        )

        self.assertIsNone(
            document["facts"][
                "current_generation_updated"
            ]
        )

    def test_cleanup_owned_staging_final_permissions(
        self,
    ) -> None:
        (
            roots,
            _cycle,
            staging,
            _manifest,
            _reports,
            _deadline,
        ) = (
            self.make_generation_promotion_inputs()
        )

        project_root = (
            Path(
                self.runner.__file__
            ).resolve().parent.parent
        )

        configuration = (
            self.runner
            .load_configuration(
                project_root
            )
        )

        staging_path = (
            staging.root.path
        )

        self.runner.cleanup_owned_staging(
            roots,
            staging,
            configuration,
        )

        self.assertFalse(
            staging_path.exists()
        )


    def test_manifest_serialization_deterministic(
        self,
    ):
        document = {
            "b": 2,
            "a": 1,
        }

        first = (
            self.runner
            .serialize_manifest_document(
                document
            )
        )
        second = (
            self.runner
            .serialize_manifest_document(
                document
            )
        )

        self.assertEqual(
            first,
            second,
        )

    def test_manifest_serialization_key_order(
        self,
    ):
        first = {
            "b": 2,
            "a": 1,
        }
        second = {
            "a": 1,
            "b": 2,
        }

        self.assertEqual(
            self.runner
            .serialize_manifest_document(
                first
            ),
            self.runner
            .serialize_manifest_document(
                second
            ),
        )
        self.assertEqual(
            self.runner
            .serialize_manifest_document(
                first
            ),
            b'{"a":1,"b":2}\n',
        )

    def test_manifest_serialization_utf8(
        self,
    ):
        content = (
            self.runner
            .serialize_manifest_document(
                {
                    "texto": "ação",
                }
            )
        )

        self.assertEqual(
            content,
            '{"texto":"ação"}\n'.encode(
                "utf-8"
            ),
        )
        self.assertNotIn(
            b"\\u",
            content,
        )

    def test_manifest_serialization_compact(
        self,
    ):
        content = (
            self.runner
            .serialize_manifest_document(
                {
                    "a": 1,
                    "b": 2,
                }
            )
        )

        self.assertEqual(
            content,
            b'{"a":1,"b":2}\n',
        )
        self.assertNotIn(
            b": ",
            content,
        )
        self.assertNotIn(
            b", ",
            content,
        )

    def test_manifest_serialization_final_newline(
        self,
    ):
        content = (
            self.runner
            .serialize_manifest_document(
                {
                    "a": 1,
                }
            )
        )

        self.assertTrue(
            content.endswith(
                b"\n"
            )
        )
        self.assertEqual(
            content.count(
                b"\n"
            ),
            1,
        )

    def test_manifest_serialization_returns_bytes(
        self,
    ):
        content = (
            self.runner
            .serialize_manifest_document(
                {
                    "a": 1,
                }
            )
        )

        self.assertIsInstance(
            content,
            bytes,
        )

    def test_manifest_serialization_exact_limit(
        self,
    ):
        import json

        overhead = len(
            (
                json.dumps(
                    {
                        "payload": "",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode(
                "utf-8"
            )
        )

        payload = (
            "x"
            * (
                self.runner
                .MANIFEST_MAX_BYTES
                - overhead
            )
        )

        content = (
            self.runner
            .serialize_manifest_document(
                {
                    "payload": payload,
                }
            )
        )

        self.assertEqual(
            len(content),
            self.runner
            .MANIFEST_MAX_BYTES,
        )

    def test_manifest_serialization_above_limit(
        self,
    ):
        import json

        overhead = len(
            (
                json.dumps(
                    {
                        "payload": "",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode(
                "utf-8"
            )
        )

        payload = (
            "x"
            * (
                self.runner
                .MANIFEST_MAX_BYTES
                - overhead
                + 1
            )
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ) as caught:
            (
                self.runner
                .serialize_manifest_document(
                    {
                        "payload": payload,
                    }
                )
            )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            caught.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_manifest_serialization_non_finite(
        self,
    ):
        with self.assertRaises(
            self.runner.RunnerFailure
        ) as caught:
            (
                self.runner
                .serialize_manifest_document(
                    {
                        "value": float("nan"),
                    }
                )
            )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            caught.exception.code,
            "STRUCTURAL_FAILURE",
        )

    def test_manifest_persistence_success(
        self,
    ):
        (
            _roots,
            _cycle,
            staging,
            _secure,
        ) = self.persist_manifest_sample()

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        self.assertTrue(
            manifest.is_file()
        )

    def test_manifest_persistence_temporary_name(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )
        content = b'{"a":1}\n'
        opened_names = []
        original_open = self.runner.os.open

        def controlled_open(
            path,
            flags,
            *args,
            **kwargs,
        ):
            if (
                isinstance(path, str)
                and path.startswith(
                    ".manifest-"
                )
            ):
                opened_names.append(path)

            return original_open(
                path,
                flags,
                *args,
                **kwargs,
            )

        with mock.patch.object(
            self.runner.os,
            "open",
            side_effect=controlled_open,
        ):
            self.runner.persist_manifest(
                roots,
                staging,
                content,
                (
                    self.runner
                    .load_rename_noreplace()
                ),
            )

        self.assertEqual(
            opened_names,
            [
                (
                    ".manifest-"
                    + cycle.generation_id
                    + ".tmp"
                )
            ],
        )

    def test_manifest_persistence_exact_content(
        self,
    ):
        content = (
            '{"texto":"ação"}\n'
            .encode("utf-8")
        )

        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        self.runner.persist_manifest(
            roots,
            staging,
            content,
            (
                self.runner
                .load_rename_noreplace()
            ),
        )

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        self.assertEqual(
            manifest.read_bytes(),
            content,
        )

    def test_manifest_persistence_mode(
        self,
    ):
        (
            _roots,
            _cycle,
            staging,
            _secure,
        ) = self.persist_manifest_sample()

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        self.assertEqual(
            stat.S_IMODE(
                os.lstat(manifest).st_mode
            ),
            self.runner.STAGING_FILE_MODE,
        )

    def test_manifest_persistence_single_link(
        self,
    ):
        (
            _roots,
            _cycle,
            staging,
            _secure,
        ) = self.persist_manifest_sample()

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        self.assertEqual(
            os.lstat(manifest).st_nlink,
            1,
        )

    def test_manifest_persistence_no_temporary_after_success(
        self,
    ):
        (
            _roots,
            cycle,
            staging,
            _secure,
        ) = self.persist_manifest_sample()

        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        self.assertFalse(
            temporary.exists()
        )

    def test_manifest_persistence_destination_collision(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )
        manifest.write_bytes(
            b"preserved\n"
        )
        manifest.chmod(
            self.runner.STAGING_FILE_MODE
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ) as caught:
            self.runner.persist_manifest(
                roots,
                staging,
                b'{"a":1}\n',
                (
                    self.runner
                    .load_rename_noreplace()
                ),
            )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertEqual(
            caught.exception.code,
            "STRUCTURAL_FAILURE",
        )
        self.assertEqual(
            manifest.read_bytes(),
            b"preserved\n",
        )

    def test_manifest_persistence_temporary_collision(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )
        temporary.write_bytes(
            b"foreign\n"
        )
        temporary.chmod(
            self.runner.STAGING_FILE_MODE
        )

        with self.assertRaises(
            self.runner.RunnerFailure
        ):
            self.runner.persist_manifest(
                roots,
                staging,
                b'{"a":1}\n',
                (
                    self.runner
                    .load_rename_noreplace()
                ),
            )

        self.assertEqual(
            temporary.read_bytes(),
            b"foreign\n",
        )
        self.assertFalse(
            (
                staging.root.path
                / self.runner
                .MANIFEST_FILE_NAME
            ).exists()
        )

    def test_manifest_persistence_partial_write(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )
        content = b'{"abcdefgh":123456789}\n'
        original_write = self.runner.os.write

        def controlled_write(
            descriptor,
            data,
        ):
            return original_write(
                descriptor,
                data[:3],
            )

        with mock.patch.object(
            self.runner.os,
            "write",
            side_effect=controlled_write,
        ):
            self.runner.persist_manifest(
                roots,
                staging,
                content,
                (
                    self.runner
                    .load_rename_noreplace()
                ),
            )

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )

        self.assertEqual(
            manifest.read_bytes(),
            content,
        )

    def test_manifest_persistence_write_failure_cleanup(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        with mock.patch.object(
            self.runner.os,
            "write",
            side_effect=OSError(
                self.runner.errno.EIO,
                "forced",
            ),
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.persist_manifest(
                    roots,
                    staging,
                    b'{"a":1}\n',
                    (
                        self.runner
                        .load_rename_noreplace()
                    ),
                )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertFalse(
            temporary.exists()
        )
        self.assertFalse(
            (
                staging.root.path
                / self.runner
                .MANIFEST_FILE_NAME
            ).exists()
        )

    def test_manifest_persistence_temporary_fsync_failure_cleanup(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        with mock.patch.object(
            self.runner.os,
            "fsync",
            side_effect=OSError(
                self.runner.errno.EIO,
                "forced",
            ),
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.persist_manifest(
                    roots,
                    staging,
                    b'{"a":1}\n',
                    (
                        self.runner
                        .load_rename_noreplace()
                    ),
                )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertFalse(
            temporary.exists()
        )
        self.assertFalse(
            (
                staging.root.path
                / self.runner
                .MANIFEST_FILE_NAME
            ).exists()
        )

    def test_manifest_persistence_rename_failure_cleanup(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )

        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        def failing_renameat2(*_args):
            return -1

        with mock.patch.object(
            self.runner.ctypes,
            "get_errno",
            return_value=self.runner.errno.EIO,
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.persist_manifest(
                    roots,
                    staging,
                    b'{"a":1}\n',
                    failing_renameat2,
                )

        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertFalse(
            temporary.exists()
        )
        self.assertFalse(
            (
                staging.root.path
                / self.runner
                .MANIFEST_FILE_NAME
            ).exists()
        )

    def test_manifest_persistence_staging_fsync_failure_preserves_manifest(
        self,
    ):
        roots, cycle, staging = (
            self.make_manifest_staging()
        )
        content = b'{"a":1}\n'
        original_fsync = self.runner.os.fsync
        calls = 0

        def controlled_fsync(
            descriptor,
        ):
            nonlocal calls
            calls += 1

            if calls == 2:
                raise OSError(
                    self.runner.errno.EIO,
                    "forced",
                )

            return original_fsync(
                descriptor
            )

        with mock.patch.object(
            self.runner.os,
            "fsync",
            side_effect=controlled_fsync,
        ):
            with self.assertRaises(
                self.runner.RunnerFailure
            ) as caught:
                self.runner.persist_manifest(
                    roots,
                    staging,
                    content,
                    (
                        self.runner
                        .load_rename_noreplace()
                    ),
                )

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )
        temporary = (
            staging.root.path
            / (
                ".manifest-"
                + cycle.generation_id
                + ".tmp"
            )
        )

        self.assertEqual(
            calls,
            2,
        )
        self.assertEqual(
            caught.exception.exit_code,
            self.runner.EXIT_STRUCTURAL,
        )
        self.assertTrue(
            manifest.is_file()
        )
        self.assertEqual(
            manifest.read_bytes(),
            content,
        )
        self.assertFalse(
            temporary.exists()
        )

    def test_manifest_persistence_secure_content_matches_final(
        self,
    ):
        (
            _roots,
            _cycle,
            staging,
            secure,
        ) = self.persist_manifest_sample()

        manifest = (
            staging.root.path
            / self.runner.MANIFEST_FILE_NAME
        )
        status = os.lstat(
            manifest
        )

        self.assertEqual(
            secure.identity,
            self.runner.path_identity(
                status
            ),
        )
        self.assertEqual(
            secure.size,
            status.st_size,
        )
        self.assertEqual(
            secure.mtime_ns,
            status.st_mtime_ns,
        )
        self.assertEqual(
            secure.ctime_ns,
            status.st_ctime_ns,
        )
        self.assertEqual(
            secure.content,
            manifest.read_bytes(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
