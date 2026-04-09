from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"


class TaskStatus(Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"


class VolatilityLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MarketRegime(Enum):
    TREND = "TREND"
    FLAT = "FLAT"
    VOLATILE = "VOLATILE"


class TransactionType(Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class Asset:
    def __init__(self, asset_id: int, symbol: str):
        self._id = asset_id
        self._symbol = symbol

    @property
    def id(self) -> int:
        return self._id

    @property
    def symbol(self) -> str:
        return self._symbol


class Balance:
    def __init__(self, amount: float = 0.0):
        if amount < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._amount = amount

    @property
    def amount(self) -> float:
        return self._amount

    def can_afford(self, amount: float) -> bool:
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
        return self._amount >= amount

    def deposit(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Сумма пополнения должна быть положительной")
        self._amount += amount

    def withdraw(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Сумма списания должна быть положительной")
        if self._amount < amount:
            raise ValueError("Недостаточно средств")
        self._amount -= amount


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER,
        balance: Optional[Balance] = None,
    ):
        self._id = user_id
        self._username = username
        self._email = email
        self._password_hash = password_hash
        self._role = role
        self._balance = balance or Balance()

    @property
    def id(self) -> int:
        return self._id

    @property
    def username(self) -> str:
        return self._username

    @property
    def email(self) -> str:
        return self._email

    @property
    def role(self) -> UserRole:
        return self._role

    @property
    def balance(self) -> Balance:
        return self._balance


class Admin(User):
    def __init__(
        self,
        user_id: int,
        username: str,
        email: str,
        password_hash: str,
        balance: Optional[Balance] = None,
    ):
        super().__init__(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=UserRole.ADMIN,
            balance=balance,
        )

    def approve_top_up(self, user: User, amount: float) -> None:
        user.balance.deposit(amount)


class PredictionResult:
    def __init__(
        self,
        direction: Direction,
        probability: float,
        volatility_level: VolatilityLevel,
        market_regime: MarketRegime,
        created_at: Optional[datetime] = None,
    ):
        if not 0.0 <= probability <= 1.0:
            raise ValueError("Вероятность должна быть в диапазоне от 0 до 1")

        self._direction = direction
        self._probability = probability
        self._volatility_level = volatility_level
        self._market_regime = market_regime
        self._created_at = created_at or datetime.now()

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def probability(self) -> float:
        return self._probability

    @property
    def volatility_level(self) -> VolatilityLevel:
        return self._volatility_level

    @property
    def market_regime(self) -> MarketRegime:
        return self._market_regime

    @property
    def created_at(self) -> datetime:
        return self._created_at


class MLModel(ABC):
    def __init__(
        self,
        model_id: int,
        name: str,
        description: str,
        price_per_prediction: float,
    ):
        if price_per_prediction <= 0:
            raise ValueError("Стоимость предсказания должна быть положительной")

        self._id = model_id
        self._name = name
        self._description = description
        self._price_per_prediction = price_per_prediction

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def price_per_prediction(self) -> float:
        return self._price_per_prediction

    @abstractmethod
    def predict(self, asset: Asset) -> PredictionResult:
        pass


class CryptoAnalysisModel(MLModel):
    def predict(self, asset: Asset) -> PredictionResult:
        return PredictionResult(
            direction=Direction.UP,
            probability=0.73,
            volatility_level=VolatilityLevel.MEDIUM,
            market_regime=MarketRegime.TREND,
        )


class PredictionTask:
    def __init__(
        self,
        task_id: int,
        user: User,
        asset: Asset,
        model: MLModel,
        created_at: Optional[datetime] = None,
    ):
        self._id = task_id
        self._user = user
        self._asset = asset
        self._model = model
        self._status = TaskStatus.WAITING
        self._created_at = created_at or datetime.now()
        self._result: Optional[PredictionResult] = None

    @property
    def id(self) -> int:
        return self._id

    @property
    def user(self) -> User:
        return self._user

    @property
    def asset(self) -> Asset:
        return self._asset

    @property
    def model(self) -> MLModel:
        return self._model

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def result(self) -> Optional[PredictionResult]:
        return self._result

    @property
    def created_at(self) -> datetime:
        return self._created_at

    def start(self) -> None:
        if self._status != TaskStatus.WAITING:
            raise ValueError("Запустить можно только задачу в статусе WAITING")

        if not self._user.balance.can_afford(self._model.price_per_prediction):
            raise ValueError("У пользователя недостаточно средств")

        self._status = TaskStatus.IN_PROGRESS

    def complete(self, result: PredictionResult) -> None:
        if self._status != TaskStatus.IN_PROGRESS:
            raise ValueError("Завершить можно только задачу в статусе IN_PROGRESS")

        self._result = result
        self._status = TaskStatus.SUCCESS

    def fail(self) -> None:
        if self._status not in (TaskStatus.WAITING, TaskStatus.IN_PROGRESS):
            raise ValueError("Перевести в FAILED можно только незавершённую задачу")

        self._status = TaskStatus.FAILED


class PredictionHistory:
    def __init__(self, history_id: int, user: User):
        self._id = history_id
        self._user = user
        self._tasks: list[PredictionTask] = []

    @property
    def id(self) -> int:
        return self._id

    @property
    def user(self) -> User:
        return self._user

    @property
    def tasks(self) -> list[PredictionTask]:
        return self._tasks.copy()

    def add_task(self, task: PredictionTask) -> None:
        if task.user != self._user:
            raise ValueError("В историю пользователя можно добавить только его задачи")
        self._tasks.append(task)


class Transaction(ABC):
    def __init__(
        self,
        transaction_id: int,
        user: User,
        amount: float,
        transaction_type: TransactionType,
        created_at: Optional[datetime] = None,
        task: Optional[PredictionTask] = None,
    ):
        if amount <= 0:
            raise ValueError("Сумма транзакции должна быть положительной")

        self._id = transaction_id
        self._user = user
        self._amount = amount
        self._transaction_type = transaction_type
        self._created_at = created_at or datetime.now()
        self._task = task

    @property
    def id(self) -> int:
        return self._id

    @property
    def user(self) -> User:
        return self._user

    @property
    def amount(self) -> float:
        return self._amount

    @property
    def transaction_type(self) -> TransactionType:
        return self._transaction_type

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def task(self) -> Optional[PredictionTask]:
        return self._task

    @abstractmethod
    def apply(self) -> None:
        pass


class CreditTransaction(Transaction):
    def __init__(
        self,
        transaction_id: int,
        user: User,
        amount: float,
        created_at: Optional[datetime] = None,
        task: Optional[PredictionTask] = None,
    ):
        super().__init__(
            transaction_id=transaction_id,
            user=user,
            amount=amount,
            transaction_type=TransactionType.CREDIT,
            created_at=created_at,
            task=task,
        )

    def apply(self) -> None:
        self._user.balance.deposit(self._amount)


class DebitTransaction(Transaction):
    def __init__(
        self,
        transaction_id: int,
        user: User,
        amount: float,
        created_at: Optional[datetime] = None,
        task: Optional[PredictionTask] = None,
    ):
        super().__init__(
            transaction_id=transaction_id,
            user=user,
            amount=amount,
            transaction_type=TransactionType.DEBIT,
            created_at=created_at,
            task=task,
        )

    def apply(self) -> None:
        self._user.balance.withdraw(self._amount)


class MLService:
    def __init__(self):
        self._transactions: list[Transaction] = []

    @property
    def transactions(self) -> list[Transaction]:
        return self._transactions.copy()

    def top_up_balance(
        self,
        admin: Admin,
        user: User,
        amount: float,
        transaction_id: int,
    ) -> CreditTransaction:
        transaction = CreditTransaction(
            transaction_id=transaction_id,
            user=user,
            amount=amount,
        )
        transaction.apply()
        self._transactions.append(transaction)
        return transaction

    def execute_task(
        self,
        task: PredictionTask,
        history: PredictionHistory,
        transaction_id: int,
    ) -> PredictionResult:
        task.start()
        result = task.model.predict(task.asset)
        task.complete(result)

        debit_transaction = DebitTransaction(
            transaction_id=transaction_id,
            user=task.user,
            amount=task.model.price_per_prediction,
            task=task,
        )
        debit_transaction.apply()
        self._transactions.append(debit_transaction)

        history.add_task(task)
        return result