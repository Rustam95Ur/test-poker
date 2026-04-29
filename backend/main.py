import base64
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = ROOT_DIR / "stat_catalog.json"
POPULATION_PATH = ROOT_DIR / "population_hands.txt"
GTO_PATH = ROOT_DIR / "gto_hands.txt"
USE_CLICKHOUSE_STATS = os.getenv("USE_CLICKHOUSE_STATS", "0").lower() in {"1", "true", "yes"}
CLICKHOUSE_HTTP_HOST = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_HTTP_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "poker")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "app")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "app_pass_123")
CLICKHOUSE_AGG_TABLE = os.getenv("CLICKHOUSE_AGG_TABLE", "events_agg")

TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*[:=]\s*([A-Za-z0-9_./-]+)")

app = FastAPI(title="Mini Poker Stats Explorer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _parse_hands(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    hands: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = {k: v for k, v in TOKEN_RE.findall(line)}
        if tokens:
            hands.append(tokens)
    return hands


def _matches_context(hand: dict[str, str], context_filters: dict[str, Any] | None) -> bool:
    if not context_filters:
        return True
    for key, value in context_filters.items():
        if value is None:
            continue
        if hand.get(key) != str(value):
            return False
    return True


def _matches_rule(hand: dict[str, str], rule: dict[str, Any] | None) -> bool:
    if not rule:
        return False
    for key, value in rule.items():
        if value is None:
            continue
        if hand.get(key) != str(value):
            return False
    return True


def _compute_single_stat(stat: dict[str, Any], hands: list[dict[str, str]]) -> dict[str, Any]:
    state = stat.get("state", "AVAILABLE")
    if state in {"NO_STAT", "INVALID_CONTEXT"}:
        return {
            "value": None,
            "numerator": None,
            "denominator": None,
            "sampleStatus": state.lower(),
            "matchedHands": [],
        }

    context_filters = stat.get("contextFilters") or {}
    opportunity = stat.get("opportunity")
    success = stat.get("success")

    context_hands = [hand for hand in hands if _matches_context(hand, context_filters)]
    denominator_hands = [hand for hand in context_hands if _matches_rule(hand, opportunity)]
    numerator_hands = [hand for hand in denominator_hands if _matches_rule(hand, success)]

    denominator = len(denominator_hands)
    numerator = len(numerator_hands)

    if denominator == 0:
        return {
            "value": None,
            "numerator": numerator,
            "denominator": denominator,
            "sampleStatus": "no_data",
            "matchedHands": numerator_hands[:5],
        }

    value = numerator / denominator
    min_sample = int(stat.get("minSample") or 0)
    sample_status = "low_sample" if denominator < min_sample else "ok"
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "sampleStatus": sample_status,
        "matchedHands": numerator_hands[:5],
    }


def _compute_stats() -> list[dict[str, Any]]:
    catalog = _load_catalog()
    population_hands = _parse_hands(POPULATION_PATH)
    gto_hands = _parse_hands(GTO_PATH)
    rows: list[dict[str, Any]] = []

    for stat in catalog:
        pop = _compute_single_stat(stat, population_hands)
        gto = _compute_single_stat(stat, gto_hands)
        pop_value = pop["value"]
        gto_value = gto["value"]
        delta = None if pop_value is None or gto_value is None else pop_value - gto_value
        rows.append(
            {
                "stat": stat,
                "population": pop,
                "gto": gto,
                "delta": delta,
            }
        )
    return rows


