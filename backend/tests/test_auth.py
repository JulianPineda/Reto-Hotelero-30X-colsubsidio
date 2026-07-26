from types import SimpleNamespace

import bcrypt
import jwt
import pytest
from fastapi import HTTPException

from app.api.auth import LoginRequest, login
from app.config import settings

_ip_counter = 0
_KNOWN_PIN = "1234"


def _fake_request() -> SimpleNamespace:
    """Each test gets its own fake client IP so the module-level rate
    limiter (shared across the whole test process) never carries state
    over between tests."""
    global _ip_counter
    _ip_counter += 1
    return SimpleNamespace(client=SimpleNamespace(host=f"10.0.0.{_ip_counter}"))


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _session_for(operator_id: str, pin: str = _KNOWN_PIN, role: str = "operator") -> object:
    """Simplest case: a session that resolves to exactly one operator_id, regardless of what's queried."""
    pin_hash = bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    operator = SimpleNamespace(operator_id=operator_id, pin_hash=pin_hash, role=role)

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _FakeExecResult(operator)

    return _Session()


def _session_with_no_operators() -> object:
    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _FakeExecResult(None)

    return _Session()


async def test_login_issues_a_token_carrying_operator_id_and_role():
    response = await login(
        LoginRequest(operator_id="OP-231", pin=_KNOWN_PIN), _fake_request(), session=_session_for("OP-231")
    )

    assert response.token_type == "bearer"
    assert response.expires_in == settings.jwt_expire_minutes * 60
    assert response.role == "operator"
    assert response.operator_id == "OP-231"

    payload = jwt.decode(response.access_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["operator_id"] == "OP-231"
    assert payload["role"] == "operator"
    assert "exp" in payload


async def test_login_rejects_unknown_operator_id():
    with pytest.raises(HTTPException) as exc_info:
        await login(
            LoginRequest(operator_id="NOBODY", pin=_KNOWN_PIN),
            _fake_request(),
            session=_session_with_no_operators(),
        )
    assert exc_info.value.status_code == 401


async def test_login_rejects_wrong_pin():
    with pytest.raises(HTTPException) as exc_info:
        await login(
            LoginRequest(operator_id="OP-231", pin="0000"), _fake_request(), session=_session_for("OP-231")
        )
    assert exc_info.value.status_code == 401


async def test_login_token_is_accepted_by_get_current_operator():
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.deps import get_current_operator

    response = await login(
        LoginRequest(operator_id="OP-999", pin=_KNOWN_PIN),
        _fake_request(),
        session=_session_for("OP-999", role="supervisor"),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=response.access_token)

    claims = await get_current_operator(credentials=credentials)

    assert claims.operator_id == "OP-999"
    assert claims.role == "supervisor"


async def test_login_rate_limited_after_too_many_attempts_from_the_same_ip():
    request = _fake_request()
    session = _session_for("OP-1")

    for _ in range(10):
        await login(LoginRequest(operator_id="OP-1", pin=_KNOWN_PIN), request, session=session)

    with pytest.raises(HTTPException) as exc_info:
        await login(LoginRequest(operator_id="OP-1", pin=_KNOWN_PIN), request, session=session)

    assert exc_info.value.status_code == 429


async def test_login_rate_limit_is_tracked_per_ip():
    saturated_request = _fake_request()
    session = _session_for("OP-1")
    for _ in range(10):
        await login(LoginRequest(operator_id="OP-1", pin=_KNOWN_PIN), saturated_request, session=session)

    # A different client IP has its own, unsaturated bucket.
    fresh_request = _fake_request()
    response = await login(LoginRequest(operator_id="OP-2", pin=_KNOWN_PIN), fresh_request, session=_session_for("OP-2"))
    assert response.access_token is not None
