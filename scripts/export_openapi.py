"""Export the FastAPI OpenAPI 3.1 specification to openapi.json and sync TypeScript contracts."""

import json
from pathlib import Path

from app.main import app


def main() -> None:
    schema = app.openapi()
    out_path = Path(__file__).resolve().parent.parent / "openapi.json"
    out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Exported OpenAPI specification ({len(schema.get('paths', {}))} paths) to {out_path}")


if __name__ == "__main__":
    main()
