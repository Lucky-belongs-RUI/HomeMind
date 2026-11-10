"""同一会话（thread_id）的执行互斥。

同一 thread 被并发推进会让 checkpointer 的状态互相覆盖：两个请求各自
`reset_thread`、各自推进 super-step，最终落库的会话顺序与用户预期不符。
典型触发是同一账号多标签页 / 多端同时发消息。

语义：**快速失败，不排队**。LLM 回答动辄数十秒，让第二个请求静默排队
反而更差；前端收到 409 后提示“上一轮还在执行中”即可。

⚠️ 进程内实现（单事件循环下 set 的“判断 + 加入”之间没有 await，天然原子）。
多 worker / 多实例部署时必须换成 Redis 锁，否则每个进程各有一份 `_busy`。
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

_busy: set[str] = set()


class SessionBusy(RuntimeError):
    """该会话已有请求在执行中。"""


def _key(thread_id: object) -> str:
    return str(thread_id or "default")


def is_busy(thread_id: object) -> bool:
    return _key(thread_id) in _busy


def acquire(thread_id: object) -> None:
    """占用会话；已被占用则立刻抛 `SessionBusy`。"""
    key = _key(thread_id)
    if key in _busy:
        raise SessionBusy("该会话上一轮还在执行中，请稍候再发")
    _busy.add(key)


def release(thread_id: object) -> None:
    """释放会话；重复释放是安全的（供流式响应兜底）。"""
    _busy.discard(_key(thread_id))


@contextlib.asynccontextmanager
async def session_guard(thread_id: object) -> AsyncIterator[None]:
    """占用该会话，退出时释放（含异常/取消路径）。"""
    acquire(thread_id)
    try:
        yield
    finally:
        release(thread_id)


__all__ = ["SessionBusy", "is_busy", "acquire", "release", "session_guard"]
