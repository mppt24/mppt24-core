#!/usr/bin/python3 -I
"""Testes do contrato de snapshot validado MPPT24 1.0.0."""

import json
import sys
import unittest
from pathlib import Path
from typing import NoReturn

from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent

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

EXPECTED_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)

EXPECTED_SCHEMA_ID = (
    "urn:mppt24:schema:"
    "validated-generation-snapshot:1.0.0"
)

SNAPSHOT_MAX_BYTES = 16777216
SNAPSHOT_MAX_DEPTH = 40

EXPECTED_FIXTURES = {
    "valid-complete": {
        "state": "COMPLETE",
        "reports": 7,
    },
    "valid-partial": {
        "state": "PARTIAL",
        "reports": 1,
    },
    "valid-failed": {
        "state": "FAILED",
        "reports": 0,
    },
}


class DuplicateKeyError(ValueError):
    """Documento JSON contém uma chave duplicada."""


class NonFiniteNumberError(ValueError):
    """Documento JSON contém um número não finito."""


def reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document: dict[str, object] = {}

    for key, value in pairs:
        if key in document:
            raise DuplicateKeyError(key)

        document[key] = value

    return document


def reject_non_finite(value: str) -> NoReturn:
    raise NonFiniteNumberError(value)


def parse_json_strict(content: bytes) -> object:
    text = content.decode(
        "utf-8",
        errors="strict",
    )

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_finite,
    )


def load_schema(path: Path) -> dict[str, object]:
    document = parse_json_strict(
        path.read_bytes()
    )

    if not isinstance(document, dict):
        raise TypeError(
            f"{path}: schema não é objeto"
        )

    Draft202012Validator.check_schema(
        document
    )
    return document


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

    return 1


def external_references(value: object) -> list[str]:
    references: list[str] = []
    stack = [value]

    while stack:
        current = stack.pop()

        if isinstance(current, dict):
            for key, child in current.items():
                if (
                    key in {
                        "$ref",
                        "$dynamicRef",
                    }
                    and isinstance(child, str)
                    and not child.startswith("#")
                ):
                    references.append(child)

                stack.append(child)

        elif isinstance(current, list):
            stack.extend(current)

    return sorted(references)


