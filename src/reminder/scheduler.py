import asyncio
import logging

from aiogram import Bot

from src.core.database import Database
from src.membership import service

logger = logging.getLogger(__name__)


async def expiration_loop(db: Database, bot: Bot, grace_days: int = 3, interval: int = 60) -> None:
    while True:
        try:
            # Expire past grace period
            expired = await service.expire_subscriptions(db, grace_days)
            if expired:
                logger.info("Expired %d subscriptions", expired)

            # Remind expiring
            expiring = await service.get_expiring_subscriptions(db, days_ahead=3)
            for sub in expiring:
                try:
                    await bot.send_message(int(str(sub["user_id"])), f"⏰ Подписка истекает {str(sub['end_at'])[:10]}.\nПродлите, чтобы не потерять доступ.")
                except Exception as e:
                    logger.warning("Failed to remind user %s: %s", sub["user_id"], e)
        except Exception as e:
            logger.error("Expiration loop error: %s", e)
        await asyncio.sleep(interval)
