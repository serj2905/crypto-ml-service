from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import Balance
from .domain import Direction
from .domain import MLModel
from .domain import MarketRegime
from .domain import PredictionTask
from .domain import TaskStatus
from .domain import Transaction
from .domain import TransactionType
from .domain import User
from .domain import UserRole
from .domain import VolatilityLevel


def get_or_create_balance(session: Session, user: User) -> Balance:
    if user.balance_account is None:
        user.balance_account = Balance(amount=Decimal("0.00"))
        session.add(user.balance_account)
        session.flush()
    return user.balance_account


def get_user_balance_amount(user: User) -> Decimal:
    if user.balance_account is None:
        return Decimal("0.00")
    return user.balance_account.amount.quantize(Decimal("0.01"))


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
        balance_account=Balance(amount=balance),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


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

    balance = get_or_create_balance(session, user)
    balance.amount += amount
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
    balance = get_or_create_balance(session, user)
    if balance.amount < amount:
        raise ValueError("Недостаточно средств")

    balance.amount -= amount
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
    input_payload: dict[str, object],
) -> PredictionTask:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")

    model = session.get(MLModel, model_id)
    if model is None:
        raise ValueError("ML-модель не найдена")

    price = model.price_per_prediction.quantize(Decimal("0.01"))
    balance = get_or_create_balance(session, user)
    if balance.amount < price:
        raise ValueError("Недостаточно средств")

    task = PredictionTask(
        user=user,
        model=model,
        asset_symbol=asset_symbol,
        input_payload=input_payload,
        status=TaskStatus.WAITING,
        amount=price,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def complete_prediction_task(
    session: Session,
    task_id: int,
    worker_id: str,
    direction: Direction,
    probability: Decimal,
    volatility_level: VolatilityLevel,
    market_regime: MarketRegime,
) -> PredictionTask:
    task = session.get(PredictionTask, task_id)
    if task is None:
        raise ValueError("ML-задача не найдена")
    if task.status != TaskStatus.WAITING:
        return task

    user = session.get(User, task.user_id)
    if user is None:
        raise ValueError("Пользователь не найден")

    balance = get_or_create_balance(session, user)
    price = task.amount.quantize(Decimal("0.01"))
    if balance.amount < price:
        task.status = TaskStatus.FAILED
        task.worker_id = worker_id
        task.error_message = "Недостаточно средств"
        session.commit()
        session.refresh(task)
        return task

    task.status = TaskStatus.SUCCESS
    task.worker_id = worker_id
    task.direction = direction
    task.probability = probability
    task.volatility_level = volatility_level
    task.market_regime = market_regime
    task.error_message = None
    balance.amount -= price
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


def fail_prediction_task(session: Session, task_id: int, worker_id: str, message: str) -> PredictionTask:
    task = session.get(PredictionTask, task_id)
    if task is None:
        raise ValueError("ML-задача не найдена")
    if task.status == TaskStatus.WAITING:
        task.status = TaskStatus.FAILED
        task.worker_id = worker_id
        task.error_message = message[:255]
        session.commit()
        session.refresh(task)
    return task


def get_prediction_task(session: Session, user_id: int, task_id: int) -> PredictionTask | None:
    return session.scalar(
        select(PredictionTask).where(
            PredictionTask.id == task_id,
            PredictionTask.user_id == user_id,
        )
    )


def get_prediction_history(session: Session, user_id: int) -> list[PredictionTask]:
    if session.get(User, user_id) is None:
        raise ValueError("Пользователь не найден")

    query = (
        select(PredictionTask)
        .where(PredictionTask.user_id == user_id)
        .order_by(PredictionTask.created_at.desc(), PredictionTask.id.desc())
    )
    return list(session.scalars(query))


def get_transaction_history(session: Session, user_id: int) -> list[Transaction]:
    if session.get(User, user_id) is None:
        raise ValueError("Пользователь не найден")

    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
    )
    return list(session.scalars(query))
