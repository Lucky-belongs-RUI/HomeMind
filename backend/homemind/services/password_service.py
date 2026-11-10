

import base64
import hashlib
import logging

import bcrypt

logger = logging.getLogger(__name__)

_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def _prehash(password: str) -> bytes:
    """sha256 预哈希，规避 bcrypt 的 72 字节输入上限。"""
    digest = hashlib.sha256((password or "").encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（每次调用使用新的随机盐）。"""
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def is_hashed(stored: str) -> bool:
    """判断存储值是否已是 bcrypt 哈希。"""
    return bool(stored) and stored.startswith(_BCRYPT_PREFIXES)


def verify_password(password: str, stored: str) -> bool:
    """校验密码（仅接受 bcrypt 哈希形式的存储值）。"""
    if not is_hashed(stored):
        return False
    try:
        return bcrypt.checkpw(_prehash(password), stored.encode("ascii"))
    except (ValueError, TypeError):
        return False


def verify_and_maybe_upgrade(password: str, stored: str) -> tuple[bool, bool]:
    """校验密码，并判断是否需要把历史明文值升级为哈希。

    返回 (是否通过, 是否需要重新哈希写回)。
    仅当存储值不是 bcrypt 哈希（历史明文）且比对通过时，第二个返回值为 True。
    """
    if is_hashed(stored):
        return verify_password(password, stored), False
    if stored and password == stored:
        logger.warning("检测到明文存储的密码，本次登录后已自动升级为 bcrypt 哈希")
        return True, True
    return False, False
