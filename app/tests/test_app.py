from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient


def test_register_login_and_profile(
    client: TestClient,
    register_user: Callable[..., dict[str, object]],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    created = register_user("maria")
    login = client.post(
        "/auth/login",
        json={"username": "maria", "password": "secret123"},
    )

    assert login.status_code == 200
    assert created["user"]["username"] == "maria"

    profile = client.get("/users/me", headers=auth_headers(login.json()["token"]))
    assert profile.status_code == 200
    assert profile.json()["email"] == "maria@example.com"


def test_web_cabinet_is_served(client: TestClient) -> None:
    page = client.get("/")
    script = client.get("/static/app.js")

    assert page.status_code == 200
    assert "Личный кабинет ML-сервиса" in page.text
    assert script.status_code == 200
    assert "refreshHistory" in script.text


def test_top_up_balance_and_read_it(
    client: TestClient,
    register_user: Callable[..., dict[str, object]],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    created = register_user()
    headers = auth_headers(created["token"])

    top_up = client.post("/balance/top-up", headers=headers, json={"amount": "30.00"})
    assert top_up.status_code == 200
    assert top_up.json()["balance"] == "30.00"

    balance = client.get("/balance", headers=headers)
    assert balance.status_code == 200
    assert balance.json()["balance"] == "30.00"


def test_prediction_debits_balance_and_writes_history(
    client: TestClient,
    register_user: Callable[..., dict[str, object]],
    auth_headers: Callable[[str], dict[str, str]],
    prediction_payload: Callable[[int], dict[str, object]],
) -> None:
    created = register_user()
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


def test_prediction_fails_with_insufficient_balance(
    client: TestClient,
    register_user: Callable[..., dict[str, object]],
    auth_headers: Callable[[str], dict[str, str]],
    prediction_payload: Callable[[int], dict[str, object]],
) -> None:
    created = register_user()
    headers = auth_headers(created["token"])
    model_id = client.get("/models").json()[0]["id"]

    response = client.post("/predict", headers=headers, json=prediction_payload(model_id))
    assert response.status_code == 402
    assert response.json()["code"] == "insufficient_balance"


def test_validation_error_has_unified_shape(
    client: TestClient,
    register_user: Callable[..., dict[str, object]],
    auth_headers: Callable[[str], dict[str, str]],
    prediction_payload: Callable[[int], dict[str, object]],
) -> None:
    created = register_user()
    headers = auth_headers(created["token"])
    model_id = client.get("/models").json()[0]["id"]
    invalid_payload = prediction_payload(model_id)
    invalid_payload["close_price"] = "200.00"

    response = client.post("/predict", headers=headers, json=invalid_payload)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"]
