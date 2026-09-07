"""文件接口：上传、列表、状态与删除（按家庭隔离）。"""
import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from app.api.deps import get_current_user, require_owner_or_resident
from app.config import settings
from app.rag.vector_store import FAMILY_COLLECTION, USER_COLLECTION, vector_store
from app.schemas.file import FileStatusResponse
from app.services import file_service

router = APIRouter(prefix="/files", tags=["文件"])


def _file_dict(record) -> dict:
    return {
        "id": record.id,
        "family_id": record.family_id,
        "user_id": record.user_id,
        "filename": record.filename,
        "file_type": record.file_type,
        "file_size": record.file_size,
        "status": record.status,
        "chunk_count": record.chunk_count,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile,
    current_user: dict = Depends(require_owner_or_resident),
    collection: str = Query(default=USER_COLLECTION, description="user_documents 或 family_regulations"),
):
    """上传 PDF/Word 文件，异步解析并构建向量库。

    规章制度文件（family_regulations）仅房主可上传，家庭所有成员可检索。
    """
    if collection not in (USER_COLLECTION, FAMILY_COLLECTION):
        raise HTTPException(status_code=400, detail="collection 仅支持 user_documents 或 family_regulations")
    if collection == FAMILY_COLLECTION and current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="只有房主可以上传家庭规章制度")

    filename = file.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in {".pdf", ".docx", ".doc"}:
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 Word 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空，请检查文件内容")
    if len(content) > settings.max_file_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制")

    file_path = await file_service.save_upload_file(
        file, current_user["user_id"], content=content
    )
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

    asyncio.create_task(file_service.process_file_async(record.id, collection))
    return {"file_id": record.id, "status": "processing", "collection": collection}


@router.get("")
async def list_files(current_user: dict = Depends(get_current_user)):
    """列出当前家庭上传的文件。"""
    records = await file_service.list_files(current_user["family_id"])
    return [_file_dict(r) for r in records]


@router.get("/{file_id}/status", response_model=FileStatusResponse)
async def get_file_status(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询文件处理状态。"""
    record = await file_service.get_file_record(file_id, current_user["family_id"])
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"file_id": record.id, "status": record.status, "chunk_count": record.chunk_count}


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    """删除文件（房主/上传者本人可删）。"""
    record = await file_service.get_file_record(file_id, current_user["family_id"])
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")
    if current_user["role"] != "owner" and record.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="只能删除自己上传的文件")
    result = await file_service.delete_file(file_id, current_user["family_id"])
    await vector_store.delete_by_file_id(
        file_id=file_id,
        user_id=current_user["user_id"],
        family_id=current_user["family_id"],
    )
    return result