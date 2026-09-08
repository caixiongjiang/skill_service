#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""技能管理 REST 路由。

前端与各后端通过 HTTP 调用本路由。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from loguru import logger

from api.schemas import (
    ApiResponse,
    DescriptorsResponse,
    SkillCreateRequest,
    SkillDescriptorResponse,
    SkillDetailResponse,
    SkillEnabledRequest,
    SkillUpdateRequest,
)

router = APIRouter(tags=["Skills"])


# ---------------------------------------------------------------------------
# 依赖：获取全局 SkillService 实例
# ---------------------------------------------------------------------------


def _get_service():
    from main import get_skill_service
    return get_skill_service()


_COVER_UNSET = object()


def _to_desc_response(
    desc,
    cover_url: Optional[str] | object = _COVER_UNSET,
) -> SkillDescriptorResponse:
    svc = _get_service()
    resolved = (
        svc.cover_url(desc.name) if cover_url is _COVER_UNSET else cover_url
    )
    return SkillDescriptorResponse(
        name=desc.name,
        description=desc.description,
        category=desc.category,
        tags=list(desc.tags),
        version=desc.version,
        requires_tools=list(desc.requires_tools),
        fallback_for_tools=list(desc.fallback_for_tools),
        source=desc.source,
        enabled=desc.enabled,
        deletable=desc.deletable,
        cover_url=resolved if isinstance(resolved, str) else None,
    )


# ---------------------------------------------------------------------------
# 读路径
# ---------------------------------------------------------------------------


@router.get("/skills/descriptors", response_model=ApiResponse[DescriptorsResponse])
async def get_descriptors(enabled_only: bool = Query(True)):
    """拉取全部技能 descriptor + 版本号（供各后端构建 Level-0 索引）。"""
    svc = _get_service()
    result = svc.descriptors_with_version(enabled_only=enabled_only)
    cover_urls = svc.cover_urls()
    return ApiResponse.success(
        DescriptorsResponse(
            descriptors=[
                _to_desc_response(d, cover_url=cover_urls.get(d.name))
                for d in result["descriptors"]
            ],
            version=result["version"],
        )
    )


@router.get("/skills", response_model=ApiResponse[list[SkillDescriptorResponse]])
async def list_skills(
    q: Optional[str] = Query(None, description="搜索关键词（前缀/模糊匹配 name+description）"),
    enabled_only: bool = Query(False, description="仅返回启用的技能"),
):
    """列出全部技能（侧栏 + slash 自动补全）。"""
    svc = _get_service()
    descs = svc.list(q=q, enabled_only=enabled_only)
    cover_urls = svc.cover_urls()
    return ApiResponse.success(
        [_to_desc_response(d, cover_url=cover_urls.get(d.name)) for d in descs]
    )


@router.get("/skills/{name}", response_model=ApiResponse[SkillDetailResponse])
async def get_skill(name: str):
    """获取技能详情（含正文 body）。"""
    svc = _get_service()
    try:
        desc, body, files = svc.get(name)
        return ApiResponse.success(
            SkillDetailResponse(
                descriptor=_to_desc_response(desc),
                body=body,
                files=list(files),
            )
        )
    except Exception as e:
        _raise_http(e)


# ---------------------------------------------------------------------------
# 写路径
# ---------------------------------------------------------------------------


@router.post("/skills", response_model=ApiResponse[SkillDescriptorResponse], status_code=201)
async def create_skill(req: SkillCreateRequest):
    """创建自定义技能。"""
    svc = _get_service()
    try:
        desc = svc.create(req.body)
        return ApiResponse.success(_to_desc_response(desc))
    except Exception as e:
        _raise_http(e)


@router.put("/skills/{name}", response_model=ApiResponse[SkillDescriptorResponse])
async def update_skill(name: str, req: SkillUpdateRequest):
    """编辑自定义技能。"""
    svc = _get_service()
    try:
        desc = svc.update(name, req.body)
        return ApiResponse.success(_to_desc_response(desc))
    except Exception as e:
        _raise_http(e)


@router.patch("/skills/{name}/enabled", response_model=ApiResponse)
async def set_skill_enabled(name: str, req: SkillEnabledRequest):
    """启用/停用技能。"""
    svc = _get_service()
    try:
        svc.set_enabled(name, req.enabled)
        return ApiResponse.success()
    except Exception as e:
        _raise_http(e)


@router.delete("/skills/{name}", response_model=ApiResponse)
async def delete_skill(name: str):
    """删除自定义技能。"""
    svc = _get_service()
    try:
        svc.delete(name)
        return ApiResponse.success()
    except Exception as e:
        _raise_http(e)


@router.get("/skills/{name}/cover")
async def get_skill_cover(name: str):
    """读取技能封面图片（供 <img> 直接引用）。"""
    svc = _get_service()
    try:
        found = svc.get_cover_bytes(name)
    except Exception as e:
        _raise_http(e)
    if not found:
        raise HTTPException(status_code=404, detail="该技能未设置自定义封面")
    data, media_type = found
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
    )


@router.post("/skills/{name}/cover", response_model=ApiResponse[SkillDescriptorResponse])
async def upload_skill_cover(
    name: str,
    file: UploadFile = File(..., description="封面图片（JPG/PNG/WEBP/GIF，最大 5MB）"),
):
    """上传或替换自定义技能封面。"""
    svc = _get_service()
    try:
        data = await file.read()
        cover_url = svc.save_cover(name, data, file.content_type or "")
        desc, _, _ = svc.get(name)
        return ApiResponse.success(
            _to_desc_response(desc, cover_url=cover_url),
            message="封面已保存",
        )
    except Exception as e:
        _raise_http(e)


@router.delete("/skills/{name}/cover", response_model=ApiResponse)
async def delete_skill_cover(name: str):
    """删除自定义技能封面，恢复为生成封面。"""
    svc = _get_service()
    try:
        svc.clear_cover(name)
        return ApiResponse.success(message="封面已移除")
    except Exception as e:
        _raise_http(e)


# ---------------------------------------------------------------------------
# 异常映射
# ---------------------------------------------------------------------------


def _raise_http(e: Exception) -> None:
    from skill_service import Forbidden, NotFound, DuplicateName, SkillRejected

    if isinstance(e, NotFound):
        raise HTTPException(status_code=404, detail=e.args[0])
    if isinstance(e, Forbidden):
        raise HTTPException(status_code=403, detail=e.message)
    if isinstance(e, DuplicateName):
        raise HTTPException(status_code=409, detail=e.args[0])
    if isinstance(e, SkillRejected):
        raise HTTPException(
            status_code=422,
            detail=f"技能内容未通过安全扫描: {list(e.hits)}",
        )
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=e.args[0])

    logger.exception(f"技能操作异常: {e}")
    raise HTTPException(status_code=500, detail="内部服务器错误")
