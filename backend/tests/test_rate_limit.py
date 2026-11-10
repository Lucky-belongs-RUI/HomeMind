"""限流与账号锁定测试。

用假时钟推进时间，避免 `time.sleep` 让测试变慢。
"""

import pytest

from homemind.services import rate_limit as rl


class _FakeClock:
    """可手动推进的单调时钟。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr(rl.time, "monotonic", fake.monotonic)
    return fake


# ============================================================
# 滑动窗口
# ============================================================


def test_allow_under_limit(clock):
    counter = rl.SlidingWindowCounter()
    assert counter.allow("k", limit=3, window_seconds=60) is True
    assert counter.allow("k", limit=3, window_seconds=60) is True
    assert counter.allow("k", limit=3, window_seconds=60) is True


def test_deny_at_limit(clock):
    counter = rl.SlidingWindowCounter()
    for _ in range(3):
        counter.allow("k", limit=3, window_seconds=60)
    assert counter.allow("k", limit=3, window_seconds=60) is False


def test_window_slides(clock):
    """窗口过期后重新放行。"""
    counter = rl.SlidingWindowCounter()
    for _ in range(3):
        counter.allow("k", limit=3, window_seconds=60)
    assert counter.allow("k", limit=3, window_seconds=60) is False

    clock.advance(61)
    assert counter.allow("k", limit=3, window_seconds=60) is True


def test_keys_are_isolated(clock):
    """不同 key 互不影响。"""
    counter = rl.SlidingWindowCounter()
    for _ in range(3):
        counter.allow("a", limit=3, window_seconds=60)
    assert counter.allow("a", limit=3, window_seconds=60) is False
    assert counter.allow("b", limit=3, window_seconds=60) is True


def test_long_key_is_truncated(clock):
    """超长 key 被截断，避免被恶意超长字符串撑爆内存。"""
    counter = rl.SlidingWindowCounter()
    counter.allow("x" * 10_000, limit=1, window_seconds=60)
    assert len(counter._hits) == 1
    (stored_key,) = counter._hits.keys()
    assert len(stored_key) <= rl._MAX_KEY_LENGTH


def test_record_accumulates_within_window(clock):
    counter = rl.SlidingWindowCounter()
    assert counter.record("f", window_seconds=100) == 1
    assert counter.record("f", window_seconds=100) == 2
    clock.advance(101)
    assert counter.record("f", window_seconds=100) == 1


def test_count_does_not_record(clock):
    counter = rl.SlidingWindowCounter()
    assert counter.count("k", window_seconds=60) == 0
    assert counter.count("k", window_seconds=60) == 0


def test_clear_resets_key(clock):
    counter = rl.SlidingWindowCounter()
    for _ in range(3):
        counter.allow("k", limit=3, window_seconds=60)
    counter.clear("k")
    assert counter.allow("k", limit=3, window_seconds=60) is True


# ============================================================
# 账号失败锁定
# ============================================================


def test_account_locks_after_threshold():
    username = "lock-test-user"
    rl.clear_login_failures(username)

    for _ in range(rl.LOGIN_FAILURE_THRESHOLD - 1):
        rl.record_login_failure(username)
    assert rl.is_account_locked(username) is False

    rl.record_login_failure(username)
    assert rl.is_account_locked(username) is True


def test_successful_login_clears_failures():
    username = "clear-test-user"
    for _ in range(rl.LOGIN_FAILURE_THRESHOLD):
        rl.record_login_failure(username)
    assert rl.is_account_locked(username) is True

    rl.clear_login_failures(username)
    assert rl.is_account_locked(username) is False


def test_lock_expires(clock):
    username = "expire-test-user"
    rl.clear_login_failures(username)
    for _ in range(rl.LOGIN_FAILURE_THRESHOLD):
        rl.record_login_failure(username)
    assert rl.is_account_locked(username) is True

    clock.advance(rl.LOGIN_LOCK_SECONDS + 1)
    assert rl.is_account_locked(username) is False


def test_nonexistent_username_also_accumulates_failures():
    """用户名不存在时也计入失败次数。

    否则攻击者可以借"该账号是否被锁定"的差异枚举出有效用户名。
    """
    username = "definitely-not-registered"
    rl.clear_login_failures(username)
    for _ in range(rl.LOGIN_FAILURE_THRESHOLD):
        rl.record_login_failure(username)
    assert rl.is_account_locked(username) is True
