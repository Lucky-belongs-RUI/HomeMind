"""规则规划测试：参数抽取、房间解析与多任务拆解。

`_parse_attributes` 是纯函数，零依赖，是整套系统里最该被测试覆盖的一环——
它一旦解析错，设备就会被设成错误状态，而用户看到的只是"AI 执行了"。

规则规划只处理用户**明确表达**的指令：身体不适只生成关怀任务，
不再自动生成任何设备操作。
"""

import pytest

from homemind.agent.rules.devices import find_room, resolve_room_name
from homemind.agent.rules.plan import _parse_attributes, control_tasks, rule_plan

_STANDARD_DEVICES = [
    {"room_name": "客厅", "type": "air_conditioner"},
    {"room_name": "卧室", "type": "air_conditioner"},
    {"room_name": "客厅", "type": "light"},
    {"room_name": "卧室", "type": "light"},
    {"room_name": "客厅", "type": "air_purifier"},
    {"room_name": "厨房", "type": "water_heater"},
]
_STANDARD_ROOMS = ["客厅", "卧室", "厨房"]


@pytest.mark.parametrize(
    "text,device_type,expected",
    [
        # 空调
        ("把卧室空调调到26度", "air_conditioner", {"temperature": 26}),
        ("空调设置为23°", "air_conditioner", {"temperature": 23}),
        ("空调设为23℃", "air_conditioner", {"temperature": 23}),
        ("空调调到 26 °C", "air_conditioner", {"temperature": 26}),
        ("空调调高一点", "air_conditioner", {"temperature": 28}),
        ("空调调低一点", "air_conditioner", {"temperature": 24}),
        ("空调调到制冷模式", "air_conditioner", {"mode": "cool"}),
        ("空调切到制热", "air_conditioner", {"mode": "heat"}),
        ("打开空调", "air_conditioner", {"power": "on"}),
        # 热水器：回归用例——温度分支曾经不可达
        ("帮我把热水器调到50度", "water_heater", {"temperature": 50}),
        ("烧壶热水", "water_heater", {"power": "on"}),
        ("关掉热水器", "water_heater", {"power": "off"}),
        # 灯
        ("客厅灯调到30%", "light", {"brightness": 30}),
        ("把灯调亮一点", "light", {"brightness": 100}),
        ("把灯调暗一点", "light", {"brightness": 30}),
        ("关灯", "light", {"power": "off"}),
        # 窗帘
        ("把窗帘拉开", "curtain", {"position": 100}),
        ("窗帘拉上", "curtain", {"position": 0}),
        # 电视 / 音箱
        ("电视调到频道5", "tv", {"channel": 5}),
        # 回归用例：前缀用贪婪的 `.` 时会吃掉位数，把 123 解析成 3
        ("电视调到频道123", "tv", {"channel": 123}),
        ("把音量调到20", "speaker", {"volume": 20}),
        # 门锁
        ("门锁上锁", "door_lock", {"locked": True}),
        ("门锁解锁", "door_lock", {"locked": False}),
        # 扫地机器人
        ("开始扫地", "robot_vacuum", {"power": "on", "status": "cleaning"}),
        ("扫地机回充", "robot_vacuum", {"power": "off", "status": "idle"}),
    ],
)
def test_parse_attributes_hits_expected_fields(text, device_type, expected):
    """期望字段必须全部命中（键与值都对）。"""
    attrs = _parse_attributes(text, device_type)
    for key, value in expected.items():
        assert attrs.get(key) == value, f"{text!r} 的 {key} 应为 {value}，实际 {attrs.get(key)!r}"


def test_parse_attributes_water_heater_keeps_both_temperature_and_power():
    """热水器同时给出温度与开关时，两者都要解析出来。

    这是对"分支不可达"这类结构性缺陷的直接防护：
    只测单一维度时，即使某个分支永远走不到也测不出来。
    """
    attrs = _parse_attributes("打开热水器并调到55度", "water_heater")
    assert attrs.get("temperature") == 55
    assert attrs.get("power") == "on"


def test_parse_attributes_unknown_device_returns_empty():
    """无法识别的设备类型不应凭空产出参数。"""
    assert _parse_attributes("随便说点什么", "not_a_device") == {}


