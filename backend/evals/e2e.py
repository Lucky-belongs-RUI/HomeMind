"""端到端 Agent 评测：真实 LangGraph v2 + 真实模型 + 真实 SQLite 业务库。

与 `evals.runner` 的区别：

| 维度 | runner（离线套件） | e2e（本文件） |
| --- | --- | --- |
| 评测对象 | 意图/参数/澄清/路由的单项能力 | 一轮对话的最终结果 |
| 模型 | 规则 / 路由模型直调 | 完整 v2 图：护栏 → Supervisor → 子图 → 汇总 → 回复 |
| 数据库 | 不查库 | 内存 SQLite（与生产同一套仓库/服务） |
| 指标 | F1 / 准确率 | 任务成功率、工具成功率、端到端 P50/P95 |

运行（backend/ 目录）::

    conda activate langGraph
    python -m evals.e2e
    python -m evals.e2e --json evals/reports/e2e.json
    python -m evals.e2e --case ambiguous_room
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from evals.instrument import latency_summary
from homemind.agent.runtime.graph import build_agent_graph
from homemind.models.device import Device
from homemind.models.family import Family
from homemind.models.room import Room
from homemind.models.scene import Scene
from homemind.models.user import User
from homemind.repositories import default_status, unit_of_work
from homemind.services.device_service import get_device_by_room_and_type
from homemind.services.room_service import get_room_by_name
from tests.db import memory_database

ROOMS = ("客厅", "卧室", "厨房", "书房")

# (room, type, name, status overrides)
DEVICES = (
    ("客厅", "light", "客厅主灯", None),
    ("卧室", "light", "卧室灯", None),
    ("客厅", "air_conditioner", "客厅空调", None),
    ("卧室", "air_conditioner", "卧室空调", None),
    ("客厅", "tv", "客厅电视", None),
    ("客厅", "weather_station", "气象站", {"weather": "晴", "temperature": 12.0}),
    ("客厅", "temp_humidity_sensor", "温湿度", None),
    ("厨房", "fridge", "冰箱", None),
    ("客厅", "door_lock", "门锁", None),
)


@dataclass
class CaseContext:
    """一次用例执行后可断言的全部信息。"""

    case: E2ECase
    family_id: int
    user_id: int
    state: dict[str, Any]
    interrupt_types: list[str]


Check = Callable[[CaseContext], Awaitable[None]]


@dataclass
class E2ECase:
    id: str
    category: str
    text: str
    check: Check
    role: str = "owner"
    clarification_answer: str = "客厅"
    cancel_clarification: bool = False
    approve: bool = True


# ============================================================
# 家庭数据
# ============================================================


def _build_household():
    async def seed() -> dict[str, Any]:
        async with unit_of_work() as uow:
            family = await uow.families.add(Family(name="评测家庭", owner_user_id=0))
            owner = await uow.users.add(
                User(
                    username=f"eval_{uuid.uuid4().hex[:8]}",
                    password="eval-only",
                    nickname="评测用户",
                    role="owner",
                    family_id=family.id,
                )
            )
            family.owner_user_id = owner.id

            room_ids: dict[str, int] = {}
            for index, name in enumerate(ROOMS, 1):
                room = await uow.rooms.add(
                    Room(family_id=family.id, name=name, icon="home", sort_order=index)
                )
                room_ids[name] = room.id

            device_ids: dict[tuple[str, str], int] = {}
            for room_name, device_type, name, overrides in DEVICES:
                status = default_status(device_type)
                if overrides:
                    status.update(overrides)
                device = await uow.devices.add(
                    Device(
                        family_id=family.id,
                        name=name,
                        type=device_type,
                        room_id=room_ids[room_name],
                        status=status,
                    )
                )
                device_ids[(room_name, device_type)] = device.id

            await uow.scenes.add(
                Scene(
                    family_id=family.id,
                    name="回家模式",
                    description="打开客厅灯",
                    actions={
                        "actions": [
                            {
                                "room_name": "客厅",
                                "device_type": "light",
                                "attributes": {"power": "on"},
                            }
                        ]
                    },
                )
            )
            await uow.commit()
            return {
                "family_id": family.id,
                "user_id": owner.id,
                "room_ids": room_ids,
                "device_ids": device_ids,
            }

    return seed


async def _device_status(family_id: int, room_name: str, device_type: str) -> dict[str, Any] | None:
    room = await get_room_by_name(room_name, family_id)
    if not room:
        return None
    device = await get_device_by_room_and_type(room.id, device_type, family_id)
    return dict(device.status or {}) if device else None


# ============================================================
# 图执行
# ============================================================


def _thread_id(family_id: int, user_id: int, session_id: str) -> str:
    return f"v2:{family_id}:{user_id}:{session_id}"


def _initial_state(
    text: str,
    *,
    family_id: int,
    user_id: int,
    role: str,
    session_id: str,
    thread_id: str,
) -> dict[str, Any]:
    return {
        "request": {
            "user_id": user_id,
            "family_id": family_id,
            "role": role,
            "session_id": session_id,
            "thread_id": thread_id,
            "trace_id": uuid.uuid4().hex,
        },
        "user_input": text,
        "messages": [HumanMessage(content=text)],
        "results": [],
        "tool_events": [],
        "token_usage": {},
        "avatar_emotion": "idle",
        "clarification_attempts": 0,
        "blocked": False,
        "degraded": False,
    }


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    raw = result.get("__interrupt__") or []
    if not raw:
        return None
    first = raw[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"type": "unknown", "value": value}


def _resume_payload(payload: dict[str, Any], case: E2ECase) -> dict[str, Any]:
    if payload.get("type") == "approval":
        tasks = payload.get("tasks") or []
        if not case.approve:
            return {"approved": False, "task_ids": []}
        return {"approved": True, "task_ids": [task.get("task_id") for task in tasks]}
    if case.cancel_clarification:
        return {"cancelled": True}
    return {"answer": case.clarification_answer}


async def _run_case(case: E2ECase, seed: dict[str, Any]) -> dict[str, Any]:
    family_id = seed["family_id"]
    user_id = seed["user_id"]
    session_id = f"e2e_{case.id}_{uuid.uuid4().hex[:8]}"
    thread_id = _thread_id(family_id, user_id, session_id)
    graph = build_agent_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(
        case.text,
        family_id=family_id,
        user_id=user_id,
        role=case.role,
        session_id=session_id,
        thread_id=thread_id,
    )

    started = time.perf_counter()
    interrupt_types: list[str] = []
    graph_input: Any = state
    result: dict[str, Any] = {}
    error = ""

    try:
        # 一次请求最多处理 3 次中断：澄清 → 审批 → （可能的二次澄清）
        for _ in range(3):
            result = await graph.ainvoke(graph_input, config=config)
            payload = _interrupt_payload(result)
            if payload is None:
                break
            interrupt_types.append(str(payload.get("type") or "unknown"))
            graph_input = Command(resume=_resume_payload(payload, case))
    except Exception as exc:  # 评测需要记录异常而不是中断整批
        error = f"{type(exc).__name__}: {exc}"

    elapsed_ms = (time.perf_counter() - started) * 1000
    context = CaseContext(
        case=case,
        family_id=family_id,
        user_id=user_id,
        state=result,
        interrupt_types=interrupt_types,
    )

    passed = False
    failure = error
    if not error:
        try:
            await case.check(context)
            passed = True
        except AssertionError as exc:
            failure = str(exc)

    return {
        "id": case.id,
        "category": case.category,
        "text": case.text,
        "passed": passed,
        "failure": failure,
        "latency_ms": round(elapsed_ms, 1),
        "interrupts": interrupt_types,
        "response": str(result.get("final_answer") or "")[:500],
        "tool_events": [
            {
                "tool": item.get("tool"),
                "task_id": item.get("task_id"),
                "success": item.get("success"),
            }
            for item in result.get("tool_events") or []
        ],
    }


# ============================================================
# 用例
# ============================================================


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _response(ctx: CaseContext) -> str:
    return str(ctx.state.get("final_answer") or "")


def _branch_results(ctx: CaseContext, branch: str) -> list[dict[str, Any]]:
    return [
        item for item in ctx.state.get("results") or [] if item.get("branch") == branch
    ]


def _control_observations(ctx: CaseContext) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in _branch_results(ctx, "control"):
        observations.extend((item.get("data") or {}).get("observations") or [])
    return observations


async def check_light_on(ctx: CaseContext) -> None:
    status = await _device_status(ctx.family_id, "客厅", "light")
    _require(status and status.get("power") == "on", f"客厅灯未打开: {status}")


async def check_ac_temperature(ctx: CaseContext) -> None:
    status = await _device_status(ctx.family_id, "卧室", "air_conditioner")
    _require(status is not None, "卧室空调不存在")
    _require(status.get("power") == "on", f"空调未开启: {status}")
    _require(status.get("temperature") == 26, f"温度未设为 26: {status}")


async def check_query_light(ctx: CaseContext) -> None:
    status = await _device_status(ctx.family_id, "客厅", "light")
    _require(status and status.get("power") == "off", "查询不应改变设备状态")
    _require(_response(ctx).strip(), "查询没有返回回复")
    _require(
        any(item.get("success") for item in _control_observations(ctx)),
        "状态查询工具未成功返回",
    )


async def check_time_query(ctx: CaseContext) -> None:
    response = _response(ctx)
    _require(response.strip(), "时间查询没有返回回复")
    _require(
        any(
            (item.get("result") or {}).get("datetime")
            for item in _control_observations(ctx)
        ),
        f"未调用时间工具: {_control_observations(ctx)}",
    )
    _require(any(marker in response for marker in (":", "点", "星期")), f"回复缺少时间: {response}")


async def check_weather_query(ctx: CaseContext) -> None:
    response = _response(ctx)
    _require(response.strip(), "天气查询没有返回回复")
    _require(
        any(marker in response for marker in ("晴", "12", "天气")), f"回复缺少天气信息: {response}"
    )


async def check_missing_device(ctx: CaseContext) -> None:
    results = _branch_results(ctx, "control")
    _require(
        any(item.get("success") is False for item in results),
        f"不存在的设备应返回失败: {results}",
    )
    response = _response(ctx)
    _require(
        any(
            marker in response
            for marker in ("没有", "未找到", "不支持", "无法", "尚未", "未配置")
        ),
        f"回复未说明设备不存在: {response}",
    )


async def check_ambiguous_room(ctx: CaseContext) -> None:
    _require("clarification" in ctx.interrupt_types, f"未触发澄清: {ctx.interrupt_types}")
    living = await _device_status(ctx.family_id, "客厅", "air_conditioner")
    bedroom = await _device_status(ctx.family_id, "卧室", "air_conditioner")
    _require(living and living.get("power") == "on", f"澄清后客厅空调未开启: {living}")
    _require(not bedroom or bedroom.get("power") == "off", f"不应操作卧室空调: {bedroom}")


async def check_cancel_clarification(ctx: CaseContext) -> None:
    _require("clarification" in ctx.interrupt_types, "未触发澄清中断")
    _require(_response(ctx).strip(), "取消澄清后应有自然语言回复（不能崩溃）")


async def check_approval_rejected(ctx: CaseContext) -> None:
    _require("approval" in ctx.interrupt_types, f"未触发审批: {ctx.interrupt_types}")
    status = await _device_status(ctx.family_id, "客厅", "door_lock")
    _require(status and status.get("locked") is not False, f"拒绝审批后门锁应保持锁定: {status}")
    _require(_response(ctx).strip(), "拒绝审批后没有回复")


async def check_guest_denied(ctx: CaseContext) -> None:
    status = await _device_status(ctx.family_id, "客厅", "light")
    _require(status and status.get("power") == "off", f"访客不应能控制设备: {status}")
    results = _branch_results(ctx, "control")
    _require(
        any(item.get("success") is False for item in results),
        f"访客操作应产生失败结果: {results}",
    )
    response = _response(ctx)
    _require(
        any(marker in response for marker in ("权限", "无法", "不能", "失败")),
        f"回复未说明权限不足: {response}",
    )


async def check_chat(ctx: CaseContext) -> None:
    _require(_response(ctx).strip(), "闲聊没有返回回复")
    _require(not _branch_results(ctx, "control"), "闲聊不应产生设备操作")


async def check_scene(ctx: CaseContext) -> None:
    status = await _device_status(ctx.family_id, "客厅", "light")
    _require(status and status.get("power") == "on", f"场景未打开客厅灯: {status}")
    _require(
        any(item.get("success") for item in _branch_results(ctx, "control")),
        "场景工具未成功执行",
    )


async def check_report(ctx: CaseContext) -> None:
    response = _response(ctx)
    _require(len(response) >= 40, f"报告过短: {response}")
    _require(
        any(marker in response for marker in ("报告", "设备", "温度", "房间")),
        f"报告内容异常: {response}",
    )


CASES = [
    E2ECase("light_on_basic", "设备控制", "打开客厅的灯", check_light_on),
    E2ECase("ac_temperature", "设备控制", "把卧室空调调到26度", check_ac_temperature),
    E2ECase("query_light", "设备查询", "客厅的灯现在是什么状态", check_query_light),
    E2ECase("time_query", "实时查询", "现在几点了", check_time_query),
    E2ECase("weather_query", "实时查询", "今天室外天气怎么样", check_weather_query),
    E2ECase("missing_device", "异常处理", "打开厨房的灯", check_missing_device),
    E2ECase(
        "ambiguous_room",
        "澄清",
        "打开空调",
        check_ambiguous_room,
        clarification_answer="客厅",
    ),
    E2ECase(
        "cancel_clarification",
        "澄清",
        "打开空调",
        check_cancel_clarification,
        cancel_clarification=True,
    ),
    E2ECase(
        "approval_rejected",
        "审批",
        "打开客厅的门锁",
        check_approval_rejected,
        approve=False,
    ),
    E2ECase("guest_denied", "权限", "打开客厅的灯", check_guest_denied, role="visitor"),
    E2ECase("chat", "闲聊", "我今天工作有点累，陪我聊两句", check_chat),
    E2ECase("scene_trigger", "场景", "执行回家模式", check_scene),
    E2ECase("report", "报告", "帮我生成一份家庭情况报告", check_report),
]


# ============================================================
# 汇总与报告
# ============================================================


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    categories: dict[str, dict[str, Any]] = {}
    for item in results:
        bucket = categories.setdefault(item["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if item["passed"] else 0
    for bucket in categories.values():
        bucket["pass_rate"] = round(bucket["passed"] / bucket["total"], 4)

    tool_success = sum(
        1 for item in results for event in item["tool_events"] if event["success"]
    )
    tool_failure = sum(
        1 for item in results for event in item["tool_events"] if not event["success"]
    )
    produced = tool_success + tool_failure

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_category": categories,
        "latency": latency_summary([item["latency_ms"] for item in results]),
        "tool_calls": {
            "success": tool_success,
            "failed": tool_failure,
            "success_rate": round(tool_success / produced, 4) if produced else 0.0,
        },
        "interrupts": {
            "clarification": sum(
                1 for item in results if "clarification" in item["interrupts"]
            ),
            "approval": sum(1 for item in results if "approval" in item["interrupts"]),
        },
    }


def _print_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print("=" * 74)
    print(f"Agent v2 端到端评测    时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 74)
    print(
        f"\n总用例 {summary['total']}    通过 {summary['passed']}"
        f"    成功率 {summary['pass_rate'] * 100:.1f}%"
    )
    latency = summary["latency"]
    print(
        f"端到端耗时  P50 {latency['p50_ms']:.0f}ms"
        f"    P95 {latency['p95_ms']:.0f}ms"
        f"    均值 {latency['mean_ms']:.0f}ms"
    )
    tools = summary["tool_calls"]
    print(
        f"工具调用   成功 {tools['success']} / 失败 {tools['failed']}"
        f"    成功率 {tools['success_rate'] * 100:.1f}%"
    )

    print("\n分类结果")
    print("-" * 74)
    for category, bucket in summary["by_category"].items():
        print(
            f"  {category:<8} {bucket['passed']}/{bucket['total']}"
            f"    {bucket['pass_rate'] * 100:5.1f}%"
        )

    failures = [item for item in results if not item["passed"]]
    if failures:
        print("\n失败用例")
        print("-" * 74)
        for item in failures:
            print(f"  [{item['id']}] {item['text']}")
            print(f"      原因: {item['failure']}")
            if item["response"]:
                print(f"      回复: {item['response'][:160]}")
    print("\n" + "=" * 74)


async def run_cases(cases: list[E2ECase]) -> list[dict[str, Any]]:
    seed = _build_household()
    results: list[dict[str, Any]] = []
    for case in cases:
        async with memory_database():
            ids = await seed()
            result = await _run_case(case, ids)
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"[{mark}] {case.id:<22} {result['latency_ms']:>7.0f}ms  {case.text}")
        if not result["passed"]:
            print(f"       {result['failure']}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent v2 端到端评测")
    parser.add_argument("--case", nargs="+", help="只跑指定用例 id")
    parser.add_argument("--json", dest="json_path", help="把报告写入 JSON 文件")
    args = parser.parse_args(argv)

    cases = CASES
    if args.case:
        wanted = set(args.case)
        cases = [case for case in CASES if case.id in wanted]
        if not cases:
            print(f"未找到用例: {', '.join(sorted(wanted))}", file=sys.stderr)
            return 2

    results = asyncio.run(run_cases(cases))
    summary = _aggregate(results)
    _print_report(results, summary)

    report = {
        "mode": "v2+llm+sqlite",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "cases": results,
    }
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {path}")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
