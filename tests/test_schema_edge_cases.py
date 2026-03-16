"""
Cross-Validator Edge-Case Tests

These are Python-local defensive tests covering known jsonschema-vs-Ajv
divergence points for the specific schemas in this protocol.

These are NOT canonical fixtures — they are guardrails against silent
behavioral drift between Draft202012Validator+FormatChecker and
Ajv2020+ajv-formats strict mode.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS_DIR = Path(__file__).parent.parent / "hiveai" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def _v(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


# ---------------------------------------------------------------------------
# additionalProperties enforcement (strict vs permissive)
# ---------------------------------------------------------------------------


class TestAdditionalProperties:
    """Strict schemas reject extra fields. Permissive schemas accept them."""

    @pytest.mark.parametrize("schema_name", [
        "provenance_v2.json",
        "artifact_ref.json",
        "baseline_registry_entry.json",
        "manifest_eval_sweep.json",
        "manifest_data_generation.json",
        "manifest_domain_lora_train.json",
    ])
    def test_strict_schemas_reject_extra_field(self, schema_name: str):
        """Schemas with additionalProperties: false must reject unknown keys."""
        schema = _load(schema_name)
        # Build a minimal valid object, then add an extra field
        # We just test that adding "___extra_test_field" to ANY object fails
        fixture_base = schema_name.replace(".json", "")
        # Map to fixture name
        fixture_map = {
            "provenance_v2": "provenance",
            "artifact_ref": None,  # tested separately
            "baseline_registry_entry": None,
            "manifest_eval_sweep": "manifest_eval_sweep",
            "manifest_data_generation": "manifest_data_generation",
            "manifest_domain_lora_train": "manifest_domain_lora_train",
        }
        fixture_name = fixture_map.get(fixture_base)
        if fixture_name is None:
            pytest.skip("Tested in dedicated class")

        valid_path = SCHEMAS_DIR / "fixtures" / f"{fixture_name}_valid.json"
        valid = json.loads(valid_path.read_text(encoding="utf-8"))
        valid["___extra_test_field"] = "should be rejected"
        v = _v(schema)
        assert not v.is_valid(valid), (
            f"{schema_name} accepted an unknown extra field"
        )

    @pytest.mark.parametrize("schema_name", [
        "result_eval_sweep.json",
        "result_data_generation.json",
        "result_domain_lora_train.json",
    ])
    def test_permissive_schemas_accept_extra_field(self, schema_name: str):
        """Result schemas with additionalProperties: true must accept unknown keys."""
        schema = _load(schema_name)
        fixture_base = schema_name.replace(".json", "")
        valid_path = SCHEMAS_DIR / "fixtures" / f"{fixture_base}_valid.json"
        valid = json.loads(valid_path.read_text(encoding="utf-8"))
        valid["___extra_future_field"] = "forward compat"
        v = _v(schema)
        assert v.is_valid(valid), (
            f"{schema_name} rejected an unknown field — violates forward-compat policy"
        )


# ---------------------------------------------------------------------------
# null vs absent
# ---------------------------------------------------------------------------


class TestNullHandling:
    """Optional fields do NOT allow null unless schema says type: [string, null]."""

    def test_provenance_null_base_model_sha_rejected(self):
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "provenance_valid.json").read_text()
        )
        valid["base_model_sha256"] = None  # null, not absent
        v = _v(_load("provenance_v2.json"))
        assert not v.is_valid(valid), (
            "Provenance accepted null base_model_sha256 — schema says type: string"
        )

    def test_manifest_null_server_url_rejected(self):
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_eval_sweep_valid.json").read_text()
        )
        valid["server_url"] = None
        v = _v(_load("manifest_eval_sweep.json"))
        assert not v.is_valid(valid), (
            "Manifest accepted null server_url — schema says type: string"
        )


# ---------------------------------------------------------------------------
# Numeric boundaries
# ---------------------------------------------------------------------------


class TestNumericBoundaries:
    """Boundary values for numeric constraints."""

    def test_learning_rate_zero_rejected(self):
        """exclusiveMinimum: 0 means 0 itself must be rejected."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_domain_lora_train_valid.json")
            .read_text()
        )
        valid["learning_rate"] = 0
        v = _v(_load("manifest_domain_lora_train.json"))
        assert not v.is_valid(valid), (
            "learning_rate: 0 accepted — schema has exclusiveMinimum: 0"
        )

    def test_learning_rate_max_accepted(self):
        """maximum: 0.01 is inclusive — 0.01 should pass."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_domain_lora_train_valid.json")
            .read_text()
        )
        valid["learning_rate"] = 0.01
        v = _v(_load("manifest_domain_lora_train.json"))
        assert v.is_valid(valid), "learning_rate: 0.01 rejected — maximum is inclusive"

    def test_overall_score_integer_one_accepted(self):
        """JSON Schema treats integer 1 as valid for type: number, maximum: 1."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "result_eval_sweep_valid.json").read_text()
        )
        valid["overall_score"] = 1  # integer, not 1.0
        v = _v(_load("result_eval_sweep.json"))
        assert v.is_valid(valid), "Integer 1 rejected for number field"

    def test_artifact_size_negative_rejected(self):
        v = _v(_load("artifact_ref.json"))
        assert not v.is_valid({
            "output_cid": "QmTest",
            "output_sha256": "a" * 64,
            "output_size_bytes": -1,
        })

    def test_artifact_size_float_rejected(self):
        """output_size_bytes is type: integer — 1.5 must fail."""
        v = _v(_load("artifact_ref.json"))
        assert not v.is_valid({
            "output_cid": "QmTest",
            "output_sha256": "a" * 64,
            "output_size_bytes": 1.5,
        })


