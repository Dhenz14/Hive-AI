"""
Protocol Policy Tests

These test behavioral requirements from the HivePoA schemas/README.md that
go beyond simple pass/fail fixture validation:

1. Workers MUST reject schema_version > supported_version
2. Workers MAY accept unknown optional fields (forward compatibility)
3. Coordinator MUST reject results not validating against current version

These are the policy tests that prevent "schema aligned but protocol broken."
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS_DIR = Path(__file__).parent.parent / "hiveai" / "schemas"

SUPPORTED_SCHEMA_VERSION = 2


def _load(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def _v(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


# ---------------------------------------------------------------------------
# Policy 1: Reject future schema_version
# ---------------------------------------------------------------------------


class TestSchemaVersionRejection:
    """Workers MUST reject schema_version > supported_version.

    The manifests use const: 2 for schema_version, so any value != 2
    already fails schema validation. But this test explicitly verifies
    the behavior for future versions (3, 99) to document the contract.
    """

    @pytest.mark.parametrize("manifest_schema", [
        "manifest_eval_sweep.json",
        "manifest_data_generation.json",
        "manifest_domain_lora_train.json",
    ])
    @pytest.mark.parametrize("future_version", [3, 99])
    def test_future_schema_version_rejected(
        self, manifest_schema: str, future_version: int
    ):
        schema = _load(manifest_schema)
        # Load valid fixture and change schema_version to future value
        fixture_map = {
            "manifest_eval_sweep.json": "manifest_eval_sweep",
            "manifest_data_generation.json": "manifest_data_generation",
            "manifest_domain_lora_train.json": "manifest_domain_lora_train",
        }
        fixture_base = fixture_map[manifest_schema]
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / f"{fixture_base}_valid.json").read_text()
        )
        valid["schema_version"] = future_version
        v = _v(schema)
        assert not v.is_valid(valid), (
            f"schema_version {future_version} accepted by {manifest_schema} — "
            f"const: {SUPPORTED_SCHEMA_VERSION} should reject it"
        )

    @pytest.mark.parametrize("manifest_schema", [
        "manifest_eval_sweep.json",
        "manifest_data_generation.json",
        "manifest_domain_lora_train.json",
    ])
    def test_past_schema_version_rejected(self, manifest_schema: str):
        """schema_version: 1 (the old version) must also be rejected."""
        schema = _load(manifest_schema)
        fixture_map = {
            "manifest_eval_sweep.json": "manifest_eval_sweep",
            "manifest_data_generation.json": "manifest_data_generation",
            "manifest_domain_lora_train.json": "manifest_domain_lora_train",
        }
        fixture_base = fixture_map[manifest_schema]
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / f"{fixture_base}_valid.json").read_text()
        )
        valid["schema_version"] = 1
        v = _v(schema)
        assert not v.is_valid(valid), (
            f"schema_version 1 accepted by {manifest_schema} — "
            f"only version {SUPPORTED_SCHEMA_VERSION} should be accepted"
        )


# ---------------------------------------------------------------------------
# Policy 2: Forward compatibility — unknown optional fields
# ---------------------------------------------------------------------------


class TestForwardCompatibility:
    """Workers MAY accept unknown optional fields in result schemas.

    Result schemas have additionalProperties: true. This is intentional:
    HivePoA can add new optional fields to results without breaking workers.

    Manifest schemas have additionalProperties: false. Workers MUST NOT
    accept unknown fields in manifests — this prevents phantom config.
    """

    @pytest.mark.parametrize("result_schema", [
        "result_eval_sweep.json",
        "result_data_generation.json",
        "result_domain_lora_train.json",
    ])
    def test_results_accept_new_optional_fields(self, result_schema: str):
        """Simulates HivePoA adding a new field in a future minor version."""
        schema = _load(result_schema)
        fixture_base = result_schema.replace(".json", "")
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / f"{fixture_base}_valid.json").read_text()
        )
        # Add hypothetical future fields
        valid["new_metric_v3"] = 0.95
        valid["telemetry_hash"] = "abc123"
        v = _v(schema)
        assert v.is_valid(valid), (
            f"{result_schema} rejected unknown optional fields — "
            f"violates forward-compat policy"
        )

    @pytest.mark.parametrize("manifest_schema", [
        "manifest_eval_sweep.json",
        "manifest_data_generation.json",
        "manifest_domain_lora_train.json",
    ])
    def test_manifests_reject_unknown_fields(self, manifest_schema: str):
        """Manifests MUST NOT silently accept unknown config fields."""
        schema = _load(manifest_schema)
        fixture_map = {
            "manifest_eval_sweep.json": "manifest_eval_sweep",
            "manifest_data_generation.json": "manifest_data_generation",
            "manifest_domain_lora_train.json": "manifest_domain_lora_train",
        }
        fixture_base = fixture_map[manifest_schema]
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / f"{fixture_base}_valid.json").read_text()
        )
        valid["phantom_config_option"] = True
        v = _v(schema)
        assert not v.is_valid(valid), (
            f"{manifest_schema} accepted unknown config field — "
            f"manifests must be strict to prevent phantom configuration"
        )


# ---------------------------------------------------------------------------
# Policy 3: const workload_type enforcement
# ---------------------------------------------------------------------------


class TestWorkloadTypeEnforcement:
    """Each manifest schema pins its own workload_type via const.

    A data_generation manifest with workload_type: eval_sweep must fail,
    even if all other fields are valid. This prevents cross-workload
    confusion at the protocol level.
    """

    def test_eval_sweep_rejects_wrong_workload_type(self):
        schema = _load("manifest_eval_sweep.json")
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_eval_sweep_valid.json").read_text()
        )
        valid["workload_type"] = "data_generation"
        v = _v(schema)
        assert not v.is_valid(valid)

    def test_data_generation_rejects_wrong_workload_type(self):
        schema = _load("manifest_data_generation.json")
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_data_generation_valid.json")
            .read_text()
        )
        valid["workload_type"] = "eval_sweep"
        v = _v(schema)
        assert not v.is_valid(valid)

    def test_lora_train_rejects_wrong_workload_type(self):
        schema = _load("manifest_domain_lora_train.json")
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_domain_lora_train_valid.json")
            .read_text()
        )
        valid["workload_type"] = "eval_sweep"
        v = _v(schema)
        assert not v.is_valid(valid)
