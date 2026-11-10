"""文件服务：落盘、记录管理、解析与向量化。

SQL 已下沉到 FileRepository；解析/向量化等 IO 仍在本层。
"""

import asyncio
import hashlib
import logging
import os
import uuid

from homemind.core.config import settings
from homemind.core.exceptions import NotFoundError
from homemind.models.file import UploadedFile
from homemind.rag.chunker import TextChunker
from homemind.rag.embedder import get_embedder
from homemind.rag.vector_store import (
    USER_COLLECTION,
    get_vector_store,
)
from homemind.repositories import unit_of_work

logger = logging.getLogger(__name__)


async def save_upload_file(file, user_id: int, content: bytes | None = None) -> str:
    """保存上传文件到 upload_dir/user_{user_id}/，返回相对存储路径。

    content 由接口层读取一次后传入，避免重复读取导致落盘空文件；
    未传入时（兼容旧调用）由本函数读取一次。
    """
    user_dir = os.path.join(settings.upload_dir, f"user_{user_id}")
    os.makedirs(user_dir, exist_ok=True)
    extension = os.path.splitext(file.filename or "")[1].lower()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(user_dir, stored_name)
    if content is None:
        content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


def get_file_type(filename: str) -> str:
    """根据扩展名返回文件类型：pdf / docx（上传入口已限制仅 .pdf/.docx）。"""
    extension = os.path.splitext(filename or "")[1].lower()
    return "pdf" if extension == ".pdf" else "docx"


def compute_content_hash(content: bytes) -> str:
    """计算文件内容 MD5，用于去重标记。"""
    return hashlib.md5(content).hexdigest()


async def create_file_record(
    user_id: int,
    family_id: int,
    filename: str,
    file_path: str,
    file_type: str,
    file_size: int = 0,
    content_hash: str = None,
    collection: str = "user_documents",
) -> UploadedFile:
    """创建上传文件记录，初始状态为 pending。"""
    async with unit_of_work() as uow:
        record = await uow.files.add(
            UploadedFile(
                family_id=family_id,
                user_id=user_id,
                filename=filename,
                file_path=file_path,
                file_type=file_type,
                file_size=file_size,
                content_hash=content_hash,
                collection=collection,
                status="pending",
            )
        )
        await uow.commit()
        await uow.refresh(record)
        return record


async def get_file_record(file_id: int, family_id: int = None) -> UploadedFile | None:
    """查询文件记录；传入 family_id 时校验归属。"""
    async with unit_of_work() as uow:
        return await uow.files.find(file_id, family_id)


async def list_files(family_id: int, user_id: int = None) -> list[UploadedFile]:
    """列出当前用户可见的上传文件（按创建时间倒序）。

    可见性规则：家庭文件（family_regulations）全家庭可见；
    私人文件（user_documents）仅上传者本人可见。
    """
    async with unit_of_work() as uow:
        return await uow.files.list_visible(family_id, user_id)


async def update_file_status(file_id: int, status: str, chunk_count: int = None) -> UploadedFile:
    """更新文件处理状态与切片数。"""
    async with unit_of_work() as uow:
        record = await uow.files.get(file_id)
        if not record:
            raise NotFoundError(f"文件记录不存在: {file_id}")
        record.status = status
        if chunk_count is not None:
            record.chunk_count = chunk_count
        await uow.commit()
        await uow.refresh(record)
        return record


async def delete_file(file_id: int, family_id: int) -> dict:
    """删除文件记录并清理磁盘文件。"""
    async with unit_of_work() as uow:
        record = await uow.files.get(file_id)
        if not record or record.family_id != family_id:
            raise NotFoundError("文件不存在")
        file_path = record.file_path
        await uow.files.delete(record)
        await uow.commit()
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            logger.warning("清理上传文件失败: %s", exc)
    return {"success": True}


