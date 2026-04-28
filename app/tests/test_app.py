from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = ROOT_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.pop("RABBITMQ_URL", None)

from source.auth import token_store
from source.domain import Base
from source.main import app
from source.db import engine


def setup_function() -> None:
    token_store.reset()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def register_user(client: TestClient, username: str = "alex") -> dict[str, object]:
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


def auth_headers(token: str) -> dict[str, str]:
    return {"X-Auth-Token": token}


def prediction_payload(model_id: int) -> dict[str, object]:
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


def test_register_login_and_profile() -> None:
    with TestClient(app) as client:
        created = register_user(client, "maria")
        login = client.post(
            "/auth/login",
            json={"username": "maria", "password": "secret123"},
        )

        assert login.status_code == 200
        assert created["user"]["username"] == "maria"

        profile = client.get("/users/me", headers=auth_headers(login.json()["token"]))
        assert profile.status_code == 200
        assert profile.json()["email"] == "maria@example.com"


def test_web_cabinet_is_served() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/app.js")

        assert page.status_code == 200
        assert "Личный кабинет ML-сервиса" in page.text
        assert script.status_code == 200
        assert "refreshHistory" in script.text


def test_top_up_balance_and_read_it() -> None:
    with TestClient(app) as client:
        created = register_user(client)
        headers = auth_headers(created["token"])

        top_up = client.post("/balance/top-up", headers=headers, json={"amount": "30.00"})
        assert top_up.status_code == 200
        assert top_up.json()["balance"] == "30.00"

        balance = client.get("/balance", headers=headers)
        assert balance.status_code == 200
        assert balance.json()["balance"] == "30.00"


def test_prediction_debits_balance_and_writes_history() -> None:
    with TestClient(app) as client:
        created = register_user(client)
        headers = auth_headers(created["token"])

        client.post("/balance/top-up", headers=headers, json={"amount": "50.00"})
        models = client.get("/models")
        model_id = models.json()[0]["id"]

        prediction = client.post("/predict", headers=headers, json=prediction_payload(model_id))
        assert prediction.status_code == 200
        assert prediction.json()["credits_spent"] == "10.00"
        assert prediction.json()["balance"] == "40.00"
        assert prediction.json()["result"]["direction"] in {"UP", "DOWN"}
        assert prediction.json()["worker_id"] == "api-inline"

        status_response = client.get(f"/predict/{prediction.json()['task_id']}", headers=headers)
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "success"

        prediction_history = client.get("/history/predictions", headers=headers)
        assert prediction_history.status_code == 200
        assert len(prediction_history.json()) == 1
        assert prediction_history.json()[0]["credits_spent"] == "10.00"

        transaction_history = client.get("/history/transactions", headers=headers)
        assert transaction_history.status_code == 200
        assert len(transaction_history.json()) == 2
        assert transaction_history.json()[0]["transaction_type"] == "debit"


def test_prediction_fails_with_insufficient_balance() -> None:
    with TestClient(app) as client:
        created = register_user(client)
        headers = auth_headers(created["token"])
        model_id = client.get("/models").json()[0]["id"]

        response = client.post("/predict", headers=headers, json=prediction_payload(model_id))
        assert response.status_code == 402
        assert response.json()["code"] == "insufficient_balance"


def test_validation_error_has_unified_shape() -> None:
    with TestClient(app) as client:
        created = register_user(client)
        headers = auth_headers(created["token"])
        model_id = client.get("/models").json()[0]["id"]
        invalid_payload = prediction_payload(model_id)
        invalid_payload["close_price"] = "200.00"

        response = client.post("/predict", headers=headers, json=invalid_payload)
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
        assert response.json()["details"]
