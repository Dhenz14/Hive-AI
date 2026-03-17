"""
Schema Conformance Tests — Python side of the HivePoA protocol contract.

Validates the exact same canonical fixtures that HivePoA validates via Ajv.
If a fixture passes here but fails in TypeScript (or vice versa), the
protocol has drifted.

Validator: jsonschema Draft202012Validator with FormatChecker enabled.
FormatChecker is REQUIRED — without it, format: uri and format: date-time
become dead letters and diverge from Ajv+ajv-formats behavior.
"""
import hashlib
import json
from pathlib import Path


def _read_normalized(path: Path) -> bytes:
    """Read file bytes with line endings normalized to LF (platform-independent hashing)."""
    return path.read_bytes().replace(b"\r\n", b"\n")

import pytest
from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS_DIR = Path(__file__).parent.parent / "hiveai" / "schemas"
FIXTURES_DIR = SCHEMAS_DIR / "fixtures"

# Mirrors HivePoA's SCHEMA_FIXTURE_MAP exactly
SCHEMA_FIXTURE_MAP = {
    "provenance_v2.json": "provenance",
    "manifest_eval_sweep.json": "manifest_eval_sweep",
    "manifest_data_generation.json": "manifest_data_generation",
    "manifest_domain_lora_train.json": "manifest_domain_lora_train",
    "result_eval_sweep.json": "result_eval_sweep",
    "result_data_generation.json": "result_data_generation",
    "result_domain_lora_train.json": "result_domain_lora_train",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_validator(schema: dict) -> Draft202012Validator:
    """Create a validator with format checking enabled (matches Ajv+ajv-formats)."""
    return Draft202012Validator(schema, format_checker=FormatChecker())


# ---------------------------------------------------------------------------
# Core conformance: compile all schemas
# ---------------------------------------------------------------------------


class TestSchemaCompilation:
    """All 10 schema files must parse and compile under Draft 2020-12."""

    def test_all_schemas_compile(self):
        schemas = list(SCHEMAS_DIR.glob("*.json"))
        # Exclude SCHEMA_MANIFEST.json — it's not a JSON Schema file
        schemas = [s for s in schemas if s.name != "SCHEMA_MANIFEST.json"]
        assert len(schemas) >= 10, f"Expected >=10 schemas, found {len(schemas)}"
        for schema_path in schemas:
            schema = _load(schema_path)
            Draft202012Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Fixture parity: exact same valid/invalid corpus as HivePoA TypeScript
# ---------------------------------------------------------------------------


class TestFixtureParity:
    """Each schema-fixture pair must produce the same pass/fail as Ajv strict mode."""

    @pytest.mark.parametrize(
        "schema_file,fixture_base",
        list(SCHEMA_FIXTURE_MAP.items()),
        ids=list(SCHEMA_FIXTURE_MAP.values()),
    )
    def test_valid_fixture_passes(self, schema_file: str, fixture_base: str):
        schema = _load(SCHEMAS_DIR / schema_file)
        fixture = _load(FIXTURES_DIR / f"{fixture_base}_valid.json")
        validator = _make_validator(schema)
        errors = list(validator.iter_errors(fixture))
        assert errors == [], (
            f"Valid fixture {fixture_base}_valid.json rejected:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )

    @pytest.mark.parametrize(
        "schema_file,fixture_base",
        list(SCHEMA_FIXTURE_MAP.items()),
        ids=list(SCHEMA_FIXTURE_MAP.values()),
    )
    def test_invalid_fixture_fails(self, schema_file: str, fixture_base: str):
        schema = _load(SCHEMAS_DIR / schema_file)
        fixture = _load(FIXTURES_DIR / f"{fixture_base}_invalid.json")
        # Strip _reason field (documentation only — HivePoA does the same)
        fixture.pop("_reason", None)
        validator = _make_validator(schema)
        errors = list(validator.iter_errors(fixture))
        assert len(errors) > 0, (
            f"Invalid fixture {fixture_base}_invalid.json was accepted "
            f"(expected at least one validation error)"
        )


# ---------------------------------------------------------------------------
# Standalone schema tests (artifact_ref, error_codes, baseline_registry)
# ---------------------------------------------------------------------------


class TestArtifactRef:
    """artifact_ref.json — additionalProperties: false, strict sha256 pattern."""

    def _schema(self):
        return _load(SCHEMAS_DIR / "artifact_ref.json")

    def test_valid_artifact(self):
        v = _make_validator(self._schema())
        assert v.is_valid({
            "output_cid": "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
            "output_sha256": "a" * 64,
            "output_size_bytes": 1048576,
        })

    def test_bad_sha256_rejected(self):
        v = _make_validator(self._schema())
        assert not v.is_valid({
            "output_cid": "QmTest",
            "output_sha256": "not-a-sha256",
            "output_size_bytes": 100,
        })

    def test_missing_fields_rejected(self):
        v = _make_validator(self._schema())
        assert not v.is_valid({"output_cid": "QmTest"})

    def test_extra_field_rejected(self):
        v = _make_validator(self._schema())
        assert not v.is_valid({
            "output_cid": "QmTest",
            "output_sha256": "a" * 64,
            "output_size_bytes": 1024,
            "extra": "should fail",
        })


class TestErrorCodes:
    """error_codes.json — enum enforcement on 21 error codes."""

    def _schema(self):
        return _load(SCHEMAS_DIR / "error_codes.json")

    def test_valid_error_code(self):
        v = _make_validator(self._schema())
        assert v.is_valid({
            "error_code": "JOB_NONCE_MISMATCH",
            "error_message": "nonce did not match",
        })

    def test_unknown_error_code_rejected(self):
        v = _make_validator(self._schema())
        assert not v.is_valid({"error_code": "MADE_UP_CODE"})


class TestBaselineRegistry:
    """baseline_registry_entry.json — strict with date-time format."""

    def _schema(self):
        return _load(SCHEMAS_DIR / "baseline_registry_entry.json")

    def test_valid_entry(self):
        v = _make_validator(self._schema())
        errors = list(v.iter_errors({
            "version": "v6",
            "parent_version": "v5",
            "merged_at": "2026-04-01T12:00:00Z",
            "contributing_job_ids": ["job-1", "job-2"],
            "contributing_workers": ["worker-a"],
            "dataset_cids": ["QmAbc"],
            "merge_algorithm": "dense_delta_svd",
            "merge_rank": 32,
            "discarded_residual_norm": 0.023,
            "eval_scores": {"python": 0.94, "rust": 0.96},
            "overall_score": 0.945,
            "baseline_improvement": 0.012,
            "adapter_cid": "QmMerged",
            "adapter_sha256": "sha256:" + "a" * 64,
        }))
        assert errors == [], [e.message for e in errors]

    def test_invalid_merge_algorithm_rejected(self):
        v = _make_validator(self._schema())
        assert not v.is_valid({
            "version": "v6",
            "merged_at": "2026-04-01T12:00:00Z",
            "contributing_job_ids": ["job-1"],
            "merge_algorithm": "magic_merge",
            "merge_rank": 32,
            "eval_scores": {},
            "overall_score": 0.9,
            "adapter_cid": "QmTest",
            "adapter_sha256": "sha256:" + "a" * 64,
        })


# ---------------------------------------------------------------------------
# Drift detection: SCHEMA_MANIFEST.json hash verification
# ---------------------------------------------------------------------------


class TestSchemaManifestIntegrity:
    """Vendored schema artifacts must match SCHEMA_MANIFEST.json hashes."""

    def test_manifest_exists(self):
        assert (SCHEMAS_DIR / "SCHEMA_MANIFEST.json").exists(), (
            "SCHEMA_MANIFEST.json missing — run scripts/sync_schemas.py"
        )

    def test_schema_hashes_match(self):
        manifest = _load(SCHEMAS_DIR / "SCHEMA_MANIFEST.json")
        for filename, expected_sha in manifest.get("files", {}).items():
            file_path = SCHEMAS_DIR / filename
            assert file_path.exists(), f"Schema {filename} missing"
            actual = "sha256:" + hashlib.sha256(_read_normalized(file_path)).hexdigest()
            assert actual == expected_sha, (
                f"{filename} drifted from manifest "
                f"(expected {expected_sha[:30]}..., got {actual[:30]}...)"
            )

    def test_fixture_hashes_match(self):
        manifest = _load(SCHEMAS_DIR / "SCHEMA_MANIFEST.json")
        for filename, expected_sha in manifest.get("fixtures", {}).items():
            file_path = FIXTURES_DIR / filename
            assert file_path.exists(), f"Fixture {filename} missing"
            actual = "sha256:" + hashlib.sha256(_read_normalized(file_path)).hexdigest()
            assert actual == expected_sha, (
                f"Fixture {filename} drifted from manifest"
            )
