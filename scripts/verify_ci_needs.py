from __future__ import annotations

import json
import os


def failed_dependencies(value: dict) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, details in value.items()
            if not isinstance(details, dict) or details.get("result") != "success"
        )
    )


def main() -> int:
    raw = os.environ.get("CI_NEEDS_JSON")
    if not raw:
        print("CI_NEEDS_JSON is required")
        return 1
    value = json.loads(raw)
    if not isinstance(value, dict):
        print("CI_NEEDS_JSON must contain an object")
        return 1
    failed = failed_dependencies(value)
    print(json.dumps({"failed_dependencies": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
