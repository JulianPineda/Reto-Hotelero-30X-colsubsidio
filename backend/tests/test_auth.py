import jwt

from app.api.auth import LoginRequest, login
from app.config import settings


async def test_login_issues_a_token_carrying_operator_id():
    response = await login(LoginRequest(operator_id="OP-231", pin="1234"))

    assert response.token_type == "bearer"
    assert response.expires_in == settings.jwt_expire_minutes * 60

    payload = jwt.decode(response.access_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["operator_id"] == "OP-231"
    assert "exp" in payload


async def test_login_token_is_accepted_by_get_current_operator():
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.deps import get_current_operator

    response = await login(LoginRequest(operator_id="OP-999", pin="0000"))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=response.access_token)

    claims = await get_current_operator(credentials=credentials)

    assert claims.operator_id == "OP-999"
