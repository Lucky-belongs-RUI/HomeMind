"""向量存储：用户私有数据 + 家庭规章制度双集合。

优先使用 ChromaDB；未安装时回退到本地 JSON + 余弦相似度。
- user_documents：按 user_id 隔离（兼容旧数据不带 family_id）
- family_regulations：按 family_id 隔离
"""

import json
import logging
import math
import os
import uuid
from typing import Any

from homemind.core.config import settings

logger = logging.getLogger(__name__)

USER_COLLECTION = "user_documents"
FAMILY_COLLECTION = "family_regulations"
# 阈值校准（v2.2）：阿里云 text-embedding-v2（1536 维稠密向量）实测——
# 强相关片段余弦 ≈0.54~0.81，弱相关 ≈0.44（如"申请学生会"vs"研究生会报名表"），
# 完全不相关 <0.05。0.45 会把弱相关真实结果误杀（实测 0.4409 被拦），
# 降到 0.40：弱相关结果返回给模型自主判断，明显噪声仍被过滤。
MIN_SCORE = 0.40
TOP_K = 3


class VectorStore:
    def __init__(self):
        self._use_chroma = False
        self._collections = {}
        self._local_path = os.path.join(settings.chroma_path, "local_vector_store.json")
        self._records = []  # [{id, user_id, family_id, file_id, collection, text, vector}]
        self._init_backend()

    def _init_backend(self):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=settings.chroma_path)
            # 显式指定余弦距离度量（ChromaDB 默认是 L2）；
            # 查询阶段 score = 1.0 - distance 才等价于余弦相似度，范围 [-1, 1]
            cosine_metadata = {"hnsw:space": "cosine"}
            self._collections = {
                USER_COLLECTION: client.get_or_create_collection(
                    USER_COLLECTION, metadata=cosine_metadata
                ),
                FAMILY_COLLECTION: client.get_or_create_collection(
                    FAMILY_COLLECTION, metadata=cosine_metadata
                ),
            }
            self._use_chroma = True
        except Exception:
            self._load_local()

    def _load_local(self):
        if os.path.exists(self._local_path):
            with open(self._local_path, encoding="utf-8") as f:
                self._records = json.load(f)

    def _save_local(self):
        os.makedirs(os.path.dirname(self._local_path), exist_ok=True)
        with open(self._local_path, "w", encoding="utf-8") as f:
            json.dump(self._records, f, ensure_ascii=False)

    async def add_documents(
        self,
        chunks: list[str],
        user_id: int,
        file_id: int,
        family_id: int,
        collection: str = USER_COLLECTION,
        embedder=None,
        filename: str = "",
    ) -> list[str]:
        """写入指定集合；collection 仅支持 user_documents / family_regulations。"""
        if collection not in (USER_COLLECTION, FAMILY_COLLECTION):
            raise ValueError(f"不支持的向量集合: {collection}")

        embeddings = await embedder.embed(chunks)
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [
            {
                "user_id": user_id,
                "family_id": family_id,
                "file_id": file_id,
                "collection": collection,
                "filename": filename,
            }
            for _ in chunks
        ]
        if self._use_chroma:
            self._collections[collection].add(
                embeddings=embeddings,
                documents=chunks,
                ids=ids,
                metadatas=metadatas,
            )
        else:
            for cid, chunk, vec, meta in zip(ids, chunks, embeddings, metadatas, strict=False):
                self._records.append({"id": cid, "text": chunk, "vector": vec, **meta})
            self._save_local()
        return ids

    async def query(
        self,
        query_text: str,
        user_id: int,
        family_id: int,
        top_k: int = TOP_K,
        embedder=None,
        min_score: float = MIN_SCORE,
        include_private: bool = True,
    ) -> list[dict[str, Any]]:
        """双集合检索：用户私有数据 + 家庭规章制度，按相似度合并排序。

        include_private=False 时（家庭报告等家庭级场景）不检索私人文件。
        """
        if self._use_chroma:
            return await self._query_chroma(
                query_text, user_id, family_id, top_k, embedder, min_score, include_private
            )
        return await self._query_local(
            query_text, user_id, family_id, top_k, embedder, min_score, include_private
        )

    async def _query_chroma(
        self,
        query_text,
        user_id,
        family_id,
        top_k,
        embedder,
        min_score,
        include_private: bool = True,
    ) -> list[dict[str, Any]]:
        query_vector = await embedder.embed([query_text])
        results = []
        queries = []
        if include_private:
            queries.append((USER_COLLECTION, {"user_id": user_id}))
        queries.append((FAMILY_COLLECTION, {"family_id": family_id}))
        for collection, where in queries:
            try:
                raw = self._collections[collection].query(
                    query_embeddings=query_vector,
                    n_results=max(top_k, 1),
                    where=where,
                )
                docs = (raw.get("documents") or [[]])[0]
                metas = (raw.get("metadatas") or [[]])[0]
                distances = (raw.get("distances") or [[]])[0]
                for doc, meta, distance in zip(docs, metas, distances, strict=False):
                    score = max(0.0, min(1.0, 1.0 - float(distance)))
                    if score >= min_score:
                        results.append(self._pack_result(doc, meta, score, collection))
            except Exception:
                # 集合为空或元数据过滤不兼容时跳过
                continue
        results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return results[:top_k]

    async def _query_local(
        self,
        query_text,
        user_id,
        family_id,
        top_k,
        embedder,
        min_score,
        include_private: bool = True,
    ) -> list[dict[str, Any]]:
        if not self._records:
            return []
        query_vec = (await embedder.embed([query_text]))[0]
        scored = []
        for rec in self._records:
            collection = rec.get("collection", USER_COLLECTION)
            if collection == USER_COLLECTION and not include_private:
                continue
            if collection == USER_COLLECTION and rec.get("user_id") != user_id:
                continue
            if collection == FAMILY_COLLECTION and rec.get("family_id") != family_id:
                continue
            score = self._cosine(query_vec, rec.get("vector") or [])
            if score >= min_score:
                scored.append((score, rec, collection))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            self._pack_result(rec["text"], rec, score, collection)
            for score, rec, collection in scored[:top_k]
        ]

    @staticmethod
    def _pack_result(
        content: str, metadata: dict[str, Any], score: float, collection: str
    ) -> dict[str, Any]:
        return {
            "content": content,
            "score": round(score, 4),
            "metadata": {
                "user_id": metadata.get("user_id"),
                "family_id": metadata.get("family_id"),
                "file_id": metadata.get("file_id"),
                "collection": collection,
                "filename": metadata.get("filename", ""),
            },
        }

    async def get_all_file_ids(self) -> set:
        """返回向量库中全部 file_id（用于与 uploaded_files 表对账）。"""
        file_ids = set()
        if self._use_chroma:
            for collection in (USER_COLLECTION, FAMILY_COLLECTION):
                try:
                    existing = self._collections[collection].get(limit=100000)
                    for meta in existing.get("metadatas") or []:
                        fid = meta.get("file_id")
                        if fid is not None:
                            file_ids.add(int(fid))
                except Exception:
                    continue
        else:
            for rec in self._records:
                fid = rec.get("file_id")
                if fid is not None:
                    file_ids.add(int(fid))
        return file_ids

    async def clear_all(self):
        """清空两个集合的全部向量（维度迁移/全量重建前调用）。

        重建逻辑随后按 uploaded_files 表逐文件重新入库，
        因此孤儿向量在此一并清除，不再单独对账。
        """
        if self._use_chroma:
            for collection in (USER_COLLECTION, FAMILY_COLLECTION):
                try:
                    existing = self._collections[collection].get(limit=100000)
                    ids = (existing or {}).get("ids", [])
                    if ids:
                        self._collections[collection].delete(ids=ids)
                except Exception as exc:
                    logger.warning("清空向量集合 %s 失败: %s", collection, exc)
        else:
            if self._records:
                self._records = []
                self._save_local()

    def get_collections_for_file(self, file_id: int) -> list[str]:
        """返回某文件在当前向量索引中使用的集合列表。

        注意：重建索引流程会先清空集合，此时再调用必然得到空列表，
        因此 collection 一律以数据库记录为准（见 file_service.rebuild_file_vectors）。
        """
        if self._use_chroma:
            result = []
            for collection in (USER_COLLECTION, FAMILY_COLLECTION):
                try:
                    existing = self._collections[collection].get(where={"file_id": file_id})
                    if (existing or {}).get("ids"):
                        result.append(collection)
                except Exception:
                    continue
            return result
        return sorted(
            {
                rec.get("collection", USER_COLLECTION)
                for rec in self._records
                if rec.get("file_id") == file_id
            }
        )

    async def delete_by_file_id(self, file_id: int, user_id: int = None, family_id: int = None):
        """按文件 ID 从两个集合删除向量。"""
        if self._use_chroma:
            for collection in (USER_COLLECTION, FAMILY_COLLECTION):
                try:
                    where = {"file_id": file_id}
                    existing = self._collections[collection].get(where=where)
                    ids = (existing or {}).get("ids", [])
                    if ids:
                        self._collections[collection].delete(ids=ids)
                except Exception:
                    continue
        else:
            before = len(self._records)
            self._records = [rec for rec in self._records if rec.get("file_id") != file_id]
            if len(self._records) != before:
                self._save_local()

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)


# ============================================================
# 单例（懒加载）
# ============================================================

_vector_store: "VectorStore | None" = None


def get_vector_store() -> VectorStore:
    """返回向量库单例，首次调用时才初始化。

    为什么不在模块级直接 `vector_store = VectorStore()`：
    构造 VectorStore 会立刻创建 Chroma PersistentClient（涉及文件锁与磁盘 IO）。
    模块级实例化意味着「只要 import 这个模块就初始化向量库」——
    这迫使所有使用方都改写成函数内导入来规避副作用，
    也是本项目 49 处函数内 import 的根源之一。

    改为懒加载后，导入只是纯声明，真正用到时才建立连接。
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
