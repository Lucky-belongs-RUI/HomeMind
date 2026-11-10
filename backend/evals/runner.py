"""Agent 离线评测（Eval）。

**它回答的问题**：改了 prompt、换了模型、调了规则之后，效果到底是变好还是变坏？
没有评测，所有"优化"都只是感觉；有了评测，每次改动都有可对比的数字。

## 两种模式

| 模式 | 走哪条路径 | 依赖 | 用途 |
| --- | --- | --- | --- |
| `rule`（默认） | 规则引擎 | 无（不需要 Key / MySQL） | CI 门禁、回归验证、快速自检 |
| `llm` | 真实模型 + 生产 prompt | LLM API Key | 衡量 prompt 与模型的实际效果 |

`rule` 模式必须能离线跑通——这是评测体系能被持续使用的前提。
`llm` 模式只注入"标准家庭上下文 + 生产 prompt"，不查数据库，
因此它衡量的是 **prompt + 模型** 的能力，不含 DB 层差异。

## 用法（在 backend/ 目录执行）

    pip install -r requirements-dev.txt

    python -m evals.runner                                  # 规则模式跑全部
    python -m evals.runner --suite intent attribute          # 只跑指定套件
    python -m evals.runner --json evals/reports/baseline.json  # 存档基线
    python -m evals.runner --mode llm --suite intent         # 真实模型
    python -m evals.runner --baseline evals/reports/baseline.json  # 与基线对比

最后一条是本模块的核心用法：**改 prompt 前存档基线，改完再跑一次对比**。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from evals import metrics as M
from evals.household import STANDARD_DEVICES, STANDARD_ROOMS

DATASET_DIR = Path(__file__).parent / "datasets"

SUITE_NAMES = ("intent", "attribute", "clarification", "routing")
SUITE_LABELS = {
    "intent": "意图分类",
    "attribute": "参数抽取",
    "clarification": "澄清决策",
    "routing": "多链路路由",
}

# 套件名 -> 数据集文件名（不带扩展名）。
# 刻意分开：套件名要短（命令行好用），文件名要能自我说明（打开目录就懂）。
DATASET_FILES = {
    "intent": "intent_classification",
    "attribute": "attribute_extraction",
    "clarification": "clarification_decision",
    "routing": "chain_routing",
}


# ============================================================
# 数据集加载
# ============================================================


def load_dataset(name: str) -> list[dict[str, Any]]:
    """按套件名加载对应的 YAML 评测集。"""
    import yaml

    filename = DATASET_FILES.get(name, name)
    path = DATASET_DIR / f"{filename}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"评测集不存在: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


# ============================================================
# 预测器：rule 模式（与 v2 planner 的规则兜底等价）
# ============================================================


_CONTROL_TOOL_TYPES = {
    "set_device_state": "device_control",
    "trigger_scene": "scene_trigger",
    "get_device_state": "device_query",
    "list_room_devices": "device_query",
    "get_current_time": "device_query",
    "get_weather": "device_query",
}

_BRANCH_TYPES = {
    "knowledge": "knowledge_query",
    "report": "report",
    "chat": "chat",
}


def _control_types(text: str) -> list[str]:
    from homemind.agent.rules.devices import find_device_type
    from homemind.agent.rules.plan import control_tasks

    tasks, question, _ = control_tasks(
        text, list(STANDARD_DEVICES), list(STANDARD_ROOMS)
    )
    types: list[str] = []
    for task in tasks:
        intent_type = _CONTROL_TOOL_TYPES.get(task["tool"])
        if intent_type and intent_type not in types:
            types.append(intent_type)

    # 识别出设备但缺少房间时仍属于设备控制，只是需要先澄清
    if not types and question and find_device_type(text):
        return ["device_control"]
    return types


def _plan_payload(plan, text: str) -> dict[str, Any]:
    """把新规划契约转换成评测集使用的意图类型与链路集合。"""
    intents: list[dict[str, Any]] = []
    chains: list[str] = []
    seen_types: set[str] = set()

    for task in plan.tasks:
        branch = str(task.branch)
        if branch not in chains:
            chains.append(branch)
        types = _control_types(task.instruction or text) if branch == "control" else []
        for intent_type in types or [_BRANCH_TYPES.get(branch, "chat")]:
            if intent_type in seen_types:
                continue
            seen_types.add(intent_type)
            intents.append(
                {
                    "type": intent_type,
                    "description": task.instruction or intent_type,
                    "clarity": 1.0 if not plan.needs_clarification else 0.4,
                }
            )

    if plan.needs_clarification and not (seen_types & {"device_control", "scene_trigger"}):
        from homemind.agent.rules.devices import find_device_type

        if find_device_type(text):
            intents = [
                {
                    "type": "device_control",
                    "description": plan.clarification_question or "设备控制待澄清",
                    "clarity": 0.4,
                }
            ]
            seen_types = {"device_control"}
        else:
            intents = [
                {
                    "type": "clarification",
                    "description": plan.clarification_question or "需要澄清",
                    "clarity": 0.4,
                }
            ]
            seen_types = {"clarification"}

    question = plan.clarification_question
    if plan.needs_clarification and not question:
        question = "您的指令还不够明确，请补充一下。"
    return {
        "intents": intents,
        "intent_clarity_score": 0.4 if plan.needs_clarification else 1.0,
        "needs_clarification": plan.needs_clarification,
        "clarification_question": question,
        "active_chains": chains or ["chat"],
    }


def predict_intents_rule(text: str) -> dict[str, Any]:
    """用规则规划器预测任务分支。"""
    from homemind.agent.rules.plan import rule_plan
    from homemind.agent.runtime.schemas import Plan, PlanTask

    rule = rule_plan(text, list(STANDARD_DEVICES), list(STANDARD_ROOMS))
    plan = Plan(
        tasks=[PlanTask(**task) for task in rule.tasks],
        needs_clarification=rule.needs_clarification,
        clarification_question=rule.clarification_question,
        clarification_options=rule.clarification_options,
    )
    return _plan_payload(plan, text)


def predict_attributes_rule(text: str, device_type: str) -> dict[str, Any]:
    """用规则引擎抽取设备属性。"""
    from homemind.agent.rules.plan import _parse_attributes

    return _parse_attributes(text, device_type)


# ============================================================
# 预测器：llm 模式（真实模型 + 生产规划 prompt，不查库）
# ============================================================


async def predict_intents_llm(text: str) -> dict[str, Any]:
    """复用生产规划节点衡量真实模型的任务拆解效果。"""
    from homemind.agent.runtime.planner import plan_node
    from homemind.agent.runtime.schemas import Plan

    result = await plan_node(
        {
            "user_input": text,
            "request": {},
            "house_snapshot": {
                "devices": [
                    {"room": row["room_name"], "type": row["type"]}
                    for row in STANDARD_DEVICES
                ]
            },
        }
    )
    return _plan_payload(Plan(**result["plan"]), text)


# ============================================================
# 套件执行
# ============================================================


async def _predict_all(
    cases: list[dict[str, Any]], predict: Callable, concurrency: int = 4
) -> list[Any]:
    """批量预测；异步预测器按并发上限并行执行，同步预测器直接顺序执行。"""
    if not asyncio.iscoroutinefunction(predict):
        return [predict(case["input"]) for case in cases]

    semaphore = asyncio.Semaphore(concurrency)

    async def one(case: dict[str, Any]):
        async with semaphore:
            return await predict(case["input"])

    return list(await asyncio.gather(*(one(case) for case in cases)))


async def run_intent(cases, predict) -> dict[str, Any]:
    predictions = await _predict_all(cases, predict)
    pred_sets, gold_sets, failures = [], [], []
    for case, result in zip(cases, predictions, strict=False):
        actual = {item.get("type") for item in result["intents"] if item.get("type")}
        expected = set(case["expected_types"])
        pred_sets.append(actual)
        gold_sets.append(expected)
        if actual != expected:
            failures.append(
                {
                    "id": case["id"],
                    "input": case["input"],
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                }
            )
    score = M.score_multilabel(pred_sets, gold_sets)
    return {
        "suite": "intent",
        "total": len(cases),
        "metrics": score.as_dict(),
        "failures": failures,
    }


async def run_attribute(cases, predict=None) -> dict[str, Any]:
    predictions, golds, failures = [], [], []
    for case in cases:
        actual = predict_attributes_rule(case["input"], case["device_type"])
        expected = case["expected"] or {}
        predictions.append(actual)
        golds.append(expected)
        if any(actual.get(key) != value for key, value in expected.items()):
            failures.append(
                {
                    "id": case["id"],
                    "input": case["input"],
                    "device_type": case["device_type"],
                    "expected": expected,
                    "actual": actual,
                }
            )
    score = M.score_fields(predictions, golds)
    return {
        "suite": "attribute",
        "total": len(cases),
        "metrics": score.as_dict(),
        "failures": failures,
    }


async def run_clarification(cases, predict) -> dict[str, Any]:
    predictions = await _predict_all(cases, predict)
    pred_flags, gold_flags, failures = [], [], []
    for case, result in zip(cases, predictions, strict=False):
        actual = bool(result["needs_clarification"])
        expected = bool(case["expect_clarification"])
        pred_flags.append(actual)
        gold_flags.append(expected)
        if actual != expected:
            failures.append(
                {
                    "id": case["id"],
                    "input": case["input"],
                    "expected": expected,
                    "actual": actual,
                    "clarity": result.get("intent_clarity_score"),
                    "kind": "该追问却直接执行" if expected and not actual else "该执行却去追问",
                }
            )
    score = M.score_boolean(pred_flags, gold_flags)
    return {
        "suite": "clarification",
        "total": len(cases),
        "metrics": score.as_dict(),
        "failures": failures,
    }


async def run_routing(cases, predict) -> dict[str, Any]:
    predictions = await _predict_all(cases, predict)
    pred_sets, gold_sets, failures = [], [], []
    for case, result in zip(cases, predictions, strict=False):
        actual = set(result.get("active_chains") or [])
        expected = set(case["expected_chains"])
        pred_sets.append(actual)
        gold_sets.append(expected)
        if actual != expected:
            failures.append(
                {
                    "id": case["id"],
                    "input": case["input"],
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                }
            )
    score = M.score_multilabel(pred_sets, gold_sets)
    return {
        "suite": "routing",
        "total": len(cases),
        "metrics": score.as_dict(),
        "failures": failures,
    }


# ============================================================
# 报告输出
# ============================================================


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def print_report(results: list[dict[str, Any]], mode: str) -> None:
    """在终端打印可读报告。"""
    print("=" * 68)
    print(f"Agent 离线评测报告    模式: {mode}    时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 68)

    for result in results:
        name = result["suite"]
        label = SUITE_LABELS.get(name, name)
        metrics = result["metrics"]
        print(f"\n[{label}]  共 {result['total']} 例")

        if name == "attribute":
            print(
                f"  字段准确率 {_pct(metrics['field_accuracy'])}"
                f"    整例全中 {_pct(metrics['case_exact_match'])}"
            )
        elif name == "clarification":
            print(
                f"  准确率 {_pct(metrics['accuracy'])}"
                f"    精确率 {_pct(metrics['precision'])}"
                f"    召回率 {_pct(metrics['recall'])}"
            )
            print(
                f"  该执行却追问(FP) {metrics['false_positives']}"
                f"    该追问却执行(FN) {metrics['false_negatives']}"
            )
        else:
            print(
                f"  完全匹配 {_pct(metrics['exact_match'])}"
                f"    micro-P {_pct(metrics['precision'])}"
                f"    micro-R {_pct(metrics['recall'])}"
                f"    F1 {_pct(metrics['f1'])}"
            )

        per_class = metrics.get("per_class") or {}
        if per_class:
            weak = sorted(per_class.items(), key=lambda kv: kv[1]["f1"])[:4]
            print("  逐类（最弱四项）:")
            for cls, stats in weak:
                print(
                    f"    {cls:<18} P {_pct(stats['precision'])}"
                    f"  R {_pct(stats['recall'])}"
                    f"  F1 {_pct(stats['f1'])}"
                    f"  (n={int(stats['support'])})"
                )

        if result["failures"]:
            print(f"  失败用例 ({len(result['failures'])}):")
            for item in result["failures"][:8]:
                print(f"    {item['id']}  「{item['input']}」")
                print(f"        期望 {item['expected']}  实际 {item['actual']}")
            if len(result["failures"]) > 8:
                print(f"    ... 其余 {len(result['failures']) - 8} 条见 JSON 报告")
        else:
            print("  全部通过")

    print("\n" + "=" * 68)


def print_comparison(baseline: dict[str, Any], current: dict[str, Any]) -> None:
    """与基线对比，输出每个套件的指标变化。"""
    print("\n与基线对比（正数 = 变好）")
    print("-" * 68)
    base_suites = {item["suite"]: item["metrics"] for item in baseline.get("results", [])}
    for item in current.get("results", []):
        name = item["suite"]
        label = SUITE_LABELS.get(name, name)
        old = base_suites.get(name)
        if not old:
            print(f"  {label:<10} 基线中无此套件")
            continue
        key = _primary_metric(name)
        delta = item["metrics"][key] - old[key]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        print(
            f"  {label:<10} {key:<14} "
            f"{_pct(old[key])} → {_pct(item['metrics'][key])}  {arrow} {delta * 100:+.1f}pt"
        )
    print("-" * 68)


def _primary_metric(suite: str) -> str:
    if suite == "attribute":
        return "field_accuracy"
    if suite == "clarification":
        return "accuracy"
    return "f1"


# ============================================================
# 入口
# ============================================================


def _build_predictor(mode: str):
    if mode == "llm":
        return predict_intents_llm
    return predict_intents_rule


async def run_suites(suites: list[str], mode: str) -> list[dict[str, Any]]:
    predict = _build_predictor(mode)
    results = []
    for name in suites:
        cases = load_dataset(name)
        if name == "intent":
            results.append(await run_intent(cases, predict))
        elif name == "attribute":
            results.append(await run_attribute(cases))
        elif name == "clarification":
            results.append(await run_clarification(cases, predict))
        elif name == "routing":
            results.append(await run_routing(cases, predict))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent 离线评测")
    parser.add_argument(
        "--mode",
        choices=("rule", "llm"),
        default="rule",
        help="rule=规则引擎（离线、零成本）；llm=真实模型（需 API Key）",
    )
    parser.add_argument(
        "--suite",
        nargs="+",
        choices=SUITE_NAMES,
        default=list(SUITE_NAMES),
        help="要跑的套件，默认全部",
    )
    parser.add_argument("--json", dest="json_path", help="把本次报告写入指定 JSON 文件")
    parser.add_argument("--baseline", help="与指定的历史报告 JSON 对比")
    args = parser.parse_args(argv)

    try:
        results = asyncio.run(run_suites(args.suite, args.mode))
    except ImportError as exc:
        print(f"缺少依赖: {exc}\n请先执行 pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    report = {
        "mode": args.mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    print_report(results, args.mode)

    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {path}")

    if args.baseline:
        base_path = Path(args.baseline)
        if base_path.exists():
            baseline = json.loads(base_path.read_text(encoding="utf-8"))
            print_comparison(baseline, report)
        else:
            print(f"基线文件不存在，跳过对比: {base_path}", file=sys.stderr)

    # 退出码：全部用例通过返回 0，否则返回 1（便于接入 CI 门禁）
    has_failure = any(item["failures"] for item in results)
    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
