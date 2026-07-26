"""POST /api/v1/auth/login — issues the JWT every other endpoint requires
(api-contracts.md §Autenticación: "Token obtenido vía POST /api/v1/auth/
login con credenciales SSO/PIN del operario").

STOPGAP, clearly flagged: there is no operators/users table anywhere in
db-schema.md, and no ticket ever defined one — "credenciales SSO/PIN" has
no backing credential store to validate against. Real SSO/PIN validation
is a business decision (which SSO provider? how are PINs provisioned and
rotated?) that needs a schema addition, not something to invent
unilaterally here. This endpoint issues a valid, correctly-signed token
for ANY operator_id + non-empty pin — enough to unblock every other
JWT-gated endpoint for local dev, the demo, and tests — but it is NOT a
real login and must not be mistaken for one before that business decision
is made and a real credential store exists.

RATE LIMITING: precisely because it accepts any credentials, this
endpoint would otherwise mint unlimited valid tokens for free — an
in-memory fixed-window limiter (per client IP) closes that off cheaply.
In-memory means per-process and reset on restart, same caveat as
exporter/router.py's in-memory `_JOBS` dict — a real deployment with
multiple backend instances would need a shared store (Redis) instead.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 10
_login_attempts: dict[str, list[float]] = defaultdict(list)


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


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request) -> LoginResponse:
    client_ip = http_request.client.host if http_request.client else "unknown"
    _enforce_rate_limit(client_ip)

    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta

    token = jwt.encode(
        {"operator_id": request.operator_id, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return LoginResponse(access_token=token, expires_in=int(expires_delta.total_seconds()))
