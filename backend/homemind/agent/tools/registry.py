"""工具注册表：把「工具定义」与「执行实现」绑定在一起。

## 为什么需要它

原实现里新增一个工具要同时改**两处**：

1. `TOOL_DEFINITIONS` 列表——给模型看的工具描述；
2. `execute_tool` 里的一串 `if/elif` 分支——实际执行逻辑。

漏改任何一处都要等到运行时才暴露，而且症状很隐蔽：

| 漏改的地方 | 症状 |
| --- | --- |
| 漏加定义 | 模型根本不知道有这个工具，永远不调用 |
| 漏加分支 | 模型调用了，却返回"未知工具" |

注册表把两者绑成一个条目，并在构造时做**双向一致性校验**——
定义与实现必须一一对应，否则导入阶段直接报错。这类错误从"用户对话时才发现"
提前到"启动时就知道"。

## 为什么在构造时校验而不是运行时

工具集是静态的（不会在运行期增减），所以不一致属于**配置错误**而非运行时状况。
配置错误应该在进程启动时失败，而不是等到某个用户恰好触发了那条路径。
"""

from collections.abc import Awaitable, Callable
from typing import Any

from homemind.core.exceptions import DOMAIN_ERRORS
from homemind.llm.types import ToolDefinition

# 所有工具执行函数统一签名：(arguments, user_id, user_role, family_id) -> dict
ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistryError(RuntimeError):
    """注册表配置错误：工具定义与执行实现不匹配。"""


class ToolRegistry:
    """工具定义 + 执行实现的注册表。"""

    def __init__(
        self,
        definitions: list[ToolDefinition],
        handlers: dict[str, ToolHandler],
    ) -> None:
        self._definitions: dict[str, ToolDefinition] = {d.name: d for d in definitions}
        self._handlers: dict[str, ToolHandler] = dict(handlers)
        self._validate()

    def _validate(self) -> None:
        """双向校验：每个定义都要有实现，每个实现都要有定义。"""
        missing = set(self._definitions) - set(self._handlers)
        orphan = set(self._handlers) - set(self._definitions)
        if missing:
            raise ToolRegistryError(
                f"以下工具只有定义、缺少执行实现，模型调用时会返回未知工具: {sorted(missing)}"
            )
        if orphan:
            raise ToolRegistryError(
                f"以下执行实现没有对应定义，模型看不到也永远不会调用: {sorted(orphan)}"
            )

    @property
    def names(self) -> list[str]:
        """已注册的工具名列表（供测试与文档使用）。"""
        return list(self._definitions)

    def definitions(self) -> list[ToolDefinition]:
        """给模型看的工具定义列表，顺序与注册顺序一致。"""
        return list(self._definitions.values())

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        return self._definitions.get(tool_name)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: int,
        user_role: str,
        family_id: int,
    ) -> dict[str, Any]:
        """按名字执行工具。

        异常处理策略：工具执行失败不应中断整轮对话——
        设备控制是"尽力而为"的，单条失败要以 `{"success": False}` 的形式
        回传给上层（由回复生成节点告知用户），而不是抛出异常炸掉整个图。
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return {"success": False, "error": f"未知工具: {tool_name}"}

        try:
            return await handler(arguments, user_id, user_role, family_id)
        except DOMAIN_ERRORS as exc:
            # 领域异常：属于预期内的业务结果（设备不存在、权限不足等），原样回传原因
            return {"success": False, "error": str(exc)}
        except Exception as exc:  # 非预期异常：兜底，避免单点故障扩散
            return {"success": False, "error": f"工具执行异常: {exc}"}
