import os
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from db import create_pool

# твой роутер
from app.order.routes import build_router


@dataclass
class Settings:
    bot_token: str
    target_channel_id: int

    @staticmethod
    def from_environment() -> "Settings":
        try:
            from dotenv import load_dotenv  # optional
            load_dotenv()
        except Exception:
            pass

        token = os.getenv("BOT_TOKEN", "").strip()
        channel_id_raw = os.getenv("CHANNEL_ID", "").strip()

        if not token:
            raise RuntimeError("BOT_TOKEN is not set. Define it in env or .env file.")
        if not channel_id_raw:
            raise RuntimeError("CHANNEL_ID is not set. Define it in env or .env file.")

        try:
            channel_id = int(channel_id_raw)
        except ValueError as exc:
            raise RuntimeError("CHANNEL_ID must be an integer like -1001234567890") from exc

        return Settings(bot_token=token, target_channel_id=channel_id)


def setup_routes(dp: Dispatcher) -> None:
    """Подключаем роуты — как у тебя было."""
    dp.include_router(build_router())


def make_storage_from_env(logger: Optional[logging.Logger] = None):
    """
    Пытаемся создать RedisStorage из REDIS_URL.
    Если не получилось — MemoryStorage.
    Если и это не вышло — вернём None (Dispatcher без storage).
    """
    log = logger or logging.getLogger(__name__)
    storage = None

    redis_url = os.getenv("REDIS_URL", "").strip()
    log.info("Initializing FSM storage... REDIS_URL: %s", redis_url if redis_url else "Not set")

    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(redis_url)
            log.info("Successfully initialized RedisStorage")
            return storage
        except Exception:
            log.exception("Failed to use RedisStorage, falling back to MemoryStorage")

    try:
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
        log.info("Successfully initialized MemoryStorage")
        return storage
    except Exception:
        log.exception("Failed to initialize MemoryStorage")
        return None


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def create_dispatcher(storage=None) -> Dispatcher:
    if storage is None:
        dp = Dispatcher()
        dp.workflow_data.update(db_pool=await create_pool())
        return dp
    return Dispatcher(storage=storage)
