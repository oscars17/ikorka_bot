from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    waiting_for_order_start: State = State()
    waiting_for_contact: State = State()
    waiting_for_quantity: State = State()
    waiting_for_name: State = State()
    waiting_for_address: State = State()
    waiting_for_phone: State = State()
    waiting_for_manual_phone: State = State()
    waiting_for_extra_info: State = State()
