from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import Direction
from domain import MLModel
from domain import MarketRegime
from domain import PredictionTask
from domain import TaskStatus
from domain import Transaction
from domain import TransactionType
from domain import User
from domain import UserRole
from domain import VolatilityLevel


def create_user(
    session: Session,
    username: str,
    email: str,
    password_hash: str,
    role: UserRole = UserRole.USER,
    initial_balance: float | str | Decimal = Decimal("0.00"),
) -> User:
    balance = Decimal(str(initial_balance)).quantize(Decimal("0.01"))
    if balance < 0:
        raise ValueError("Баланс не может быть отрицательным")

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        balance=balance,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def list_models(session: Session) -> list[MLModel]:
    query = select(MLModel).order_by(MLModel.id)
    return list(session.scalars(query))


def top_up_balance(session: Session, user_id: int, amount: float | str | Decimal) -> Transaction:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")

    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")

    user.balance += amount
    transaction = Transaction(
        user=user,
        transaction_type=TransactionType.CREDIT,
        amount=amount,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def debit_balance(
    session: Session,
    user_id: int,
    amount: float | str | Decimal,
    task: PredictionTask | None = None,
) -> Transaction:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")

    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")
    if user.balance < amount:
        raise ValueError("Недостаточно средств")

    user.balance -= amount
    transaction = Transaction(
        user=user,
        task=task,
        transaction_type=TransactionType.DEBIT,
        amount=amount,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def create_prediction_request(
    session: Session,
    user_id: int,
    model_id: int,
    asset_symbol: str,
) -> PredictionTask:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")

    model = session.get(MLModel, model_id)
    if model is None:
        raise ValueError("ML-модель не найдена")

    price = model.price_per_prediction.quantize(Decimal("0.01"))
    if user.balance < price:
        raise ValueError("Недостаточно средств")

    task = PredictionTask(
        user=user,
        model=model,
        asset_symbol=asset_symbol,
        status=TaskStatus.SUCCESS,
        direction=Direction.UP,
        probability=Decimal("0.7300"),
        volatility_level=VolatilityLevel.MEDIUM,
        market_regime=MarketRegime.TREND,
        amount=price,
    )
    session.add(task)
    session.flush()

    user.balance -= price
    session.add(
        Transaction(
            user=user,
            task=task,
            transaction_type=TransactionType.DEBIT,
            amount=price,
        )
    )

    session.commit()
    session.refresh(task)
    return task


def get_prediction_history(session: Session, user_id: int) -> list[PredictionTask]:
    if session.get(User, user_id) is None:
        raise ValueError("Пользователь не найден")

    query = (
        select(PredictionTask)
        .where(PredictionTask.user_id == user_id)
        .order_by(PredictionTask.created_at.desc(), PredictionTask.id.desc())
    )
    return list(session.scalars(query))
