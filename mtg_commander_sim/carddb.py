from __future__ import annotations

import difflib
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .util import iter_jsonl, normalize_card_name, stable_json, truncate

SCHEMA_VERSION = 1


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Ruling:
    oracle_id: str
    published_at: str
    source: str
    comment: str


@dataclass(frozen=True, slots=True)
class CardRecord:
    oracle_id: str
    name: str
    mana_cost: str
    mana_value: float
    type_line: str
    oracle_text: str
    power: str | None
    toughness: str | None
    loyalty: str | None
    defense: str | None
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    keywords: tuple[str, ...]
    produced_mana: tuple[str, ...]
    layout: str
    released_at: str
    legalities: dict[str, str]
    faces: tuple[dict[str, Any], ...]
    raw: dict[str, Any]

    def has_type(self, card_type: str) -> bool:
        return card_type.casefold() in self.type_line.casefold()

    @property
    def is_land(self) -> bool:
        return self.has_type("land")

    @property
    def is_creature(self) -> bool:
        return self.has_type("creature")

    @property
    def is_instant(self) -> bool:
        return self.has_type("instant")

    @property
    def is_sorcery(self) -> bool:
        return self.has_type("sorcery")

    @property
    def is_permanent_spell(self) -> bool:
        return any(
            self.has_type(card_type)
            for card_type in ("artifact", "battle", "creature", "enchantment", "planeswalker")
        )

    @property
    def has_flash(self) -> bool:
        return "Flash" in self.keywords or self.oracle_text.startswith("Flash")

    @property
    def has_haste(self) -> bool:
        return "Haste" in self.keywords

    @property
    def has_vigilance(self) -> bool:
        return "Vigilance" in self.keywords

    def compact(self, include_raw: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "oracle_id": self.oracle_id,
            "name": self.name,
            "mana_cost": self.mana_cost,
            "mana_value": self.mana_value,
            "type_line": self.type_line,
            "oracle_text": self.oracle_text,
            "power": self.power,
            "toughness": self.toughness,
            "loyalty": self.loyalty,
            "defense": self.defense,
            "colors": list(self.colors),
            "color_identity": list(self.color_identity),
            "keywords": list(self.keywords),
            "produced_mana": list(self.produced_mana),
            "layout": self.layout,
            "released_at": self.released_at,
            "faces": list(self.faces),
        }
        if include_raw:
            result["raw"] = self.raw
        return result


