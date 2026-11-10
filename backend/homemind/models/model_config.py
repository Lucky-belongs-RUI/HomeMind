from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from homemind.core.database import Base, BigIntPK


class UserModelConfig(Base):
    """用户个人模型配置。

    API Key 只保存 Fernet 密文，接口永远不返回明文。
    Ollama 本地模型允许不填 Key，其余供应商必须配置。
    """

    __tablename__ = "user_model_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_model_config_name"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255))
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
