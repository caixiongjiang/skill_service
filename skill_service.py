#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""SkillService 核心逻辑。

管理面唯一编排者：CRUD / 启停 / 写入期安全扫描 / 索引失效。
路由层只做参数校验与序列化。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from skill_core import (
    SkillDescriptor,
    SkillRegistry,
    parse_skill_md,
    scan_content,
)
from skill_core.adapters.mysql_repo import MySQLSkillRepository
from skill_core.ports import SkillRepository
from skill_core.types import CustomSkillRecord


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class NotFound(Exception):
    """技能不存在。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"技能 '{name}' 不存在")


class Forbidden(Exception):
    """操作被禁止（如编辑/删除内置技能）。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DuplicateName(Exception):
    """技能名冲突。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"技能名 '{name}' 已存在（与内置或已有自定义技能冲突）")


class SkillRejected(Exception):
    """技能内容未通过安全扫描。"""

    def __init__(self, hits: tuple[str, ...]) -> None:
        self.hits = hits
        super().__init__(f"技能内容未通过安全扫描: {hits}")


# ---------------------------------------------------------------------------
# 正则校验
# ---------------------------------------------------------------------------

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


# ---------------------------------------------------------------------------
# SkillService
# ---------------------------------------------------------------------------


class SkillService:
    """技能管理服务（独立进程，拥有存储）。"""

    def __init__(
        self,
        registry: SkillRegistry,
        repo: SkillRepository,
    ) -> None:
        self._registry = registry
        self._repo = repo

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        q: str | None = None,
        enabled_only: bool = False,
    ) -> list[SkillDescriptor]:
        """列出全部技能（合并 builtin + custom）。"""
        descs = self._registry.list_descriptors(include_disabled=not enabled_only)
        if q:
            q_lower = q.lower()
            descs = [
                d for d in descs
                if q_lower in d.name.lower() or q_lower in d.description.lower()
            ]
        return descs

    def get(self, name: str) -> tuple[SkillDescriptor, str, tuple[str, ...]]:
        """获取技能详情（descriptor, body, files）。

        Raises:
            NotFound: 技能不存在。
        """
        skill = self._registry.get(name)
        if skill is None:
            raise NotFound(name)
        return skill.descriptor, skill.body, skill.files

    def descriptors_with_version(self, *, enabled_only: bool = True) -> dict[str, Any]:
        """返回 {descriptors, version}，供各后端拉取。"""
        descs = self._registry.list_descriptors(include_disabled=not enabled_only)
        version = self._repo.table_version()
        return {"descriptors": descs, "version": version}

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def create(self, raw_md: str) -> SkillDescriptor:
        """创建自定义技能。

        Raises:
            DuplicateName: 名称冲突。
            SkillRejected: 安全扫描未通过。
            ValueError: 校验失败。
        """
        parsed = parse_skill_md(raw_md)

        # 名称校验
        self._assert_valid_name(parsed.name)
        self._assert_name_available(parsed.name)

        # 安全扫描
        scan = scan_content(parsed.body)
        if not scan.ok:
            raise SkillRejected(scan.hits)

        now = datetime.now()
        rec = CustomSkillRecord(
            name=parsed.name,
            description=parsed.description,
            category=parsed.category,
            tags=parsed.tags,
            version=parsed.version,
            requires_tools=parsed.requires_tools,
            fallback_for_tools=parsed.fallback_for_tools,
            body=raw_md,
            created_by="",
            created_at=now,
            updated_at=now,
        )
        self._repo.create(rec)
        self._registry.invalidate()
        logger.info(f"技能已创建: {parsed.name}")

        return SkillDescriptor(
            name=parsed.name,
            description=parsed.description,
            category=parsed.category,
            tags=parsed.tags,
            version=parsed.version,
            requires_tools=parsed.requires_tools,
            fallback_for_tools=parsed.fallback_for_tools,
            source="custom",
            enabled=True,
            deletable=True,
            path=None,
        )

    def update(self, name: str, raw_md: str) -> SkillDescriptor:
        """编辑自定义技能。

        Raises:
            NotFound: 技能不存在。
            Forbidden: 尝试编辑内置技能。
            SkillRejected: 安全扫描未通过。
        """
        self._assert_custom(name)

        parsed = parse_skill_md(raw_md)

        # 安全扫描
        scan = scan_content(parsed.body)
        if not scan.ok:
            raise SkillRejected(scan.hits)

        now = datetime.now()
        rec = CustomSkillRecord(
            name=name,  # name 不变
            description=parsed.description,
            category=parsed.category,
            tags=parsed.tags,
            version=parsed.version,
            requires_tools=parsed.requires_tools,
            fallback_for_tools=parsed.fallback_for_tools,
            body=raw_md,
            created_by="",
            created_at=now,
            updated_at=now,
        )
        self._repo.update(rec)
        self._registry.invalidate()
        logger.info(f"技能已更新: {name}")

        return SkillDescriptor(
            name=name,
            description=parsed.description,
            category=parsed.category,
            tags=parsed.tags,
            version=parsed.version,
            requires_tools=parsed.requires_tools,
            fallback_for_tools=parsed.fallback_for_tools,
            source="custom",
            enabled=True,
            deletable=True,
            path=None,
        )

    def set_enabled(self, name: str, enabled: bool) -> None:
        """启用/停用技能（builtin + custom 均可）。

        Raises:
            NotFound: 技能不存在。
        """
        self._assert_exists(name)
        self._repo.set_state(name, enabled)
        self._registry.invalidate()
        logger.info(f"技能 {'启用' if enabled else '停用'}: {name}")

    def delete(self, name: str) -> None:
        """删除自定义技能。

        Raises:
            NotFound: 技能不存在。
            Forbidden: 尝试删除内置技能。
        """
        self._assert_custom(name)
        self._repo.delete(name)
        self._registry.invalidate()
        logger.info(f"技能已删除: {name}")

    # ------------------------------------------------------------------
    # 内部校验
    # ------------------------------------------------------------------

    def _assert_valid_name(self, name: str) -> None:
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                f"技能名 '{name}' 格式不合法，必须匹配 ^[a-z][a-z0-9_-]*$"
            )

    def _assert_name_available(self, name: str) -> None:
        # 检查 builtin
        for desc in self._registry.list_descriptors(include_disabled=True):
            if desc.name == name:
                raise DuplicateName(name)
        # 检查 custom
        if self._repo.get(name) is not None:
            raise DuplicateName(name)

    def _assert_exists(self, name: str) -> None:
        skill = self._registry.get(name)
        if skill is None:
            raise NotFound(name)

    def _assert_custom(self, name: str) -> None:
        for desc in self._registry.list_descriptors(include_disabled=True):
            if desc.name == name:
                if desc.source != "custom":
                    raise Forbidden(f"内置技能 '{name}' 不可编辑/删除")
                return
        raise NotFound(name)
