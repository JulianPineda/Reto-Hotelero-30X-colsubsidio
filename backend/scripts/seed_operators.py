"""Seeds two role-exclusive test users, replacing the "any credentials
work" login stopgap (app/api/auth.py). Idempotent: re-running updates the
PIN hash for existing operator_ids instead of failing on the unique
constraint.

Uso:
    python scripts/seed_operators.py
"""
import asyncio
import sys
from pathlib import Path

import bcrypt
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.operator import Operator  # noqa: E402

TEST_USERS = [
    {"operator_id": "OPERADOR1", "pin": "1234", "role": "operator", "full_name": "Operario de Prueba"},
    {"operator_id": "SUPERVISOR1", "pin": "5678", "role": "supervisor", "full_name": "Supervisor de Prueba"},
]


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for user in TEST_USERS:
            existing = (
                await session.execute(select(Operator).where(Operator.operator_id == user["operator_id"]))
            ).scalar_one_or_none()
            pin_hash = _hash_pin(user["pin"])
            if existing is not None:
                existing.pin_hash = pin_hash
                existing.role = user["role"]
                existing.full_name = user["full_name"]
            else:
                session.add(
                    Operator(
                        operator_id=user["operator_id"],
                        pin_hash=pin_hash,
                        role=user["role"],
                        full_name=user["full_name"],
                    )
                )
        await session.commit()

    print("OK: usuarios de prueba creados/actualizados:")
    for user in TEST_USERS:
        print(f"  {user['operator_id']} / PIN {user['pin']} -> rol '{user['role']}'")


if __name__ == "__main__":
    asyncio.run(seed())
