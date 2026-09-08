#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""技能封面：MinIO 存图 + MySQL 记对象地址。"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from loguru import logger

from cover_repo import SkillCoverRepository
from minio_store import MinioObjectStore

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

MAX_COVER_BYTES = 5 * 1024 * 1024
_MAGIC_EXT = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def detect_cover_ext(data: bytes, content_type: str) -> str:
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    for magic, ext in _MAGIC_EXT:
        if data.startswith(magic):
            return ext
    ext = ALLOWED_IMAGE_TYPES.get((content_type or "").lower())
    if ext:
        return ext
    raise ValueError("仅支持 JPG、PNG、WEBP、GIF 封面图片")


def mime_for_key(storage_path: str) -> str:
    return _MIME_BY_EXT.get(Path(storage_path).suffix.lower(), "application/octet-stream")


def build_object_key(name: str, ext: str, *, tenant: str, timestamp: int) -> str:
    return f"skill-covers/{tenant}/{name}/cover_{timestamp}{ext}"


class CoverStore:
    """校验图片 → 上传 MinIO → 回写 skill 表封面列。"""

    def __init__(
        self,
        repo: SkillCoverRepository,
        minio: MinioObjectStore,
        *,
        tenant: str | None = None,
    ) -> None:
        self._repo = repo
        self._minio = minio
        self._tenant = (tenant or os.getenv("MYSQL_DATABASE") or "default").strip() or "default"

    def public_url(self, name: str) -> str | None:
        self._assert_name(name)
        rec = self._repo.get(name)
        return rec.cover_url if rec and rec.cover_url else None

    def public_urls(self) -> dict[str, str]:
        return self._repo.list_urls()

    def save(self, name: str, data: bytes, content_type: str) -> str:
        self._assert_name(name)
        if not data:
            raise ValueError("封面文件内容为空")
        if len(data) > MAX_COVER_BYTES:
            raise ValueError(
                f"封面过大 ({len(data) / 1024 / 1024:.1f}MB)，最大允许 5MB"
            )

        ext = detect_cover_ext(data, content_type)
        mime = _MIME_BY_EXT.get(ext, content_type or "application/octet-stream")
        stamp = int(time.time())
        object_key = build_object_key(name, ext, tenant=self._tenant, timestamp=stamp)
        previous = self._repo.get(name)
        storage_path = self._minio.put(object_key, data, mime)
        cover_url = f"/skills/{name}/cover?t={stamp}"
        try:
            self._repo.set(name, cover_url, storage_path)
        except Exception:
            try:
                self._minio.remove(storage_path)
            except Exception as exc:
                logger.warning(f"回滚 MinIO 封面失败: {storage_path}, {exc}")
            raise

        if (
            previous
            and previous.cover_object_key
            and previous.cover_object_key != storage_path
        ):
            try:
                self._minio.remove(previous.cover_object_key)
            except Exception as exc:
                logger.warning(
                    f"清理旧封面失败（忽略）: {previous.cover_object_key}, {exc}"
                )
        return cover_url

    def delete(self, name: str, *, clear_row: bool = True) -> bool:
        """删除 MinIO 对象；clear_row=True 时同时清空 MySQL 封面列。"""
        self._assert_name(name)
        rec = self._repo.get(name)
        if rec is None:
            return False
        if rec.cover_object_key:
            try:
                self._minio.remove(rec.cover_object_key)
            except Exception as exc:
                logger.warning(f"删除 MinIO 封面失败（继续清库）: {rec.cover_object_key}, {exc}")
        if clear_row:
            self._repo.clear(name)
        return True

    def get_bytes(self, name: str) -> tuple[bytes, str] | None:
        self._assert_name(name)
        rec = self._repo.get(name)
        if rec is None or not rec.cover_object_key:
            return None
        data = self._minio.get(rec.cover_object_key)
        return data, mime_for_key(rec.cover_object_key)

    @staticmethod
    def _assert_name(name: str) -> None:
        if not _NAME_PATTERN.match(name or ""):
            raise ValueError(f"技能名 '{name}' 格式不合法")