def _sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _value_clause(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if key == "linePrefix":
        return f"startsWith(line, '{_sql_escape(str(value))}')"
    if key == "canAct":
        return f"canAct = {1 if bool(value) else 0}"
    return f"{key} = '{_sql_escape(str(value))}'"


def _build_where(stat: dict[str, Any], mode: str) -> str:
    context = stat.get("contextFilters") or {}
    rule = stat.get(mode) or {}
    clauses: list[str] = []
    for key, value in context.items():
        clause = _value_clause(key, value)
        if clause:
            clauses.append(clause)
    for key, value in rule.items():
        clause = _value_clause(key, value)
        if clause:
            clauses.append(clause)
    return " AND ".join(clauses) if clauses else "1"


def _clickhouse_query(query: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"database": CLICKHOUSE_DB, "query": query})
    url = f"http://{CLICKHOUSE_HTTP_HOST}:{CLICKHOUSE_HTTP_PORT}/?{params}"
    req = urllib.request.Request(url=url, method="POST")
    token = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASSWORD}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = resp.read().decode("utf-8", errors="ignore")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _compute_single_stat_clickhouse(stat: dict[str, Any], source_type: str) -> dict[str, Any]:
    state = stat.get("state", "AVAILABLE")
    if state in {"NO_STAT", "INVALID_CONTEXT"}:
        return {
            "value": None,
            "numerator": None,
            "denominator": None,
            "sampleStatus": state.lower(),
            "matchedHands": [],
        }

    den_where = _build_where(stat, "opportunity")
    num_where = _build_where(stat, "success")
    source = _sql_escape(source_type)
    query = f"""
    WITH
    den AS (
      SELECT coalesce(sum(cnt), 0) AS denominator
      FROM {CLICKHOUSE_AGG_TABLE}
      WHERE source_type = '{source}' AND {den_where}
    ),
    num AS (
      SELECT coalesce(sum(cnt), 0) AS numerator
      FROM {CLICKHOUSE_AGG_TABLE}
      WHERE source_type = '{source}' AND {num_where}
    )
    SELECT
      toInt64(numerator) AS numerator,
      toInt64(denominator) AS denominator,
      if(denominator = 0, NULL, numerator / denominator) AS value
    FROM num, den
    FORMAT JSONEachRow
    """
    rows = _clickhouse_query(query)
    payload = rows[0] if rows else {"numerator": 0, "denominator": 0, "value": None}
    numerator = int(payload.get("numerator") or 0)
    denominator = int(payload.get("denominator") or 0)
    value = payload.get("value")
    if denominator == 0:
        return {
            "value": None,
            "numerator": numerator,
            "denominator": denominator,
            "sampleStatus": "no_data",
            "matchedHands": [],
        }
    min_sample = int(stat.get("minSample") or 0)
    sample_status = "low_sample" if denominator < min_sample else "ok"
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "sampleStatus": sample_status,
        "matchedHands": [],
    }


def _compute_stats_clickhouse() -> list[dict[str, Any]]:
    catalog = _load_catalog()
    rows: list[dict[str, Any]] = []
    for stat in catalog:
        pop = _compute_single_stat_clickhouse(stat, "population")
        gto = _compute_single_stat_clickhouse(stat, "gto")
        pop_value = pop["value"]
        gto_value = gto["value"]
        delta = None if pop_value is None or gto_value is None else pop_value - gto_value
        rows.append({"stat": stat, "population": pop, "gto": gto, "delta": delta})
    return rows


def _matches_stat_filters(
    stat: dict[str, Any],
    spot: str | None,
    formation: str | None,
    position: str | None,
    role: str | None,
    line: str | None,
    street: str | None,
) -> bool:
    checks = {
        "spot": spot,
        "formation": formation,
        "position": position,
        "role": role,
        "line": line,
        "street": street,
    }
    for key, value in checks.items():
        if value is None:
            continue
        if str(stat.get(key)) != value:
            return False
    return True


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/meta")
def meta() -> dict[str, Any]:
    return {
        "catalogPath": str(CATALOG_PATH),
        "populationPath": str(POPULATION_PATH),
        "gtoPath": str(GTO_PATH),
        "populationExists": POPULATION_PATH.exists(),
        "gtoExists": GTO_PATH.exists(),
        "useClickhouseStats": USE_CLICKHOUSE_STATS,
        "clickhouseAggTable": CLICKHOUSE_AGG_TABLE,
        "assumption": "Parser expects tokenized lines like key=value or key:value per hand event.",
    }


@app.get("/api/v1/stats")
def stats(
    spot: str | None = Query(default=None),
    formation: str | None = Query(default=None),
    position: str | None = Query(default=None),
    role: str | None = Query(default=None),
    line: str | None = Query(default=None),
    street: str | None = Query(default=None),
) -> dict[str, Any]:
    if USE_CLICKHOUSE_STATS:
        try:
            rows = _compute_stats_clickhouse()
        except Exception:
            rows = _compute_stats()
    else:
        rows = _compute_stats()
    rows = [
        row
        for row in rows
        if _matches_stat_filters(row["stat"], spot, formation, position, role, line, street)
    ]
    return {"items": rows, "count": len(rows)}
