from typing import Optional
import logging
import os
import time

from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)
from aiogram.fsm.context import FSMContext
from aiogram import Bot

from app.order.consts import SHARE_CONTACT_BUTTON_TEXT, NEW_ORDER_BUTTON_TEXT, FAQ_BUTTON_TEXT, START_ORDER_BUTTON_TEXT
from app.order.states import OrderStates


def _build_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=START_ORDER_BUTTON_TEXT)],
            [KeyboardButton(text=FAQ_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=False,
    )


def _build_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SHARE_CONTACT_BUTTON_TEXT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=False,
    )


_IDLE_THRESHOLD_SECONDS: int = 9 * 60  # 9 minutes


async def _send_idle_timeout_message(bot: Bot, user_id: int) -> None:
    """Send timeout message to user and clear their state."""
    try:
        await bot.send_message(
            user_id,
            "Похоже, вы были в простое более 9 минут. Чтобы начать заново, отправьте /start",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as exc:
        logging.exception("Failed to send idle timeout message to user %s: %s", user_id, exc)


async def _check_and_handle_idle(message: Message, state: FSMContext) -> bool:
    """Returns True if user was idle longer than threshold and we handled it.

    Clears state and asks the user to restart with /start.
    """
    try:
        data = await state.get_data()
        last_activity_at = data.get("last_activity_at")

        # If there is no timestamp yet, set it and allow processing to continue
        if last_activity_at is None:
            await _touch_activity(state)
            return False

        # Normalize possible string value from storage
        if not isinstance(last_activity_at, (int, float)):
            try:
                last_activity_at = float(str(last_activity_at))
            except Exception:
                await _touch_activity(state)
                return False

        idle_seconds = max(0, int(time.time() - float(last_activity_at)))
        if idle_seconds >= _IDLE_THRESHOLD_SECONDS:
            await state.clear()
            await message.answer(
                "Похоже, вы были в простое более 9 минут. Чтобы начать заново, отправьте /start",
                reply_markup=ReplyKeyboardRemove(),
            )
            return True
    except Exception:
        # Non-fatal: proceed normally if anything goes wrong
        logging.exception("Idle check failed")
    return False


async def _touch_activity(state: FSMContext) -> None:
    await state.update_data(last_activity_at=time.time())


def _normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return "—"
    return phone.strip() or "—"


def _build_order_message_for_user(
    user: User,
    quantity_text: str,
    name_text: str,
    address_text: str,
    phone_text: Optional[str],
    extra_info_text: Optional[str],
) -> str:
    full_name = user.full_name
    username: str = f"@{user.username}" if user.username else "—"
    user_id: int = user.id
    profile_link = f"tg://user?id={user_id}"

    quantity_text = (quantity_text or "").strip() or "—"
    name_text = (name_text or "").strip() or "—"
    address_text = (address_text or "").strip() or "—"
    phone_text = _normalize_phone(phone_text)
    extra_info_text = (extra_info_text or "").strip() or "—"

    formatted = (
        "Новый заказ\n\n"
        f"Имя в Telegram: {full_name}\n"
        f"Username: {username}\n"
        f"User ID: {user_id}\n"
        f"Профиль: {profile_link}\n\n"
        f"Телефон: {phone_text}\n"
        f"ФИО получателя: {name_text}\n"
        f"Адрес: {address_text}\n"
        f"Количество: {quantity_text}\n"
        f"Доп. информация: {extra_info_text}"
    )
    return formatted


def _resolve_target_channel_id() -> int:
    raw = os.getenv("CHANNEL_ID", "").strip()
    if not raw:
        raise RuntimeError("CHANNEL_ID is not set in environment")
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError("CHANNEL_ID must be an integer like -1001234567890") from exc


class OrderHandler:
    @staticmethod
    async def handle_start(message: Message, state: FSMContext) -> None:
        logging.info("handle_start called for user %s", message.from_user.id if message.from_user else "unknown")
        await state.clear()
        await state.set_state(OrderStates.waiting_for_order_start)
        await _touch_activity(state)
        await message.answer(
            "Привет! Нажмите «Сделать заказ», чтобы начать оформление.",
            reply_markup=_build_main_keyboard(),
        )

    @staticmethod
    async def handle_start_order(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        await _touch_activity(state)
        await state.set_state(OrderStates.waiting_for_contact)
        await message.answer(
            'Нажмите на кнопку "Поделиться контактом", чтобы мы могли с вами связаться.,
            reply_markup=_build_contact_keyboard(),
        )

    @staticmethod
    async def handle_faq(message: Message) -> None:
        text = (
            "<b>Где и когда была произведена икра?</b>\n"
            "Наша дальневосточная красная икра добывается из тихоокеанских лососевой рыбы горбуши в регионах Дальнего Востока России, преимущественно на Сахалине \n"
            "\n"
            "Сейчас в наличии свежайший вылов горбуши от июля 2025г. \n"
            "\n"
            "<b>У вас качественная икра?</b> \n"
            "Да, вся икра производится по ГОСТу 1629-2015, имеет Декларацию соответствия и Удостоверение качества. \n"
            "Сорт: Первый \n"
            "\n"
            "<b>Какой срок годности у икры?</b>\n"
            "Срок годности нашей икры — до 8 месяцев при соблюдении температурного режима от -2 до -6°C. После вскрытия упаковки продукт нужно употребить в течение 72 часов. \n"
            "\n"
            "<b>Как правильно хранить икру дома?</b> \n"
            "Храните икру в холодильнике при температуре от 0 до +5°C в оригинальной пластиковой таре с плотно закрытой крышкой. \n"
            "\n"
            "<b>Есть ли скидки или акции на икру?</b>\n"
            "Доп бонус на первый заказ: \n"
            "-500₽ на каждые 500г при заказе через бот @ikorka_moscow_bot и подписке на канал @ikorka_moscow"
        )
        await message.answer(text, parse_mode="HTML")

    @staticmethod
    async def handle_contact(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        await _touch_activity(state)
        contact = message.contact
        if not contact or not contact.user_id:
            await message.answer(
                f"Не удалось получить контакт. Попробуйте ещё раз нажать «{SHARE_CONTACT_BUTTON_TEXT}».",
                reply_markup=_build_main_keyboard(),
            )
            return
        await state.update_data(phone=contact.phone_number)
        await state.set_state(OrderStates.waiting_for_quantity)
        text = (
            "Укажите количество упаковок (по 500 г). Введите число, например: 2 \n"
            "---------------------------\n"
            "Сейчас в наличии икра горбуши в фасовке 500г (вылов июль 2025) \n"
            "\n"
            "Специальное предложение: \n"
            "Обычная цена: <s>5000₽</s> → Для вас: <b>4000₽</b> за 500г \n"
            "\n"
            "Доп бонус на первый заказ: \n"
            "-500₽ на каждые 500г при заказе через бот @ikorka_moscow_bot и подписку на канал @ikorka_moscow"
        )
        await message.answer(
            text,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )

    @staticmethod
    async def handle_quantity(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        if not message.text:
            return
        text = message.text.strip()
        if not text.isdigit() or int(text) <= 0:
            await message.answer("Пожалуйста, введите положительное число, например: 2")
            return
        await _touch_activity(state)
        await state.update_data(quantity=text)
        await state.set_state(OrderStates.waiting_for_name)
        await message.answer("Укажите ФИО получателя")

    @staticmethod
    async def handle_name(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        if not message.text:
            return
        await _touch_activity(state)
        await state.update_data(full_name=message.text.strip())
        await state.set_state(OrderStates.waiting_for_address)
        await message.answer("Укажите адрес доставки (город, улица, дом, кв., подъезд, этаж)")

    @staticmethod
    async def handle_address(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        if not message.text:
            return
        await _touch_activity(state)
        await state.update_data(address=message.text.strip())
        await state.set_state(OrderStates.waiting_for_phone)
        await message.answer(
            "Укажите номер телефона для связи",
            reply_markup=ReplyKeyboardRemove(),
        )

    @staticmethod
    async def handle_phone(message: Message, state: FSMContext, bot: Bot) -> None:
        if await _check_and_handle_idle(message, state):
            return
        # Accept either text or previously shared contact
        phone_text: Optional[str] = None
        if message.text:
            phone_text = message.text.strip()
        if message.contact and message.contact.phone_number:
            phone_text = message.contact.phone_number

        # Save phone and move to extra info step
        await _touch_activity(state)
        await state.update_data(phone=phone_text)
        await state.set_state(OrderStates.waiting_for_extra_info)
        await message.answer(
            "Добавьте дополнительную информацию по заказу (по желанию). Если нет — отправьте «-».",
            reply_markup=ReplyKeyboardRemove(),
        )

    @staticmethod
    async def handle_extra_info(message: Message, state: FSMContext, bot: Bot) -> None:
        if await _check_and_handle_idle(message, state):
            return
        extra_text = (message.text or "").strip()
        if extra_text == "-":
            extra_text = ""

        data = await state.get_data()
        quantity_text: str = str(data.get("quantity") or "—")
        name_text: str = str(data.get("full_name") or "—")
        address_text: str = str(data.get("address") or "—")
        phone_text: Optional[str] = data.get("phone")  # type: ignore[assignment]

        try:
            user = message.from_user
            assert user is not None
            formatted = _build_order_message_for_user(
                user=user,
                quantity_text=quantity_text,
                name_text=name_text,
                address_text=address_text,
                phone_text=phone_text,
                extra_info_text=extra_text,
            )
            channel_id = _resolve_target_channel_id()
            await bot.send_message(chat_id=channel_id, text=formatted)
        except Exception as exc:
            logging.exception("Failed to send order: %s", exc)
            await message.answer("Не удалось принять заказ. Попробуйте ещё раз позже.")
            return

        await state.clear()
        await message.answer(
            "Заказ принят в обработку! Ждите ответа от администратора.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=NEW_ORDER_BUTTON_TEXT)]], resize_keyboard=True
            ),
        )

    @staticmethod
    async def handle_new_order(message: Message, state: FSMContext) -> None:
        if await _check_and_handle_idle(message, state):
            return
        await OrderHandler.handle_start(message, state)
