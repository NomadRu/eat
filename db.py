import os
import asyncpg

_pool = None

async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=1,
        max_size=5,
    )
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     BIGINT PRIMARY KEY,
                partner_id  BIGINT,
                eaten       INTEGER NOT NULL DEFAULT 0,
                drunk       INTEGER NOT NULL DEFAULT 0,
                praised     INTEGER NOT NULL DEFAULT 0,
                paired      BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                code        TEXT PRIMARY KEY,
                inviter_id  BIGINT NOT NULL
            );
        """)

async def get_user(user_id):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None

async def ensure_user(user_id):
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
            user_id,
        )
    return await get_user(user_id)

async def increment(user_id, field):
    if field not in ("eaten", "drunk", "praised"):
        raise ValueError("bad field")
    async with _pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {field} = {field} + 1 WHERE user_id = $1", user_id)

async def set_partner(user_id, partner_id):
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET partner_id = $1, paired = TRUE WHERE user_id = $2",
                partner_id, user_id,
            )
            await conn.execute(
                "UPDATE users SET partner_id = $1, paired = TRUE WHERE user_id = $2",
                user_id, partner_id,
            )

async def unlink_pair(user_id):
    user = await get_user(user_id)
    if not user or not user["partner_id"]:
        return
    partner_id = user["partner_id"]
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET partner_id = NULL, paired = FALSE WHERE user_id IN ($1, $2)",
            user_id, partner_id,
        )

async def create_invite(code, inviter_id):
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO invites (code, inviter_id) VALUES ($1, $2) ON CONFLICT (code) DO UPDATE SET inviter_id = EXCLUDED.inviter_id",
            code, inviter_id,
        )

async def pop_invite(code):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inviter_id FROM invites WHERE code = $1", code)
        if not row:
            return None
        await conn.execute("DELETE FROM invites WHERE code = $1", code)
        return row["inviter_id"]
