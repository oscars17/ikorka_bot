from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, Update
from aiogram.fsm.context import FSMContext
import logging

from app.order.handler import OrderHandler
from app.order.states import OrderStates
from app.order.consts import (
    NEW_ORDER_BUTTON_TEXT,
    FAQ_BUTTON_TEXT,
    START_ORDER_BUTTON_TEXT,
)
from db import create_pool

async def build_router() -> Router:
    db_pool = await create_pool()

    router = Router()

    order_handler = OrderHandler(db_pool=db_pool)

    # === Основные хэндлеры ===
    router.message.register(order_handler.handle_start, CommandStart())
    router.message.register(order_handler.handle_faq, F.text == FAQ_BUTTON_TEXT)

    router.message.register(
        order_handler.handle_start_order,
        StateFilter(OrderStates.waiting_for_order_start),
        F.text == START_ORDER_BUTTON_TEXT,
    )

    # Contact at the first step
    router.message.register(
        order_handler.handle_contact,
        F.contact,
        StateFilter(OrderStates.waiting_for_contact),
    )

    # Quantity, Name, Address by state
    router.message.register(
        order_handler.handle_quantity,
        StateFilter(OrderStates.waiting_for_quantity),
        F.text,
    )
    router.message.register(
        order_handler.handle_name,
        StateFilter(OrderStates.waiting_for_name),
        F.text,
    )
    router.message.register(
        order_handler.handle_address,
        StateFilter(OrderStates.waiting_for_address),
        F.text,
    )

    # Final phone step: text only (no contact button here)
    router.message.register(
        order_handler.handle_phone,
        StateFilter(OrderStates.waiting_for_phone),
        F.text,
    )

    # Extra info step (final confirmation + send)
    router.message.register(
        order_handler.handle_extra_info,
        StateFilter(OrderStates.waiting_for_extra_info),
        F.text,
    )

    # Restart flow via button
    router.message.register(
        order_handler.handle_new_order,
        F.text == NEW_ORDER_BUTTON_TEXT,
    )

    # === Fallback-хэндлер для любых неожиданных сообщений ===
    @router.message()
    async def fallback(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "⚠️ Мы обновили бота. Пожалуйста, начните заново — /start"
        )

    # === Глобальный обработчик ошибок ===
    @router.errors()
    async def errors_handler(update: Update, exception: Exception, state: FSMContext):
        logging.error(f"Ошибка при обработке апдейта {update}: {exception}")

        if update.message:
            await update.message.answer(
                "⚠️ Мы обновили бота. Пожалуйста, начните заново — /start"
            )

        # Сбрасываем FSM, чтобы избежать зависаний
        await state.clear()
        return True  # помечаем, что ошибка обработана

    return router
