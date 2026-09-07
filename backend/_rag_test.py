# -*- coding: utf-8 -*-
import asyncio
from app.llm.embed_utils import local_embed_text, local_embed_texts
from app.rag.vector_store import VectorStore, MIN_SCORE

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)

query1 = "朱仰瑞音乐鉴赏论文题目"
doc1 = "《中国民族音乐鉴赏》课程考试论文 数字重构与文化再生：古琴艺术的计算机技术赋能路径研究 作者：朱仰瑞 学号：240854042 2025 级 计算机技术 学院 信息科学与工程学院"
query2 = "KFR-35GW_01GFC13是什么设备，怎么使用"
doc2 = "本产品型号为 KFR-35GW_01GFC13，是一台分体式壁挂空调，制冷量 3500W，使用遥控器开机并选择制冷或制热模式。"

vq1 = local_embed_text(query1)
vd1 = local_embed_text(doc1)
s1 = cosine(vq1, vd1)
print("论文查询相似度:", round(s1, 4), "阈值:", MIN_SCORE, "通过:", s1 >= MIN_SCORE)

vq2 = local_embed_text(query2)
vd2 = local_embed_text(doc2)
s2 = cosine(vq2, vd2)
print("空调型号查询相似度:", round(s2, 4), "阈值:", MIN_SCORE, "通过:", s2 >= MIN_SCORE)

unrelated = local_embed_text("今天天气不错，去公园散步")
s3 = cosine(vq1, unrelated)
print("无关文档相似度:", round(s3, 4), "不应误召回:", s3 < MIN_SCORE)

# 模拟本地向量检索
vs = VectorStore()
vs._use_chroma = False
vs._records = [
    {"id": "a", "user_id": 5, "family_id": 3, "file_id": 6, "collection": "user_documents", "text": doc1, "vector": vd1},
    {"id": "b", "user_id": 5, "family_id": 3, "file_id": 6, "collection": "user_documents", "text": doc2, "vector": vd2},
    {"id": "c", "user_id": 1, "family_id": 1, "file_id": 9, "collection": "user_documents", "text": "无关内容", "vector": unrelated},
]
class MockEmbedder:
    async def embed(self, texts):
        return local_embed_texts(texts)

embedder = MockEmbedder()

async def main():
    results = await vs.query(query1, user_id=5, family_id=3, top_k=3, embedder=embedder)
    print("论文检索结果数:", len(results))
    for r in results:
        print("  score:", r["score"], "file_id:", r["metadata"]["file_id"], "content:", r["content"][:30])
    results2 = await vs.query(query2, user_id=5, family_id=3, top_k=3, embedder=embedder)
    print("空调检索结果数:", len(results2))
    for r in results2:
        print("  score:", r["score"], "file_id:", r["metadata"]["file_id"], "content:", r["content"][:30])

asyncio.run(main())
