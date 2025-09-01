# db.py
import asyncpg

async def create_pool():
    return await asyncpg.create_pool(
        dsn="postgres://ikorka:ikorka@localhost:5432/ikorka"
    )

async def insert_order(pool, *, tg_user_id, full_name, username, profile_link,
                       phone_contact, phone_manual, fio_receiver, address,
                       quantity, extra_info, datetime_moscow, datetime_khabarovsk):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO orders (
                tg_user_id, full_name, username, profile_link,
                phone_contact, phone_manual, fio_receiver, address,
                quantity, extra_info, datetime_moscow, datetime_khabarovsk
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            tg_user_id,
            full_name,
            username,
            profile_link,
            phone_contact,
            phone_manual,
            fio_receiver,
            address,
            quantity,
            extra_info,
            datetime_moscow,
            datetime_khabarovsk,
        )
        return row["id"]