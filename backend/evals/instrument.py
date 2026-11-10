"""评测延迟统计。

v2 的模型调用统一走 LangChain ChatModel，不再有可方法级打补丁的
供应商客户端，因此这里只保留 e2e 与接口基准共用的延迟汇总工具。
"""

from __future__ import annotations


def latency_summary(values: list[float]) -> dict[str, float]:
    """返回 count / mean / p50 / p95 / max，单位毫秒。"""
    if not values:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean_ms": round(sum(ordered) / len(ordered), 1),
        "p50_ms": round(_percentile(ordered, 0.50), 1),
        "p95_ms": round(_percentile(ordered, 0.95), 1),
        "max_ms": round(ordered[-1], 1),
    }


def _percentile(ordered: list[float], ratio: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    # 线性插值，与 numpy.percentile 的默认行为一致
    position = (len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
