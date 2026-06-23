#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""skill-service 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 统一响应（对齐知识系统 ApiResponse）
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式。"""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")

    @classmethod
    def success(cls, data: Any = None, message: str = "success") -> "ApiResponse":
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, message: str, code: int = 400, data: Any = None) -> "ApiResponse":
        return cls(code=code, message=message, data=data)


# ---------------------------------------------------------------------------
# 技能相关
# ---------------------------------------------------------------------------


class SkillDescriptorResponse(BaseModel):
    """技能描述符响应。"""

    name: str
    description: str
    category: str
    tags: List[str] = []
    version: str = "1.0.0"
    requires_tools: List[str] = []
    fallback_for_tools: List[str] = []
    source: str  # "builtin" | "custom"
    enabled: bool = True
    deletable: bool = False


class SkillDetailResponse(BaseModel):
    """技能详情响应（含正文）。"""

    descriptor: SkillDescriptorResponse
    body: str
    files: List[str] = []


class SkillCreateRequest(BaseModel):
    """创建自定义技能请求。"""

    body: str = Field(..., description="完整 SKILL.md 内容（含 frontmatter）")


class SkillUpdateRequest(BaseModel):
    """编辑自定义技能请求。"""

    body: str = Field(..., description="完整 SKILL.md 内容（含 frontmatter）")


class SkillEnabledRequest(BaseModel):
    """启停技能请求。"""

    enabled: bool = Field(..., description="true=启用, false=停用")


class DescriptorsResponse(BaseModel):
    """/descriptors 响应（供各后端拉取）。"""

    descriptors: List[SkillDescriptorResponse]
    version: int
