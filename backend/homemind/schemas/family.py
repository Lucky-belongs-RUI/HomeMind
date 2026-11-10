from pydantic import BaseModel, ConfigDict

# ============================================================
# 请求模型
# ============================================================


class FamilyCreate(BaseModel):
    """创建家庭请求（已登录房主创建新家庭并生成新房主账户）。"""

    name: str
    owner_username: str
    owner_nickname: str
    description: str | None = None


class FamilyUpdate(BaseModel):
    """更新家庭信息请求。"""

    name: str | None = None
    description: str | None = None


# ============================================================
# 响应模型
# ============================================================


class FamilyItem(BaseModel):
    """家庭基础信息（`PUT /families/{id}` 返回，来自 ORM 对象）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_user_id: int
    description: str | None = None


class FamilyOwnerItem(BaseModel):
    """家庭房主信息。"""

    id: int
    username: str
    nickname: str
    role: str
    family_id: int


class FamilyOverview(BaseModel):
    """家庭概览：家庭信息 + 房主 + 各类资源统计。

    字段平铺（而非嵌套 data 包装），与既有前端读取方式保持一致。
    """

    id: int
    name: str
    owner_user_id: int
    owner: FamilyOwnerItem | None = None
    description: str | None = None
    users_count: int = 0
    rooms_count: int = 0
    devices_count: int = 0
    scenes_count: int = 0


class FamilyMemberItem(BaseModel):
    """家庭成员（不含密码）。"""

    id: int
    username: str
    nickname: str
    role: str
    family_id: int


class CreatedFamilyResponse(BaseModel):
    """创建家庭后返回的新房主账户信息。

    注意这里**不返回密码**——虽然当前实现用的是固定默认密码，
    但把它写进响应等于把"知道接口就能登录"这件事显式化。
    """

    family_id: int
    family_name: str
    owner_user_id: int
    owner_username: str
