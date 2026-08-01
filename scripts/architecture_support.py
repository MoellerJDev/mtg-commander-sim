from __future__ import annotations

import base64
import hashlib
from typing import Any, Iterable, Mapping


CARD_NAME_HASH_ALGORITHM = "sha256-truncated-128-v1"
CARD_NAME_DIGEST_BYTES = 16
CARD_NAME_CHUNK_BYTES = 48 * 1024


def normalize_printed_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def printed_name_digest(value: str) -> bytes:
    normalized = normalize_printed_name(value)
    return hashlib.sha256(normalized.encode("utf-8")).digest()[
        :CARD_NAME_DIGEST_BYTES
    ]


def build_card_name_hash_index(
    names: Iterable[str], database_snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    digests = sorted({printed_name_digest(name) for name in names})
    packed = b"".join(digests)
    chunks = [
        base64.b64encode(packed[offset : offset + CARD_NAME_CHUNK_BYTES]).decode(
            "ascii"
        )
        for offset in range(0, len(packed), CARD_NAME_CHUNK_BYTES)
    ]
    return {
        "schema_version": 1,
        "algorithm": CARD_NAME_HASH_ALGORITHM,
        "digest_bytes": CARD_NAME_DIGEST_BYTES,
        "digest_count": len(digests),
        "database_snapshot": dict(database_snapshot),
        "encoding": "sorted fixed-width digests; independently base64-encoded chunks",
        "chunks": chunks,
        "content_boundary": (
            "Contains irreversible truncated SHA-256 digests only; no printed "
            "card names or Scryfall card records."
        ),
    }


def decode_card_name_hash_index(value: Mapping[str, Any]) -> frozenset[bytes]:
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported card-name hash index schema")
    if value.get("algorithm") != CARD_NAME_HASH_ALGORITHM:
        raise ValueError("Unsupported card-name hash algorithm")
    if value.get("digest_bytes") != CARD_NAME_DIGEST_BYTES:
        raise ValueError("Unsupported card-name digest width")
    packed = b"".join(
        base64.b64decode(str(chunk), validate=True)
        for chunk in value.get("chunks", [])
    )
    if len(packed) % CARD_NAME_DIGEST_BYTES:
        raise ValueError("Card-name hash index has a partial digest")
    digests = tuple(
        packed[offset : offset + CARD_NAME_DIGEST_BYTES]
        for offset in range(0, len(packed), CARD_NAME_DIGEST_BYTES)
    )
    if tuple(sorted(digests)) != digests or len(set(digests)) != len(digests):
        raise ValueError("Card-name hash index must be sorted and unique")
    if len(digests) != int(value.get("digest_count") or -1):
        raise ValueError("Card-name hash index count does not match its payload")
    return frozenset(digests)
