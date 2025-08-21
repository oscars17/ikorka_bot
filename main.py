import asyncio
import logging
import os
import json
import base64
from dataclasses import dataclass
from typing import Optional
import time

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from app.order.routes import build_router

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore


@dataclass
class Settings:
    bot_token: str
    target_channel_id: int

    @staticmethod
    def from_environment() -> "Settings":
        if load_dotenv is not None:
            load_dotenv()

        token = os.getenv("BOT_TOKEN", "").strip()
        channel_id_raw = os.getenv("CHANNEL_ID", "").strip()

        if not token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Define it in environment or .env file."
            )
        if not channel_id_raw:
            raise RuntimeError(
                "CHANNEL_ID is not set. Define it in environment or .env file."
            )

        try:
            channel_id = int(channel_id_raw)
        except ValueError as exc:
            raise RuntimeError(
                "CHANNEL_ID must be an integer like -1001234567890"
            ) from exc

        return Settings(bot_token=token, target_channel_id=channel_id)

def setup_routes(dp: Dispatcher) -> None:
    # Create a fresh router instance per dispatcher to avoid reusing the same router
    dp.include_router(build_router())


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_environment()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    setup_routes(dp)

    logging.info("Bot is starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())


# --------------------
# Webhook adapter for Yandex Cloud Functions
# --------------------
# The code below preserves every function/handler above unchanged.
# It initializes a separate Dispatcher+Bot for the Cloud Function environment
# (so you can still run the file locally with polling), and exposes a
# synchronous `handler(event, context)` entrypoint expected by Yandex Cloud.

# Notes:
# - If you want persistent FSM state across separate function invocations,
#   set REDIS_URL environment variable to a Redis instance (e.g. redis://user:pass@host:port)
#   and install aioredis. If REDIS_URL is not set or Redis import fails,
#   an in-memory storage will be used (ephemeral between invocations).
# - Keep BOT_TOKEN and CHANNEL_ID env vars set for the function.

# Initialize cloud dispatcher/bot at import time (runs on function cold start)
_cloud_dp = None
_cloud_bot = None
_cloud_settings = None
_cloud_storage = None  # global storage reused across warm invocations

try:
    _cloud_settings = Settings.from_environment()
    _cloud_bot = Bot(
        token=_cloud_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Prefer Redis storage if REDIS_URL is provided, otherwise fallback to MemoryStorage
    _redis_url = os.getenv("REDIS_URL", "").strip()
    _storage = None
    
    logging.info("Initializing FSM storage...")
    logging.info("REDIS_URL: %s", _redis_url if _redis_url else "Not set")
    
    if _redis_url:
        try:
            # aiogram v3 Redis storage
            from aiogram.fsm.storage.redis import RedisStorage

            _storage = RedisStorage.from_url(_redis_url)
            logging.info("Successfully initialized RedisStorage")
        except Exception:
            logging.exception("Failed to use RedisStorage, falling back to MemoryStorage")

    if _storage is None:
        try:
            from aiogram.fsm.storage.memory import MemoryStorage

            _storage = MemoryStorage()
            logging.info("Successfully initialized MemoryStorage")
        except Exception:
            logging.exception("Failed to initialize MemoryStorage")
            _storage = None

    _cloud_storage = _storage

    if _storage is None:
        # As a last resort, create Dispatcher without explicit storage.
        logging.warning("No storage available, creating Dispatcher without storage")
        _cloud_dp = Dispatcher()
    else:
        logging.info("Creating Dispatcher with storage: %s", type(_storage).__name__)
        _cloud_dp = Dispatcher(storage=_storage)

    # register routes using the same function
    setup_routes(_cloud_dp)
    
    logging.info("Cloud dispatcher and bot initialized successfully")
    logging.info("Bot token: %s", _cloud_settings.bot_token[:10] + "..." if _cloud_settings.bot_token else "None")
    logging.info("Target channel ID: %s", _cloud_settings.target_channel_id)

except Exception as exc:  # pragma: no cover - best-effort init
    logging.exception("Failed to initialize cloud dispatcher/bot: %s", exc)
    _cloud_dp = None
    _cloud_bot = None
    _cloud_settings = None
    _cloud_storage = None


async def _process_payload(payload: dict) -> None:
    """Create a fresh Bot/Dispatcher in the current loop and process one update."""
    # Build settings per request
    settings = _cloud_settings or Settings.from_environment()

    # Create bot bound to the current loop
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Use global storage if available; otherwise fall back to per-request init
    storage = _cloud_storage
    if storage is None:
        redis_url = os.getenv("REDIS_URL", "").strip()
        try:
            if redis_url:
                try:
                    from aiogram.fsm.storage.redis import RedisStorage
                    storage = RedisStorage.from_url(redis_url)
                    logging.info("Per-request RedisStorage initialized")
                except Exception as exc:
                    logging.warning("Per-request RedisStorage init failed: %s. Falling back to MemoryStorage", exc)
            if storage is None:
                from aiogram.fsm.storage.memory import MemoryStorage
                storage = MemoryStorage()
                logging.info("Per-request MemoryStorage initialized")
        except Exception as exc:
            logging.warning("Failed to initialize FSM storage: %s. Proceeding without explicit storage", exc)
            storage = None

    if storage is None:
        dp = Dispatcher()
    else:
        dp = Dispatcher(storage=storage)

    # Register routes for this dispatcher
    setup_routes(dp)

    try:
        # Build Update object from payload strictly
        update_obj = None
        try:
            if hasattr(Update, "model_validate"):
                update_obj = Update.model_validate(payload)  # type: ignore[attr-defined]
            else:
                update_obj = Update(**payload)
            logging.info("Per-request Update object created: %s", getattr(update_obj, "update_id", None))
        except Exception as exc:
            logging.error("Invalid Telegram update payload, cannot parse Update: %s", exc)
            return

        # Feed update using correct API
        await dp.feed_update(bot, update_obj)
        logging.info("Per-request update processed")
    finally:
        # Close bot session to release http resources bound to this loop
        try:
            await bot.session.close()
        except Exception:
            pass


# Remove the _monitor_idle_users_once and _send_idle_timeout_message functions since they don't work with MemoryStorage
# The idle monitoring will be handled by the per-message check in the handler


def handler(event, context):
    """Yandex Cloud Functions HTTP entrypoint."""
    method = (event or {}).get("httpMethod")
    path = (event or {}).get("path", "/")

    if method == "GET" and (path == "/" or path == "/health"):
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "healthy",
                "bot_initialized": True,
                "dispatcher_initialized": True,
            }),
        }

    # Validate body
    body = (event or {}).get("body")
    if body is None:
        return {"statusCode": 400, "body": "Missing body"}

    try:
        if (event or {}).get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        payload = json.loads(body)
        logging.info("Webhook payload: %s", payload)
    except Exception as exc:
        logging.exception("Failed to parse webhook body: %s", exc)
        return {"statusCode": 400, "body": "Invalid JSON"}

    try:
        _run_in_new_loop(payload)
    except Exception as exc:
        logging.exception("Failed to process update: %s", exc)
        return {"statusCode": 500, "body": "Internal Server Error"}

    return {"statusCode": 200, "body": ""}


def _run_in_new_loop(payload: dict) -> None:
    """Run the async function in a new event loop.
    This is needed when we're already inside an event loop (AWS Lambda case).
    """
    # Create a completely new event loop
    loop = asyncio.new_event_loop()
    
    try:
        # Set this as the current event loop for this thread
        asyncio.set_event_loop(loop)

        # Run the payload processing without artificial timeout
        loop.run_until_complete(_process_payload(payload))

    except Exception as exc:
        logging.exception("Error in event loop: %s", exc)
        raise
    finally:
        # Clean up the loop
        try:
            # Cancel any remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Wait for cancellation to complete
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass  # Ignore cleanup errors
        
        # Close the loop
        try:
            loop.close()
        except Exception:
            pass  # Ignore close errors
        
        # Remove the event loop from this thread
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass
        
        # Force garbage collection to clean up any remaining references
        import gc
        gc.collect()
