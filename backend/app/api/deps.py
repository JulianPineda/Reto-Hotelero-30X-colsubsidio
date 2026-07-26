"""Shared REST auth dependency (CLAUDE.md §5 — "verificar JWT token" applies
to every endpoint, not only the voice WebSocket). Reuses the same
OperatorClaims/JWT settings the WS handshake already validates against
(`app/agents/voice/router.py::verify_ws_token`) so both entry points accept
the exact same token.
"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agents.voice.schemas import OperatorClaims
from app.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> OperatorClaims:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta token de autenticación")

    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return OperatorClaims(**payload)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado") from exc


def require_role(*allowed_roles: str):
    """Module-boundary gate: an 'operator'-role token can't hit a
    supervisor-only endpoint and vice versa, regardless of what the
    frontend happens to show. Roles come from the `operators` table
    (migration 003) via `app/api/auth.py::login`, not a frontend choice."""

    async def _check(operator: OperatorClaims = Depends(get_current_operator)) -> OperatorClaims:
        if operator.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "FORBIDDEN_ROLE",
                    "message": "Tu cuenta no tiene permiso para acceder a este módulo.",
                },
            )
        return operator

    return _check