def test_parse_attributes_returns_dict():
    """返回值类型契约：始终是 dict，调用方无需判空。"""
    assert isinstance(_parse_attributes("把灯调暗", "light"), dict)
    assert isinstance(_parse_attributes("", "light"), dict)


# ============================================================
# 房间解析：必须落到家庭真实房间
# ============================================================


def test_find_room_prefers_real_room_names():
    """“主卧/次卧”不能被别名表一律归一成“卧室”。"""
    assert find_room("打开主卧的灯", ["主卧", "次卧"]) == "主卧"
    assert find_room("打开次卧的灯", ["主卧", "次卧"]) == "次卧"


def test_find_room_ambiguous_alias_returns_none():
    """只说“卧室”而家里有主卧、次卧时必须返回 None，交给澄清而不是瞎猜。"""
    assert find_room("打开卧室的灯", ["主卧", "次卧"]) is None


def test_find_room_resolves_unique_variant():
    """家里只有主卧时，“卧室”可以安全落到“主卧”。"""
    assert find_room("打开卧室的灯", ["主卧"]) == "主卧"


def test_resolve_room_name_keeps_unknown_room():
    assert resolve_room_name("书房", ["客厅"]) == "书房"


# ============================================================
# 控制任务拆解
# ============================================================


def test_control_tasks_maps_explicit_device_command():
    tasks, question, options = control_tasks(
        "把卧室空调调到26度", _STANDARD_DEVICES, _STANDARD_ROOMS
    )

    assert question == ""
    assert options == []
    assert len(tasks) == 1
    assert tasks[0]["tool"] == "set_device_state"
    assert tasks[0]["arguments"] == {
        "room_name": "卧室",
        "device_type": "air_conditioner",
        "attributes": {"temperature": 26},
    }


def test_control_tasks_asks_room_when_device_ambiguous():
    tasks, question, options = control_tasks(
        "把空调调到20度", _STANDARD_DEVICES, _STANDARD_ROOMS
    )

    assert tasks == []
    assert "哪个房间" in question
    assert len(options) == 2


def test_control_tasks_auto_fills_single_room():
    tasks, question, _ = control_tasks(
        "打开空气净化器", _STANDARD_DEVICES, _STANDARD_ROOMS
    )

    assert question == ""
    assert tasks[0]["arguments"]["room_name"] == "客厅"


def test_control_tasks_splits_multiple_device_clauses():
    """一句话里多个设备必须拆成多个独立任务，参数不能串到别的设备。"""
    tasks, question, _ = control_tasks(
        "把卧室灯调暗，空调设置为23°，给我讲个睡眠故事",
        [{"room_name": "卧室", "type": "light"}, {"room_name": "卧室", "type": "air_conditioner"}],
        ["卧室"],
    )

    assert question == ""
    assert len(tasks) == 2
    by_type = {task["arguments"]["device_type"]: task["arguments"]["attributes"] for task in tasks}
    assert by_type["light"] == {"brightness": 30}
    assert by_type["air_conditioner"] == {"temperature": 23}


def test_control_tasks_keeps_light_and_ac_actions_independent():
    """“空调26度，灯关掉”不能被误解析成“关掉空调”。"""
    tasks, _, _ = control_tasks(
        "把卧室空调调到26度，灯关掉",
        [{"room_name": "卧室", "type": "air_conditioner"}, {"room_name": "卧室", "type": "light"}],
        ["卧室"],
    )

    by_type = {task["arguments"]["device_type"]: task["arguments"]["attributes"] for task in tasks}
    assert by_type["air_conditioner"] == {"temperature": 26}
    assert by_type["light"] == {"power": "off"}


def test_control_tasks_skips_implicit_scene_with_explicit_device_commands():
    """明确设备指令优先，不再自动叠加“睡觉”场景覆盖用户设置。"""
    tasks, _, _ = control_tasks(
        "我想睡觉了，把卧室灯调暗，空调设置为23°",
        [{"room_name": "卧室", "type": "light"}, {"room_name": "卧室", "type": "air_conditioner"}],
        ["卧室"],
    )

    assert [task["tool"] for task in tasks] == ["set_device_state", "set_device_state"]


