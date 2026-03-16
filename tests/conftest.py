"""
Pytest configuration — schema conformance CI metadata.

Prints validator identity, draft version, and schema provenance at the
top of every test run. When a dependency upgrade causes divergence,
this header tells you exactly what changed.
"""
import json
import sys
from pathlib import Path


def pytest_report_header(config):
    """Print schema conformance metadata at test start."""
    lines = []

    lines.append(f"Python: {sys.version.split()[0]}")

    try:
        import jsonschema
        lines.append(f"jsonschema: {jsonschema.__version__}")
    except ImportError:
        lines.append("jsonschema: NOT INSTALLED")

    lines.append("JSON Schema draft: 2020-12")

    manifest_path = (
        Path(__file__).parent.parent / "hiveai" / "schemas" / "SCHEMA_MANIFEST.json"
    )
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        lines.append(
            f"Schema source: {manifest.get('source_repo', '?')} "
            f"@ {manifest.get('source_commit', '?')} "
            f"(synced {manifest.get('synced_at', '?')})"
        )
    else:
        lines.append("Schema source: SCHEMA_MANIFEST.json not found")

    return lines
