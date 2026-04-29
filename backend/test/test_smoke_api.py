import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import main


def _write_fixture_files(tmp_path: Path) -> None:
    catalog = [
        {
            "id": "s1",
            "label": "Flop bet frequency",
            "spot": "SRP",
            "formation": "BB_SB",
            "position": "OOP",
            "role": "PFR",
            "line": "B",
            "street": "flop",
            "state": "AVAILABLE",
            "minSample": 1,
            "contextFilters": {"spot": "SRP", "formation": "BB_SB", "position": "OOP", "role": "PFR"},
            "opportunity": {"street": "flop", "canAct": "true"},
            "success": {"street": "flop", "action": "bet"},
        }
    ]
    (tmp_path / "stat_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (tmp_path / "population_hands.txt").write_text(
        "spot=SRP formation=BB_SB position=OOP role=PFR street=flop canAct=true action=bet line=B\n",
        encoding="utf-8",
    )
    (tmp_path / "gto_hands.txt").write_text(
        "spot=SRP formation=BB_SB position=OOP role=PFR street=flop canAct=true action=check line=X\n",
        encoding="utf-8",
    )


def test_health_endpoint() -> None:
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stats_endpoint_filters(tmp_path: Path, monkeypatch) -> None:
    _write_fixture_files(tmp_path)
    monkeypatch.setattr(main, "CATALOG_PATH", tmp_path / "stat_catalog.json")
    monkeypatch.setattr(main, "POPULATION_PATH", tmp_path / "population_hands.txt")
    monkeypatch.setattr(main, "GTO_PATH", tmp_path / "gto_hands.txt")

    client = TestClient(main.app)
    response = client.get("/api/v1/stats", params={"spot": "SRP", "street": "flop"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    row = payload["items"][0]
    assert row["population"]["denominator"] == 1
    assert row["population"]["numerator"] == 1
    assert row["gto"]["denominator"] == 1
    assert row["gto"]["numerator"] == 0
