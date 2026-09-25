"""Export the FastAPI app's OpenAPI schema for `@cq/api-client` codegen.

Run via `uv run python backend/scripts/export_openapi.py` (also what
`make api-client` runs first). Takes no CLI flags — the destination path is
fixed so every consumer (CQ-005's generator) can rely on it.
"""

import json
from pathlib import Path

from app.main import app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "packages" / "api-client" / "openapi.json"


def export_openapi(output_path: Path = OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(app.openapi(), indent=2))
    return output_path


if __name__ == "__main__":
    written_to = export_openapi()
    print(f"Wrote OpenAPI schema to {written_to}")