def parse_file(file_path: str, file_type: str) -> str:
    """解析 PDF/DOCX 文件为纯文本（同步函数，异步任务中经 to_thread 调用）。"""
    text = ""
    if file_type == "pdf":
        import fitz

        doc = fitz.open(file_path)
        try:
            text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    else:
        # file_type == "docx"：python-docx 仅支持 OOXML（.docx），旧 .doc 已在上传入口拒绝
        import docx

        document = docx.Document(file_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return text or ""


async def process_file_async(file_id: int, collection: str = "user_documents"):
    """异步处理文件：解析 → 切片 → 向量化 → 更新状态。

    collection 决定写入哪个向量集合：user_documents（个人私有）或
    family_regulations（家庭规章制度）。
    向量化强制使用阿里云 text-embedding-v2（homemind/rag/embedder.py），失败标记 failed，不降级。
    """

    try:
        record = await get_file_record(file_id)
        if not record:
            return
        await update_file_status(file_id, "processing")
        text = await asyncio.to_thread(parse_file, record.file_path, record.file_type)
        if not (text or "").strip():
            logger.warning("文件未提取到文本（可能为空或扫描件）: %s", record.filename)
            await update_file_status(file_id, "failed", chunk_count=0)
            return
        chunks = [chunk.strip() for chunk in TextChunker.chunk_by_paragraph(text) if chunk.strip()]
        if chunks:
            embedder = get_embedder()
            # 每个 chunk 前加文档名前缀：文件名参与向量语义，用户按文件名提问
            # （如"zhongwen.docx 讲的什么"）也能命中；检索返回时模型能看到内容来源。
            prefixed_chunks = [f"[文档《{record.filename}》] {chunk}" for chunk in chunks]
            await get_vector_store().add_documents(
                chunks=prefixed_chunks,
                user_id=record.user_id,
                file_id=file_id,
                family_id=record.family_id,
                collection=collection,
                embedder=embedder,
                filename=record.filename,
            )
        await update_file_status(file_id, "ready", chunk_count=len(chunks))
    except Exception as exc:
        logger.error("文件处理失败 file_id=%s: %s", file_id, exc)
        try:
            await update_file_status(file_id, "failed")
        except Exception:
            logger.exception("更新文件失败状态时出错 file_id=%s", file_id)


async def rebuild_file_vectors():
    """启动时重建向量索引：先清空两个集合（维度迁移+孤儿向量一并处理），
    再按 uploaded_files 表逐文件重新解析向量化。

    说明（v2.1）：向量化已强制切到阿里云 text-embedding-v2（1536 维），
    旧 64 维哈希向量与 Chroma 同集合混维会导致查询报错，因此重建前必须清空；
    孤儿向量（DB 已无记录的文件）清空后不会重新入库，等效于原对账清理。

    向量化没有本地降级：先做一次在线探活，不可用时直接跳过重建。
    否则一旦清空后才发现 Key 缺失/网络不通，会让原本可用的索引被清空且无法恢复。
    """

    try:
        embedder = get_embedder()
        await asyncio.wait_for(embedder.embed(["向量化健康检查"]), timeout=20)
    except Exception as exc:
        logger.warning("向量化服务不可用，跳过本次重建以保留现有索引: %s", exc)
        return

    # 先清空两个集合，保证向量维度统一（text-embedding-v2, 1536 维）
    try:
        await get_vector_store().clear_all()
    except Exception as exc:
        logger.warning("清空向量库失败: %s", exc)
        return

    try:
        async with unit_of_work() as uow:
            records = await uow.files.list_for_rebuild()
    except Exception as exc:
        logger.warning("读取上传文件记录失败: %s", exc)
        return

    for record in records:
        try:
            collection = getattr(record, "collection", None) or USER_COLLECTION
            await process_file_async(record.id, collection)
            logger.info("已重建文件向量 file_id=%s collection=%s", record.id, collection)
        except Exception as exc:
            logger.warning("重建文件向量失败 file_id=%s: %s", record.id, exc)
