import asyncio
import logging

from bot_shared import Settings, create_bot, create_dispatcher, setup_routes, make_storage_from_env


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("bot_polling")

    settings = Settings.from_environment()
    bot = create_bot(settings)

    storage = make_storage_from_env(logger)
    dp = create_dispatcher(storage)

    setup_routes(dp)

    logger.info("Bot is starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
