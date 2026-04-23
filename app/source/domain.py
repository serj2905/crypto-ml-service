from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import JSON
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class TaskStatus(str, Enum):
    WAITING = "waiting"
    SUCCESS = "success"
    FAILED = "failed"


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class VolatilityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MarketRegime(str, Enum):
    TREND = "TREND"
    FLAT = "FLAT"
    VOLATILE = "VOLATILE"


class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        default=UserRole.USER,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    balance_account: Mapped["Balance"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    prediction_tasks: Mapped[list["PredictionTask"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def balance(self) -> Decimal:
        if self.balance_account is None:
            return Decimal("0.00")
        return self.balance_account.amount


class MLModel(Base):
    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    price_per_prediction: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    prediction_tasks: Mapped[list["PredictionTask"]] = relationship(back_populates="model")


class Balance(Base):
    __tablename__ = "balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="balance_account")


class PredictionTask(Base):
    __tablename__ = "prediction_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("ml_models.id"), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), nullable=False)
    direction: Mapped[Optional[Direction]] = mapped_column(SqlEnum(Direction))
    probability: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    volatility_level: Mapped[Optional[VolatilityLevel]] = mapped_column(SqlEnum(VolatilityLevel))
    market_regime: Mapped[Optional[MarketRegime]] = mapped_column(SqlEnum(MarketRegime))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="prediction_tasks")
    model: Mapped["MLModel"] = relationship(back_populates="prediction_tasks")
    transaction: Mapped[Optional["Transaction"]] = relationship(back_populates="task")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prediction_tasks.id"),
        unique=True,
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="transactions")
    task: Mapped[Optional["PredictionTask"]] = relationship(back_populates="transaction")