def _combined_faces(card: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    faces = card.get("card_faces") or []
    if not faces:
        return (
            str(card.get("mana_cost") or ""),
            str(card.get("oracle_text") or ""),
            [],
        )
    compact_faces: list[dict[str, Any]] = []
    mana_costs: list[str] = []
    texts: list[str] = []
    for face in faces:
        face_compact = {
            "name": face.get("name"),
            "mana_cost": face.get("mana_cost") or "",
            "type_line": face.get("type_line") or "",
            "oracle_text": face.get("oracle_text") or "",
            "power": face.get("power"),
            "toughness": face.get("toughness"),
            "loyalty": face.get("loyalty"),
            "defense": face.get("defense"),
            "colors": face.get("colors") or [],
        }
        compact_faces.append(face_compact)
        mana_costs.append(str(face_compact["mana_cost"]))
        text = str(face_compact["oracle_text"])
        if text:
            texts.append(f"{face_compact['name']}: {text}")
    return " // ".join(mana_costs), "\n//\n".join(texts), compact_faces


def build_card_database(
    oracle_cards_path: str | Path,
    rulings_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    batch_size: int = 1000,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Build a compact indexed SQLite database from Scryfall bulk JSONL files."""
    oracle_cards_path = Path(oracle_cards_path)
    rulings_path = Path(rulings_path)
    output_path = Path(output_path)
    if output_path.exists():
        if not overwrite:
            raise FileExistsError(f"Database already exists: {output_path}")
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(output_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE cards (
            oracle_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            mana_cost TEXT NOT NULL,
            mana_value REAL NOT NULL,
            type_line TEXT NOT NULL,
            oracle_text TEXT NOT NULL,
            power TEXT,
            toughness TEXT,
            loyalty TEXT,
            defense TEXT,
            colors_json TEXT NOT NULL,
            color_identity_json TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            produced_mana_json TEXT NOT NULL,
            layout TEXT NOT NULL,
            released_at TEXT NOT NULL,
            legalities_json TEXT NOT NULL,
            faces_json TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE aliases (
            normalized_alias TEXT NOT NULL,
            alias TEXT NOT NULL,
            oracle_id TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (normalized_alias, oracle_id),
            FOREIGN KEY (oracle_id) REFERENCES cards(oracle_id)
        );

        CREATE TABLE rulings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            oracle_id TEXT NOT NULL,
            published_at TEXT NOT NULL,
            source TEXT NOT NULL,
            comment TEXT NOT NULL
        );

        CREATE INDEX idx_cards_normalized_name ON cards(normalized_name);
        CREATE INDEX idx_aliases_normalized_alias ON aliases(normalized_alias);
        CREATE INDEX idx_aliases_oracle_id ON aliases(oracle_id);
        CREATE INDEX idx_rulings_oracle_id ON rulings(oracle_id, published_at);
        """
    )

    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("oracle_source", str(oracle_cards_path)),
            ("oracle_source_sha256", file_sha256(oracle_cards_path)),
            ("rulings_source", str(rulings_path)),
            ("rulings_source_sha256", file_sha256(rulings_path)),
            ("include_raw", "1" if include_raw else "0"),
        ],
    )

    card_rows: list[tuple[Any, ...]] = []
    alias_rows: list[tuple[str, str, str, int]] = []
    card_count = 0
    alias_count = 0

    def flush_cards() -> None:
        nonlocal card_count, alias_count
        if not card_rows:
            return
        connection.executemany(
            """
            INSERT INTO cards(
                oracle_id, name, normalized_name, mana_cost, mana_value,
                type_line, oracle_text, power, toughness, loyalty, defense,
                colors_json, color_identity_json, keywords_json,
                produced_mana_json, layout, released_at, legalities_json,
                faces_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            card_rows,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO aliases(normalized_alias, alias, oracle_id, priority)
            VALUES (?, ?, ?, ?)
            """,
            alias_rows,
        )
        card_count += len(card_rows)
        alias_count += len(alias_rows)
        card_rows.clear()
        alias_rows.clear()

    for card in iter_jsonl(oracle_cards_path):
        oracle_id = str(card.get("oracle_id") or "")
        name = str(card.get("name") or "")
        if not oracle_id or not name:
            continue
        mana_cost, oracle_text, faces = _combined_faces(card)
        type_line = str(card.get("type_line") or "")
        if not type_line and faces:
            type_line = " // ".join(str(face.get("type_line") or "") for face in faces)
        card_rows.append(
            (
                oracle_id,
                name,
                normalize_card_name(name),
                mana_cost,
                float(card.get("cmc") or 0),
                type_line,
                oracle_text,
                card.get("power"),
                card.get("toughness"),
                card.get("loyalty"),
                card.get("defense"),
                stable_json(card.get("colors") or []),
                stable_json(card.get("color_identity") or []),
                stable_json(card.get("keywords") or []),
                stable_json(card.get("produced_mana") or []),
                str(card.get("layout") or "normal"),
                str(card.get("released_at") or ""),
                stable_json(card.get("legalities") or {}),
                stable_json(faces),
                stable_json(card) if include_raw else "{}",
            )
        )
        alias_rows.append((normalize_card_name(name), name, oracle_id, 100))
        if " // " in name:
            for face_name in name.split(" // "):
                alias_rows.append((normalize_card_name(face_name), face_name, oracle_id, 80))
        for face in faces:
            face_name = str(face.get("name") or "")
            if face_name:
                alias_rows.append((normalize_card_name(face_name), face_name, oracle_id, 90))
        if len(card_rows) >= batch_size:
            flush_cards()
            connection.commit()
    flush_cards()
    connection.commit()

    ruling_rows: list[tuple[str, str, str, str]] = []
    ruling_count = 0
    for ruling in iter_jsonl(rulings_path):
        oracle_id = str(ruling.get("oracle_id") or "")
        comment = str(ruling.get("comment") or "")
        if not oracle_id or not comment:
            continue
        ruling_rows.append(
            (
                oracle_id,
                str(ruling.get("published_at") or ""),
                str(ruling.get("source") or ""),
                comment,
            )
        )
        if len(ruling_rows) >= batch_size:
            connection.executemany(
                "INSERT INTO rulings(oracle_id, published_at, source, comment) VALUES (?, ?, ?, ?)",
                ruling_rows,
            )
            ruling_count += len(ruling_rows)
            ruling_rows.clear()
            connection.commit()
    if ruling_rows:
        connection.executemany(
            "INSERT INTO rulings(oracle_id, published_at, source, comment) VALUES (?, ?, ?, ?)",
            ruling_rows,
        )
        ruling_count += len(ruling_rows)
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [("card_count", str(card_count)), ("ruling_count", str(ruling_count))],
    )
    connection.commit()

    fts_enabled = False
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE cards_fts USING fts5(name, oracle_text, oracle_id UNINDEXED)"
        )
        connection.execute(
            "INSERT INTO cards_fts(name, oracle_text, oracle_id) SELECT name, oracle_text, oracle_id FROM cards"
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('fts_enabled', '1')"
        )
        connection.commit()
        fts_enabled = True
    except sqlite3.OperationalError:
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('fts_enabled', '0')"
        )
        connection.commit()

    connection.execute("PRAGMA optimize")
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.close()
    return {
        "database": str(output_path),
        "cards": card_count,
        "aliases": alias_count,
        "rulings": ruling_count,
        "fts_enabled": fts_enabled,
    }


class CardDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CardDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def metadata(self) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in self.connection.execute("SELECT key, value FROM metadata")
        }

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> CardRecord:
        return CardRecord(
            oracle_id=str(row["oracle_id"]),
            name=str(row["name"]),
            mana_cost=str(row["mana_cost"]),
            mana_value=float(row["mana_value"]),
            type_line=str(row["type_line"]),
            oracle_text=str(row["oracle_text"]),
            power=row["power"],
            toughness=row["toughness"],
            loyalty=row["loyalty"],
            defense=row["defense"],
            colors=tuple(json.loads(row["colors_json"])),
            color_identity=tuple(json.loads(row["color_identity_json"])),
            keywords=tuple(json.loads(row["keywords_json"])),
            produced_mana=tuple(json.loads(row["produced_mana_json"])),
            layout=str(row["layout"]),
            released_at=str(row["released_at"]),
            legalities=dict(json.loads(row["legalities_json"])),
            faces=tuple(json.loads(row["faces_json"])),
            raw=dict(json.loads(row["raw_json"])),
        )

    def by_oracle_id(self, oracle_id: str) -> CardRecord:
        row = self.connection.execute(
            "SELECT * FROM cards WHERE oracle_id = ?", (oracle_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown oracle_id: {oracle_id}")
        return self._row_to_card(row)

    def lookup(self, name: str, *, fuzzy: bool = True) -> CardRecord:
        normalized = normalize_card_name(name)
        row = self.connection.execute(
            """
            SELECT c.*
            FROM aliases a
            JOIN cards c ON c.oracle_id = a.oracle_id
            WHERE a.normalized_alias = ?
            ORDER BY a.priority DESC, c.released_at DESC
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        if row is not None:
            return self._row_to_card(row)
        if not fuzzy:
            raise KeyError(f"Card not found: {name}")
        suggestions = self.suggest(name, limit=8)
        if suggestions:
            raise KeyError(f"Card not found: {name}. Suggestions: {', '.join(suggestions)}")
        raise KeyError(f"Card not found: {name}")

    def suggest(self, name: str, *, limit: int = 8) -> list[str]:
        normalized = normalize_card_name(name)
        prefix = normalized[: max(2, min(8, len(normalized)))] + "%"
        rows = self.connection.execute(
            """
            SELECT DISTINCT alias, normalized_alias
            FROM aliases
            WHERE normalized_alias LIKE ?
            ORDER BY priority DESC, alias
            LIMIT 100
            """,
            (prefix,),
        ).fetchall()
        candidates = {str(row["normalized_alias"]): str(row["alias"]) for row in rows}
        if len(candidates) < 10:
            extra = self.connection.execute(
                "SELECT DISTINCT alias, normalized_alias FROM aliases LIMIT 50000"
            ).fetchall()
            for row in extra:
                candidates.setdefault(str(row["normalized_alias"]), str(row["alias"]))
        matches = difflib.get_close_matches(normalized, candidates.keys(), n=limit, cutoff=0.45)
        return [candidates[match] for match in matches]

    def rulings(self, card_or_oracle_id: str | CardRecord) -> list[Ruling]:
        oracle_id = (
            card_or_oracle_id.oracle_id
            if isinstance(card_or_oracle_id, CardRecord)
            else card_or_oracle_id
        )
        rows = self.connection.execute(
            """
            SELECT oracle_id, published_at, source, comment
            FROM rulings
            WHERE oracle_id = ?
            ORDER BY published_at, id
            """,
            (oracle_id,),
        ).fetchall()
        return [
            Ruling(
                oracle_id=str(row["oracle_id"]),
                published_at=str(row["published_at"]),
                source=str(row["source"]),
                comment=str(row["comment"]),
            )
            for row in rows
        ]

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        oracle_text: bool = True,
    ) -> list[CardRecord]:
        metadata = self.metadata()
        rows: Sequence[sqlite3.Row]
        if metadata.get("fts_enabled") == "1":
            try:
                rows = self.connection.execute(
                    """
                    SELECT c.*
                    FROM cards_fts f
                    JOIN cards c ON c.oracle_id = f.oracle_id
                    WHERE cards_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
                return [self._row_to_card(row) for row in rows]
            except sqlite3.OperationalError:
                pass
        term = f"%{query}%"
        if oracle_text:
            rows = self.connection.execute(
                "SELECT * FROM cards WHERE name LIKE ? OR oracle_text LIKE ? LIMIT ?",
                (term, term, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM cards WHERE name LIKE ? LIMIT ?", (term, limit)
            ).fetchall()
        return [self._row_to_card(row) for row in rows]

    def rules_digest(
        self,
        names: Iterable[str],
        *,
        include_rulings: bool = True,
        max_rulings_per_card: int | None = None,
        format: str = "markdown",
    ) -> str | list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in names:
            card = self.lookup(name)
            if card.oracle_id in seen:
                continue
            seen.add(card.oracle_id)
            rulings = self.rulings(card) if include_rulings else []
            if max_rulings_per_card is not None:
                rulings = rulings[-max_rulings_per_card:]
            payload.append(
                {
                    "name": card.name,
                    "oracle_id": card.oracle_id,
                    "mana_cost": card.mana_cost,
                    "mana_value": card.mana_value,
                    "type_line": card.type_line,
                    "oracle_text": card.oracle_text,
                    "power": card.power,
                    "toughness": card.toughness,
                    "loyalty": card.loyalty,
                    "keywords": list(card.keywords),
                    "produced_mana": list(card.produced_mana),
                    "faces": list(card.faces),
                    "rulings": [
                        {
                            "published_at": ruling.published_at,
                            "source": ruling.source,
                            "comment": ruling.comment,
                        }
                        for ruling in rulings
                    ],
                }
            )
        if format == "json":
            return payload
        if format != "markdown":
            raise ValueError("format must be 'markdown' or 'json'")
        sections: list[str] = []
        for item in payload:
            heading = f"### {item['name']}"
            line = f"{item['mana_cost']} — {item['type_line']} — MV {item['mana_value']:g}"
            stats = []
            if item["power"] is not None or item["toughness"] is not None:
                stats.append(f"P/T {item['power']}/{item['toughness']}")
            if item["loyalty"] is not None:
                stats.append(f"Loyalty {item['loyalty']}")
            if item["keywords"]:
                stats.append("Keywords: " + ", ".join(item["keywords"]))
            body = item["oracle_text"] or "(No Oracle text.)"
            section = [heading, line]
            if stats:
                section.append("; ".join(stats))
            section.append(body)
            if item["rulings"]:
                section.append("Rulings:")
                for ruling in item["rulings"]:
                    section.append(
                        f"- {ruling['published_at']} [{ruling['source']}]: {ruling['comment']}"
                    )
            sections.append("\n\n".join(section))
        return "\n\n".join(sections)

    def compact_brief(self, name: str, *, max_text: int = 280) -> dict[str, Any]:
        card = self.lookup(name)
        return {
            "name": card.name,
            "mana_cost": card.mana_cost,
            "mana_value": card.mana_value,
            "type_line": card.type_line,
            "oracle_text": truncate(card.oracle_text, max_text),
            "power_toughness": (
                f"{card.power}/{card.toughness}"
                if card.power is not None or card.toughness is not None
                else None
            ),
            "keywords": list(card.keywords),
            "produced_mana": list(card.produced_mana),
        }
