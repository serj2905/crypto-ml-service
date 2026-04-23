from __future__ import annotations

import hashlib
import secrets
from typing import Any


class TokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, int] = {}

    def issue(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = user_id
        return token

    def get_user_id(self, token: str) -> int | None:
        return self._tokens.get(token)

    def reset(self) -> None:
        self._tokens.clear()


token_store = TokenStore()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def build_prediction_result(payload: dict[str, Any]) -> dict[str, Any]:
    open_price = float(payload["open_price"])
    close_price = float(payload["close_price"])
    high_price = float(payload["high_price"])
    low_price = float(payload["low_price"])
    volume = float(payload["volume"])

    price_delta = close_price - open_price
    span = max(high_price - low_price, 0.0001)
    ratio = abs(price_delta) / span

    if price_delta >= 0:
        direction = "UP"
        probability = min(0.55 + ratio * 0.35, 0.97)
    else:
        direction = "DOWN"
        probability = min(0.55 + ratio * 0.35, 0.97)

    if span / max(open_price, 0.0001) > 0.05 or volume > 1_000_000:
        volatility_level = "HIGH"
    elif span / max(open_price, 0.0001) > 0.02:
        volatility_level = "MEDIUM"
    else:
        volatility_level = "LOW"

    if ratio > 0.6:
        market_regime = "TREND"
    elif span / max(open_price, 0.0001) > 0.04:
        market_regime = "VOLATILE"
    else:
        market_regime = "FLAT"

    return {
        "direction": direction,
        "probability": round(probability, 4),
        "volatility_level": volatility_level,
        "market_regime": market_regime,
    }
