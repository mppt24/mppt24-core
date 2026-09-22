#!/usr/bin/python3 -I
"""Testes do Registo de Observers MPPT24 1.0.0."""

import copy
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "config" / "observer-registry.json"
SCHEMA = (
    ROOT
    / "schemas"
    / "observer-registry"
    / "1.0.0"
    / "observer-registry.schema.json"
)
REPORT_VALIDATOR = ROOT / "core" / "validate-report.py"

EXPECTED_DIALECT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_ID = "urn:mppt24:schema:observer-registry:1.0.0"
REGISTRY_MAX_BYTES = 65536

EXPECTED_MODULES = [
    "observer-cpu",
    "observer-memory",
    "observer-network",
    "observer-services",
    "observer-ssh",
    "observer-storage",
    "observer-system",
]

EXPECTED_LIMITS = {
    "observer_timeout_seconds": 30,
    "stdout_max_bytes": 262144,
    "stderr_max_bytes": 65536,
    "report_max_bytes": 262144,
    "json_max_depth": 32,
    "max_observers": 32,
}

MODULE_DECLARATION = re.compile(
    r'^readonly MODULE_NAME="([^"]+)"$',
    re.MULTILINE,
)
VERSION_DECLARATION = re.compile(
    r'^readonly MODULE_VERSION="([^"]+)"$',
    re.MULTILINE,
)


class DuplicateKeyError(ValueError):
    """Chave JSON repetida."""


class NonFiniteNumberError(ValueError):
    """Número não pertencente a JSON."""


def reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result = {}

    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value

    return result


def reject_non_finite(value: str) -> None:
    raise NonFiniteNumberError(value)


def load_json_strict(path: Path) -> object:
    content = path.read_bytes()

    if len(content) > REGISTRY_MAX_BYTES:
        raise ValueError("documento acima do limite")

    text = content.decode("utf-8", errors="strict")

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_finite,
    )


def container_depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max(
            (container_depth(item) for item in value.values()),
            default=0,
        )

    if isinstance(value, list):
        return 1 + max(
            (container_depth(item) for item in value),
            default=0,
        )

    return 0


def external_references(document: object) -> list[str]:
    external = []
    stack = [document]

    while stack:
        value = stack.pop()

        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"}:
                    if not isinstance(child, str) or not child.startswith("#"):
                        external.append(str(child))
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)

    return external


def validate_semantics(
    document: dict[str, object],
    project_root: Path,
    *,
    check_installation: bool = True,
) -> None:
    limits = document["limits"]
    observers = document["observers"]

    if limits != EXPECTED_LIMITS:
        raise ValueError("limites incompatíveis")

    if len(observers) > limits["max_observers"]:
        raise ValueError("número de Observers acima do limite")

    modules = [entry["module"] for entry in observers]
    executables = [entry["executable"] for entry in observers]

    if modules != EXPECTED_MODULES:
        raise ValueError("lista ou ordem de módulos incompatível")

    if len(modules) != len(set(modules)):
        raise ValueError("módulo duplicado")

    if len(executables) != len(set(executables)):
        raise ValueError("executável duplicado")

    for entry in observers:
        module = entry["module"]
        executable = entry["executable"]
        path = PurePosixPath(executable)

        if path.is_absolute():
            raise ValueError("caminho absoluto")

        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("componente de caminho inválido")

        expected = f"observer/{module}.sh"
        if executable != expected:
            raise ValueError("módulo e executável divergentes")

        if entry["required"] is not True:
            raise ValueError("Observer não obrigatório")

        if entry["module_versions"] != ["1.0.0"]:
            raise ValueError("versão de módulo incompatível")

        if entry["output_contract"] != document["report_contract"]:
            raise ValueError("contrato de saída incompatível")

        if not check_installation:
            continue

        installed = project_root / executable
        installed_status = os.lstat(installed)

        if stat.S_ISLNK(installed_status.st_mode):
            raise ValueError("link simbólico")

        if not stat.S_ISREG(installed_status.st_mode):
            raise ValueError("executável não regular")

        if not os.access(installed, os.X_OK):
            raise ValueError("ficheiro não executável")

        source = installed.read_text(encoding="utf-8")
        module_match = MODULE_DECLARATION.search(source)
        version_match = VERSION_DECLARATION.search(source)

        if module_match is None or module_match.group(1) != module:
            raise ValueError("identidade declarada divergente")

        if (
            version_match is None
            or version_match.group(1) not in entry["module_versions"]
        ):
            raise ValueError("versão declarada divergente")


