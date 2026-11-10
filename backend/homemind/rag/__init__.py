"""RAG 服务：文档切片、向量存储与检索。

注意这里只导出 `get_vector_store`（函数）而非实例——
模块级实例化会在 import 时初始化 Chroma，详见 vector_store.py 的说明。
"""

from homemind.rag.chunker import TextChunker
from homemind.rag.vector_store import get_vector_store

__all__ = ["TextChunker", "get_vector_store"]
