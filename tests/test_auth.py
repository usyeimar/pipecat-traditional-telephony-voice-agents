import base64

import pytest

from telephony.auth import token_from_authorization


def basic(credentials: str) -> str:
    return "Basic " + base64.b64encode(credentials.encode()).decode()


def test_bearer_token():
    assert token_from_authorization("Bearer s3cret") == "s3cret"


def test_basic_password_is_the_token():
    assert token_from_authorization(basic("asterisk:s3cret")) == "s3cret"


def test_basic_password_may_contain_colons():
    assert token_from_authorization(basic("asterisk:a:b")) == "a:b"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic !!!", basic("no-colon"), basic("user:"), "Digest abc"],
)
def test_anything_else_carries_no_token(header):
    assert token_from_authorization(header) is None