def test_control_tasks_keeps_implicit_scene_when_no_device_command():
    tasks, _, _ = control_tasks(
        "我想睡觉了", [{"room_name": "卧室", "type": "light"}], ["卧室"]
    )

    assert tasks[0]["tool"] == "trigger_scene"
    assert tasks[0]["arguments"]["scene_name"] == "睡眠模式"


def test_control_tasks_uses_dedicated_time_and_weather_tools():
    for text, tool_name in (
        ("现在几点了", "get_current_time"),
        ("今天天气怎么样", "get_weather"),
    ):
        tasks, _, _ = control_tasks(text, _STANDARD_DEVICES, _STANDARD_ROOMS)
        assert [task["tool"] for task in tasks] == [tool_name]
        assert tasks[0]["arguments"] == {}


def test_control_tasks_maps_scene_and_query():
    scene, _, _ = control_tasks("我要回家了", _STANDARD_DEVICES, _STANDARD_ROOMS)
    assert scene[0]["tool"] == "trigger_scene"
    assert scene[0]["arguments"]["scene_name"] == "回家模式"

    query, _, _ = control_tasks("客厅灯现在是什么状态", _STANDARD_DEVICES, _STANDARD_ROOMS)
    assert query[0]["tool"] == "get_device_state"


def test_control_tasks_infers_sensor_and_meter_devices():
    """用户说的是指标而不是设备名时，应落到家庭里的传感器/表计。"""
    temperature, _, _ = control_tasks(
        "查询客厅温度", _STANDARD_DEVICES, _STANDARD_ROOMS
    )
    assert temperature[0]["arguments"]["device_type"] == "temp_humidity_sensor"

    electricity, _, _ = control_tasks(
        "家里用电情况怎么样",
        [{"room_name": "客厅", "type": "electricity_meter"}],
        ["客厅"],
    )
    assert electricity[0]["arguments"]["device_type"] == "electricity_meter"


# ============================================================
# 整轮规则规划
# ============================================================


def _branches(text: str) -> list[str]:
    return [task["branch"] for task in rule_plan(text, _STANDARD_DEVICES, _STANDARD_ROOMS).tasks]


def test_rule_plan_health_only_produces_chat():
    """“我感冒了”不能隐式生成设备操作——只回应关怀。"""
    plan = rule_plan("我感冒了", _STANDARD_DEVICES, _STANDARD_ROOMS)

    assert [task["branch"] for task in plan.tasks] == ["chat"]
    assert plan.needs_clarification is False


def test_rule_plan_splits_explicit_multi_intent():
    """关怀 + 明确空调指令 + 药箱问题应拆成三条任务。"""
    plan = rule_plan(
        "我感冒了，调高一下空调温度，药箱里的药我该吃哪些药",
        [{"room_name": "卧室", "type": "air_conditioner"}],
        ["卧室"],
    )

    assert {task["branch"] for task in plan.tasks} == {"chat", "control", "knowledge"}
    assert plan.needs_clarification is False


def test_rule_plan_health_does_not_trigger_control_even_with_devices():
    plan = rule_plan(
        "好冷啊，我有点不舒服",
        _STANDARD_DEVICES,
        _STANDARD_ROOMS,
    )

    assert [task["branch"] for task in plan.tasks] == ["chat"]


def test_rule_plan_time_query_is_control_not_chat():
    plan = rule_plan("现在几点了", _STANDARD_DEVICES, _STANDARD_ROOMS)

    assert [task["branch"] for task in plan.tasks] == ["control"]


def test_rule_plan_knowledge_and_report_are_separate_branches():
    assert _branches("家里有什么规定") == ["knowledge"]
    assert _branches("帮我生成一份家庭情况报告") == ["report"]


def test_rule_plan_marks_ambiguous_room_for_clarification():
    plan = rule_plan("把空调调到20度", _STANDARD_DEVICES, _STANDARD_ROOMS)

    assert plan.needs_clarification is True
    assert plan.clarification_question
    assert plan.clarification_options


def test_rule_plan_asks_when_action_has_no_device():
    plan = rule_plan("帮我调一下", _STANDARD_DEVICES, _STANDARD_ROOMS)

    assert plan.needs_clarification is True
    assert plan.clarification_question