class ObserverRegistryContractTest(unittest.TestCase):
    """Validar o registo, o schema e a instalação autorizada."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mppt24-observer-registry-"
        )
        self.temp_path = Path(self.temporary.name)

        self.registry = load_json_strict(REGISTRY)
        self.schema = load_json_strict(SCHEMA)

        Draft202012Validator.check_schema(self.schema)
        self.schema_validator = Draft202012Validator(self.schema)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(
        self,
        document: object,
        name: str = "registry.json",
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
        name: str = "registry.json",
    ) -> Path:
        path = self.temp_path / name
        path.write_bytes(content)
        return path

    def schema_errors(
        self,
        document: object,
    ) -> list[object]:
        return list(self.schema_validator.iter_errors(document))

    def assert_schema_rejects(
        self,
        document: object,
    ) -> None:
        self.assertNotEqual(self.schema_errors(document), [])

    def test_schema_identity_and_dialect(self) -> None:
        self.assertEqual(
            self.schema["$schema"],
            EXPECTED_DIALECT,
        )
        self.assertEqual(
            self.schema["$id"],
            EXPECTED_SCHEMA_ID,
        )

    def test_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(self.schema)

    def test_schema_has_no_external_references(self) -> None:
        self.assertEqual(
            external_references(self.schema),
            [],
        )

    def test_official_registry_is_structurally_valid(self) -> None:
        self.assertEqual(
            self.schema_errors(self.registry),
            [],
        )

    def test_official_registry_is_semantically_valid(self) -> None:
        validate_semantics(
            self.registry,
            ROOT,
        )

    def test_official_registry_size(self) -> None:
        self.assertLessEqual(
            REGISTRY.stat().st_size,
            REGISTRY_MAX_BYTES,
        )

    def test_official_module_order(self) -> None:
        modules = [
            entry["module"]
            for entry in self.registry["observers"]
        ]
        self.assertEqual(modules, EXPECTED_MODULES)

    def test_official_registry_has_seven_observers(self) -> None:
        self.assertEqual(
            len(self.registry["observers"]),
            7,
        )

    def test_invalid_utf8(self) -> None:
        path = self.write_bytes(b"\xff\xfe")

        with self.assertRaises(UnicodeDecodeError):
            load_json_strict(path)

    def test_duplicate_key(self) -> None:
        path = self.write_bytes(
            b'{"registry_version":"1.0.0",'
            b'"registry_version":"9.9.9"}'
        )

        with self.assertRaises(DuplicateKeyError):
            load_json_strict(path)

    def test_non_finite_numbers(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                path = self.write_bytes(
                    f'{{"value":{value}}}'.encode("utf-8"),
                    name=f"{value}.json",
                )

                with self.assertRaises(NonFiniteNumberError):
                    load_json_strict(path)

    def test_empty_json_document(self) -> None:
        path = self.write_bytes(b"")

        with self.assertRaises(json.JSONDecodeError):
            load_json_strict(path)

    def test_truncated_json_document(self) -> None:
        path = self.write_bytes(b"{")

        with self.assertRaises(json.JSONDecodeError):
            load_json_strict(path)

    def test_additional_json_document(self) -> None:
        path = self.write_bytes(b"{} {}")

        with self.assertRaises(json.JSONDecodeError):
            load_json_strict(path)

    def test_registry_size_limit(self) -> None:
        path = self.write_bytes(
            b"{" + b" " * REGISTRY_MAX_BYTES
        )

        with self.assertRaisesRegex(
            ValueError,
            "acima do limite",
        ):
            load_json_strict(path)

    def test_missing_top_level_fields(self) -> None:
        for field in (
            "registry_version",
            "report_contract",
            "limits",
            "observers",
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.registry)
                document.pop(field)
                self.assert_schema_rejects(document)

    def test_unknown_top_level_property(self) -> None:
        document = copy.deepcopy(self.registry)
        document["unexpected"] = True

        self.assert_schema_rejects(document)

    def test_wrong_top_level_type(self) -> None:
        self.assert_schema_rejects([])

    def test_incompatible_registry_version(self) -> None:
        document = copy.deepcopy(self.registry)
        document["registry_version"] = "2.0.0"

        self.assert_schema_rejects(document)

    def test_incompatible_report_contract(self) -> None:
        document = copy.deepcopy(self.registry)
        document["report_contract"] = "2.0.0"

        self.assert_schema_rejects(document)

    def test_missing_limits(self) -> None:
        for field in EXPECTED_LIMITS:
            with self.subTest(field=field):
                document = copy.deepcopy(self.registry)
                document["limits"].pop(field)
                self.assert_schema_rejects(document)

    def test_incorrect_limits(self) -> None:
        for field, expected in EXPECTED_LIMITS.items():
            with self.subTest(field=field):
                document = copy.deepcopy(self.registry)
                document["limits"][field] = expected + 1
                self.assert_schema_rejects(document)

    def test_non_integer_limits(self) -> None:
        for field in EXPECTED_LIMITS:
            with self.subTest(field=field):
                document = copy.deepcopy(self.registry)
                document["limits"][field] = 1.5
                self.assert_schema_rejects(document)

    def test_unknown_limit(self) -> None:
        document = copy.deepcopy(self.registry)
        document["limits"]["unexpected"] = 1

        self.assert_schema_rejects(document)

    def test_empty_observer_list(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"] = []

        self.assert_schema_rejects(document)

    def test_observer_list_above_maximum(self) -> None:
        document = copy.deepcopy(self.registry)
        entry = copy.deepcopy(document["observers"][0])
        document["observers"] = [
            copy.deepcopy(entry)
            for _index in range(33)
        ]

        self.assert_schema_rejects(document)

    def test_missing_observer_fields(self) -> None:
        fields = (
            "module",
            "executable",
            "required",
            "module_versions",
            "output_contract",
        )

        for field in fields:
            with self.subTest(field=field):
                document = copy.deepcopy(self.registry)
                document["observers"][0].pop(field)
                self.assert_schema_rejects(document)

    def test_unknown_observer_property(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][0]["unexpected"] = True

        self.assert_schema_rejects(document)

    def test_invalid_module_names(self) -> None:
        values = (
            "",
            "Observer-cpu",
            "observer cpu",
            "-observer-cpu",
            "observer-cpu-",
            "observer--cpu",
        )

        for value in values:
            with self.subTest(value=value):
                document = copy.deepcopy(self.registry)
                document["observers"][0]["module"] = value
                self.assert_schema_rejects(document)

    def test_invalid_executable_paths(self) -> None:
        values = (
            "",
            "/observer/observer-cpu.sh",
            "observer/../observer-cpu.sh",
            "observer//observer-cpu.sh",
            "./observer/observer-cpu.sh",
            "observer/observer-cpu",
            "runner/observer-cpu.sh",
        )

        for value in values:
            with self.subTest(value=value):
                document = copy.deepcopy(self.registry)
                document["observers"][0]["executable"] = value
                self.assert_schema_rejects(document)

    def test_optional_observer_is_rejected(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][0]["required"] = False

        self.assert_schema_rejects(document)

    def test_incompatible_module_versions(self) -> None:
        values = (
            [],
            ["2.0.0"],
            ["1.0.0", "2.0.0"],
        )

        for value in values:
            with self.subTest(value=value):
                document = copy.deepcopy(self.registry)
                document["observers"][0]["module_versions"] = value
                self.assert_schema_rejects(document)

    def test_incompatible_output_contract(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][0]["output_contract"] = "2.0.0"

        self.assert_schema_rejects(document)

    def make_temporary_installation(self) -> Path:
        project_root = self.temp_path / "installation"

        for entry in self.registry["observers"]:
            source = ROOT / entry["executable"]
            target = project_root / entry["executable"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            target.chmod(0o755)

        return project_root

    def test_semantics_reject_missing_observer(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"].pop()

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_semantics_reject_reordered_observers(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][0], document["observers"][1] = (
            document["observers"][1],
            document["observers"][0],
        )

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_semantics_reject_duplicate_module(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][1]["module"] = (
            document["observers"][0]["module"]
        )

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_semantics_reject_duplicate_executable(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][1]["executable"] = (
            document["observers"][0]["executable"]
        )

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_semantics_reject_module_path_mismatch(self) -> None:
        document = copy.deepcopy(self.registry)
        document["observers"][0]["executable"] = (
            "observer/observer-memory.sh"
        )

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_semantics_reject_incompatible_limits(self) -> None:
        document = copy.deepcopy(self.registry)
        document["limits"]["json_max_depth"] = 64

        with self.assertRaises(ValueError):
            validate_semantics(
                document,
                ROOT,
                check_installation=False,
            )

    def test_temporary_installation_is_valid(self) -> None:
        project_root = self.make_temporary_installation()

        validate_semantics(
            self.registry,
            project_root,
        )

    def test_missing_executable(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        (project_root / entry["executable"]).unlink()

        with self.assertRaises(FileNotFoundError):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_directory_instead_of_executable(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        target = project_root / entry["executable"]
        target.unlink()
        target.mkdir()

        with self.assertRaisesRegex(
            ValueError,
            "não regular",
        ):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_symbolic_link_executable(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        target = project_root / entry["executable"]
        target.unlink()
        target.symlink_to(ROOT / entry["executable"])

        with self.assertRaisesRegex(
            ValueError,
            "link simbólico",
        ):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_non_executable_file(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        target = project_root / entry["executable"]
        target.chmod(0o644)

        with self.assertRaisesRegex(
            ValueError,
            "não executável",
        ):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_declared_module_mismatch(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        target = project_root / entry["executable"]
        source = target.read_text(encoding="utf-8")
        source = source.replace(
            'readonly MODULE_NAME="observer-cpu"',
            'readonly MODULE_NAME="observer-other"',
            1,
        )
        target.write_text(source, encoding="utf-8")
        target.chmod(0o755)

        with self.assertRaisesRegex(
            ValueError,
            "identidade declarada",
        ):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_declared_version_mismatch(self) -> None:
        project_root = self.make_temporary_installation()
        entry = self.registry["observers"][0]
        target = project_root / entry["executable"]
        source = target.read_text(encoding="utf-8")
        source = source.replace(
            'readonly MODULE_VERSION="1.0.0"',
            'readonly MODULE_VERSION="2.0.0"',
            1,
        )
        target.write_text(source, encoding="utf-8")
        target.chmod(0o755)

        with self.assertRaisesRegex(
            ValueError,
            "versão declarada",
        ):
            validate_semantics(
                self.registry,
                project_root,
            )

    def test_unregistered_file_does_not_enter_registry(self) -> None:
        project_root = self.make_temporary_installation()
        extra = project_root / "observer" / "observer-extra.sh"
        extra.write_text(
            "#!/usr/bin/env bash\nexit 99\n",
            encoding="utf-8",
        )
        extra.chmod(0o755)

        validate_semantics(
            self.registry,
            project_root,
        )

        registered = {
            entry["executable"]
            for entry in self.registry["observers"]
        }
        self.assertNotIn(
            "observer/observer-extra.sh",
            registered,
        )

    def test_official_observers_respect_registry(self) -> None:
        limits = self.registry["limits"]
        environment = {
            "PATH": (
                "/usr/local/sbin:/usr/local/bin:"
                "/usr/sbin:/usr/bin:/sbin:/bin"
            ),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        }

        for entry in self.registry["observers"]:
            module = entry["module"]
            executable = ROOT / entry["executable"]

            with self.subTest(module=module):
                result = subprocess.run(
                    [str(executable)],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    timeout=limits["observer_timeout_seconds"],
                )

                self.assertEqual(result.returncode, 0)
                self.assertLessEqual(
                    len(result.stdout),
                    limits["stdout_max_bytes"],
                )
                self.assertLessEqual(
                    len(result.stderr),
                    limits["stderr_max_bytes"],
                )
                self.assertLessEqual(
                    len(result.stdout),
                    limits["report_max_bytes"],
                )

                report_path = self.temp_path / f"{module}.json"
                report_path.write_bytes(result.stdout)

                validation = subprocess.run(
                    [
                        str(REPORT_VALIDATOR),
                        "--max-bytes",
                        str(limits["report_max_bytes"]),
                        "--max-depth",
                        str(limits["json_max_depth"]),
                        "--expected-module",
                        module,
                        str(report_path),
                    ],
                    cwd=ROOT,
                    env=environment,
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
                self.assertEqual(validation.stdout, "")
                self.assertEqual(validation.stderr, "")

                report = json.loads(
                    result.stdout.decode(
                        "utf-8",
                        errors="strict",
                    )
                )

                self.assertEqual(report["module"], module)
                self.assertIn(
                    report["version"],
                    entry["module_versions"],
                )
                self.assertLessEqual(
                    container_depth(report),
                    limits["json_max_depth"],
                )

    def test_registry_is_regular_and_not_symlink(self) -> None:
        registry_status = os.lstat(REGISTRY)

        self.assertTrue(stat.S_ISREG(registry_status.st_mode))
        self.assertFalse(stat.S_ISLNK(registry_status.st_mode))

    def test_schema_is_regular_and_not_symlink(self) -> None:
        schema_status = os.lstat(SCHEMA)

        self.assertTrue(stat.S_ISREG(schema_status.st_mode))
        self.assertFalse(stat.S_ISLNK(schema_status.st_mode))

    def test_external_reference_is_detected(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["$defs"]["external"] = {
            "$ref": "https://example.invalid/schema.json"
        }

        self.assertEqual(
            external_references(schema),
            ["https://example.invalid/schema.json"],
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
                    "run_name='registry_import_test')"
                ),
                str(Path(__file__).resolve()),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
