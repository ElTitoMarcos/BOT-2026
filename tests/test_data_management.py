from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from moneybot.api.app import app
from moneybot.api.data_management import get_datastore
from moneybot.datastore import DataStore


def _seed_day(base_dir: Path, symbol: str, day: date) -> None:
    day_path = base_dir / "binance" / symbol / day.isoformat()
    day_path.mkdir(parents=True, exist_ok=True)
    (day_path / "aggTrade.jsonl.gz").write_text("{}", encoding="utf-8")


def test_available_dates_returns_sorted_dates(tmp_path: Path) -> None:
    _seed_day(tmp_path, "BTCUSDT", date(2024, 5, 12))
    _seed_day(tmp_path, "BTCUSDT", date(2024, 5, 10))
    _seed_day(tmp_path, "BTCUSDT", date(2024, 5, 11))
    app.dependency_overrides[get_datastore] = lambda: DataStore(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/data/available-dates", params={"symbol": "BTCUSDT"})

    assert response.status_code == 200
    assert response.json()["dates"] == ["2024-05-10", "2024-05-11", "2024-05-12"]
    app.dependency_overrides.clear()


def test_delete_day_removes_directory(tmp_path: Path) -> None:
    target_day = date(2024, 4, 1)
    _seed_day(tmp_path, "ETHUSDT", target_day)
    app.dependency_overrides[get_datastore] = lambda: DataStore(base_dir=tmp_path)
    client = TestClient(app)

    response = client.delete(
        "/data/day",
        params={"symbol": "ETHUSDT", "date": target_day.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert not (tmp_path / "binance" / "ETHUSDT" / target_day.isoformat()).exists()
    app.dependency_overrides.clear()
