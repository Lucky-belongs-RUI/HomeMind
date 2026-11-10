"""回复证据门槛测试：没有成功写操作时不得声称已完成设备动作。"""

from homemind.agent.runtime.evidence import (
    NO_ACTION_FALLBACK,
    can_stream,
    control_failures,
    executed_writes,
    has_successful_write,
    strip_unbacked_claims,
)


def _control_result(*observations: dict) -> dict:
    return {"branch": "control", "success": True, "data": {"observations": list(observations)}}


def _observation(
    tool: str,
    success: bool = True,
    arguments: dict | None = None,
    result: dict | None = None,
) -> dict:
    return {
        "tool": tool,
        "success": success,
        "arguments": arguments or {},
        "result": result or {"message": "执行成功"},
    }


def _write(device_type: str, attributes: dict, room_name: str = "卧室") -> dict:
    return _observation(
        "set_device_state",
        arguments={
            "room_name": room_name,
            "device_type": device_type,
            "attributes": attributes,
        },
        result={"message": f"已将{room_name}设备更新"},
    )


def test_executed_writes_only_counts_successful_write_tools():
    results = [
        _control_result(
            _observation("set_device_state"),
            _observation("get_device_state"),
            _observation("trigger_scene", success=False),
        )
    ]

    writes = executed_writes(results)

    assert [write["tool"] for write in writes] == ["set_device_state"]
    assert has_successful_write(results) is True


def test_read_only_success_is_not_a_write():
    results = [_control_result(_observation("get_device_state"))]

    assert has_successful_write(results) is False


def test_unbacked_claims_are_removed_when_nothing_was_executed():
    answer = "已为您把卧室空调调到27度。净化器已启动最大档。需要我帮您倒杯水吗？"

    cleaned = strip_unbacked_claims(answer, [])

    assert "调到27度" not in cleaned
    assert "已启动" not in cleaned
    assert "需要我帮您倒杯水吗？" in cleaned


def test_all_claims_are_replaced_with_explicit_no_action_notice():
    assert strip_unbacked_claims("已经打开客厅灯。", []) == NO_ACTION_FALLBACK


def test_suggestion_sentences_are_kept():
    answer = "是否需要我帮您打开客厅灯？"

    assert strip_unbacked_claims(answer, []) == answer


def test_claims_are_kept_when_matching_write_succeeded():
    answer = "已为您打开客厅灯。"

    cleaned = strip_unbacked_claims(
        answer,
        [_control_result(_write("light", {"power": "on"}, "客厅"))],
    )

    assert cleaned == answer


def test_claim_for_device_without_write_is_removed_even_if_other_write_succeeded():
    """灯成功不能给“空调已调好”背书。"""
    answer = "已为您把卧室灯调暗到30%。已为您把卧室空调设置为23度。故事已经准备好了。"

    cleaned = strip_unbacked_claims(
        answer,
        [_control_result(_write("light", {"brightness": 30}))],
    )

    assert "灯调暗" in cleaned
    assert "空调" not in cleaned
    assert "故事" in cleaned


def test_mixed_sentence_keeps_only_backed_clause():
    answer = "已为您把卧室灯调暗到30%，已将空调设置为23度。"

    cleaned = strip_unbacked_claims(
        answer,
        [_control_result(_write("light", {"brightness": 30}))],
    )

    assert "灯调暗" in cleaned
    assert "空调" not in cleaned


def test_temperature_claim_requires_actual_temperature_write():
    """只写了睡眠模式、没写温度时，不能声称温度已设置。"""
    answer = "已为您把卧室空调设置为23度。"

    cleaned = strip_unbacked_claims(
        answer,
        [_control_result(_write("air_conditioner", {"mode": "sleep"}))],
    )

    assert "23" not in cleaned


def test_temperature_claim_requires_matching_value():
    answer = "已为您把卧室空调设置为23度。"

    cleaned = strip_unbacked_claims(
        answer,
        [_control_result(_write("air_conditioner", {"temperature": 26}))],
    )

    assert "23" not in cleaned


def test_partial_failure_disables_streaming_and_is_reported():
    results = [
        {
            "branch": "control",
            "success": False,
            "degraded": True,
            "summary": "设备操作未完成：空调离线",
            "data": {
                "observations": [
                    _write("light", {"brightness": 30}),
                    _observation(
                        "set_device_state",
                        success=False,
                        result={"error": "空调离线"},
                    ),
                ]
            },
        }
    ]

    assert can_stream(results) is False
    assert "空调离线" in control_failures(results)


def test_scene_partial_failure_counts_as_failure():
    results = [
        _control_result(
            _observation(
                "trigger_scene",
                arguments={"scene_name": "睡眠模式"},
                result={"message": "部分动作执行失败（成功 1/2）", "failed_count": 1},
            )
        )
    ]

    assert can_stream(results) is False
    assert control_failures(results)


def test_empty_answer_stays_empty():
    assert strip_unbacked_claims("", []) == ""
