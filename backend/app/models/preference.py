from datetime import datetime
from sqlalchemy import JSON, BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntPK


class UserPreference(Base):
    """用户偏好画像表：按用户存储（非家庭）。"""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
