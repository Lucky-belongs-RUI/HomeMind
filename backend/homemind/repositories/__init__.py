"""数据访问层（repositories）。

约定：SQL 只出现在本包内；service 层通过 `unit_of_work()` 拿到仓库，
只写业务规则与事务边界。详见 `base.py` 的分层说明。
"""

from homemind.repositories.base import BaseRepository
from homemind.repositories.conversation import ConversationRepository
from homemind.repositories.device import DeviceRepository, default_status
from homemind.repositories.family import FamilyRepository
from homemind.repositories.file import FileRepository
from homemind.repositories.model_config import ModelConfigRepository
from homemind.repositories.preference import PreferenceRepository
from homemind.repositories.room import RoomRepository
from homemind.repositories.scene import SceneRepository
from homemind.repositories.unit_of_work import UnitOfWork, unit_of_work
from homemind.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "ConversationRepository",
    "DeviceRepository",
    "FamilyRepository",
    "FileRepository",
    "ModelConfigRepository",
    "PreferenceRepository",
    "RoomRepository",
    "SceneRepository",
    "UnitOfWork",
    "UserRepository",
    "default_status",
    "unit_of_work",
]
