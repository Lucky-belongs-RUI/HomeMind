"""进程内滑动窗口限流与登录失败锁定。

定位：这是防止暴力破解与批量刷号的**第一道防线**，不是分布式限流方案。
状态保存在进程内存中：
- 单副本部署：完全有效；
- 多副本部署：每个副本各自计数，实际阈值被放大为「副本数 × 阈值」。
  上多副本时应把本模块替换为 Redis 实现（对外函数签名保持不变即可）。

内存控制：每个 key 只保留窗口内的访问记录；key 总数接近上限时清理过期条目，
避免被大量随机 key（如伪造 IP、随机用户名）撑爆内存。
"""

import time
from collections import deque

# ===== 阈值（可按业务需要调整）=====
LOGIN_IP_LIMIT = 20  # 单 IP 5 分钟内最多 20 次登录尝试
LOGIN_IP_WINDOW = 300
LOGIN_FAILURE_THRESHOLD = 5  # 单账号连续失败 5 次即锁定
LOGIN_LOCK_SECONDS = 900  # 锁定 15 分钟
REGISTER_IP_LIMIT = 5  # 单 IP 每小时最多注册 5 个家庭
REGISTER_IP_WINDOW = 3600

# key 长度上限：username 来自请求体，需截断以防被超长字符串滥用为内存 key
_MAX_KEY_LENGTH = 128
_MAX_KEYS = 20000
_STALE_SECONDS = 3600


def _normalize(key: str) -> str:
    return (key or "")[:_MAX_KEY_LENGTH]


def _normalize_username(username: str) -> str:
    """用户名在 MySQL 默认排序规则下大小写不敏感，限流 key 必须同样归一化。"""
    return (username or "").strip().casefold()


class SlidingWindowCounter:
    """按 key 维护滑动窗口内的访问时间戳。"""

    def __init__(self, max_keys: int = _MAX_KEYS):
        self._hits: dict[str, deque[float]] = {}
        self._max_keys = max_keys

    @staticmethod
    def _prune(bucket: deque[float], window_seconds: float, now: float) -> None:
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

    def _bucket_for(self, key: str, now: float) -> deque[float]:
        bucket = self._hits.get(key)
        if bucket is None:
            self._make_room(now)
            bucket = self._hits.setdefault(key, deque())
        return bucket

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        """记录一次访问并判断是否放行；已超限时不记录。"""
        key = _normalize(key)
        now = time.monotonic()
        bucket = self._bucket_for(key, now)
        self._prune(bucket, window_seconds, now)
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def record(self, key: str, window_seconds: float) -> int:
        """记录一次失败，返回窗口内的累计次数。"""
        key = _normalize(key)
        now = time.monotonic()
        bucket = self._bucket_for(key, now)
        self._prune(bucket, window_seconds, now)
        bucket.append(now)
        return len(bucket)

    def count(self, key: str, window_seconds: float) -> int:
        """返回窗口内的累计次数（不记录）。"""
        bucket = self._hits.get(_normalize(key))
        if not bucket:
            return 0
        self._prune(bucket, window_seconds, time.monotonic())
        return len(bucket)

    def clear(self, key: str) -> None:
        self._hits.pop(_normalize(key), None)

    def _make_room(self, now: float) -> None:
        """key 数量达到上限时清理过期条目；仍满则整体清空（宁可放宽限流也不 OOM）。"""
        if len(self._hits) < self._max_keys:
            return
        stale = [
            key
            for key, bucket in self._hits.items()
            if not bucket or now - bucket[-1] > _STALE_SECONDS
        ]
        for key in stale:
            self._hits.pop(key, None)
        if len(self._hits) >= self._max_keys:
            self._hits.clear()


_counter = SlidingWindowCounter()


def allow_login_attempt(client_ip: str) -> bool:
    """单 IP 登录频率限制。"""
    return _counter.allow(f"login:ip:{client_ip}", LOGIN_IP_LIMIT, LOGIN_IP_WINDOW)


def is_account_locked(username: str) -> bool:
    """账号是否因连续失败被临时锁定。"""
    key = f"login:fail:{_normalize_username(username)}"
    return _counter.count(key, LOGIN_LOCK_SECONDS) >= LOGIN_FAILURE_THRESHOLD


def record_login_failure(username: str) -> int:
    """记录一次登录失败，返回累计失败次数。

    用户名不存在时同样记录：否则攻击者可借"是否被锁定"的差异枚举出有效用户名。
    """
    return _counter.record(f"login:fail:{_normalize_username(username)}", LOGIN_LOCK_SECONDS)


def clear_login_failures(username: str) -> None:
    """登录成功后清除失败计数。"""
    _counter.clear(f"login:fail:{_normalize_username(username)}")


def allow_register_attempt(client_ip: str) -> bool:
    """单 IP 注册频率限制（防止脚本批量创建家庭消耗模型额度）。"""
    return _counter.allow(f"register:ip:{client_ip}", REGISTER_IP_LIMIT, REGISTER_IP_WINDOW)
