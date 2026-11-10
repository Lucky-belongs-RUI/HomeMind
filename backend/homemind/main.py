"""FastAPI 应用入口：挂载路由、CORS、WebSocket 与启动事件。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from homemind.api import agent as agent_api
from homemind.api import agent_chat as agent_chat_api
from homemind.api import auth as auth_api
from homemind.api import device as device_api
from homemind.api import family as family_api
from homemind.api import file as file_api
from homemind.api import model_config as model_config_api
from homemind.api import room as room_api
from homemind.api import scene as scene_api
from homemind.api import user as user_api
from homemind.core.config import settings
from homemind.core.handlers import register_exception_handlers
from homemind.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

API_PREFIX = "/api"

# 不安全的默认值：出现在配置里即说明未按生产要求显式设置
_INSECURE_DEFAULTS = {
    "jwt_secret": "smart-home-secret-key-change-in-production",
}


def _validate_security_settings() -> None:
    """启动期安全校验。

    默认值兜底在演示阶段很方便，但在生产是静默的致命漏洞——运维忘记配置时
    服务照常启动，而密钥是公开的，任何人都能伪造任意用户（含房主）的 token。
    因此 production 环境下发现未修改的默认值直接拒绝启动。
    """
    problems = [
        name
        for name, insecure in _INSECURE_DEFAULTS.items()
        if getattr(settings, name, None) == insecure
    ]
    if not problems:
        return
    if settings.is_production:
        raise RuntimeError(
            "生产环境安全配置校验失败，以下配置仍为默认值："
            + "、".join(problems)
            + "。请在 .env 中显式配置后重启。"
        )
    logger.warning(
        "安全提示：以下配置仍为默认值（%s），仅可用于本地开发，上线前必须修改",
        "、".join(problems),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时迁移文件集合列并重建向量索引，初始化 LangGraph 持久化，再启动设备模拟引擎。"""

    # 安全配置校验放在最前：不安全的默认值必须在服务对外提供能力前拦下
    _validate_security_settings()

    from homemind.services import file_service

    try:
        await file_service.rebuild_file_vectors()
    except Exception as exc:
        logger.warning("启动时重建文件向量索引失败: %s", exc)

    # LangGraph 持久化：Postgres checkpointer（中断态）+ Store（长期记忆）。
    # 初始化失败会自动降级为进程内 MemorySaver，不阻断服务启动。
    from homemind.agent.runtime.graph import build_agent_graph, set_agent_app
    from homemind.agent.runtime.persistence import init_persistence, shutdown_persistence

    checkpointer, store = await init_persistence()
    set_agent_app(build_agent_graph(checkpointer=checkpointer, store=store))

    if settings.enable_scheduler:
        start_scheduler()
    yield
    stop_scheduler()
    await shutdown_persistence()


app = FastAPI(
    title="智能家居大模型体验平台",
    version="3.0",
    description="基于 FastAPI + LangGraph + RAG 的智能家居后端服务",
    lifespan=lifespan,
)

# CORS：来源由 CORS_ORIGINS 配置（逗号分隔），默认仅本地开发地址。
# 生产必须配置为真实前端域名——不要图省事写成 "*"，
# 在 allow_credentials=True 时通配来源会带来跨站凭据泄露风险。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router, prefix=API_PREFIX)
app.include_router(family_api.router, prefix=API_PREFIX)
app.include_router(room_api.router, prefix=API_PREFIX)
app.include_router(device_api.router, prefix=API_PREFIX)
app.include_router(user_api.router, prefix=API_PREFIX)
app.include_router(scene_api.router, prefix=API_PREFIX)
app.include_router(file_api.router, prefix=API_PREFIX)
app.include_router(model_config_api.router, prefix=API_PREFIX)
app.include_router(agent_api.router, prefix=API_PREFIX)
app.include_router(agent_chat_api.router, prefix=API_PREFIX)

# 全局异常处理：服务层抛领域异常（AppError 子类），
# 由这里统一转成带 code 的错误响应，API 层不再需要逐接口 try/except
register_exception_handlers(app)


@app.get("/")
async def root():
    """健康检查。"""
    from homemind.agent.runtime.persistence import persistence_status

    return {
        "service": "smart-home-backend",
        "status": "running",
        "docs": "/docs",
        "llm_provider": settings.llm_provider,
        "persistence": persistence_status(),
    }
