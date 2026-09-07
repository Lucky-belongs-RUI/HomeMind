"""FastAPI 应用入口：挂载路由、CORS、WebSocket 与启动事件。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent as agent_api
from app.api import auth as auth_api
from app.api import device as device_api
from app.api import family as family_api
from app.api import file as file_api
from app.api import room as room_api
from app.api import scene as scene_api
from app.api import user as user_api
from app.config import settings
from app.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时迁移文件集合列并重建向量索引，再启动设备模拟引擎。"""

    from app.services import file_service

    try:
        await file_service.ensure_collection_column()
        await file_service.rebuild_file_vectors()
    except Exception as exc:
        logger.warning("启动时重建文件向量索引失败: %s", exc)

    if settings.enable_scheduler:
        start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="智能家居大模型体验平台",
    version="3.0",
    description="基于 FastAPI + LangGraph + RAG 的智能家居后端服务",
    lifespan=lifespan,
)

# 开发环境 CORS：前端 Vite 默认 5173 端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ],
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
app.include_router(agent_api.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    """健康检查。"""
    return {
        "service": "smart-home-backend",
        "status": "running",
        "docs": "/docs",
        "llm_provider": settings.llm_provider,
    }