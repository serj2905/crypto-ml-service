from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .db import engine
from .domain import Base
from .domain import MLModel
from .domain import UserRole
from .services import create_user
from .services import get_user_by_username


def init_db(session: Session) -> None:
    Base.metadata.create_all(bind=engine)
    _create_demo_users(session)
    _create_demo_models(session)


def _create_demo_users(session: Session) -> None:
    if get_user_by_username(session, "demo_user") is None:
        create_user(
            session=session,
            username="demo_user",
            email="demo_user@example.com",
            password_hash=hash_password("demo_user_password"),
            initial_balance=Decimal("100.00"),
        )

    if get_user_by_username(session, "demo_admin") is None:
        create_user(
            session=session,
            username="demo_admin",
            email="demo_admin@example.com",
            password_hash=hash_password("demo_admin_password"),
            role=UserRole.ADMIN,
            initial_balance=Decimal("1000.00"),
        )


def _create_demo_models(session: Session) -> None:
    models = [
        ("trend-analyzer", "Базовая модель анализа тренда", Decimal("10.00")),
        ("volatility-checker", "Базовая модель оценки волатильности", Decimal("15.00")),
    ]

    for name, description, price in models:
        exists = session.scalar(select(MLModel).where(MLModel.name == name))
        if exists is None:
            session.add(
                MLModel(
                    name=name,
                    description=description,
                    price_per_prediction=price,
                )
            )

    session.commit()
