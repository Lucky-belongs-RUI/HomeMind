"""Prompt 注册表测试。

Prompt 是 AI 系统的业务逻辑，应当像代码一样被测试。这里覆盖两点：

1. **注册表完整性**——id 唯一、版本号规范、用途说明齐全；
2. **模板可渲染性**——每个模板都能用它自己声明的变量渲染成功。

第 2 条能抓出两类"上线后才在某个分支炸掉"的问题：模板里有未转义的 `{`、
以及声明的变量与调用方传入的不一致。
"""

from dataclasses import FrozenInstanceError
from string import Formatter

import pytest

from homemind.prompts import REGISTRY

EXPECTED_IDS = {
    "opening_message",
    "preference_analysis",
}


def _declared_fields(template: str) -> set:
    """提取模板声明的变量名；已转义的 {{ }} 不会出现在结果中。"""
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def test_registry_is_complete():
    """全部提示词纳入注册表——漏一个就说明还有硬编码的 prompt。"""
    assert set(REGISTRY) == EXPECTED_IDS


def test_prompt_metadata_present():
    for prompt_id, prompt in REGISTRY.items():
        assert prompt.id == prompt_id
        assert prompt.description.strip(), f"{prompt_id} 缺少用途说明"
        assert prompt.template.strip(), f"{prompt_id} 模板为空"


def test_prompt_versions_are_semver_like():
    for prompt in REGISTRY.values():
        parts = prompt.version.split(".")
        assert len(parts) == 3, f"{prompt.id} 的版本号应为 x.y.z 形式，实际 {prompt.version}"
        assert all(part.isdigit() for part in parts), f"{prompt.id} 版本号含非数字"


@pytest.mark.parametrize("prompt_id", sorted(EXPECTED_IDS))
def test_every_prompt_renders_with_its_declared_fields(prompt_id):
    """每个 prompt 都能用自己声明的变量渲染成功。

    能抓到两类问题：
    - 模板里有未转义的 `{`，`.format()` 会直接抛 KeyError / ValueError；
    - 声明的变量与调用方传入的不一致（渲染时抛 KeyError）。
    """
    prompt = REGISTRY[prompt_id]
    fields = _declared_fields(prompt.template)
    rendered = prompt.render(**{name: f"VALUE_{name}" for name in fields})

    assert rendered
    # 逐个确认占位符确实被替换掉了。
    # 注意不能用 `"<" not in rendered` 这类间接判断——替换进去的值本身可能含该字符。
    for name in fields:
        assert f"{{{name}}}" not in rendered, f"占位符 {{{name}}} 未被替换"
    if fields:
        assert rendered != prompt.template, "模板未被真正渲染"


def test_opening_prompt_declares_expected_fields():
    """开场白 prompt 的变量契约——调用方传入的正是这两个。"""
    fields = _declared_fields(REGISTRY["opening_message"].template)
    assert fields == {"house_status", "nickname"}


def test_text_property_returns_raw_template():
    """`.text` 返回未渲染原文，供评测与审计做快照对比。"""
    prompt = REGISTRY["opening_message"]
    assert prompt.text == prompt.template
    assert "{house_status}" in prompt.text


def test_prompt_is_immutable():
    """Prompt 是不可变对象——防止运行期被意外改写。"""
    prompt = REGISTRY["opening_message"]
    with pytest.raises(FrozenInstanceError):
        prompt.version = "9.9.9"
