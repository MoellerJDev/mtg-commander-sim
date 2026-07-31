from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .carddb import CardDatabase, build_card_database
from .util import stable_json
from .version import __version__

SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
SCRYFALL_USER_AGENT = f"mtg-commander-sim/{__version__} (local bulk-data importer)"
ALLOWED_DOWNLOAD_HOSTS = frozenset({"data.scryfall.io"})


class ScryfallBulkDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScryfallBulkItem:
    type: str
    name: str
    updated_at: str
    download_uri: str
    compressed_size: int | None = None


def parse_bulk_manifest(payload: Mapping[str, Any]) -> dict[str, ScryfallBulkItem]:
    if payload.get("object") != "list" or not isinstance(payload.get("data"), list):
        raise ScryfallBulkDataError("Scryfall bulk-data response is not a list")

    items: dict[str, ScryfallBulkItem] = {}
    for raw in payload["data"]:
        if not isinstance(raw, Mapping):
            continue
        item_type = str(raw.get("type") or "")
        download_uri = str(
            raw.get("jsonl_download_uri") or raw.get("download_uri") or ""
        )
        parsed_uri = urllib.parse.urlparse(download_uri)
        if (
            not item_type
            or parsed_uri.scheme.casefold() != "https"
            or (parsed_uri.hostname or "").casefold() not in ALLOWED_DOWNLOAD_HOSTS
        ):
            continue
        raw_size = raw.get("compressed_size")
        if raw_size is None and str(raw.get("content_encoding") or "").casefold() == "gzip":
            raw_size = raw.get("size")
        items[item_type] = ScryfallBulkItem(
            type=item_type,
            name=str(raw.get("name") or item_type),
            updated_at=str(raw.get("updated_at") or ""),
            download_uri=download_uri,
            compressed_size=int(raw_size) if raw_size is not None else None,
        )
    return items


def fetch_bulk_manifest(
    *,
    url: str = SCRYFALL_BULK_DATA_URL,
    timeout: float = 30,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[dict[str, ScryfallBulkItem], dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": SCRYFALL_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ScryfallBulkDataError(f"Unable to read {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScryfallBulkDataError("Scryfall bulk-data response must be a JSON object")
    return parse_bulk_manifest(payload), payload


def _download_bulk_item(
    item: ScryfallBulkItem,
    destination_dir: Path,
    *,
    timeout: float,
    force: bool,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    filename = Path(urllib.parse.urlparse(item.download_uri).path).name
    if not filename:
        raise ScryfallBulkDataError(f"Bulk item {item.type!r} has no filename")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    if destination.exists() and not force and destination.stat().st_size > 0:
        return destination

    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        temporary.unlink()
    request = urllib.request.Request(
        item.download_uri,
        headers={
            "Accept": "application/json,application/gzip,application/octet-stream",
            "User-Agent": SCRYFALL_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response, temporary.open("wb") as output:
            content_length = response.headers.get("Content-Length")
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if content_length is not None and temporary.stat().st_size != int(content_length):
            raise ScryfallBulkDataError(
                f"{item.type} download has {temporary.stat().st_size} bytes; "
                f"HTTP response declared {content_length}"
            )
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return destination


def refresh_scryfall_database(
    output_path: str | Path,
    *,
    download_dir: str | Path,
    manifest_url: str = SCRYFALL_BULK_DATA_URL,
    timeout: float = 60,
    force_download: bool = False,
) -> dict[str, Any]:
    """Discover current Oracle/rulings exports and atomically rebuild SQLite.

    Network access is confined to this explicit pre-game import operation.
    Running games continue to use only the resulting local database.
    """

    items, manifest_payload = fetch_bulk_manifest(url=manifest_url, timeout=timeout)
    missing = [item_type for item_type in ("oracle_cards", "rulings") if item_type not in items]
    if missing:
        raise ScryfallBulkDataError(
            "Scryfall manifest omitted required bulk item(s): " + ", ".join(missing)
        )

    download_path = Path(download_dir)
    oracle_path = _download_bulk_item(
        items["oracle_cards"],
        download_path,
        timeout=timeout,
        force=force_download,
    )
    rulings_path = _download_bulk_item(
        items["rulings"],
        download_path,
        timeout=timeout,
        force=force_download,
    )
    (download_path / "bulk-manifest.json").write_text(
        stable_json(manifest_payload), encoding="utf-8"
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".building")
    if temporary.exists():
        temporary.unlink()
    try:
        result = build_card_database(
            oracle_path,
            rulings_path,
            temporary,
            overwrite=True,
        )
        connection = sqlite3.connect(temporary)
        try:
            connection.executemany(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                [
                    ("bulk_manifest_url", manifest_url),
                    ("scryfall_oracle_updated_at", items["oracle_cards"].updated_at),
                    (
                        "scryfall_oracle_download_uri",
                        items["oracle_cards"].download_uri,
                    ),
                    ("scryfall_rulings_updated_at", items["rulings"].updated_at),
                    (
                        "scryfall_rulings_download_uri",
                        items["rulings"].download_uri,
                    ),
                ],
            )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        finally:
            connection.close()
        temporary.replace(output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    with CardDatabase(output) as database:
        metadata = database.metadata()
    result.update(
        {
            "database": str(output),
            "oracle_updated_at": metadata["scryfall_oracle_updated_at"],
            "rulings_updated_at": metadata["scryfall_rulings_updated_at"],
            "oracle_sha256": metadata["oracle_source_sha256"],
            "rulings_sha256": metadata["rulings_source_sha256"],
            "oracle_download": str(oracle_path),
            "rulings_download": str(rulings_path),
        }
    )
    return result
