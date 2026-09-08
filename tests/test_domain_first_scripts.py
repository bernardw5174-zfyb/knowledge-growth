"""Behavior tests for Starter v0.2 domain-first helper scripts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CREATE_DOMAIN = ROOT / "scripts" / "create_domain.py"
IMPORT_ATTACHMENT = ROOT / "scripts" / "import_attachment.py"
IMPORT_URL = ROOT / "scripts" / "import_url.py"


class DomainFirstScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name) / "starter"
        (self.workspace / "vault" / "00-系统").mkdir(parents=True)
        (self.workspace / "vault" / "00-系统" / "index.md").write_text(
            "# 知识生长 Starter 索引\n\n| 领域 | 首次建立 | 说明 |\n|---|---|---|\n| （尚无） |  |  |\n",
            encoding="utf-8",
        )
        self.attachment = Path(self.tempdir.name) / "material.md"
        self.attachment.write_text("first version\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        return subprocess.run(
            [sys.executable, str(script), *args],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_create_domain_uses_content_layers_and_updates_index(self) -> None:
        result = self.run_script(CREATE_DOMAIN, "学习")

        expected = [
            "00-raw",
            "01-知识",
            "01-知识/_drafts",
            "02-框架",
            "03-实战",
            "04-复盘",
        ]
        for relative in expected:
            self.assertTrue((self.workspace / "vault" / "学习" / relative).is_dir(), relative)
        self.assertIn("| 学习 |", (self.workspace / "vault" / "00-系统" / "index.md").read_text(encoding="utf-8"))
        self.assertIn("domain-ready: vault/学习", result.stdout)

    def test_import_attachment_copies_bytes_without_overwriting_different_same_name(self) -> None:
        self.run_script(CREATE_DOMAIN, "学习")
        first = self.run_script(IMPORT_ATTACHMENT, str(self.attachment), "学习")
        raw_dir = self.workspace / "vault" / "学习" / "00-raw"
        first_raw = raw_dir / "material.md"
        self.assertEqual(first_raw.read_bytes(), self.attachment.read_bytes())
        self.assertIn("byte-identical: YES", first.stdout)

        repeated = self.run_script(IMPORT_ATTACHMENT, str(self.attachment), "学习")
        self.assertIn("raw-status: existing-identical", repeated.stdout)
        self.assertEqual(len(list(raw_dir.glob("material*.md"))), 1)

        self.attachment.write_text("second different version\n", encoding="utf-8")
        changed = self.run_script(IMPORT_ATTACHMENT, str(self.attachment), "学习")
        raw_files = sorted(raw_dir.glob("material*.md"))
        self.assertEqual(len(raw_files), 2)
        self.assertEqual(first_raw.read_text(encoding="utf-8"), "first version\n")
        self.assertIn("raw-status: copied-new", changed.stdout)
        self.assertTrue(any(path.read_text(encoding="utf-8") == "second different version\n" for path in raw_files))

    def test_create_domain_rejects_path_like_domain_name(self) -> None:
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        result = subprocess.run(
            [sys.executable, str(CREATE_DOMAIN), "学习/坏名字"],
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR: invalid domain", result.stdout)

    def test_create_domain_updates_manifest_active_domains(self) -> None:
        manifest = self.workspace / "vault" / "00-系统" / "manifest.yaml"
        manifest.write_text("active_domains: []\n", encoding="utf-8")

        self.run_script(CREATE_DOMAIN, "学习")
        text = manifest.read_text(encoding="utf-8")
        self.assertIn("active_domains:", text)
        self.assertIn("- 学习", text)

        # 幂等：重复创建同一领域不重复添加
        self.run_script(CREATE_DOMAIN, "学习")
        text2 = manifest.read_text(encoding="utf-8")
        self.assertEqual(text2.count("- 学习"), 1)

        # 追加：新领域追加到列表
        self.run_script(CREATE_DOMAIN, "健康")
        text3 = manifest.read_text(encoding="utf-8")
        self.assertIn("- 健康", text3)
        self.assertEqual(text3.count("- 学习"), 1)


class ImportUrlScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import import_url

        cls.import_url = import_url

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name) / "starter"
        (self.workspace / "vault" / "00-系统").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_extract_body_prefers_js_content_and_keeps_image_placeholder(self) -> None:
        html_text = (
            "<html><body>"
            "<script>var x=1;</script>"
            "<div id='js_content'>"
            "<p>第一段文字</p><p><img src='a.jpg'>第二段</p>"
            "<script>var inner=2;</script>"
            "</div>"
            "<div>正文之外的内容不应出现</div>"
            "</body></html>"
        )
        body = self.import_url.extract_body(html_text)
        self.assertIn("第一段文字", body)
        self.assertIn("[图片]", body)
        self.assertIn("第二段", body)
        self.assertNotIn("正文之外的内容不应出现", body)

    def test_extract_title_prefers_og_title(self) -> None:
        html_text = (
            "<html><head><title>页内标题</title>"
            "<meta property='og:title' content='分享标题'></head></html>"
        )
        self.assertEqual(self.import_url.extract_title(html_text), "分享标题")

    def test_extract_date_from_published_time(self) -> None:
        html_text = (
            "<meta property='article:published_time' content='2026-06-13T10:00:00+08:00'>"
        )
        self.assertEqual(self.import_url.extract_date(html_text), "2026-06-13")

    def test_build_raw_markdown_marks_non_byte_identical(self) -> None:
        content = self.import_url.build_raw_markdown(
            "标题",
            "https://example.com/a",
            "2026-06-13",
            "2026-09-08 12:00 CST",
            "正文内容",
        )
        self.assertIn("字节级完整性：**否**", content)
        self.assertIn("原文 URL：https://example.com/a", content)
        self.assertIn("正文内容", content)

    def test_sanitize_filename_strips_illegal_chars(self) -> None:
        self.assertEqual(self.import_url.sanitize_filename('a/b:c*d?e"f'), "abcdef")

    def test_import_url_rejects_uninitialized_domain(self) -> None:
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        result = subprocess.run(
            [sys.executable, str(IMPORT_URL), "https://example.com/", "学习"],
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("domain not initialized", result.stdout)

    def test_import_url_rejects_non_http(self) -> None:
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        result = subprocess.run(
            [sys.executable, str(IMPORT_URL), "ftp://example.com/", "学习"],
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must start with http", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
