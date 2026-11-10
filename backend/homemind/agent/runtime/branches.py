"""轻量分支：闲聊、知识检索与家庭报告。

三者都只有一个节点，直接作为主图节点注册，不再各自维护单节点子图。
最终措辞统一交给 compose，避免同一轮重复调用回复模型。
"""

from __future__ import annotations

import logging
from typing import Any

from homemind.agent.house_status import build_house_status_text
from homemind.agent.runtime.schemas import BranchResult
from homemind.rag.retriever import retrieve_relevant_docs

logger = logging.getLogger(__name__)

_CARE_WORDS = (
    "感冒",
    "发烧",
    "不舒服",
    "头疼",
    "喉咙痛",
    "身体难受",
    "冷",
    "热",
    "难过",
    "不开心",
    "累",
    "孤独",
    "害怕",
)


def _task_text(state: dict[str, Any]) -> str:
    return str((state.get("task") or {}).get("instruction") or state.get("query") or "")


async def chat_node(state: dict[str, Any]) -> dict[str, Any]:
    text = _task_text(state)
    caring = any(word in text for word in _CARE_WORDS)
    return {
        "results": [
            BranchResult(
                branch="chat",
                success=True,
                summary="用户需要情感陪伴" if caring else "用户在进行日常交流",
                data={"tone": "caring" if caring else "friendly"},
            ).model_dump()
        ]
    }


def _sources(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, doc in enumerate(documents, 1):
        metadata = doc.get("metadata") or {}
        result.append(
            {
                "index": index,
                "source": metadata.get("filename") or metadata.get("source") or "知识库",
                "collection": metadata.get("collection") or "",
                "score": doc.get("score"),
            }
        )
    return result


async def knowledge_node(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("request") or {}
    task = state.get("task") or {}
    query = str(task.get("query") or task.get("instruction") or state.get("query") or "").strip()
    user_id = request.get("user_id")
    family_id = request.get("family_id")

    if not query:
        return {
            "results": [
                BranchResult(
                    branch="knowledge",
                    success=False,
                    summary="知识查询缺少有效问题",
                    degraded=True,
                ).model_dump()
            ]
        }
    if user_id is None or family_id is None:
        return {
            "results": [
                BranchResult(
                    branch="knowledge",
                    success=False,
                    summary="缺少可信身份上下文，无法检索知识库",
                    degraded=True,
                ).model_dump()
            ]
        }

    try:
        documents = await retrieve_relevant_docs(
            query=query,
            user_id=int(user_id),
            family_id=int(family_id),
            top_k=3,
        )
    except Exception as exc:
        logger.warning("知识检索失败: %s", exc)
        return {
            "results": [
                BranchResult(
                    branch="knowledge",
                    success=False,
                    summary=f"知识库检索失败：{exc}",
                    degraded=True,
                ).model_dump()
            ]
        }

    if not documents:
        return {
            "results": [
                BranchResult(
                    branch="knowledge",
                    success=True,
                    summary="知识库中没有找到相关资料",
                    data={"context": "", "documents": []},
                ).model_dump()
            ]
        }

    context = "\n".join(
        f"[{index}] {doc.get('content') or ''}"
        for index, doc in enumerate(documents, 1)
        if (doc.get("content") or "").strip()
    )
    return {
        "results": [
            BranchResult(
                branch="knowledge",
                success=True,
                summary=f"检索到 {len(documents)} 条相关资料",
                data={"context": context, "documents": documents},
                sources=_sources(documents),
            ).model_dump()
        ]
    }


async def report_node(state: dict[str, Any]) -> dict[str, Any]:
    snapshot = state.get("house_snapshot") or {}
    return {
        "results": [
            BranchResult(
                branch="report",
                success=True,
                summary="已汇总全屋状态",
                data={"context": build_house_status_text(snapshot), "snapshot": snapshot},
            ).model_dump()
        ]
    }
