"""文档切片器：长文档切为适合向量化的语义片段。

- 先按句子标点（。！？；!?;）和换行切句，再合并到目标长度；
- 单句超过上限时安全硬切（带重叠）；
- 输出去除空白与相邻重复片段。
"""
import re
from typing import List

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*|\n+")
_WHITESPACE = re.compile(r"[ \t\u3000]+")


class TextChunker:
    """文档切片器：长文档切为适合向量化的片段。"""

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _WHITESPACE.sub(" ", text)
        return text.strip()

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        sentences = []
        for part in _SENTENCE_SPLIT.split(text):
            part = part.strip()
            if part:
                sentences.append(part)
        return sentences

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """硬切分：单句超长或无法按句合并时的兜底实现。"""
        chunks = []
        step = max(1, chunk_size - overlap)
        start = 0
        while start < len(text):
            chunks.append(text[start : start + chunk_size])
            start += step
            if start >= len(text):
                break
        return chunks

    @classmethod
    def chunk_by_paragraph(cls, text: str, max_size: int = 500, overlap: int = 50) -> List[str]:
        """按句子合并切片：优先在句号/换行处断开，避免从句子中间截断。"""
        text = cls._normalize(text)
        if not text:
            return []

        sentences = cls._split_sentences(text)
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            if len(sentence) > max_size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(cls.chunk_text(sentence, max_size, overlap))
                continue
            if current and len(current) + 1 + len(sentence) > max_size:
                chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            chunks.append(current)

        result = []
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk and (not result or result[-1] != chunk):
                result.append(chunk)
        return result