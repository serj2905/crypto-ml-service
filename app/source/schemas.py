from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator


class ErrorResponse(BaseModel):
    error: str
    code: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: str
    balance: Decimal
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class BalanceResponse(BaseModel):
    user_id: int
    balance: Decimal


class BalanceTopUpRequest(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_type: str
    amount: Decimal
    created_at: datetime
    task_id: int | None


class ModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    price_per_prediction: Decimal
    created_at: datetime


class PredictionRequest(BaseModel):
    model_id: int = Field(gt=0)
    asset_symbol: str = Field(min_length=2, max_length=20)
    timeframe: str = Field(min_length=2, max_length=20)
    open_price: Decimal = Field(gt=0, decimal_places=8)
    high_price: Decimal = Field(gt=0, decimal_places=8)
    low_price: Decimal = Field(gt=0, decimal_places=8)
    close_price: Decimal = Field(gt=0, decimal_places=8)
    volume: Decimal = Field(gt=0, decimal_places=8)

    @field_validator("asset_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_candle_range(self) -> "PredictionRequest":
        if self.high_price < self.low_price:
            raise ValueError("high_price must be greater than or equal to low_price")
        if not self.low_price <= self.open_price <= self.high_price:
            raise ValueError("open_price must be within [low_price, high_price]")
        if not self.low_price <= self.close_price <= self.high_price:
            raise ValueError("close_price must be within [low_price, high_price]")
        return self


class PredictionResult(BaseModel):
    direction: str
    probability: Decimal
    volatility_level: str
    market_regime: str


class PredictionResponse(BaseModel):
    task_id: int
    model_id: int
    asset_symbol: str
    credits_spent: Decimal
    balance: Decimal
    status: str
    worker_id: str | None = None
    error_message: str | None = None
    result: PredictionResult | None = None
    created_at: datetime


class PredictionHistoryItem(BaseModel):
    task_id: int
    model_id: int
    model_name: str
    asset_symbol: str
    timeframe: str
    status: str
    credits_spent: Decimal
    worker_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    result: PredictionResult | None
