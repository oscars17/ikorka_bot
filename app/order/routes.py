from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from app.order.handler import OrderHandler
from app.order.states import OrderStates
from app.order.consts import NEW_ORDER_BUTTON_TEXT, FAQ_BUTTON_TEXT, START_ORDER_BUTTON_TEXT


def build_router() -> Router:
    router = Router()

    router.message.register(OrderHandler.handle_start, CommandStart())
    router.message.register(OrderHandler.handle_faq, F.text == FAQ_BUTTON_TEXT)
    router.message.register(
        OrderHandler.handle_start_order,
        StateFilter(OrderStates.waiting_for_order_start),
        F.text == START_ORDER_BUTTON_TEXT,
    )

    # Contact at the first step
    router.message.register(
        OrderHandler.handle_contact,
        F.contact,
        StateFilter(OrderStates.waiting_for_contact),
    )

    # Quantity, Name, Address by state
    router.message.register(
        OrderHandler.handle_quantity,
        StateFilter(OrderStates.waiting_for_quantity),
        F.text,
    )
    router.message.register(
        OrderHandler.handle_name,
        StateFilter(OrderStates.waiting_for_name),
        F.text,
    )
    router.message.register(
        OrderHandler.handle_address,
        StateFilter(OrderStates.waiting_for_address),
        F.text,
    )

    # Final phone step: text only (no contact button here)
    router.message.register(
        OrderHandler.handle_phone,
        StateFilter(OrderStates.waiting_for_phone),
        F.text,
    )

    # Extra info step (final confirmation + send)
    router.message.register(
        OrderHandler.handle_extra_info,
        StateFilter(OrderStates.waiting_for_extra_info),
        F.text,
    )

    # Restart flow via button
    router.message.register(
        OrderHandler.handle_new_order,
        F.text == NEW_ORDER_BUTTON_TEXT,
    )

    return router
