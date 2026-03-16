# Schema Contract Artifacts

**Status:** Vendored from HivePoA — do NOT edit directly.

## Source of Truth

HivePoA repo (`schemas/` directory) is canonical. These files are
byte-exact copies synced via `scripts/sync_schemas.py`.

Changes go to HivePoA first, then sync here.

## Validator

- Library: `jsonschema[format]` (pinned `>=4.21,<5.0`)
- Validator class: `Draft202012Validator`
- Format checking: **enabled** via `FormatChecker()` — this is required
  for behavioral parity with Ajv strict mode + ajv-formats
- Draft: JSON Schema 2020-12

## Sync Method

```bash
python scripts/sync_schemas.py /path/to/HivePoA
python scripts/sync_schemas.py /path/to/HivePoA --force  # if files changed
```

The script copies schemas + fixtures and writes `SCHEMA_MANIFEST.json`
with SHA-256 hashes for every file. CI verifies these hashes to detect
drift.

## Drift Detection

`SCHEMA_MANIFEST.json` records:
- Source repo + commit
- SHA-256 hash of every schema and fixture file
- Sync date

`tests/test_schema_conformance.py::TestSchemaManifestIntegrity` verifies
all hashes match on every test run. If a schema is hand-edited, CI fails.

## What These Are NOT

- These are not Pydantic models (those come later, derived from proven schemas)
- These are not runtime validation code (that comes in Phase 0)
- These are not hand-maintained — treat as generated contract artifacts
