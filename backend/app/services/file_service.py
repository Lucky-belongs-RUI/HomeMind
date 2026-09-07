import asyncio
import hashlib
import logging
import os
import uuid

from sqlalchemy import select, text

from app.config import settings
from app.database import get_db_session
from app.models.file import UploadedFile

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
    """根据扩展名返回文件类型：pdf / word。"""
    extension = os.path.splitext(filename or "")[1].lower()
    return "pdf" if extension == ".pdf" else "word"


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
    async with get_db_session() as db:
        record = UploadedFile(
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
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record


async def get_file_record(file_id: int, family_id: int = None) -> UploadedFile | None:
    """查询文件记录；传入 family_id 时校验归属。"""
    async with get_db_session() as db:
        conditions = [UploadedFile.id == file_id]
        if family_id is not None:
            conditions.append(UploadedFile.family_id == family_id)
        result = await db.execute(select(UploadedFile).where(*conditions))
        return result.scalar_one_or_none()


async def list_files(family_id: int) -> list[UploadedFile]:
    """列出家庭内所有上传文件（按创建时间倒序）。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(UploadedFile)
            .where(UploadedFile.family_id == family_id)
            .order_by(UploadedFile.created_at.desc())
        )
        return list(result.scalars().all())


async def update_file_status(file_id: int, status: str, chunk_count: int = None) -> UploadedFile:
    """更新文件处理状态与切片数。"""
    async with get_db_session() as db:
        record = await db.get(UploadedFile, file_id)
        if not record:
            raise ValueError(f"文件记录不存在: {file_id}")
        record.status = status
        if chunk_count is not None:
            record.chunk_count = chunk_count
        await db.commit()
        await db.refresh(record)
        return record


async def delete_file(file_id: int, family_id: int) -> dict:
    """删除文件记录并清理磁盘文件。"""
    async with get_db_session() as db:
        record = await db.get(UploadedFile, file_id)
        if not record or record.family_id != family_id:
            raise ValueError("文件不存在")
        file_path = record.file_path
        await db.delete(record)
        await db.commit()
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            logger.warning("清理上传文件失败: %s", exc)
    return {"success": True}


def parse_file(file_path: str, file_type: str) -> str:
    """解析 PDF/Word 文件为纯文本（同步函数，异步任务中经 to_thread 调用）。"""
    text = ""
    if file_type == "pdf":
        import fitz

        doc = fitz.open(file_path)
        try:
            text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    else:
        import docx

        document = docx.Document(file_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return text or ""


async def process_file_async(file_id: int, collection: str = "user_documents"):
    """异步处理文件：解析 → 切片 → 向量化 → 更新状态。

    collection 决定写入哪个向量集合：user_documents（个人私有）或
    family_regulations（家庭规章制度）。
    """
    from app.rag.chunker import TextChunker
    from app.rag.vector_store import vector_store

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
        chunks = [
            chunk.strip()
            for chunk in TextChunker.chunk_by_paragraph(text)
            if chunk.strip()
        ]
        if chunks:
            client = get_llm_client()
            await vector_store.add_documents(
                chunks=chunks,
                user_id=record.user_id,
                file_id=file_id,
                family_id=record.family_id,
                collection=collection,
                embedder=client,
                filename=record.filename,
            )
        await update_file_status(file_id, "ready", chunk_count=len(chunks))
    except Exception as exc:
        logger.error("文件处理失败 file_id=%s: %s", file_id, exc)
        try:
            await update_file_status(file_id, "failed")
        except Exception:
            logger.exception("更新文件失败状态时出错 file_id=%s", file_id)


async def ensure_collection_column():
    """兼容旧库：为 uploaded_files 表补充 collection 列（先查后加，兼容 MySQL 5.7）。"""
    async with get_db_session() as db:
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'uploaded_files' "
                "AND column_name = 'collection'"
            )
        )
        if (result.scalar() or 0) == 0:
            await db.execute(
                text(
                    "ALTER TABLE uploaded_files ADD COLUMN collection VARCHAR(32) "
                    "NOT NULL DEFAULT 'user_documents' COMMENT '向量集合'"
                )
            )
            await db.commit()


async def rebuild_file_vectors():
    """启动时重建向量索引：旧版本中文向量化无效，重新解析并向量化已有文件。"""
    from app.rag.vector_store import USER_COLLECTION, vector_store

    try:
        await ensure_collection_column()
    except Exception as exc:
        logger.warning("检查 uploaded_files.collection 列失败: %s", exc)

    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(UploadedFile).where(
                    UploadedFile.status.in_(["ready", "failed"]),
                    UploadedFile.file_path.isnot(None),
                )
            )
            records = list(result.scalars().all())
    except Exception as exc:
        logger.warning("读取上传文件记录失败: %s", exc)
        return

    for record in records:
        try:
            collections = vector_store.get_collections_for_file(record.id)
            collection = (
                collections[0]
                if collections
                else getattr(record, "collection", None) or USER_COLLECTION
            )
            await vector_store.delete_by_file_id(record.id)
            await process_file_async(record.id, collection)
            logger.info("已重建文件向量 file_id=%s collection=%s", record.id, collection)
        except Exception as exc:
            logger.warning("重建文件向量失败 file_id=%s: %s", record.id, exc)



def get_llm_client():
    """延迟导入 LLM 客户端，避免模块加载时的依赖问题。"""
    from app.llm.factory import get_llm_client as _get_client

    return _get_client()