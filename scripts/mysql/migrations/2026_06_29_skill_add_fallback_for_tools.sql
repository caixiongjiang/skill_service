-- Migration: Add fallback_for_tools column to skill table
-- Date: 2026-06-29
-- 说明: skill_core 0.2.0 ORM 已声明 fallback_for_tools，旧表缺少该列会导致 /skills 500
-- 影响: skill 表
-- 回滚: ALTER TABLE skill DROP COLUMN fallback_for_tools;

ALTER TABLE skill
ADD COLUMN fallback_for_tools JSON NULL
COMMENT '降级工具 JSON 数组'
AFTER requires_tools;
