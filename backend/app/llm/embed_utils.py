"""本地中文向量化：字符 n-gram 哈希向量，兼容中文与英文。
用于没有云端 Embedding 接口（如 DeepSeek）或 API 异常时的本地降级。"""
import hashlib
import math
import re
from typing import List

EMBED_DIM = 64
_WHITESPACE = re.compile(r"\s+")
_DIGEST_BYTES = 2  # 16 bit -> 64 个桶


def local_embed_text(text: str, dim: int = EMBED_DIM) -> List[float]:
    """把一段文本编码为定长归一化向量：字符 1-3 gram 哈希桶。"""
    normalized = _WHITESPACE.sub("", (text or "").lower())
    if not normalized:
        return [0.0] * dim
    vector = [0.0] * dim
    for size in (1, 2, 3):
        for i in range(len(normalized) - size + 1):
            digest = hashlib.md5(normalized[i : i + size].encode("utf-8")).digest()
            idx = int.from_bytes(digest[:_DIGEST_BYTES], "little") % dim
            vector[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def local_embed_texts(texts: List[str], dim: int = EMBED_DIM) -> List[List[float]]:
    return [local_embed_text(text, dim) for text in texts]
