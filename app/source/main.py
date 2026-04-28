from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

from fastapi import Depends
from fastapi import FastAPI
from fastapi import Header
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import build_prediction_result
from .auth import hash_password
from .auth import token_store
from .auth import verify_password
from .db import engine
from .db import session_dependency
from .domain import Base
from .domain import Direction
from .domain import MarketRegime
from .domain import VolatilityLevel
from .init_db import init_db
from .schemas import AuthResponse
from .schemas import BalanceResponse
from .schemas import BalanceTopUpRequest
from .schemas import ErrorResponse
from .schemas import LoginRequest
from .schemas import ModelResponse
from .schemas import PredictionHistoryItem
from .schemas import PredictionRequest
from .schemas import PredictionResponse
from .schemas import PredictionResult
from .schemas import RegisterRequest
from .schemas import TransactionResponse
from .schemas import UserResponse
from .rabbitmq import is_queue_enabled
from .rabbitmq import publish_prediction_task
from .services import complete_prediction_task
from .services import create_prediction_request
from .services import create_user
from .services import get_prediction_history
from .services import get_prediction_task
from .services import get_transaction_history
from .services import get_user
from .services import get_user_balance_amount
from .services import get_user_by_email
from .services import get_user_by_username
from .services import list_models
from .services import top_up_balance


STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def get_db_session() -> Generator[Session, None, None]:
    yield from session_dependency()


def require_current_user(
    x_auth_token: str | None = Header(default=None),
    session: Session = Depends(get_db_session),
):
    if not x_auth_token:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "missing_token", "X-Auth-Token header is required")

    user_id = token_store.get_user_id(x_auth_token)
    if user_id is None:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Authentication token is invalid")

    user = get_user(session, user_id)
    if user is None:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Authentication token is invalid")
    return user


