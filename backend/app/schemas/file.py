from pydantic import BaseModel


class FileStatusResponse(BaseModel):
    """文件处理状态响应。"""
    file_id: int
    status: str
    chunk_count: int = 0