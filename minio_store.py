#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""技能封面 MinIO 对象存储。"""

from __future__ import annotations

import os
from io import BytesIO

from loguru import logger
from minio import Minio
from minio.error import S3Error


def minio_from_env() -> "MinioObjectStore":
    endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
    access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
    secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
    bucket = os.getenv("MINIO_BUCKET", "").strip()
    secure = os.getenv("MINIO_SECURE", "false").strip().lower() in {"1", "true", "yes"}
    if not endpoint or not access_key or not secret_key or not bucket:
        raise RuntimeError(
            "MinIO 未配置完整，需要 MINIO_ENDPOINT / MINIO_ACCESS_KEY / "
            "MINIO_SECRET_KEY / MINIO_BUCKET"
        )
    return MinioObjectStore(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        secure=secure,
    )


class MinioObjectStore:
    """同步 MinIO 客户端，路径格式与头像一致：bucket/object_key。"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        *,
        secure: bool = False,
    ) -> None:
        self.bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)
            logger.info(f"已创建 MinIO bucket: {self.bucket}")

    def put(self, object_key: str, data: bytes, content_type: str) -> str:
        self._client.put_object(
            self.bucket,
            object_key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        storage_path = f"{self.bucket}/{object_key}"
        logger.info(f"技能封面已上传 MinIO: {storage_path} ({len(data)} bytes)")
        return storage_path

    def get(self, storage_path: str) -> bytes:
        bucket, object_key = split_storage_path(storage_path, default_bucket=self.bucket)
        response = self._client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def remove(self, storage_path: str) -> None:
        bucket, object_key = split_storage_path(storage_path, default_bucket=self.bucket)
        try:
            self._client.remove_object(bucket, object_key)
            logger.info(f"已从 MinIO 删除技能封面: {bucket}/{object_key}")
        except S3Error as exc:
            logger.warning(f"MinIO 删除技能封面失败（忽略）: {storage_path}, {exc}")


def split_storage_path(storage_path: str, *, default_bucket: str) -> tuple[str, str]:
    raw = (storage_path or "").strip().lstrip("/")
    if not raw:
        raise ValueError("MinIO 存储路径为空")
    if "/" not in raw:
        return default_bucket, raw
    bucket, object_key = raw.split("/", 1)
    if not object_key:
        raise ValueError(f"MinIO 存储路径不合法: {storage_path}")
    return bucket, object_key
