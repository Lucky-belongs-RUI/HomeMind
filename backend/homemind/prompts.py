"""Prompt 资产：带版本号的提示词模板与注册表。

为什么需要它：

1. **可检索**——改一句话不用 grep 整个仓库；
2. **可版本化**——每个 prompt 带 id 与 version，配合 `evals/` 可以回答
   "这次 prompt 改动到底让指标变好还是变坏"；
3. **可审计**——prompt 是 AI 系统的业务逻辑，应当与代码同等对待：
   有 diff、有 review、有版本、可回滚。

用法：

    from homemind.prompts import OPENING_PROMPT
    system = OPENING_PROMPT.render(house_status=..., nickname=...)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """带元信息的提示词模板。"""

    id: str
    version: str
    description: str
    template: str

    @property
    def text(self) -> str:
        """未渲染的模板原文（供评测与审计使用）。"""
        return self.template

    def render(self, **kwargs) -> str:
        """按关键字参数渲染模板。

        模板中的字面花括号需写成 {{ }}（沿用 str.format 规则）。
        """
        return self.template.format(**kwargs)


OPENING_PROMPT = Prompt(
    id="opening_message",
    version="1.0.0",
    description="结合全屋状态与异常项生成首次进入的开场白",
    template="""你是智能家居助理，现在要为用户生成首次进入 AI 助理界面的开场白。

当前家庭状态：
{house_status}

用户昵称：{nickname}

开场白要求：
1. 根据当前时间段问候用户，并称呼用户昵称（如“下午好，{nickname}”）。
2. 仔细检查“家庭设备”列表中每台设备的全部状态字段，自行判断是否存在异常，
   包括但不限于：余额为 0 或负数（余额不足）、漏水/漏水报警字段为 true、
   离线（online=false）、告警字段为 true、门窗开启、门锁未上锁、燃气泄漏、
   烟雾告警等。只要发现任何异常，必须在开场白中明确提示用户，不要回复“一切正常”。
3. 设备确实全部正常时，才说“当前房屋各设备正常”。
4. 结合当前天气或季节给出一句简短、自然的关怀或建议。
5. 语气温暖口语化，不要输出 JSON，不要复述设备原始字段，总长度不超过 100 字。""",
)


PREFERENCE_ANALYSIS_PROMPT = Prompt(
    id="preference_analysis",
    version="1.0.0",
    description="从对话历史中提取用户偏好画像（键名由模型自主决定，不套固定模板）",
    template="""分析以下用户对话历史，提取用户偏好画像。只输出一个 JSON 对象，不要输出代码块标记或其他解释。

对话历史：
{conversations}

要求：
1. JSON 对象的键为语义化中文标签（例如："睡眠时间"、"起床时间"、"夏季温度"、"冬季温度"、"兴趣爱好"、"常用设备"、"交互风格"、"备注"等）。键的数量与名称完全由你根据对话内容自主决定，不要套用固定模板。
2. 值为字符串、数字或字符串数组。
3. 用户明确提到的时间必须精确提取，例如用户说"平时我就这个点睡觉"应提取为"睡眠时间": "17:30"；用户说"我一般7点起床"应提取为"起床时间": "07:00"。
4. 特殊要求、健康注意、宠物、禁忌、图片说明等提取到"备注"键，值为字符串数组。
5. 没有明确依据的内容不要编造，不要输出空值字段。
6. 输出必须是纯 JSON，顶层是一个对象。
""",
)

_ALL_PROMPTS = (
    OPENING_PROMPT,
    PREFERENCE_ANALYSIS_PROMPT,
)

# prompt_id -> Prompt
REGISTRY = {prompt.id: prompt for prompt in _ALL_PROMPTS}

__all__ = [
    "Prompt",
    "REGISTRY",
    "OPENING_PROMPT",
    "PREFERENCE_ANALYSIS_PROMPT",
]
