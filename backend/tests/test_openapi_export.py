"""AC6: `export_openapi.py` writes valid JSON that round-trips through `json.load`."""

import json
from pathlib import Path

from scripts.export_openapi import OUTPUT_PATH, export_openapi


def test_default_output_path_is_packages_api_client_openapi_json() -> None:
    assert OUTPUT_PATH.name == "openapi.json"
    assert OUTPUT_PATH.parent.name == "api-client"
    assert OUTPUT_PATH.parent.parent.name == "packages"


def test_output_is_valid_json(tmp_path: Path) -> None:
    destination = tmp_path / "openapi.json"

    written_to = export_openapi(destination)

    assert written_to == destination
    with written_to.open() as f:
        schema = json.load(f)

    assert schema["openapi"]
    assert "/health" in schema["paths"]
