from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT_DIR / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT_DIR / 'test.db').as_posix()}"

from db import SessionLocal
from db import engine
from domain import Base
from domain import TransactionType
from domain import UserRole
from init_db import init_db
from services import create_prediction_request
from services import create_user
from services import get_prediction_history
from services import get_user_by_username
from services import list_models
from services import top_up_balance


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_init_db_is_idempotent() -> None:
    with SessionLocal() as session:
        init_db(session)
        init_db(session)

        assert get_user_by_username(session, "demo_user") is not None
        assert get_user_by_username(session, "demo_admin").role == UserRole.ADMIN
        assert len(list_models(session)) == 2


def test_create_user_and_top_up_balance() -> None:
    with SessionLocal() as session:
        user = create_user(
            session=session,
            username="alex",
            email="alex@example.com",
            password_hash="hash",
        )
        transaction = top_up_balance(session, user.id, "25.50")

        session.refresh(user)
        assert user.balance == Decimal("25.50")
        assert transaction.transaction_type == TransactionType.CREDIT


def test_prediction_request_writes_history_and_debits_balance() -> None:
    with SessionLocal() as session:
        init_db(session)
        user = get_user_by_username(session, "demo_user")
        model = list_models(session)[0]

        task = create_prediction_request(session, user.id, model.id, "BTCUSDT")
        history = get_prediction_history(session, user.id)

        session.refresh(user)
        assert task.transaction is not None
        assert history[0].id == task.id
        assert user.balance == Decimal("90.00")