class ValidatedGenerationSnapshotContractTest(
    unittest.TestCase
):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot_schema = load_schema(
            SNAPSHOT_SCHEMA
        )
        cls.manifest_schema = load_schema(
            MANIFEST_SCHEMA
        )
        cls.report_schema = load_schema(
            REPORT_SCHEMA
        )

        cls.snapshot_validator = (
            Draft202012Validator(
                cls.snapshot_schema
            )
        )
        cls.manifest_validator = (
            Draft202012Validator(
                cls.manifest_schema
            )
        )
        cls.report_validator = (
            Draft202012Validator(
                cls.report_schema
            )
        )

    def fixture_path(
        self,
        fixture_name: str,
    ) -> Path:
        return (
            FIXTURE_ROOT
            / fixture_name
            / "snapshot.json"
        )

    def load_snapshot(
        self,
        fixture_name: str,
    ) -> tuple[dict[str, object], bytes]:
        path = self.fixture_path(
            fixture_name
        )
        content = path.read_bytes()

        self.assertFalse(
            content.startswith(b"\xef\xbb\xbf")
        )
        self.assertTrue(
            content.endswith(b"\n")
        )
        self.assertEqual(
            content.count(b"\n"),
            1,
        )
        self.assertLessEqual(
            len(content),
            SNAPSHOT_MAX_BYTES,
        )

        document = parse_json_strict(
            content
        )

        self.assertIsInstance(
            document,
            dict,
        )

        return document, content

    def assert_schema_valid(
        self,
        validator: Draft202012Validator,
        document: object,
        role: str,
    ) -> None:
        errors = sorted(
            validator.iter_errors(document),
            key=lambda error: list(
                error.absolute_path
            ),
        )

        self.assertEqual(
            errors,
            [],
            msg=(
                role
                if not errors
                else (
                    f"{role}: "
                    f"{list(errors[0].absolute_path)}: "
                    f"{errors[0].message}"
                )
            ),
        )

    def assert_snapshot_valid(
        self,
        fixture_name: str,
    ) -> dict[str, object]:
        snapshot, content = self.load_snapshot(
            fixture_name
        )

        self.assert_schema_valid(
            self.snapshot_validator,
            snapshot,
            f"{fixture_name}:envelope",
        )

        manifest = snapshot["manifest"]
        reports = snapshot["reports"]

        self.assert_schema_valid(
            self.manifest_validator,
            manifest,
            f"{fixture_name}:manifest",
        )

        self.assertIsInstance(
            reports,
            dict,
        )

        for module, report in reports.items():
            self.assert_schema_valid(
                self.report_validator,
                report,
                f"{fixture_name}:report:{module}",
            )

        self.assertEqual(
            snapshot["generation_id"],
            manifest["generation_id"],
        )
        self.assertEqual(
            snapshot["state"],
            manifest["state"],
        )

        successful_entries = [
            entry
            for entry in manifest["modules"]
            if entry["outcome"] == "SUCCESS"
        ]

        successful_names = [
            entry["module"]
            for entry in successful_entries
        ]

        self.assertEqual(
            list(reports),
            successful_names,
        )
        self.assertEqual(
            len(reports),
            manifest["summary"]["successful"],
        )
        self.assertEqual(
            len(reports),
            manifest["summary"]["reports_written"],
        )

        for entry in successful_entries:
            module = entry["module"]
            descriptor = entry["report"]
            report = reports[module]

            expected_metadata = {
                "module": descriptor["module"],
                "version": descriptor["version"],
                "timestamp": descriptor["timestamp"],
                "status": descriptor["status"],
            }

            actual_metadata = {
                key: report.get(key)
                for key in expected_metadata
            }

            self.assertEqual(
                actual_metadata,
                expected_metadata,
            )

        self.assertLessEqual(
            container_depth(snapshot),
            SNAPSHOT_MAX_DEPTH,
        )

        expected_serialization = (
            json.dumps(
                snapshot,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )

        self.assertEqual(
            content,
            expected_serialization,
        )

        return snapshot

    def test_schema_is_valid_draft_2020_12(
        self,
    ) -> None:
        Draft202012Validator.check_schema(
            self.snapshot_schema
        )

    def test_schema_identity(self) -> None:
        self.assertEqual(
            self.snapshot_schema["$schema"],
            EXPECTED_DIALECT,
        )
        self.assertEqual(
            self.snapshot_schema["$id"],
            EXPECTED_SCHEMA_ID,
        )

    def test_schema_has_no_external_references(
        self,
    ) -> None:
        self.assertEqual(
            external_references(
                self.snapshot_schema
            ),
            [],
        )

    def test_schema_defines_exact_envelope(
        self,
    ) -> None:
        expected_properties = {
            "snapshot_version",
            "generation_id",
            "state",
            "manifest",
            "reports",
        }

        self.assertEqual(
            set(
                self.snapshot_schema[
                    "properties"
                ]
            ),
            expected_properties,
        )
        self.assertEqual(
            set(
                self.snapshot_schema[
                    "required"
                ]
            ),
            expected_properties,
        )
        self.assertIs(
            self.snapshot_schema[
                "additionalProperties"
            ],
            False,
        )
        self.assertEqual(
            self.snapshot_schema[
                "properties"
            ][
                "snapshot_version"
            ][
                "const"
            ],
            "1.0.0",
        )
        self.assertEqual(
            self.snapshot_schema[
                "properties"
            ][
                "reports"
            ][
                "maxProperties"
            ],
            32,
        )

    def test_valid_complete_fixture(
        self,
    ) -> None:
        snapshot = self.assert_snapshot_valid(
            "valid-complete"
        )

        self.assertEqual(
            snapshot["state"],
            EXPECTED_FIXTURES[
                "valid-complete"
            ][
                "state"
            ],
        )
        self.assertEqual(
            len(snapshot["reports"]),
            EXPECTED_FIXTURES[
                "valid-complete"
            ][
                "reports"
            ],
        )

    def test_valid_partial_fixture(
        self,
    ) -> None:
        snapshot = self.assert_snapshot_valid(
            "valid-partial"
        )

        self.assertEqual(
            snapshot["state"],
            EXPECTED_FIXTURES[
                "valid-partial"
            ][
                "state"
            ],
        )
        self.assertEqual(
            len(snapshot["reports"]),
            EXPECTED_FIXTURES[
                "valid-partial"
            ][
                "reports"
            ],
        )

    def test_valid_failed_fixture(
        self,
    ) -> None:
        snapshot = self.assert_snapshot_valid(
            "valid-failed"
        )

        self.assertEqual(
            snapshot["state"],
            EXPECTED_FIXTURES[
                "valid-failed"
            ][
                "state"
            ],
        )
        self.assertEqual(
            snapshot["reports"],
            {},
        )


    def assert_envelope_invalid(
        self,
        snapshot: object,
    ) -> None:
        self.assertNotEqual(
            list(
                self.snapshot_validator.iter_errors(
                    snapshot
                )
            ),
            [],
        )

    def test_envelope_missing_required_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )

        for property_name in (
            "snapshot_version",
            "generation_id",
            "state",
            "manifest",
            "reports",
        ):
            with self.subTest(
                property_name=property_name
            ):
                invalid = dict(snapshot)
                del invalid[property_name]

                self.assert_envelope_invalid(
                    invalid
                )

    def test_envelope_additional_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        snapshot["unexpected"] = True

        self.assert_envelope_invalid(
            snapshot
        )

    def test_envelope_incompatible_version(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        snapshot["snapshot_version"] = "2.0.0"

        self.assert_envelope_invalid(
            snapshot
        )

    def test_envelope_invalid_state(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        snapshot["state"] = "UNKNOWN"

        self.assert_envelope_invalid(
            snapshot
        )

    def test_envelope_incorrect_property_types(
        self,
    ) -> None:
        invalid_values = {
            "generation_id": 1,
            "state": [],
            "manifest": [],
            "reports": [],
        }

        for property_name, value in (
            invalid_values.items()
        ):
            with self.subTest(
                property_name=property_name
            ):
                snapshot, _ = self.load_snapshot(
                    "valid-complete"
                )
                snapshot[property_name] = value

                self.assert_envelope_invalid(
                    snapshot
                )

    def test_envelope_report_limit(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        snapshot["reports"] = {
            f"module-{index:02d}": {}
            for index in range(33)
        }

        self.assert_envelope_invalid(
            snapshot
        )


    def assert_document_invalid(
        self,
        validator: Draft202012Validator,
        document: object,
    ) -> None:
        self.assertNotEqual(
            list(
                validator.iter_errors(
                    document
                )
            ),
            [],
        )

    def first_report(
        self,
        snapshot: dict[str, object],
    ) -> dict[str, object]:
        reports = snapshot["reports"]

        self.assertIsInstance(
            reports,
            dict,
        )
        self.assertNotEqual(
            reports,
            {},
        )

        report = next(
            iter(reports.values())
        )

        self.assertIsInstance(
            report,
            dict,
        )
        return report

    def test_embedded_manifest_additional_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        manifest = snapshot["manifest"]
        manifest["unexpected"] = True

        self.assert_document_invalid(
            self.manifest_validator,
            manifest,
        )

    def test_embedded_manifest_missing_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        manifest = snapshot["manifest"]
        del manifest["generation_id"]

        self.assert_document_invalid(
            self.manifest_validator,
            manifest,
        )

    def test_embedded_manifest_incorrect_type(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        manifest = snapshot["manifest"]
        manifest["modules"] = {}

        self.assert_document_invalid(
            self.manifest_validator,
            manifest,
        )

    def test_embedded_report_additional_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        report = self.first_report(
            snapshot
        )
        report["unexpected"] = True

        self.assert_document_invalid(
            self.report_validator,
            report,
        )

    def test_embedded_report_missing_property(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        report = self.first_report(
            snapshot
        )
        del report["module"]

        self.assert_document_invalid(
            self.report_validator,
            report,
        )

    def test_embedded_report_incorrect_type(
        self,
    ) -> None:
        snapshot, _ = self.load_snapshot(
            "valid-complete"
        )
        report = self.first_report(
            snapshot
        )
        report["status"] = 1

        self.assert_document_invalid(
            self.report_validator,
            report,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
