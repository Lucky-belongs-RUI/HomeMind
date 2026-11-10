"""评测指标。

评测对象是多标签分类（一条输入可能同时激活多个意图 / 多条链路），
因此不能直接用单标签 accuracy，需要区分三类指标：

1. exact_match  —— 预测标签集合与标注完全一致的比例（最严格，衡量"整体对不对"）
2. micro P/R/F1 —— 跨样本汇总 TP/FP/FN 后计算（衡量"标签级整体质量"）
3. per-class    —— 每个标签单独的 P/R/F1（定位"哪一类总出错"）

参数抽取用字段级匹配：既要字段名对，也要值对；同时报告字段覆盖率，
避免"只抽对了一半字段却算全对"。
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LabelScore:
    """多标签分类得分。"""

    total: int = 0
    exact_match: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "exact_match": round(self.exact_match, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "per_class": {
                label: {k: round(v, 4) for k, v in stats.items()}
                for label, stats in self.per_class.items()
            },
        }


def score_multilabel(predictions: list[set[str]], golds: list[set[str]]) -> LabelScore:
    """计算多标签分类指标。

    predictions / golds 等长，元素为该样本的标签集合。
    """
    if len(predictions) != len(golds):
        raise ValueError("预测数与标注数不一致")

    total = len(golds)
    if total == 0:
        return LabelScore()

    exact = sum(1 for pred, gold in zip(predictions, golds, strict=False) if pred == gold)

    tp = fp = fn = 0
    labels = sorted(
        {label for gold in golds for label in gold}
        | {label for pred in predictions for label in pred}
    )
    per_class: dict[str, dict[str, float]] = {}
    for label in labels:
        c_tp = sum(
            1
            for pred, gold in zip(predictions, golds, strict=False)
            if label in pred and label in gold
        )
        c_fp = sum(
            1
            for pred, gold in zip(predictions, golds, strict=False)
            if label in pred and label not in gold
        )
        c_fn = sum(
            1
            for pred, gold in zip(predictions, golds, strict=False)
            if label not in pred and label in gold
        )
        tp += c_tp
        fp += c_fp
        fn += c_fn
        per_class[label] = {
            "precision": _safe_div(c_tp, c_tp + c_fp),
            "recall": _safe_div(c_tp, c_tp + c_fn),
            "f1": _safe_div(2 * c_tp, 2 * c_tp + c_fp + c_fn),
            "support": c_tp + c_fn,
        }

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return LabelScore(
        total=total,
        exact_match=exact / total,
        precision=precision,
        recall=recall,
        f1=_safe_div(2 * precision * recall, precision + recall),
        per_class=per_class,
    )


@dataclass
class FieldScore:
    """参数抽取得分（字段级）。"""

    total: int = 0
    field_accuracy: float = 0.0
    case_exact_match: float = 0.0
    mismatches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "field_accuracy": round(self.field_accuracy, 4),
            "case_exact_match": round(self.case_exact_match, 4),
            "mismatch_count": len(self.mismatches),
        }


def score_fields(predictions: list[dict[str, Any]], golds: list[dict[str, Any]]) -> FieldScore:
    """计算参数抽取的字段级准确率。

    对每个样本：比对期望字段的键与值是否全部命中；同时统计字段级命中率。
    只统计标注中出现的字段（不惩罚多抽出的字段，多抽由上层用例体现）。
    """
    if len(predictions) != len(golds):
        raise ValueError("预测数与标注数不一致")

    total = len(golds)
    if total == 0:
        return FieldScore()

    hit = miss = 0
    exact_cases = 0
    mismatches: list[dict[str, Any]] = []

    for index, (pred, gold) in enumerate(zip(predictions, golds, strict=False)):
        case_ok = True
        for key, expected in (gold or {}).items():
            actual = (pred or {}).get(key, _MISSING)
            if actual == expected:
                hit += 1
            else:
                miss += 1
                case_ok = False
        if case_ok and gold:
            exact_cases += 1
        elif not case_ok:
            mismatches.append({"index": index, "expected": gold, "actual": pred})

    return FieldScore(
        total=total,
        field_accuracy=_safe_div(hit, hit + miss),
        case_exact_match=_safe_div(exact_cases, total),
        mismatches=mismatches,
    )


@dataclass
class BooleanScore:
    """二分类得分（如"是否应该触发澄清"）。"""

    total: int = 0
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }


def score_boolean(predictions: Iterable[bool], golds: Iterable[bool]) -> BooleanScore:
    """计算二分类指标。以"应为 True"为正类。"""
    preds = list(predictions)
    truth = list(golds)
    if len(preds) != len(truth):
        raise ValueError("预测数与标注数不一致")

    total = len(truth)
    if total == 0:
        return BooleanScore()

    correct = tp = fp = fn = 0
    errors: list[dict[str, Any]] = []
    for index, (pred, gold) in enumerate(zip(preds, truth, strict=False)):
        if pred == gold:
            correct += 1
        else:
            errors.append({"index": index, "expected": gold, "actual": pred})
        if pred and gold:
            tp += 1
        elif pred and not gold:
            fp += 1
        elif not pred and gold:
            fn += 1

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return BooleanScore(
        total=total,
        accuracy=correct / total,
        precision=precision,
        recall=recall,
        false_positives=fp,
        false_negatives=fn,
        errors=errors,
    )


class _Missing:
    """占位符：区分"字段缺失"与"字段值为 None"。"""

    def __repr__(self) -> str:  # pragma: no cover - 仅用于调试输出
        return "<MISSING>"


_MISSING = _Missing()


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def format_percent(value: float) -> str:
    """把 0-1 的比率格式化为百分比字符串，便于终端展示。"""
    return f"{value * 100:5.1f}%"
