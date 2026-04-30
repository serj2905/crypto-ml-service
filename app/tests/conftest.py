from __future__ import annotations

import os
import sys
from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = ROOT_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.pop("RABBITMQ_URL", None)

from source.auth import token_store
from source.db import engine
from source.domain import Base
from source.main import app


@pytest.fixture(autouse=True)
def clean_database() -> None:
    token_store.reset()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def register_user(client: TestClient) -> Callable[..., dict[str, object]]:
    def _register_user(username: str = "alex") -> dict[str, object]:
        response = client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "secret123",
            },
        )
        assert response.status_code == 201
        return response.json()

    return _register_user


@pytest.fixture
def auth_headers() -> Callable[[str], dict[str, str]]:
    return lambda token: {"X-Auth-Token": token}


@pytest.fixture
def prediction_payload() -> Callable[[int], dict[str, object]]:
    def _prediction_payload(model_id: int) -> dict[str, object]:
        return {
            "model_id": model_id,
            "asset_symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_price": "100.00",
            "high_price": "110.00",
            "low_price": "95.00",
            "close_price": "108.00",
            "volume": "250000.00",
        }

    return _prediction_payload