def build_prediction_response(task, balance: Decimal) -> PredictionResponse:
    result = None
    if task.direction and task.probability and task.volatility_level and task.market_regime:
        result = PredictionResult(
            direction=task.direction.value,
            probability=task.probability,
            volatility_level=task.volatility_level.value,
            market_regime=task.market_regime.value,
        )

    return PredictionResponse(
        task_id=task.id,
        model_id=task.model_id,
        asset_symbol=task.asset_symbol,
        credits_spent=task.amount,
        balance=balance,
        status=task.status.value,
        worker_id=task.worker_id,
        error_message=task.error_message,
        result=result,
        created_at=task.created_at,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        init_db(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crypto ML Service API",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(AppError)
    async def app_error_handler(_, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.message,
                code=exc.code,
                details=exc.details,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="Validation error",
                code="validation_error",
                details=details,
            ).model_dump(mode="json"),
        )

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=FileResponse)
    def web_app() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
    def register(
        payload: RegisterRequest,
        session: Session = Depends(get_db_session),
    ) -> AuthResponse:
        if get_user_by_username(session, payload.username) is not None:
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username is already in use")
        if get_user_by_email(session, payload.email) is not None:
            raise AppError(status.HTTP_409_CONFLICT, "email_taken", "Email is already in use")

        user = create_user(
            session=session,
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        token = token_store.issue(user.id)
        return AuthResponse(token=token, user=UserResponse.model_validate(user))

    @app.post("/auth/login", response_model=AuthResponse)
    def login(
        payload: LoginRequest,
        session: Session = Depends(get_db_session),
    ) -> AuthResponse:
        user = get_user_by_username(session, payload.username)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AppError(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_credentials",
                "Invalid username or password",
            )

        token = token_store.issue(user.id)
        return AuthResponse(token=token, user=UserResponse.model_validate(user))

    @app.get("/users/me", response_model=UserResponse)
    def get_current_user_profile(current_user=Depends(require_current_user)) -> UserResponse:
        return UserResponse.model_validate(current_user)

    @app.get("/models", response_model=list[ModelResponse])
    def get_models(session: Session = Depends(get_db_session)) -> list[ModelResponse]:
        return [ModelResponse.model_validate(model) for model in list_models(session)]

    @app.get("/balance", response_model=BalanceResponse)
    def get_balance(current_user=Depends(require_current_user)) -> BalanceResponse:
        return BalanceResponse(user_id=current_user.id, balance=get_user_balance_amount(current_user))

    @app.post("/balance/top-up", response_model=BalanceResponse)
    def top_up(
        payload: BalanceTopUpRequest,
        current_user=Depends(require_current_user),
        session: Session = Depends(get_db_session),
    ) -> BalanceResponse:
        top_up_balance(session, current_user.id, payload.amount)
        session.refresh(current_user)
        return BalanceResponse(user_id=current_user.id, balance=get_user_balance_amount(current_user))

    @app.post("/predict", response_model=PredictionResponse)
    def predict(
        payload: PredictionRequest,
        current_user=Depends(require_current_user),
        session: Session = Depends(get_db_session),
    ) -> PredictionResponse:
        try:
            task = create_prediction_request(
                session=session,
                user_id=current_user.id,
                model_id=payload.model_id,
                asset_symbol=payload.asset_symbol,
                input_payload=payload.model_dump(mode="json"),
            )
        except ValueError as exc:
            message = str(exc)
            if message == "Недостаточно средств":
                raise AppError(status.HTTP_402_PAYMENT_REQUIRED, "insufficient_balance", message) from exc
            raise AppError(status.HTTP_400_BAD_REQUEST, "prediction_error", message) from exc

        if is_queue_enabled():
            try:
                publish_prediction_task(task.id)
            except Exception as exc:
                raise AppError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "queue_unavailable",
                    "RabbitMQ is unavailable",
                ) from exc
        else:
            result = build_prediction_result(payload.model_dump(mode="json"))
            task = complete_prediction_task(
                session=session,
                task_id=task.id,
                worker_id="api-inline",
                direction=Direction(result["direction"]),
                probability=Decimal(str(result["probability"])),
                volatility_level=VolatilityLevel(result["volatility_level"]),
                market_regime=MarketRegime(result["market_regime"]),
            )

        session.refresh(current_user)
        return build_prediction_response(task, get_user_balance_amount(current_user))

    @app.get("/predict/{task_id}", response_model=PredictionResponse)
    def prediction_status(
        task_id: int,
        current_user=Depends(require_current_user),
        session: Session = Depends(get_db_session),
    ) -> PredictionResponse:
        task = get_prediction_task(session, current_user.id, task_id)
        if task is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "task_not_found", "Prediction task was not found")
        return build_prediction_response(task, get_user_balance_amount(current_user))

    @app.get("/history/predictions", response_model=list[PredictionHistoryItem])
    def prediction_history(
        current_user=Depends(require_current_user),
        session: Session = Depends(get_db_session),
    ) -> list[PredictionHistoryItem]:
        tasks = get_prediction_history(session, current_user.id)
        return [
            PredictionHistoryItem(
                task_id=task.id,
                model_id=task.model_id,
                model_name=task.model.name,
                asset_symbol=task.asset_symbol,
                timeframe=str(task.input_payload.get("timeframe", "")),
                status=task.status.value,
                credits_spent=task.amount,
                worker_id=task.worker_id,
                error_message=task.error_message,
                created_at=task.created_at,
                result=PredictionResult(
                    direction=task.direction.value,
                    probability=task.probability,
                    volatility_level=task.volatility_level.value,
                    market_regime=task.market_regime.value,
                )
                if task.direction and task.probability and task.volatility_level and task.market_regime
                else None,
            )
            for task in tasks
        ]

    @app.get("/history/transactions", response_model=list[TransactionResponse])
    def transaction_history(
        current_user=Depends(require_current_user),
        session: Session = Depends(get_db_session),
    ) -> list[TransactionResponse]:
        transactions = get_transaction_history(session, current_user.id)
        return [TransactionResponse.model_validate(item) for item in transactions]

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("source.main:app", host="0.0.0.0", port=8000, reload=False)
