import pytest
from fastapi import HTTPException

from app.security.auth import (
    UserContext,
    authorize_company,
)


def test_authorized_company_is_allowed():
    user = UserContext(
        user_id="user-1",
        allowed_companies=("ABC Pvt Ltd",),
    )

    company = authorize_company(
        user=user,
        requested_company="ABC Pvt Ltd",
    )

    assert company == "ABC Pvt Ltd"


def test_unauthorized_company_is_rejected():
    user = UserContext(
        user_id="user-1",
        allowed_companies=("ABC Pvt Ltd",),
    )

    with pytest.raises(HTTPException) as exc:
        authorize_company(
            user=user,
            requested_company="XYZ Pvt Ltd",
        )

    assert exc.value.status_code == 403


def test_single_company_is_auto_selected():
    user = UserContext(
        user_id="user-1",
        allowed_companies=("ABC Pvt Ltd",),
    )

    company = authorize_company(
        user=user,
        requested_company=None,
    )

    assert company == "ABC Pvt Ltd"


def test_multiple_companies_require_selection():
    user = UserContext(
        user_id="user-1",
        allowed_companies=(
            "ABC Pvt Ltd",
            "XYZ Pvt Ltd",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        authorize_company(
            user=user,
            requested_company=None,
        )

    assert exc.value.status_code == 400


def test_company_matching_is_case_insensitive():
    user = UserContext(
        user_id="user-1",
        allowed_companies=("ABC Pvt Ltd",),
    )

    company = authorize_company(
        user=user,
        requested_company="abc pvt ltd",
    )

    assert company == "ABC Pvt Ltd"


def test_user_with_no_company_access_is_rejected():
    user = UserContext(
        user_id="user-1",
        allowed_companies=(),
    )

    with pytest.raises(HTTPException) as exc:
        authorize_company(
            user=user,
            requested_company=None,
        )

    assert exc.value.status_code == 403