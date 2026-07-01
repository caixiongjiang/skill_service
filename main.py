#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Skill Service 入口。

独立进程部署，独占共享 MySQL，对外暴露 REST API。

启动方式:
    uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 加载 .env
load_dotenv()

# ---------------------------------------------------------------------------
# 全局 SkillService 实例
# ---------------------------------------------------------------------------

_skill_service = None


def get_skill_service():
    """获取全局 SkillService 实例。"""
    if _skill_service is None:
        raise RuntimeError("SkillService 尚未初始化")
    return _skill_service


# ---------------------------------------------------------------------------
# MySQL 连接（skill-service 自己管理，不依赖 agent_infra_service 的工厂）
# ---------------------------------------------------------------------------


def _create_engine_and_session():
    """从环境变量创建 SQLAlchemy engine 和 session 工厂。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "default")

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, session_factory


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _skill_service

    logger.info("Skill Service 启动中...")

    from skill_core import SkillRegistry
    from skill_core.adapters.mysql_repo import MySQLSkillRepository

    engine, session_factory = _create_engine_and_session()

    repo = MySQLSkillRepository(session_factory=session_factory)
    repo.ensure_tables()

    import skill_core as _sc
    builtin_dir = Path(_sc.__file__).resolve().parent / "skills"
    if not builtin_dir.is_dir():
        builtin_dir = Path("./skills")
        builtin_dir.mkdir(exist_ok=True)

    registry = SkillRegistry(builtin_dir=builtin_dir, repo=repo)

    from skill_service import SkillService

    _skill_service = SkillService(registry=registry, repo=repo)
    logger.info(f"Skill Service 已就绪 (builtin_dir={builtin_dir})")

    yield

    logger.info("Skill Service 关闭中...")
    engine.dispose()
    logger.info("Skill Service 已关闭")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Skill Service",
    description="Skill 技能管理服务（独立进程，独占 MySQL）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from api.routers.skill import router as skill_router

app.include_router(skill_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "skill-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
