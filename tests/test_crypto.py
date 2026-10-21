import pytest

from chakshu.core import crypto


def test_round_trip():
    secret = "sk-ant-example-value"
    token = crypto.encrypt(secret)
    assert token != secret
    assert crypto.decrypt(token) == secret


def test_decrypt_of_garbage_or_empty_is_none():
    assert crypto.decrypt(None) is None
    assert crypto.decrypt("") is None
    assert crypto.decrypt("not-a-token") is None


def test_short_secret_key_is_rejected():
    with pytest.raises(crypto.SecretKeyError):
        crypto._fernet("too-short")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), ("short", "••••••••"), ("sk-ant-api03-abcdefghijkl", "sk-ant…ijkl")],
)
def test_mask(value, expected):
    assert crypto.mask(value) == expected
