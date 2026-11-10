"""密码哈希测试。

覆盖三件事：
1. 哈希不可逆、格式正确；
2. **超长密码不被截断**——bcrypt 只取前 72 字节，若不做 sha256 预哈希，
   两个前 72 字节相同的长密码会互相通过校验，这是真实的安全隐患；
3. 历史明文密码的平滑升级路径。
"""

from homemind.services.password_service import (
    hash_password,
    is_hashed,
    verify_and_maybe_upgrade,
    verify_password,
)


def test_hash_is_bcrypt_format_and_not_plaintext():
    password = "123456"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith(("$2a$", "$2b$", "$2y$"))
    assert is_hashed(hashed) is True


def test_hash_uses_random_salt():
    """同一密码两次哈希结果必须不同（否则说明没加盐）。"""
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_correct_password():
    hashed = hash_password("correct-horse")
    assert verify_password("correct-horse", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("correct-horse")
    assert verify_password("wrong-horse", hashed) is False
    assert verify_password("", hashed) is False


def test_verify_rejects_plaintext_stored_value():
    """已是明文的历史数据不应被 verify_password 直接放行。

    明文兼容只允许发生在登录路径（verify_and_maybe_upgrade）并触发升级，
    不能被当作常规校验路径。
    """
    assert verify_password("123456", "123456") is False


def test_long_password_beyond_72_bytes_is_not_truncated():
    """超过 bcrypt 72 字节上限的密码必须仍能区分。

    若没有 sha256 预哈希，`base + "X"` 与 `base + "Y"` 会因为前 72 字节相同
    而被判为同一个密码——这条断言就是在守这个洞。
    """
    base = "a" * 72
    password_x = base + "X"
    password_y = base + "Y"

    hashed = hash_password(password_x)
    assert verify_password(password_x, hashed) is True
    assert verify_password(password_y, hashed) is False


def test_is_hashed_detects_legacy_plaintext():
    assert is_hashed("123456") is False
    assert is_hashed("") is False
    assert is_hashed(hash_password("x")) is True


# ============================================================
# 历史明文数据的平滑升级
# ============================================================


def test_legacy_plaintext_login_succeeds_and_flags_upgrade():
    """明文历史数据：比对通过，并且标记"需要升级为哈希"。"""
    ok, needs_upgrade = verify_and_maybe_upgrade("123456", "123456")
    assert ok is True
    assert needs_upgrade is True


def test_legacy_plaintext_wrong_password():
    ok, needs_upgrade = verify_and_maybe_upgrade("wrong", "123456")
    assert ok is False
    assert needs_upgrade is False


def test_hashed_value_never_flags_upgrade():
    """已是哈希的存储值不应反复触发升级。"""
    hashed = hash_password("123456")
    ok, needs_upgrade = verify_and_maybe_upgrade("123456", hashed)
    assert ok is True
    assert needs_upgrade is False