# ---------------------------------------------------------------------------
# Enum edge cases
# ---------------------------------------------------------------------------


class TestEnumEdgeCases:
    """Enum values must match exactly — no coercion, no case folding."""

    def test_lora_rank_24_rejected(self):
        """lora_rank enum is [8, 16, 32, 64] — 24 is not valid."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_domain_lora_train_valid.json")
            .read_text()
        )
        valid["lora_rank"] = 24
        v = _v(_load("manifest_domain_lora_train.json"))
        assert not v.is_valid(valid)

    def test_domain_wrong_case_rejected(self):
        """domain enum is lowercase — 'Python' must fail."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_data_generation_valid.json")
            .read_text()
        )
        valid["domain"] = "Python"
        v = _v(_load("manifest_data_generation.json"))
        assert not v.is_valid(valid)

    def test_quantization_wrong_case_rejected(self):
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_domain_lora_train_valid.json")
            .read_text()
        )
        valid["quantization"] = "4BIT-BNB"
        v = _v(_load("manifest_domain_lora_train.json"))
        assert not v.is_valid(valid)


# ---------------------------------------------------------------------------
# String constraints
# ---------------------------------------------------------------------------


class TestStringConstraints:
    """minLength, pattern, and format enforcement."""

    def test_empty_model_name_rejected(self):
        """manifest_eval_sweep model_name has minLength: 1."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_eval_sweep_valid.json").read_text()
        )
        valid["model_name"] = ""
        v = _v(_load("manifest_eval_sweep.json"))
        assert not v.is_valid(valid)

    def test_empty_generator_allowlist_rejected(self):
        """generator_model_allowlist has minItems: 1."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_data_generation_valid.json")
            .read_text()
        )
        valid["generator_model_allowlist"] = []
        v = _v(_load("manifest_data_generation.json"))
        assert not v.is_valid(valid)

    def test_uppercase_sha256_rejected(self):
        """artifact_ref sha256 pattern is [a-f0-9] — uppercase hex fails."""
        v = _v(_load("artifact_ref.json"))
        assert not v.is_valid({
            "output_cid": "QmTest",
            "output_sha256": "A" * 64,
            "output_size_bytes": 1024,
        })

    def test_empty_adapter_files_rejected(self):
        """adapter_files has minItems: 1."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "result_domain_lora_train_valid.json")
            .read_text()
        )
        valid["adapter_files"] = []
        v = _v(_load("result_domain_lora_train.json"))
        assert not v.is_valid(valid)


# ---------------------------------------------------------------------------
# patternProperties edge cases
# ---------------------------------------------------------------------------


class TestPatternProperties:
    """eval_scores / scores key pattern enforcement."""

    def test_uppercase_score_key_rejected_in_eval_sweep(self):
        """result_eval_sweep scores has additionalProperties: false on scores object.
        Keys like 'Python' don't match ^[a-z_]+$ and are thus rejected."""
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "result_eval_sweep_valid.json").read_text()
        )
        valid["scores"]["Python"] = 0.9
        v = _v(_load("result_eval_sweep.json"))
        assert not v.is_valid(valid)


# ---------------------------------------------------------------------------
# Format validation (the #1 cross-language divergence risk)
# ---------------------------------------------------------------------------


class TestFormatValidation:
    """format: uri and format: date-time must be enforced.

    This is the single most likely source of silent divergence between
    jsonschema (which ignores format by default) and Ajv+ajv-formats
    (which enforces it). FormatChecker() must be enabled.
    """

    def test_invalid_uri_rejected(self):
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_eval_sweep_valid.json").read_text()
        )
        valid["server_url"] = "not a uri at all"
        v = _v(_load("manifest_eval_sweep.json"))
        assert not v.is_valid(valid), (
            "Invalid URI accepted — FormatChecker may not be enabled"
        )

    def test_invalid_datetime_rejected(self):
        v = _v(_load("baseline_registry_entry.json"))
        assert not v.is_valid({
            "version": "v6",
            "merged_at": "not-a-date",
            "contributing_job_ids": ["job-1"],
            "merge_algorithm": "dense_delta_svd",
            "merge_rank": 32,
            "eval_scores": {"python": 0.9},
            "overall_score": 0.9,
            "adapter_cid": "QmTest",
            "adapter_sha256": "sha256:" + "a" * 64,
        }), "Invalid date-time accepted — FormatChecker may not be enabled"

    def test_valid_uri_accepted(self):
        valid = json.loads(
            (SCHEMAS_DIR / "fixtures" / "manifest_eval_sweep_valid.json").read_text()
        )
        valid["server_url"] = "http://localhost:11434/v1"
        v = _v(_load("manifest_eval_sweep.json"))
        assert v.is_valid(valid)
