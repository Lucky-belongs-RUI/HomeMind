"""工具注册表测试。

注册表的核心价值是"定义与实现绑定 + 启动时校验"，因此这里重点验证一致性约束：
只要有人加了工具定义却忘了写实现（或反之），构造注册表就会失败。

注：用 `asyncio.run` 而非 `@pytest.mark.asyncio`，这样不依赖 pytest-asyncio，
保证测试在任何环境都能跑。
"""

import asyncio

import pytest

from homemind.agent.tools.device_tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    get_tool_definitions,
)
from homemind.agent.tools.registry import ToolRegistry, ToolRegistryError

EXPECTED_TOOLS = {
    "set_device_state",
    "get_device_state",
    "list_room_devices",
    "trigger_scene",
    "get_current_time",
    "get_weather",
}


# ============================================================
# 注册完整性
# ============================================================


def test_all_expected_tools_are_exposed_to_model():
    """模型可见的工具集合应与预期一致。"""
    names = {definition.name for definition in get_tool_definitions()}
    assert names == EXPECTED_TOOLS


def test_get_tool_definitions_returns_registry_content():
    """对外接口返回的就是注册表里的定义，不存在第二份清单。"""
    assert get_tool_definitions() == TOOL_DEFINITIONS


def test_every_definition_has_description_and_parameters():
    """工具定义必须带描述与参数结构——否则模型无法正确调用。"""
    for definition in get_tool_definitions():
        assert definition.description.strip(), f"{definition.name} 缺少描述"
        assert isinstance(definition.parameters, dict)


# ============================================================
# 一致性校验（fail fast）
# ============================================================


def test_registry_rejects_definition_without_handler():
    """只有定义、没有实现 → 构造时即报错。

    若不校验，症状是"模型调用了却返回未知工具"，排查成本很高。
    """
    with pytest.raises(ToolRegistryError, match="缺少执行实现"):
        ToolRegistry(definitions=TOOL_DEFINITIONS, handlers={})


def test_registry_rejects_handler_without_definition():
    """只有实现、没有定义 → 构造时即报错。

    若不校验，症状是"这个工具永远不会被调用"，且没有任何报错。
    """

    async def orphan_handler(arguments, user_id, user_role, family_id):
        return {"success": True}

    with pytest.raises(ToolRegistryError, match="没有对应定义"):
        ToolRegistry(definitions=[], handlers={"ghost_tool": orphan_handler})


# ============================================================
# 执行分发
# ============================================================


def test_unknown_tool_returns_error_instead_of_raising():
    """未知工具应回传失败结果，而不是抛异常中断整轮对话。"""
    result = asyncio.run(execute_tool("not_a_tool", {}, 1, "owner", 1))
    assert result["success"] is False
    assert "未知工具" in result["error"]


def test_get_current_time_runs_without_database():
    """时间查询工具不依赖数据库，可离线验证完整的「注册 → 分发 → 执行」链路。"""
    result = asyncio.run(execute_tool("get_current_time", {}, 1, "owner", 1))
    assert result["success"] is True
    assert result["weekday"]
    assert result["date"]
    assert "现在是" in result["message"]


def test_module_registry_exposes_all_tools():
    """模块级注册表（实际被节点使用的那一个）包含全部工具。"""
    from homemind.agent.tools.device_tools import registry as module_registry

    assert set(module_registry.names) == EXPECTED_TOOLS
    assert len(module_registry.definitions()) == len(EXPECTED_TOOLS)
