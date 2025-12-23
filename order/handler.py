from typing import Optional
import logging
import os

from db import insert_order
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User
)
from aiogram.fsm.context import FSMContext
from aiogram import Bot

from app.order.consts import (
    SHARE_CONTACT_BUTTON_TEXT,
    NEW_ORDER_BUTTON_TEXT,
    FAQ_BUTTON_TEXT,
    START_ORDER_BUTTON_TEXT
)
from app.order.states import OrderStates
from datetime import datetime
from zoneinfo import ZoneInfo


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
    manual_phone_text: Optional[str],
    extra_info_text: Optional[str],
    datetime_moscow: str,
    datetime_khabarovsk: str,
    order_id: int
) -> str:
    full_name = user.full_name
    username: str = f"@{user.username}" if user.username else "—"
    user_id: int = user.id

    quantity_text = (quantity_text or "").strip() or "—"
    name_text = (name_text or "").strip() or "—"
    address_text = (address_text or "").strip() or "—"
    phone_text = _normalize_phone(phone_text)
    extra_info_text = (extra_info_text or "").strip() or "—"

    formatted = (
        f"Новый заказ № {order_id} \n\n"
        f"Время Москва {datetime_moscow}\n"
        f"Время Хабаровск {datetime_khabarovsk}\n\n"
        f"Имя в Telegram: {full_name}\n"
        f"Username: {username}\n"
        f"User ID: {user_id}\n"
        f"Телефон (контакт): {phone_text}\n"
        f"Телефон (ручной ввод): {manual_phone_text}\n"
        f"ФИО получателя: {name_text}\n"
        f"Адрес: {address_text}\n"
        f"Заказ: {quantity_text}\n"
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
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def handle_start(self, message: Message, state: FSMContext) -> None:
        logging.info("handle_start called for user %s", message.from_user.id if message.from_user else "unknown")
        await state.clear()
        await state.set_state(OrderStates.waiting_for_order_start)
        await message.answer(
            "Привет! Нажмите «Сделать заказ», чтобы начать оформление.",
            reply_markup=_build_main_keyboard(),
        )

    async def handle_start_order(self, message: Message, state: FSMContext) -> None:
        await state.set_state(OrderStates.waiting_for_contact)
        await message.answer(
            'Нажмите на кнопку "Поделиться контактом", чтобы мы могли с вами связаться.',
            reply_markup=_build_contact_keyboard(),
        )

    async def handle_faq(self, message: Message) -> None:
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
        )
        await message.answer(text, parse_mode="HTML")

    async def handle_contact(self, message: Message, state: FSMContext) -> None:
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
            "🔴 ИКРА ГОРБУШИ СОЛЕНАЯ \n"
            "Дикий вылов. Сезон 2025 года. \n"
            "➤  250 г — 2 500 ₽ \n"
            "➤  500 г — 4 000 ₽ \n"
            "\n"
            "🦀 КРАБ КАМЧАТСКИЙ \n"
            "Мясо 1-й фаланги (8–10 см). \n"
            "Варено-мороженое, очищенное. \n"
            "➤  600 г — 4 800 ₽ \n"
            "➤  1,2 кг — 9 600 ₽ \n"
            "\n"
            "🦐 КРЕВЕТКИ ГРЕБЕНЧАТЫЕ БОТАН \n"
            "Варено-мороженые. Размер 15–16 см. \n"
            "➤  Коробка 800 г — 3 800 ₽ \n"
            "\n"
            "🐚 МОРСКОЙ ГРЕБЕШОК ФИЛЕ \n"
            "Свежемороженый. Крупный (6–8 см). \n"
            "➤  500 г (7–9 шт.) — 2 300 ₽ \n"
            "➤  1 кг — 4 500 ₽ \n"
        )
        await message.answer(
            text,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )

    async def handle_quantity(self, message: Message, state: FSMContext) -> None:
        if not message.text:
            return
        text = message.text.strip()
        await state.update_data(quantity=text)
        await state.set_state(OrderStates.waiting_for_name)
        await message.answer("Укажите ФИО получателя")

    async def handle_name(self, message: Message, state: FSMContext) -> None:
        if not message.text:
            return
        await state.update_data(full_name=message.text.strip())
        await state.set_state(OrderStates.waiting_for_address)
        await message.answer("Укажите адрес доставки (город, улица, дом, кв., подъезд, этаж)")

    async def handle_address(self, message: Message, state: FSMContext) -> None:
        if not message.text:
            return
        await state.update_data(address=message.text.strip())
        await state.set_state(OrderStates.waiting_for_phone)
        await message.answer(
            "Укажите номер телефона для связи",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def handle_phone(self, message: Message, state: FSMContext) -> None:
        phone_text: Optional[str] = None
        if message.text:
            phone_text = message.text.strip()
        await state.update_data(manual_phone=phone_text)
        await state.set_state(OrderStates.waiting_for_extra_info)
        await message.answer(
            "Добавьте дополнительную информацию по заказу (по желанию). Если нет — отправьте «-».",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def handle_extra_info(self, message: Message, state: FSMContext, bot: Bot) -> None:
        extra_text = (message.text or "").strip()
        if extra_text == "-":
            extra_text = ""

        data = await state.get_data()
        quantity_text: str = str(data.get("quantity") or "—")
        name_text: str = str(data.get("full_name") or "—")
        address_text: str = str(data.get("address") or "—")
        phone_text: Optional[str] = data.get("phone")  # type: ignore[assignment]
        manual_phone_text: Optional[str] = data.get("manual_phone")

        user = message.from_user
        # текущее время в UTC
        now_utc = datetime.now(tz=ZoneInfo("UTC"))

        # Москва
        datetime_moscow = now_utc.astimezone(ZoneInfo("Europe/Moscow"))

        # Хабаровск
        datetime_khabarovsk = now_utc.astimezone(ZoneInfo("Asia/Vladivostok"))
        assert user is not None
        try:
            order_id = await insert_order(
                pool=self.db_pool,
                tg_user_id=user.id,
                full_name=user.full_name,
                username=user.username,
                profile_link=f"{user.id}",
                phone_contact=phone_text,
                phone_manual=manual_phone_text,
                fio_receiver=name_text,
                address=address_text,
                quantity=quantity_text,
                extra_info=extra_text,
                datetime_moscow=datetime_moscow,
                datetime_khabarovsk=datetime_khabarovsk
            )
            formatted = _build_order_message_for_user(
                datetime_moscow=datetime_moscow.strftime("%Y-%m-%d %H:%M"),
                datetime_khabarovsk=datetime_khabarovsk.strftime("%Y-%m-%d %H:%M"),
                user=user,
                quantity_text=quantity_text,
                name_text=name_text,
                address_text=address_text,
                phone_text=phone_text,
                manual_phone_text=manual_phone_text,
                extra_info_text=extra_text,
                order_id=order_id
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

    async def handle_new_order(self, message: Message, state: FSMContext) -> None:
        await self.handle_start(message, state)
