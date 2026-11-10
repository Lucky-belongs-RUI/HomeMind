"""上传文件表的数据访问。"""

from __future__ import annotations

from sqlalchemy import delete, or_, select

from homemind.models.file import UploadedFile
from homemind.rag.vector_store import FAMILY_COLLECTION
from homemind.repositories.base import BaseRepository


class FileRepository(BaseRepository):
    """上传文件表读写。"""

    async def get(self, file_id: int) -> UploadedFile | None:
        return await self.session.get(UploadedFile, file_id)

    async def find(self, file_id: int, family_id: int | None = None) -> UploadedFile | None:
        conditions = [UploadedFile.id == file_id]
        if family_id is not None:
            conditions.append(UploadedFile.family_id == family_id)
        result = await self.session.execute(select(UploadedFile).where(*conditions))
        return result.scalar_one_or_none()

    async def list_visible(self, family_id: int, user_id: int | None = None) -> list[UploadedFile]:
        """列出用户可见文件：家庭规章制度全家庭可见，私人文件仅上传者可见。"""
        query = select(UploadedFile).where(UploadedFile.family_id == family_id)
        if user_id is not None:
            query = query.where(
                or_(
                    UploadedFile.collection == FAMILY_COLLECTION,
                    UploadedFile.user_id == user_id,
                )
            )
        result = await self.session.execute(query.order_by(UploadedFile.created_at.desc()))
        return list(result.scalars().all())

    async def list_for_rebuild(self) -> list[UploadedFile]:
        """启动重建向量索引时的候选记录。"""
        result = await self.session.execute(
            select(UploadedFile).where(
                UploadedFile.status.in_(["ready", "failed"]),
                UploadedFile.file_path.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def add(self, record: UploadedFile) -> UploadedFile:
        self.session.add(record)
        await self.session.flush()
        return record

    async def delete(self, record: UploadedFile) -> None:
        await self.session.delete(record)

    async def delete_by_family(self, family_id: int) -> None:
        await self.session.execute(delete(UploadedFile).where(UploadedFile.family_id == family_id))
