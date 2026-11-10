"""文件相关的响应模型。

组织约定：**领域响应模型与同领域的其它 schema 放在一起**，
只有跨领域的通用响应（成功壳、错误体、分页等）才集中到 `responses.py`。
"""

from pydantic import BaseModel


class FileItem(BaseModel):
    """文件列表中的单个条目。"""

    id: int
    family_id: int
    user_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    collection: str
    chunk_count: int | None = None
    created_at: str | None = None


class FileUploadResponse(BaseModel):
    """上传接口响应：文件已入库，向量化在后台异步进行。"""

    file_id: int
    status: str
    collection: str


class FileStatusResponse(BaseModel):
    """文件处理状态响应。

    `chunk_count` 必须是 Optional：文件处于 pending / processing / failed 时
    该字段为 None，若声明为 `int = 0` 会让响应校验失败并返回 500。
    """

    file_id: int
    status: str
    chunk_count: int | None = None
