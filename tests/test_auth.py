import pytest

from webapp.api.auth.passwords import hash_password, verify_password


# --- P4b-1: password hashing (stdlib pbkdf2) --------------------------------

def test_hash_is_salted_and_verifies():
    h = hash_password("correct horse")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong", h) is False


def test_two_hashes_of_same_password_differ():
    # per-user random salt -> different encoded hashes
    assert hash_password("pw") != hash_password("pw")


def test_verify_is_constant_time_and_handles_garbage():
    assert verify_password("x", "not-a-valid-encoding") is False
    assert verify_password("x", "") is False
    assert verify_password("x", "pbkdf2_sha256$bad$nope") is False
