#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""技能封面 MySQL 记录（挂在 skill 表上）。

skill-service 当前依赖 skill_core wheel，封面列由本仓库自行补齐，
不依赖 wheel 是否已包含 cover_* 字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]

_ALTER_STATEMENTS = (
    """
    ALTER TABLE skill
    ADD COLUMN cover_url VARCHAR(512) NULL
    COMMENT '封面对外访问相对路径'
    AFTER body
    """,
    """
    ALTER TABLE skill
    ADD COLUMN cover_object_key VARCHAR(512) NULL
    COMMENT 'MinIO 存储路径 bucket/object_key'
    AFTER cover_url
    """,
)


@dataclass(frozen=True)
class SkillCoverRecord:
    name: str
    cover_url: str
    cover_object_key: str


class SkillCoverRepository:
    """读写 skill.cover_url / skill.cover_object_key。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def ensure_columns(self) -> None:
        session = self._session_factory()
        try:
            for sql in _ALTER_STATEMENTS:
                try:
                    session.execute(text(sql))
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    if "Duplicate column name" not in str(exc):
                        raise
            logger.info("skill 封面列已就绪 (cover_url, cover_object_key)")
        finally:
            session.close()

    def get(self, name: str) -> SkillCoverRecord | None:
        session = self._session_factory()
        try:
            row = session.execute(
                text(
                    "SELECT name, cover_url, cover_object_key "
                    "FROM skill WHERE name = :name"
                ),
                {"name": name},
            ).first()
            if row is None or not row.cover_object_key:
                return None
            return SkillCoverRecord(
                name=row.name,
                cover_url=row.cover_url or "",
                cover_object_key=row.cover_object_key,
            )
        finally:
            session.close()

    def list_urls(self) -> dict[str, str]:
        session = self._session_factory()
        try:
            rows = session.execute(
                text(
                    "SELECT name, cover_url FROM skill "
                    "WHERE cover_object_key IS NOT NULL AND cover_object_key <> ''"
                )
            ).all()
            return {row.name: row.cover_url for row in rows if row.cover_url}
        finally:
            session.close()

    def set(self, name: str, cover_url: str, cover_object_key: str) -> None:
        session = self._session_factory()
        try:
            result = session.execute(
                text(
                    "UPDATE skill SET cover_url = :cover_url, "
                    "cover_object_key = :cover_object_key, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE name = :name"
                ),
                {
                    "name": name,
                    "cover_url": cover_url,
                    "cover_object_key": cover_object_key,
                },
            )
            if result.rowcount == 0:
                session.rollback()
                raise ValueError(f"技能 '{name}' 不存在，无法写入封面")
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def clear(self, name: str) -> SkillCoverRecord | None:
        previous = self.get(name)
        if previous is None:
            return None
        session = self._session_factory()
        try:
            session.execute(
                text(
                    "UPDATE skill SET cover_url = NULL, cover_object_key = NULL, "
                    "updated_at = CURRENT_TIMESTAMP WHERE name = :name"
                ),
                {"name": name},
            )
            session.commit()
            return previous
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
