from backend.core.security import authenticate_user, normalize_username


def test_username_normalization_is_case_and_whitespace_tolerant():
    assert normalize_username("  ArU  ") == "aru"


def test_dashboard_alias_authenticates_against_configured_admin_password():
    user = authenticate_user("  ARU ", "ci-password")
    assert user == {"username": "admin"}


def test_wrong_password_is_rejected():
    assert authenticate_user("admin", "wrong-password") is None
