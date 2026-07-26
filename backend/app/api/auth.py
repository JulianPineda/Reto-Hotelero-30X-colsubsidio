"""POST /api/v1/auth/login — issues the JWT every other endpoint requires
(api-contracts.md §Autenticación: "Token obtenido vía POST /api/v1/auth/
login con credenciales SSO/PIN del operario").

Real credential check against the `operators` table (app/models/operator.py,
migration 003) — this used to accept ANY operator_id + non-empty pin (a
deliberate stopgap while no credential store existed). `role` on that table
is now the actual server-side security boundary between the operator and
supervisor modules: `app/api/deps.py::require_role` gates every endpoint
specific to one module, so a supervisor-role token can't hit an
operator-only endpoint (or vice versa) no matter what the frontend shows.

Real SSO integration is still out of scope — "credenciales SSO/PIN" per
api-contracts.md would need a business decision about which SSO provider
and how PINs get provisioned/rotated in the field. This is a real
username+PIN credential store, just not SSO-backed yet.

RATE LIMITING: an in-memory fixed-window limiter (per client IP) — even
with a real credential store, unlimited login attempts would allow PIN
brute-forcing. In-memory means per-process and reset on restart, same
caveat as exporter/router.py's in-memory `_JOBS` dict — a real deployment
with multiple backend instances would need a shared store (Redis) instead.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.operator import Operator

router = APIRouter(prefix="/auth", tags=["auth"])

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 10
_login_attempts: dict[str, list[float]] = defaultdict(list)

# Compared against when operator_id doesn't exist, so a bcrypt check still
# runs either way — a real credential store makes user enumeration via
# response-time timing a real (if minor) concern that didn't apply to the
# old "anything works" stopgap.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-pin-for-timing-parity", bcrypt.gensalt()).decode("ascii")


def _enforce_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW_SECONDS
    recent = [t for t in _login_attempts[client_ip] if t > window_start]
    if len(recent) >= _RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RATE_LIMITED",
                "message": "Demasiados intentos de inicio de sesión. Intenta de nuevo en un minuto.",
            },
        )
    recent.append(now)
    _login_attempts[client_ip] = recent


class LoginRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=1, max_length=20)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    operator_id: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest, http_request: Request, session: AsyncSession = Depends(get_db)
) -> LoginResponse:
    client_ip = http_request.client.host if http_request.client else "unknown"
    _enforce_rate_limit(client_ip)

    operator = (
        await session.execute(select(Operator).where(Operator.operator_id == request.operator_id))
    ).scalar_one_or_none()

    pin_hash = operator.pin_hash if operator is not None else _DUMMY_HASH
    pin_ok = bcrypt.checkpw(request.pin.encode("utf-8"), pin_hash.encode("utf-8"))

    if operator is None or not pin_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "ID de operario o PIN incorrectos."},
        )

    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta

    token = jwt.encode(
        {"operator_id": operator.operator_id, "role": operator.role, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return LoginResponse(
        access_token=token,
        expires_in=int(expires_delta.total_seconds()),
        role=operator.role,
        operator_id=operator.operator_id,
    )
