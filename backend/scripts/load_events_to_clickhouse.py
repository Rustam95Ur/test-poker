import base64
import os
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from pathlib import Path

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "poker")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "app")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "app_pass_123")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
POPULATION_PATH = ROOT_DIR / "population_hands.txt"
GTO_PATH = ROOT_DIR / "gto_hands.txt"

EVENT_COLUMNS = [
    "source_type",
    "spot",
    "formation",
    "position",
    "role",
    "street",
    "action",
    "line",
    "canAct",
    "facingAction",
    "sizeBucket",
]


def _ch_post(query: str) -> str:
    params = urllib.parse.urlencode({"database": CLICKHOUSE_DB, "query": query})
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/?{params}"
    req = urllib.request.Request(url=url, method="POST")
    token = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASSWORD}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except HTTPError as err:
        details = err.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"ClickHouse HTTP {err.code}: {details}") from err


def _ch_insert(query: str, body: str) -> None:
    params = urllib.parse.urlencode({"database": CLICKHOUSE_DB, "query": query})
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/?{params}"
    req = urllib.request.Request(url=url, data=body.encode("utf-8"), method="POST")
    token = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASSWORD}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=120):
            return
    except HTTPError as err:
        details = err.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"ClickHouse HTTP {err.code}: {details}") from err


def _parse_tokenized_line(line: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for part in line.strip().split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        tokens[k] = v
    return tokens


def _to_tsv_value(value: str | None) -> str:
    if value is None or value == "":
        return r"\N"
    return value.replace("\t", " ").replace("\n", " ")


def _tokenized_file_to_tsv(path: Path, source_type: str) -> tuple[str, int]:
    if not path.exists():
        return "", 0
    rows: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = _parse_tokenized_line(line)
        spot = tokens.get("spot")
        formation = tokens.get("formation")
        position = tokens.get("position")
        role = tokens.get("role")
        street = tokens.get("street")
        action = tokens.get("action")
        line_code = tokens.get("line")
        if not all([spot, formation, position, role, street, action, line_code]):
            continue
        can_act = "1" if tokens.get("canAct", "true").lower() in {"1", "true", "yes"} else "0"
        facing_action = tokens.get("facingAction")
        size_bucket = tokens.get("sizeBucket")
        row = "\t".join(
            [
                _to_tsv_value(source_type),
                _to_tsv_value(spot),
                _to_tsv_value(formation),
                _to_tsv_value(position),
                _to_tsv_value(role),
                _to_tsv_value(street),
                _to_tsv_value(action),
                _to_tsv_value(line_code),
                can_act,
                _to_tsv_value(facing_action),
                _to_tsv_value(size_bucket),
            ]
        )
        rows.append(row)
    return "\n".join(rows) + ("\n" if rows else ""), len(rows)


def _ensure_schema() -> None:
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS events
        (
            source_type LowCardinality(String),
            spot LowCardinality(String),
            formation LowCardinality(String),
            position LowCardinality(String),
            role LowCardinality(String),
            street LowCardinality(String),
            action LowCardinality(String),
            line String,
            canAct UInt8,
            facingAction Nullable(String),
            sizeBucket Nullable(String)
        )
        ENGINE = MergeTree
        ORDER BY (source_type, spot, formation, position, role, street, line, action, canAct)
        """
    )
    _ch_post(
        """
        CREATE TABLE IF NOT EXISTS events_agg
        (
            source_type LowCardinality(String),
            spot LowCardinality(String),
            formation LowCardinality(String),
            position LowCardinality(String),
            role LowCardinality(String),
            street LowCardinality(String),
            line String,
            action LowCardinality(String),
            canAct UInt8,
            facingAction Nullable(String),
            sizeBucket Nullable(String),
            cnt UInt64
        )
        ENGINE = SummingMergeTree
        ORDER BY (source_type, spot, formation, position, role, street, line, action, canAct)
        """
    )


def _reload_events() -> tuple[int, int]:
    _ch_post("TRUNCATE TABLE events")
    pop_tsv, pop_count = _tokenized_file_to_tsv(POPULATION_PATH, "population")
    gto_tsv, gto_count = _tokenized_file_to_tsv(GTO_PATH, "gto")

    insert_sql = f"INSERT INTO events ({', '.join(EVENT_COLUMNS)}) FORMAT TabSeparated"
    if pop_tsv:
        _ch_insert(insert_sql, pop_tsv)
    if gto_tsv:
        _ch_insert(insert_sql, gto_tsv)
    return pop_count, gto_count


def _rebuild_agg() -> None:
    _ch_post("TRUNCATE TABLE events_agg")
    _ch_post(
        """
        INSERT INTO events_agg
        SELECT
            source_type,
            spot,
            formation,
            position,
            role,
            street,
            line,
            action,
            canAct,
            facingAction,
            sizeBucket,
            count() AS cnt
        FROM events
        GROUP BY
            source_type, spot, formation, position, role, street, line, action, canAct, facingAction, sizeBucket
        """
    )


def _count_rows(table: str) -> int:
    result = _ch_post(f"SELECT count() FROM {table} FORMAT TSV").strip()
    return int(result or "0")


def main() -> None:
    _ensure_schema()
    pop_count, gto_count = _reload_events()
    _rebuild_agg()
    events_count = _count_rows("events")
    agg_count = _count_rows("events_agg")
    print(f"loaded population events: {pop_count}")
    print(f"loaded gto events: {gto_count}")
    print(f"events rows total: {events_count}")
    print(f"events_agg rows total: {agg_count}")


if __name__ == "__main__":
    main()
