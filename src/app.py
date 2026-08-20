from aiogram import Router

from src.core.auth import AdminGate
from src.core.database import Database
from src.core.navigation import NavRegistry


def collect_routers(
    *, gate: AdminGate, nav: NavRegistry, db: Database, trial_days: int = 3
) -> list[Router]:
    from src.admin.handlers import create_router as admin_router
    from src.membership.handlers import create_router as membership_router

    return [
        membership_router(gate=gate, nav=nav, db=db, trial_days=trial_days),
        admin_router(gate=gate, nav=nav, db=db),
    ]
