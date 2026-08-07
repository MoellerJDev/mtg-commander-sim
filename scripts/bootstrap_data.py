from __future__ import annotations

import argparse
import gzip
import json
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quorune.bulk import refresh_scryfall_database


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the local Scryfall SQLite database from a bundle or current bulk exports"
    )
    parser.add_argument(
        "--source",
        default="data/scryfall-20260728-compact.sqlite3.gz",
        help="Compressed SQLite file",
    )
    parser.add_argument(
        "--output",
        default="data/scryfall-20260728-compact.sqlite3",
        help="Destination SQLite file",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--refresh-from-scryfall",
        action="store_true",
        help="Discover current Oracle/rulings JSONL archives via GET /bulk-data and rebuild",
    )
    parser.add_argument(
        "--download-dir",
        default="data/bulk",
        help="Cache directory for downloaded Scryfall JSONL archives",
    )
    parser.add_argument("--manifest-url", default="https://api.scryfall.com/bulk-data")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    source = Path(args.source)
    output = Path(args.output)
    if args.refresh_from_scryfall:
        result = refresh_scryfall_database(
            output,
            download_dir=args.download_dir,
            manifest_url=args.manifest_url,
            timeout=args.timeout,
            force_download=args.force,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if output.exists() and not args.force:
        print(f"Already present: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with gzip.open(source, "rb") as compressed, temporary.open("wb") as expanded:
        shutil.copyfileobj(compressed, expanded, length=1024 * 1024)
    temporary.replace(output)
    print(f"Expanded {source} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
