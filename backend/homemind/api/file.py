"""文件接口：上传、列表、状态与删除（按家庭隔离）。"""

import asyncio
import os

from fastapi import APIRouter, Depends, Query, UploadFile

from homemind.api.deps import get_current_user, require_owner_or_resident
from homemind.core.config import settings
from homemind.core.exceptions import (
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    ValidationError,
)
from homemind.rag.vector_store import (
    FAMILY_COLLECTION,
    USER_COLLECTION,
    get_vector_store,
)
from homemind.schemas.file import (
    FileItem,
    FileStatusResponse,
    FileUploadResponse,
)
from homemind.schemas.responses import SuccessResponse
from homemind.services import file_service

router = APIRouter(prefix="/files", tags=["文件"])

# 后台任务强引用：事件循环只保存 Task 的弱引用，不持有引用时
# 任务可能在处理中途被垃圾回收，文件会永远停在 processing。
_background_tasks: set[asyncio.Task] = set()

# 流式读取的块大小（1MB）
_UPLOAD_CHUNK_SIZE = 1024 * 1024


async def _read_upload_within_limit(file: UploadFile) -> bytes | None:
    """分块读取上传内容，超过 max_file_size 立即中断并返回 None。

    为什么不用 `await file.read()`：Starlette 会把整个 body 物化成一个 bytes
    对象放进内存，攻击者发送超大 body 即可耗尽进程内存（`max_file_size`
    只会在读完之后才生效，挡不住这一步）。
    """
    limit = settings.max_file_size
    buffer = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            return None
    return bytes(buffer)


def _file_dict(record) -> dict:
    return {
        "id": record.id,
        "family_id": record.family_id,
        "user_id": record.user_id,
        "filename": record.filename,
        "file_type": record.file_type,
        "file_size": record.file_size,
        "status": record.status,
        "collection": record.collection,
        "chunk_count": record.chunk_count,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile,
    current_user: dict = Depends(require_owner_or_resident),
    collection: str = Query(
        default=USER_COLLECTION, description="user_documents 或 family_regulations"
    ),
):
    """上传 PDF/Word 文件，异步解析并构建向量库。

    规章制度文件（family_regulations）仅房主可上传，家庭所有成员可检索。
    """
    if collection not in (USER_COLLECTION, FAMILY_COLLECTION):
        raise ValidationError("collection 仅支持 user_documents 或 family_regulations")
    if collection == FAMILY_COLLECTION and current_user["role"] != "owner":
        raise PermissionDeniedError("只有房主可以上传家庭规章制度")

    filename = file.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    # python-docx 仅支持 .docx（OOXML），旧版二进制 .doc 无法解析，入口直接拒绝
    if extension not in {".pdf", ".docx"}:
        raise ValidationError("仅支持 PDF（.pdf）和 Word（.docx）文件")

    # 大小校验前置：先看 multipart 解析出的声明大小，再流式读取兜底，
    # 避免"先全量读进内存再判断超限"导致的大 body 内存耗尽
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > settings.max_file_size:
        raise PayloadTooLargeError(
            f"文件大小超过限制（上限 {settings.max_file_size // (1024 * 1024)}MB）"
        )

    content = await _read_upload_within_limit(file)
    if content is None:
        raise PayloadTooLargeError(
            f"文件大小超过限制（上限 {settings.max_file_size // (1024 * 1024)}MB）"
        )
    if not content:
        raise ValidationError("上传文件为空，请检查文件内容")

    file_path = await file_service.save_upload_file(file, current_user["user_id"], content=content)
    record = await file_service.create_file_record(
        user_id=current_user["user_id"],
        family_id=current_user["family_id"],
        filename=filename,
        file_path=file_path,
        file_type=file_service.get_file_type(filename),
        file_size=len(content),
        content_hash=file_service.compute_content_hash(content),
        collection=collection,
    )

    task = asyncio.create_task(file_service.process_file_async(record.id, collection))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"file_id": record.id, "status": "processing", "collection": collection}


@router.get("", response_model=list[FileItem])
async def list_files(current_user: dict = Depends(get_current_user)):
    """列出当前用户可见的文件：家庭文件全家庭可见，私人文件仅本人可见。"""
    records = await file_service.list_files(current_user["family_id"], current_user["user_id"])
    return [_file_dict(r) for r in records]


@router.get("/{file_id}/status", response_model=FileStatusResponse)
async def get_file_status(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询文件处理状态（私人文件仅本人可查）。"""
    record = await file_service.get_file_record(file_id, current_user["family_id"])
    if not record:
        raise NotFoundError("文件不存在")
    if record.collection != FAMILY_COLLECTION and record.user_id != current_user["user_id"]:
        raise NotFoundError("文件不存在")
    return {"file_id": record.id, "status": record.status, "chunk_count": record.chunk_count}


@router.delete("/{file_id}", response_model=SuccessResponse)
async def delete_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    """删除文件：家庭文件仅房主可删，私人文件仅上传者本人可删。"""
    record = await file_service.get_file_record(file_id, current_user["family_id"])
    if not record:
        raise NotFoundError("文件不存在")
    if record.collection == FAMILY_COLLECTION:
        if current_user["role"] != "owner":
            raise PermissionDeniedError("只有房主可以删除家庭规章制度")
    elif record.user_id != current_user["user_id"]:
        raise PermissionDeniedError("只能删除自己上传的私人文件")
    result = await file_service.delete_file(file_id, current_user["family_id"])
    await get_vector_store().delete_by_file_id(
        file_id=file_id,
        user_id=current_user["user_id"],
        family_id=current_user["family_id"],
    )
    return result
