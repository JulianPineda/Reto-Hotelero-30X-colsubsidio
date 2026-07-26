import pytest
from fastapi import HTTPException

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import require_role


async def test_require_role_allows_a_matching_role():
    checker = require_role("operator")
    claims = OperatorClaims(operator_id="OP-1", role="operator")

    result = await checker(operator=claims)

    assert result is claims


async def test_require_role_rejects_a_mismatched_role():
    checker = require_role("supervisor")
    claims = OperatorClaims(operator_id="OP-1", role="operator")

    with pytest.raises(HTTPException) as exc_info:
        await checker(operator=claims)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "FORBIDDEN_ROLE"


async def test_require_role_accepts_multiple_allowed_roles():
    checker = require_role("operator", "supervisor")

    for role in ("operator", "supervisor"):
        claims = OperatorClaims(operator_id="OP-1", role=role)
        assert await checker(operator=claims) is claims
