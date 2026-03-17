"""
Schema Contract Enforcement Tests

These tests prove the four cross-repo enforcement gates:

(a) Schemas are pinned to an immutable HivePoA commit SHA (not branch, not manual copy)
(b) Both valid AND invalid fixtures are validated
(c) Deliberate protocol drift is detected and fails
(d) Fixture-set digest assertion catches any file mutation

These are the tests that prevent "green checkbox, no enforcement."
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


def _read_normalized(path: Path) -> bytes:
    """Read file bytes with line endings normalized to LF (platform-independent hashing)."""
    return path.read_bytes().replace(b"\r\n", b"\n")

SCHEMAS_DIR = Path(__file__).parent.parent / "hiveai" / "schemas"
FIXTURES_DIR = SCHEMAS_DIR / "fixtures"
MANIFEST_PATH = SCHEMAS_DIR / "SCHEMA_MANIFEST.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _v(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


# ---------------------------------------------------------------------------
# Gate (a): Immutable commit SHA pinning
# ---------------------------------------------------------------------------


class TestImmutableSHAPinning:
    """SCHEMA_MANIFEST.json must pin a full 40-char immutable commit SHA."""

    def test_manifest_has_full_sha(self):
        manifest = _load(MANIFEST_PATH)
        full_sha = manifest.get("source_commit_full", "")
        assert len(full_sha) == 40, (
            f"source_commit_full must be a 40-char SHA, got {len(full_sha)} chars: {full_sha!r}"
        )
        assert all(c in "0123456789abcdef" for c in full_sha), (
            f"source_commit_full contains non-hex characters: {full_sha!r}"
        )

    def test_manifest_has_source_repo(self):
        manifest = _load(MANIFEST_PATH)
        assert manifest.get("source_repo") == "HivePoA"

    def test_short_sha_is_prefix_of_full(self):
        manifest = _load(MANIFEST_PATH)
        short = manifest.get("source_commit", "")
        full = manifest.get("source_commit_full", "")
        assert full.startswith(short), (
            f"source_commit {short!r} is not a prefix of source_commit_full {full!r}"
        )


# ---------------------------------------------------------------------------
# Gate (b): Both valid AND invalid fixtures validated
# ---------------------------------------------------------------------------


SCHEMA_FIXTURE_MAP = {
    "provenance_v2.json": "provenance",
    "manifest_eval_sweep.json": "manifest_eval_sweep",
    "manifest_data_generation.json": "manifest_data_generation",
    "manifest_domain_lora_train.json": "manifest_domain_lora_train",
    "result_eval_sweep.json": "result_eval_sweep",
    "result_data_generation.json": "result_data_generation",
    "result_domain_lora_train.json": "result_domain_lora_train",
}


class TestBidirectionalFixtureValidation:
    """Every schema must have both valid AND invalid fixtures, and both must
    produce the expected validation result.

    This is proof (b): we don't just check that valid passes — we prove
    that invalid fails. A schema that accepts everything is caught.
    """

    @pytest.mark.parametrize(
        "schema_file,fixture_base",
        list(SCHEMA_FIXTURE_MAP.items()),
        ids=[f"{v}_valid" for v in SCHEMA_FIXTURE_MAP.values()],
    )
    def test_valid_fixture_accepted(self, schema_file: str, fixture_base: str):
        schema = _load(SCHEMAS_DIR / schema_file)
        fixture = _load(FIXTURES_DIR / f"{fixture_base}_valid.json")
        errors = list(_v(schema).iter_errors(fixture))
        assert errors == [], (
            f"Valid fixture {fixture_base}_valid.json rejected:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )

    @pytest.mark.parametrize(
        "schema_file,fixture_base",
        list(SCHEMA_FIXTURE_MAP.items()),
        ids=[f"{v}_invalid" for v in SCHEMA_FIXTURE_MAP.values()],
    )
    def test_invalid_fixture_rejected(self, schema_file: str, fixture_base: str):
        schema = _load(SCHEMAS_DIR / schema_file)
        fixture = _load(FIXTURES_DIR / f"{fixture_base}_invalid.json")
        fixture.pop("_reason", None)
        errors = list(_v(schema).iter_errors(fixture))
        assert len(errors) > 0, (
            f"Invalid fixture {fixture_base}_invalid.json was ACCEPTED — "
            f"schema is too permissive or fixture is not actually invalid"
        )

    def test_every_schema_has_both_fixtures(self):
        """Every mapped schema must have both _valid.json and _invalid.json."""
        for schema_file, fixture_base in SCHEMA_FIXTURE_MAP.items():
            valid = FIXTURES_DIR / f"{fixture_base}_valid.json"
            invalid = FIXTURES_DIR / f"{fixture_base}_invalid.json"
            assert valid.exists(), f"Missing: {valid.name}"
            assert invalid.exists(), f"Missing: {invalid.name}"


# ---------------------------------------------------------------------------
# Gate (c): Deliberate protocol drift detected
# ---------------------------------------------------------------------------


class TestProtocolDriftDetection:
    """Prove that a schema mutation changes validation outcomes.

    These tests simulate what happens when HivePoA changes a schema but
    Hive-AI doesn't re-sync. The point is to prove the detection is real,
    not just a checkbox.
    """

    def test_adding_required_field_breaks_valid_fixture(self):
        """If HivePoA adds a required field, the old valid fixture must fail."""
        schema = _load(SCHEMAS_DIR / "manifest_eval_sweep.json")
        fixture = _load(FIXTURES_DIR / "manifest_eval_sweep_valid.json")

        # Simulate protocol drift: HivePoA adds a new required field
        drifted_schema = copy.deepcopy(schema)
        drifted_schema["properties"]["new_required_field_v3"] = {"type": "string"}
        drifted_schema["required"].append("new_required_field_v3")

        # The previously-valid fixture should now FAIL against the drifted schema
        errors = list(_v(drifted_schema).iter_errors(fixture))
        assert len(errors) > 0, (
            "Drifted schema (new required field) still accepted old fixture — "
            "this means drift would go undetected"
        )

    def test_narrowing_enum_breaks_valid_fixture(self):
        """If HivePoA removes an enum value, fixtures using it must fail."""
        schema = _load(SCHEMAS_DIR / "manifest_data_generation.json")
        fixture = _load(FIXTURES_DIR / "manifest_data_generation_valid.json")

        # Simulate drift: remove the fixture's domain from the enum
        drifted_schema = copy.deepcopy(schema)
        current_domain = fixture["domain"]
        if current_domain in drifted_schema["properties"]["domain"]["enum"]:
            drifted_schema["properties"]["domain"]["enum"].remove(current_domain)

        errors = list(_v(drifted_schema).iter_errors(fixture))
        assert len(errors) > 0, (
            "Drifted schema (narrowed enum) still accepted fixture — "
            "enum narrowing would go undetected"
        )

    def test_changing_const_breaks_valid_fixture(self):
        """If schema_version const changes, all existing fixtures must fail."""
        schema = _load(SCHEMAS_DIR / "manifest_eval_sweep.json")
        fixture = _load(FIXTURES_DIR / "manifest_eval_sweep_valid.json")

        drifted_schema = copy.deepcopy(schema)
        drifted_schema["properties"]["schema_version"]["const"] = 3

        errors = list(_v(drifted_schema).iter_errors(fixture))
        assert len(errors) > 0, (
            "Drifted schema (schema_version bumped to 3) still accepted v2 fixture"
        )

    def test_hash_drift_detected_by_manifest(self):
        """Mutating a schema file would change its SHA-256, caught by manifest."""
        manifest = _load(MANIFEST_PATH)

        # Pick a schema and verify its hash matches
        schema_name = "manifest_eval_sweep.json"
        expected_hash = manifest["files"][schema_name]
        actual_hash = (
            "sha256:"
            + hashlib.sha256(
                _read_normalized(SCHEMAS_DIR / schema_name)
            ).hexdigest()
        )
        assert actual_hash == expected_hash, "Baseline hash mismatch before mutation test"

        # Now simulate what a mutated file's hash would look like
        original_bytes = _read_normalized(SCHEMAS_DIR / schema_name)
        mutated_bytes = original_bytes + b"\n"  # Even a single byte changes the hash
        mutated_hash = "sha256:" + hashlib.sha256(mutated_bytes).hexdigest()
        assert mutated_hash != expected_hash, (
            "Appending a byte did not change SHA-256 — hash function is broken"
        )


# ---------------------------------------------------------------------------
# Gate (d): Fixture-set digest assertion
# ---------------------------------------------------------------------------


def _compute_fixture_set_digest() -> str:
    """Compute fixture-set digest from vendored files (same algorithm as sync_schemas.py).

    Uses LF-normalized bytes for platform independence.
    """
    h = hashlib.sha256()
    for f in sorted(SCHEMAS_DIR.glob("*.json")):
        if f.name == "SCHEMA_MANIFEST.json":
            continue
        h.update(f.name.encode())
        h.update(_read_normalized(f))
    for f in sorted(FIXTURES_DIR.glob("*.json")):
        h.update(f.name.encode())
        h.update(_read_normalized(f))
    return f"sha256:{h.hexdigest()}"


class TestFixtureSetDigest:
    """The fixture-set digest is a single hash over all schemas + fixtures.

    If ANY file changes (content, addition, or removal), the digest changes.
    CI asserts this digest matches SCHEMA_MANIFEST.json.
    """

    def test_digest_matches_manifest(self):
        manifest = _load(MANIFEST_PATH)
        expected = manifest.get("fixture_set_digest")
        assert expected is not None, "fixture_set_digest missing from SCHEMA_MANIFEST.json"

        actual = _compute_fixture_set_digest()
        assert actual == expected, (
            f"Fixture-set digest mismatch:\n"
            f"  manifest: {expected}\n"
            f"  computed: {actual}\n"
            f"Run: python scripts/sync_schemas.py /path/to/HivePoA --force"
        )

    def test_digest_is_sha256(self):
        manifest = _load(MANIFEST_PATH)
        digest = manifest.get("fixture_set_digest", "")
        assert digest.startswith("sha256:"), "Digest must start with 'sha256:'"
        hex_part = digest[7:]
        assert len(hex_part) == 64, f"SHA-256 hex must be 64 chars, got {len(hex_part)}"

    def test_digest_changes_on_file_mutation(self):
        """Prove the digest algorithm is sensitive to content changes."""
        baseline = _compute_fixture_set_digest()

        # Temporarily compute what digest would be if we added a byte to a schema
        h = hashlib.sha256()
        for f in sorted(SCHEMAS_DIR.glob("*.json")):
            if f.name == "SCHEMA_MANIFEST.json":
                continue
            h.update(f.name.encode())
            content = _read_normalized(f)
            if f.name == "manifest_eval_sweep.json":
                content = content + b" "  # mutate one file
            h.update(content)
        for f in sorted(FIXTURES_DIR.glob("*.json")):
            h.update(f.name.encode())
            h.update(_read_normalized(f))
        mutated = f"sha256:{h.hexdigest()}"

        assert mutated != baseline, (
            "Mutating a schema file did not change the fixture-set digest — "
            "digest algorithm is insensitive to content changes"
        )

    def test_digest_changes_on_extra_file(self):
        """Adding a phantom file to the schema set must change the digest.

        This proves the digest domain is "exact canonical tree" (all files
        in the directory), not "known file blobs" (only files listed in the
        manifest). An extra file that isn't in the manifest but IS in the
        directory will still change the digest and break CI.
        """
        baseline = _compute_fixture_set_digest()

        # Simulate: what if an extra file "phantom.json" existed?
        h = hashlib.sha256()
        files = sorted(SCHEMAS_DIR.glob("*.json"))
        files_filtered = [f for f in files if f.name != "SCHEMA_MANIFEST.json"]
        # Insert phantom file in sorted position
        all_names = sorted([f.name for f in files_filtered] + ["phantom.json"])
        for name in all_names:
            h.update(name.encode())
            if name == "phantom.json":
                h.update(b'{"phantom": true}')
            else:
                h.update(_read_normalized(SCHEMAS_DIR / name))
        for f in sorted(FIXTURES_DIR.glob("*.json")):
            h.update(f.name.encode())
            h.update(_read_normalized(f))
        with_extra = f"sha256:{h.hexdigest()}"

        assert with_extra != baseline, (
            "Adding an extra file did not change the digest — "
            "digest domain does not cover the full path set"
        )

    def test_digest_changes_on_missing_file(self):
        """Removing a file from the schema set must change the digest.

        The digest includes filename + content for every file. Removing
        a file removes its (filename, content) pair from the hash input.
        """
        baseline = _compute_fixture_set_digest()

        # Simulate: what if manifest_eval_sweep.json was missing?
        h = hashlib.sha256()
        for f in sorted(SCHEMAS_DIR.glob("*.json")):
            if f.name == "SCHEMA_MANIFEST.json":
                continue
            if f.name == "manifest_eval_sweep.json":
                continue  # skip this file
            h.update(f.name.encode())
            h.update(_read_normalized(f))
        for f in sorted(FIXTURES_DIR.glob("*.json")):
            h.update(f.name.encode())
            h.update(_read_normalized(f))
        without_file = f"sha256:{h.hexdigest()}"

        assert without_file != baseline, (
            "Removing a file did not change the digest — "
            "digest does not cover file set membership"
        )

    def test_digest_changes_on_rename(self):
        """Renaming a file must change the digest (filename is part of hash input)."""
        baseline = _compute_fixture_set_digest()

        # Simulate: what if "manifest_eval_sweep.json" was renamed to "manifest_eval_sweep_v2.json"?
        h = hashlib.sha256()
        for f in sorted(SCHEMAS_DIR.glob("*.json")):
            if f.name == "SCHEMA_MANIFEST.json":
                continue
            name = f.name
            if name == "manifest_eval_sweep.json":
                name = "manifest_eval_sweep_v2.json"
            h.update(name.encode())
            h.update(_read_normalized(f))
        for f in sorted(FIXTURES_DIR.glob("*.json")):
            h.update(f.name.encode())
            h.update(_read_normalized(f))
        renamed = f"sha256:{h.hexdigest()}"

        assert renamed != baseline, (
            "Renaming a file did not change the digest — "
            "filename is not part of the hash input"
        )

    def test_schema_and_fixture_counts_match(self):
        """Manifest records expected counts — catch added/removed files."""
        manifest = _load(MANIFEST_PATH)
        expected_schemas = manifest.get("schema_count", 0)
        expected_fixtures = manifest.get("fixture_count", 0)

        actual_schemas = len([
            f for f in SCHEMAS_DIR.glob("*.json")
            if f.name != "SCHEMA_MANIFEST.json"
        ])
        actual_fixtures = len(list(FIXTURES_DIR.glob("*.json")))

        assert actual_schemas == expected_schemas, (
            f"Schema count mismatch: expected {expected_schemas}, found {actual_schemas}"
        )
        assert actual_fixtures == expected_fixtures, (
            f"Fixture count mismatch: expected {expected_fixtures}, found {actual_fixtures}"
        )
