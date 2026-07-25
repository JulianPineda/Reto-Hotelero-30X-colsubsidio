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
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=1, max_length=20)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta

    token = jwt.encode(
        {"operator_id": request.operator_id, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return LoginResponse(access_token=token, expires_in=int(expires_delta.total_seconds()))
