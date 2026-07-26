from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app.api.auth import LoginRequest, login
from app.config import settings

_ip_counter = 0


def _fake_request() -> SimpleNamespace:
    """Each test gets its own fake client IP so the module-level rate
    limiter (shared across the whole test process) never carries state
    over between tests."""
    global _ip_counter
    _ip_counter += 1
    return SimpleNamespace(client=SimpleNamespace(host=f"10.0.0.{_ip_counter}"))


async def test_login_issues_a_token_carrying_operator_id():
    response = await login(LoginRequest(operator_id="OP-231", pin="1234"), _fake_request())

    assert response.token_type == "bearer"
    assert response.expires_in == settings.jwt_expire_minutes * 60

    payload = jwt.decode(response.access_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["operator_id"] == "OP-231"
    assert "exp" in payload


async def test_login_token_is_accepted_by_get_current_operator():
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.deps import get_current_operator

    response = await login(LoginRequest(operator_id="OP-999", pin="0000"), _fake_request())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=response.access_token)

    claims = await get_current_operator(credentials=credentials)

    assert claims.operator_id == "OP-999"


async def test_login_rate_limited_after_too_many_attempts_from_the_same_ip():
    request = _fake_request()

    for _ in range(10):
        await login(LoginRequest(operator_id="OP-1", pin="1234"), request)

    with pytest.raises(HTTPException) as exc_info:
        await login(LoginRequest(operator_id="OP-1", pin="1234"), request)

    assert exc_info.value.status_code == 429


async def test_login_rate_limit_is_tracked_per_ip():
    saturated_request = _fake_request()
    for _ in range(10):
        await login(LoginRequest(operator_id="OP-1", pin="1234"), saturated_request)

    # A different client IP has its own, unsaturated bucket.
    fresh_request = _fake_request()
    response = await login(LoginRequest(operator_id="OP-2", pin="1234"), fresh_request)
    assert response.access_token is not None
