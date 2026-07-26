import jwt
import pytest
from fastapi import WebSocketException

from app.agents.voice.router import verify_ws_token
from app.config import settings


def _make_token(role: str, operator_id: str = "OP-1") -> str:
    return jwt.encode({"operator_id": operator_id, "role": role}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def test_verify_ws_token_accepts_operator_role():
    claims = await verify_ws_token(_make_token("operator"))
    assert claims.operator_id == "OP-1"
    assert claims.role == "operator"


async def test_verify_ws_token_rejects_supervisor_role():
    """Voice capture (PTT) is operator-module only — confirmed live this
    needed an explicit check, since a supervisor token is otherwise a
    perfectly valid, correctly-signed JWT."""
    with pytest.raises(WebSocketException):
        await verify_ws_token(_make_token("supervisor"))


async def test_verify_ws_token_rejects_garbage_token():
    with pytest.raises(WebSocketException):
        await verify_ws_token("not-a-real-jwt")
