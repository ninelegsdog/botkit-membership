from aiogram import Router

from src.core.auth import AdminGate
from src.core.database import Database
from src.core.navigation import NavRegistry


def collect_routers(
    *, gate: AdminGate, nav: NavRegistry, db: Database, trial_days: int = 3,
    payments: object | None = None,
) -> list[Router]:
    from src.admin.handlers import create_router as admin_router
    from src.core.payments import create_payment_provider
    from src.membership.handlers import create_router as membership_router

    if payments is None:
        # Демо по умолчанию: mock-провайдер, подписка активируется сразу.
        # Переключение на реальный сервис — env PAYMENT_PROVIDER=yookassa + ключи.
        import os

        name = os.getenv("PAYMENT_PROVIDER", "mock").strip().lower() or "mock"
        if name == "mock":
            payments = create_payment_provider("mock")
        elif name == "yookassa":
            payments = create_payment_provider(
                "yookassa",
                shop_id=os.getenv("YOOKASSA_SHOP_ID", ""),
                secret_key=os.getenv("YOOKASSA_SECRET_KEY", ""),
            )
        else:
            payments = create_payment_provider("mock")

    return [
        membership_router(gate=gate, nav=nav, db=db, trial_days=trial_days, payments=payments),
        admin_router(gate=gate, nav=nav, db=db),
    ]
