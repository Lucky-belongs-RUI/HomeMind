# -*- coding: utf-8 -*-
"""Generate publication-ready vector figures for the landing design.

Run:
    python docs/figures/make_figures.py

Outputs (same directory):
    fig1_landing_logic.svg / .pdf / .png
    fig2_online_inference.svg / .pdf / .png
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "figure.dpi": 300,
    }
)

INK = "#1F2933"
MUTED = "#52606D"
ACCENT = "#2F5D8A"
ACCENT_LIGHT = "#E8EEF5"
BAND = "#F3F5F7"
BORDER = "#7B8794"
DASH = "#6B7785"
WHITE = "#FFFFFF"

HERE = os.path.dirname(os.path.abspath(__file__))


def rounded_box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    lines: list[str],
    *,
    title_size: float = 8.2,
    line_size: float = 6.8,
    fc: str = WHITE,
    ec: str = INK,
    lw: float = 0.8,
    line_step: float = 2.45,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0,rounding_size=0.8",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(
        x + 1.1,
        y + h - 1.0,
        title,
        fontsize=title_size,
        fontweight="bold",
        va="top",
        ha="left",
        color=INK,
        zorder=6,
    )
    yy = y + h - 3.7
    for line in lines:
        ax.text(
            x + 1.2,
            yy,
            line,
            fontsize=line_size,
            va="top",
            ha="left",
            color=INK,
            zorder=6,
        )
        yy -= line_step


def diamond(
    ax,
    cx: float,
    cy: float,
    w: float,
    h: float,
    text: str,
    *,
    fontsize: float = 7.0,
    fc: str = WHITE,
) -> None:
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(
        Polygon(pts, closed=True, facecolor=fc, edgecolor=INK, linewidth=0.8, zorder=3)
    )
    ax.text(cx, cy, text, fontsize=fontsize, ha="center", va="center", color=INK, zorder=6)


def arrow_head(ax, p0: tuple[float, float], p1: tuple[float, float], color: str, size: float = 0.85) -> None:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base = (p1[0] - ux * size, p1[1] - uy * size)
    left = (base[0] + px * size * 0.45, base[1] + py * size * 0.45)
    right = (base[0] - px * size * 0.45, base[1] - py * size * 0.45)
    ax.add_patch(
        Polygon([p1, left, right], closed=True, facecolor=color, edgecolor=color, linewidth=0, zorder=5)
    )


def poly_arrow(
    ax,
    points: list[tuple[float, float]],
    *,
    color: str = ACCENT,
    lw: float = 1.0,
    ls: str = "-",
    head: bool = True,
) -> None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(
        xs,
        ys,
        color=color,
        linewidth=lw,
        linestyle=ls,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=2,
    )
    if head:
        arrow_head(ax, points[-2], points[-1], color)


def label(ax, x: float, y: float, text: str, *, size: float = 6.4, color: str = MUTED, **kw) -> None:
    ax.text(x, y, text, fontsize=size, color=color, zorder=7, **kw)


def save(fig, name: str) -> None:
    for ext in ("svg", "pdf", "png"):
        path = os.path.join(HERE, f"{name}.{ext}")
        fig.savefig(path, bbox_inches="tight", pad_inches=0.03, facecolor="white")
        print("wrote", path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 1: overall landing route
# ---------------------------------------------------------------------------


def figure1() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 4.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis("off")
    fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004)

    # Stage bands
    ax.add_patch(Rectangle((1, 35), 98, 26, facecolor=BAND, edgecolor="none", zorder=0))
    ax.add_patch(Rectangle((1, 6), 98, 26, facecolor=BAND, edgecolor="none", zorder=0))
    ax.text(1.9, 48, "离线构建", rotation=90, fontsize=7.2, color=MUTED, ha="center", va="center")
    ax.text(1.9, 19, "在线与评估", rotation=90, fontsize=7.2, color=MUTED, ha="center", va="center")

    # Boxes
    rounded_box(
        ax,
        4,
        38,
        28,
        19,
        "① 领域知识构建",
        [
            "MySQL → HomeKG 三元组",
            "实体：Room / Device / Scene / Doc",
            "关系：located_in / instance_of / controls",
            "别名表 + 家庭级索引",
            "版本化快照 snapshot_id",
        ],
    )
    rounded_box(
        ax,
        36,
        38,
        28,
        19,
        "② 领域数据构造",
        [
            "四类模板：控制 / 查询 / 知识 / 报告",
            "Qwen 改写 + TAGA 增强",
            "难负样本：同型异房 / 同房异设备",
            "按家庭切分：seen / unseen / adv",
            "规模：2–5 万 mention 对",
        ],
    )
    rounded_box(
        ax,
        68,
        38,
        29,
        19,
        "③ 小模型训练与压缩",
        [
            "KG_O → 关系条件实体排序器",
            "GAGR → HomeKG 多跳推理器",
            "损失：InfoNCE / margin / 三段损失",
            "置信度校准：temperature / ECE",
            "ONNX INT8 + 一致性 / 延迟测试",
        ],
    )
    rounded_box(
        ax,
        51,
        9,
        40,
        20,
        "④ LangGraph 在线集成",
        [
            "意图识别 → 实体解析（/v1/resolve）",
            "resolved → 规划 → 审批 → 执行",
            "ambiguous → 澄清 → 重新识别",
            "知识 / 报告 → 文档 RAG + KG 多跳检索",
            "证据融合 → Qwen 生成",
            "80 / 120 ms 超时；熔断；规则回退",
        ],
        line_size=6.55,
        line_step=2.4,
    )
    rounded_box(
        ax,
        9,
        9,
        32,
        20,
        "⑤ 灰度评估与反馈",
        [
            "shadow：只记录，不影响结果",
            "assist：只影响澄清与证据",
            "active：高置信进入控制链路",
            "指标：Hit@1 / MRR / 澄清召回 / Path Hit@5",
            "LangSmith：延迟 / 降级 / 失败样本",
            "失败样本回流 → 重训",
        ],
        line_size=6.45,
        line_step=2.4,
    )

    # Main flow
    poly_arrow(ax, [(32, 47.5), (36, 47.5)])
    poly_arrow(ax, [(64, 47.5), (68, 47.5)])
    poly_arrow(ax, [(82.5, 38), (82.5, 29)])
    poly_arrow(ax, [(51, 19), (41, 19)])

    # Feedback loops
    poly_arrow(ax, [(25, 29), (25, 34.1), (18, 34.1), (18, 38)], ls=(0, (3, 2)), color=DASH, lw=0.9)
    poly_arrow(ax, [(37, 29), (37, 32.4), (49, 32.4), (49, 38)], ls=(0, (3, 2)), color=DASH, lw=0.9)

    # Arrow labels
    label(ax, 84.2, 33.5, "模型产物", rotation=90, ha="center", va="center", size=6.1)
    label(ax, 45.6, 20.3, "线上日志", ha="center", va="bottom", size=6.1)
    label(ax, 26.0, 34.7, "失败样本回流", ha="left", va="center", size=6.1)
    label(ax, 37.8, 31.6, "数据回灌", ha="left", va="center", size=6.1)

    # Legend
    ax.plot([70, 74], [59.4, 59.4], color=ACCENT, lw=1.2, solid_capstyle="round")
    ax.text(74.7, 59.4, "主流程", fontsize=6.3, color=MUTED, va="center")
    ax.plot([82, 86], [59.4, 59.4], color=DASH, lw=0.9, linestyle=(0, (3, 2)))
    ax.text(86.7, 59.4, "反馈 / 重训", fontsize=6.3, color=MUTED, va="center")

    # Constraint strip
    ax.add_patch(
        FancyBboxPatch(
            (1, 0.7),
            98,
            3.5,
            boxstyle="round,pad=0,rounding_size=0.4",
            facecolor=WHITE,
            edgecolor="#C7CDD6",
            linewidth=0.6,
            zorder=1,
        )
    )
    ax.text(
        2.2,
        2.45,
        "约束：family_id 隔离 · 模型不写库 · 80/120 ms 超时回退 · KG_MODE=off 可一键关闭",
        fontsize=6.4,
        color=MUTED,
        va="center",
    )

    save(fig, "fig1_landing_logic")


# ---------------------------------------------------------------------------
# Figure 2: online inference / decision flow
# ---------------------------------------------------------------------------


def figure2() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 5.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 80)
    ax.axis("off")
    fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004)

    # Central spine
    rounded_box(ax, 42, 70, 16, 5.2, "用户输入", [], title_size=7.6)
    rounded_box(
        ax,
        40,
        60,
        20,
        7,
        "意图识别",
        ["LLM 结构化输出 + 规则兜底"],
        title_size=7.4,
        line_size=6.0,
    )
    poly_arrow(ax, [(50, 70), (50, 67)])

    diamond(ax, 50, 51, 12, 8, "纯闲聊?")
    poly_arrow(ax, [(50, 60), (50, 55)])

    # Chat lane (upper right, clear of the knowledge lane)
    rounded_box(ax, 68, 56, 16, 7, "聊天链路", ["轻量对话 / 情感陪伴"], title_size=7.2, line_size=6.0)
    rounded_box(ax, 86, 56, 12, 7, "Qwen 回复", [], title_size=7.0)
    poly_arrow(ax, [(56, 51), (68, 59.5)])
    poly_arrow(ax, [(84, 59.5), (86, 59.5)])
    label(ax, 57.4, 53.1, "是", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    diamond(ax, 50, 41, 12, 8, "控制/查询?")
    poly_arrow(ax, [(50, 47), (50, 45)])
    label(ax, 51.2, 46.0, "否", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    # Control lane (left)
    rounded_box(
        ax,
        40,
        26,
        20,
        10,
        "实体解析",
        ["kg-service /v1/resolve", "top-k 候选 + margin", "低置信走澄清"],
        title_size=7.2,
        line_size=5.9,
    )
    poly_arrow(ax, [(50, 37), (50, 36)])
    label(ax, 51.2, 36.6, "是", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    diamond(ax, 50, 20, 10, 8, "resolved?")
    poly_arrow(ax, [(50, 26), (50, 24)])

    rounded_box(
        ax,
        24,
        14,
        18,
        8,
        "任务规划 / 审批",
        ["使用 entity_id", "避免二次猜测"],
        title_size=7.0,
        line_size=5.9,
    )
    rounded_box(
        ax,
        24,
        4,
        18,
        8,
        "工具执行",
        ["结果写入 state", "失败可回退"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(45, 20), (42, 20)])
    poly_arrow(ax, [(33, 14), (33, 12)])
    label(ax, 43.6, 21.2, "是", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    rounded_box(
        ax,
        44,
        7,
        18,
        8,
        "澄清",
        ["top-k 候选作选项", "补充后重新识别"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(50, 16), (53, 15)])
    label(ax, 51.6, 15.7, "否", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    # Clarification loop: down, left, up, back into intent
    poly_arrow(
        ax,
        [(53, 7), (53, 0.8), (8, 0.8), (8, 64), (40, 64)],
        ls=(0, (3, 2)),
        color=DASH,
        lw=0.9,
    )
    label(ax, 9.4, 35, "重新识别", rotation=90, ha="center", va="center", size=6.1)

    # Knowledge lane (right)
    rounded_box(
        ax,
        68,
        41,
        20,
        8,
        "文档 RAG + KG 多跳检索",
        ["/v1/ask；chunk + 子图", "2 跳以上答案实体"],
        title_size=6.9,
        line_size=5.8,
    )
    poly_arrow(ax, [(56, 41), (68, 41)])
    label(ax, 58.5, 42.4, "否", size=6.4, color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=WHITE, ec="none"))

    rounded_box(
        ax,
        68,
        31,
        20,
        8,
        "答案 / 证据重排",
        ["GAGR / PCRL 打分", "Answer Hit@1 / Path Recall@k"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(78, 41), (78, 39)])

    rounded_box(
        ax,
        68,
        21,
        20,
        8,
        "证据融合",
        ["文档片段 + 图谱证据", "无证据不强行回答"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(78, 31), (78, 29)])

    rounded_box(
        ax,
        68,
        11,
        20,
        8,
        "Qwen 生成",
        ["带引用的回答", "路径作可解释证据"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(78, 21), (78, 19)])

    rounded_box(
        ax,
        68,
        1,
        20,
        8,
        "回复用户",
        ["answer + sources", "失败则明确拒答"],
        title_size=7.0,
        line_size=5.9,
    )
    poly_arrow(ax, [(78, 11), (78, 9)])

    # Legend
    ax.plot([2, 6], [74.6, 74.6], color=ACCENT, lw=1.2, solid_capstyle="round")
    ax.text(6.7, 74.6, "主流程", fontsize=6.2, color=MUTED, va="center")
    ax.plot([14, 18], [74.6, 74.6], color=DASH, lw=0.9, linestyle=(0, (3, 2)))
    ax.text(18.7, 74.6, "澄清回路", fontsize=6.2, color=MUTED, va="center")

    # Constraint note (top-right, clear of all lanes)
    ax.add_patch(
        FancyBboxPatch(
            (70, 66),
            28,
            12,
            boxstyle="round,pad=0,rounding_size=0.5",
            facecolor=WHITE,
            edgecolor="#C7CDD6",
            linewidth=0.6,
            zorder=1,
        )
    )
    ax.text(71.2, 75.6, "运行约束", fontsize=6.8, fontweight="bold", color=INK, va="center")
    ax.text(71.2, 73.0, "family_id 强制隔离", fontsize=5.9, color=MUTED, va="center")
    ax.text(71.2, 70.4, "80/120 ms 超时 → 规则回退", fontsize=5.9, color=MUTED, va="center")
    ax.text(71.2, 67.8, "模型不写库 · KG_MODE=off 可关闭", fontsize=5.9, color=MUTED, va="center")

    save(fig, "fig2_online_inference")


# ---------------------------------------------------------------------------
# Figure 3: research-to-system mapping (corrected)
# ---------------------------------------------------------------------------


def figure3() -> None:
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis("off")
    fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004)

    ax.text(
        50,
        62.6,
        "两个科研模型 → 系统角色 → LangGraph 落点（修正版）",
        fontsize=9.0,
        fontweight="bold",
        ha="center",
        va="center",
        color=INK,
    )
    ax.text(
        50,
        60.8,
        "原则：按模型原生输入/输出重定义任务，不把链接预测叫实体链接，不把 KGQA 叫路径检索",
        fontsize=6.2,
        ha="center",
        va="center",
        color=MUTED,
    )

    # Column headers
    for x, text in ((16.5, "科研模型：原生任务"), (50, "重定义后的系统角色"), (83.5, "当前平台落点")):
        ax.text(x, 57.8, text, fontsize=6.8, fontweight="bold", ha="center", va="center", color=ACCENT)

    # Left: KG_O
    rounded_box(
        ax,
        2,
        33,
        29,
        22.5,
        "KG_O：原生 = 链接预测",
        [
            "输入：(head, relation) + tail 文本",
            "输出：全实体排序 / 链接分数",
            "模块：双塔 Prompt_bert",
            "· 邻居/路径提示 + 投影 768→64",
            "· 冻结 GNN + DeepFusion 门控融合",
            "训练：InfoNCE + 投影 MSE",
            "注意：不是 mention→实体链接器",
        ],
        title_size=7.4,
        line_size=6.0,
        line_step=2.55,
    )

    # Left: code-max
    rounded_box(
        ax,
        2,
        9,
        29,
        21,
        "code-max：原生 = 子图 KGQA",
        [
            "GAGR：子图 + 问题 → 答案实体分布",
            "PCRL：问题+路径 → 答案实体对比学习",
            "TAGA：多跳 QA 数据增强 / 补边",
            "GNN-RAG：GNN 检索 + LLM 生成",
            "注意：GAGR 原生输出不是路径分数",
        ],
        title_size=7.4,
        line_size=6.0,
        line_step=2.55,
    )

    # Middle: redefined roles
    rounded_box(
        ax,
        35,
        33,
        29,
        22.5,
        "角色 1：关系条件实体排序器",
        [
            "输入：用户 mention + 意图关系",
            "候选：HomeKG 内同类型实体",
            "复用：双塔 / 邻居提示 / GNN 融合",
            "领域微调：HomeKG 三元组 + 难负例",
            "附加：缺失关系补全（链接预测原生用法）",
            "输出：candidate_id + score + margin",
        ],
        title_size=7.4,
        line_size=6.0,
        line_step=2.55,
        fc=ACCENT_LIGHT,
    )

    rounded_box(
        ax,
        35,
        9,
        29,
        21,
        "角色 2：HomeKG 多跳推理器",
        [
            "GAGR：在 HomeKG 子图上推理答案实体",
            "适用：2 跳及以上、答案为实体的问句",
            "证据路径：由关系注意力回溯（派生）",
            "PCRL：对候选答案/路径重排",
            "TAGA：合成多跳训练与评测数据",
            "输出：answer_entities + evidence_paths",
        ],
        title_size=7.4,
        line_size=6.0,
        line_step=2.55,
        fc=ACCENT_LIGHT,
    )

    # Right: platform insertion points
    rounded_box(
        ax,
        68,
        40,
        30,
        15.5,
        "控制 / 查询链路",
        [
            "intent → entity_resolution(KG_O)",
            "→ task_planning → approval → tools",
            "歧义候选 → 澄清选项（带分数）",
            "低置信 / 超时 → 规则或 LLM 回退",
        ],
        title_size=7.2,
        line_size=6.0,
        line_step=2.55,
    )

    rounded_box(
        ax,
        68,
        23,
        30,
        15.5,
        "知识 / 报告链路",
        [
            "doc RAG + KG 多跳检索(GAGR)",
            "Qwen 融合文档片段与 evidence_paths",
            "路径作为可解释证据，不替代生成",
            "报告：补齐全屋结构关系",
        ],
        title_size=7.2,
        line_size=6.0,
        line_step=2.55,
    )

    rounded_box(
        ax,
        68,
        9,
        30,
        12,
        "明确不做",
        [
            "不让小模型替代 Qwen 生成",
            "不让 GAGR 直接输出路径分数",
            "不在缺 HomeKG 时强行接入",
        ],
        title_size=7.2,
        line_size=6.0,
        line_step=2.55,
        fc="#F7F7F7",
        ec=BORDER,
    )

    # Arrows
    poly_arrow(ax, [(31.2, 44.2), (34.6, 44.2)])
    poly_arrow(ax, [(31.2, 19.5), (34.6, 19.5)])
    poly_arrow(ax, [(64.2, 44.2), (67.6, 47.5)])
    poly_arrow(ax, [(64.2, 19.5), (67.6, 30.0)])

    # Bottom gate band
    ax.add_patch(Rectangle((2, 1.0), 96, 6.2, facecolor=BAND, edgecolor="none", zorder=0))
    ax.text(3.2, 5.8, "适配闸门（消融实验）", fontsize=6.9, fontweight="bold", color=INK, va="center")
    ax.text(
        3.2,
        3.6,
        "A0 当前平台 → A1 +KG_O 排序 → A2 +KG_O 补全 → A3 +GAGR → A4 +PCRL → A5 +TAGA",
        fontsize=6.0,
        color=INK,
        va="center",
    )
    ax.text(
        3.2,
        1.9,
        "判据：A1 必须降低错房间/错设备率；A3 必须在 2 跳以上问句显著优于 A1；否则删除该模型，不叙事性保留",
        fontsize=5.9,
        color=MUTED,
        va="center",
    )

    save(fig, "fig3_research_mapping")


if __name__ == "__main__":
    figure1()
    figure2()
    figure3()
