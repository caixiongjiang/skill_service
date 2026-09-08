#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""封面校验、对象键与 CoverStore 编排测试。"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from cover_repo import SkillCoverRecord
from cover_store import CoverStore, build_object_key, detect_cover_ext, mime_for_key
from minio_store import split_storage_path


class DetectCoverExtTests(unittest.TestCase):
    def test_detects_png_magic(self) -> None:
        data = b"\x89PNG\r\n\x1a\n" + b"rest"
        self.assertEqual(detect_cover_ext(data, "application/octet-stream"), ".png")

    def test_detects_webp_riff(self) -> None:
        data = b"RIFF????WEBP" + b"rest"
        self.assertEqual(detect_cover_ext(data, ""), ".webp")

    def test_falls_back_to_content_type(self) -> None:
        self.assertEqual(detect_cover_ext(b"not-an-image", "image/jpeg"), ".jpg")

    def test_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            detect_cover_ext(b"hello", "text/plain")


class ObjectKeyTests(unittest.TestCase):
    def test_build_object_key_uses_tenant(self) -> None:
        key = build_object_key("my-skill", ".webp", tenant="dev_default", timestamp=1700000000)
        self.assertEqual(key, "skill-covers/dev_default/my-skill/cover_1700000000.webp")

    def test_split_storage_path(self) -> None:
        bucket, key = split_storage_path(
            "dev-default/skill-covers/dev_default/x/cover_1.png",
            default_bucket="fallback",
        )
        self.assertEqual(bucket, "dev-default")
        self.assertEqual(key, "skill-covers/dev_default/x/cover_1.png")

    def test_mime_for_key(self) -> None:
        self.assertEqual(mime_for_key("bucket/a/cover.webp"), "image/webp")


class CoverStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Mock()
        self.minio = Mock()
        self.store = CoverStore(self.repo, self.minio, tenant="dev_default")

    def test_save_writes_minio_then_mysql(self) -> None:
        self.repo.get.return_value = None
        self.minio.put.return_value = "dev-default/skill-covers/dev_default/demo/cover_1.png"
        png = b"\x89PNG\r\n\x1a\n" + b"payload"

        url = self.store.save("demo", png, "image/png")

        self.minio.put.assert_called_once()
        self.repo.set.assert_called_once()
        name, cover_url, object_key = self.repo.set.call_args.args
        self.assertEqual(name, "demo")
        self.assertTrue(cover_url.startswith("/skills/demo/cover?t="))
        self.assertEqual(object_key, "dev-default/skill-covers/dev_default/demo/cover_1.png")
        self.assertEqual(url, cover_url)
        self.minio.remove.assert_not_called()

    def test_save_rolls_back_minio_when_mysql_fails(self) -> None:
        self.repo.get.return_value = None
        self.minio.put.return_value = "dev-default/skill-covers/x.png"
        self.repo.set.side_effect = ValueError("技能不存在")
        png = b"\x89PNG\r\n\x1a\n" + b"payload"

        with self.assertRaises(ValueError):
            self.store.save("demo", png, "image/png")

        self.minio.remove.assert_called_once_with("dev-default/skill-covers/x.png")

    def test_delete_skill_removes_object_but_can_keep_row(self) -> None:
        self.repo.get.return_value = SkillCoverRecord(
            name="demo",
            cover_url="/skills/demo/cover?t=1",
            cover_object_key="dev-default/skill-covers/demo.png",
        )

        removed = self.store.delete("demo", clear_row=False)

        self.assertTrue(removed)
        self.minio.remove.assert_called_once_with("dev-default/skill-covers/demo.png")
        self.repo.clear.assert_not_called()

    def test_clear_cover_removes_object_and_mysql_columns(self) -> None:
        self.repo.get.return_value = SkillCoverRecord(
            name="demo",
            cover_url="/skills/demo/cover?t=1",
            cover_object_key="dev-default/skill-covers/demo.png",
        )

        self.store.delete("demo", clear_row=True)

        self.minio.remove.assert_called_once()
        self.repo.clear.assert_called_once_with("demo")


if __name__ == "__main__":
    unittest.main()
