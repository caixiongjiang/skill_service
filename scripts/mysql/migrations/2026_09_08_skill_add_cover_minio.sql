-- Migration: skill 表增加 MinIO 封面地址
-- Date: 2026-09-08
-- 说明: 多租户下封面不再落本地盘，图片存 MinIO，本表记录对外 URL 与对象键
-- 影响: skill 表
-- 回滚:
--   ALTER TABLE skill DROP COLUMN cover_object_key;
--   ALTER TABLE skill DROP COLUMN cover_url;

ALTER TABLE skill
ADD COLUMN cover_url VARCHAR(512) NULL
COMMENT '封面对外访问相对路径'
AFTER body;

ALTER TABLE skill
ADD COLUMN cover_object_key VARCHAR(512) NULL
COMMENT 'MinIO 存储路径 bucket/object_key'
AFTER cover_url;
