from datetime import datetime
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntPK


class Device(Base):
    """设备表：状态以 JSON 存储，支持不同设备类型的差异化属性。"""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    room_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DeviceOperationLog(Base):
    """设备操作日志：记录手动/AI/调度触发的状态变更。"""

    __tablename__ = "device_operation_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    operation: Mapped[str] = mapped_column(String(32), default="update")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    before_status: Mapped[dict | None] = mapped_column(JSON)
    after_status: Mapped[dict | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
