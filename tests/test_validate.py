"""Behavior tests for scripts/validate.py (core invariant checks)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "scripts" / "validate.py"


class ValidateScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name) / "starter"
        system_dir = self.workspace / "vault" / "00-系统"
        system_dir.mkdir(parents=True)
        # 从真实仓库拷贝版本声明文件，保证与产品线 fixture 同步
        for name in ("manifest.yaml", "schema.md"):
            shutil.copy(ROOT / "vault" / "00-系统" / name, system_dir / name)
        readme = self.workspace / "README.md"
        m = __import__("re").search(
            r"当前版本\*\*：v([0-9.]+)", (ROOT / "README.md").read_text(encoding="utf-8")
        )
        readme.write_text(f"# README\n\n- **当前版本**：v{m.group(1)}（正式版）。\n", encoding="utf-8")
        self.knowledge = self.workspace / "vault" / "学习" / "01-知识"
        (self.knowledge / "_drafts").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_validate(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        return subprocess.run(
            [sys.executable, str(VALIDATE)],
            env=env,
            text=True,
            capture_output=True,
        )

    def test_clean_workspace_passes(self) -> None:
        result = self.run_validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validate: OK", result.stdout)

    def test_active_page_without_confirmed_at_is_warned(self) -> None:
        (self.knowledge / "无确认页.md").write_text(
            "---\ntitle: 无确认页\nstatus: active\n---\n正文\n", encoding="utf-8"
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0)  # WARN 不产生 ERROR
        self.assertIn("缺 confirmed_at", result.stdout)

    def test_compliant_active_page_is_not_warned(self) -> None:
        (self.knowledge / "_drafts" / "合规页.md").write_text(
            "---\ntitle: 前身\nstatus: draft\n---\n草稿\n", encoding="utf-8"
        )
        (self.knowledge / "合规页.md").write_text(
            "---\ntitle: 合规页\nstatus: active\nconfirmed_at: 2026-09-09\n---\n正文\n",
            encoding="utf-8",
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("promotion-warn", result.stdout)

    def test_absolute_path_leak_is_warned(self) -> None:
        (self.knowledge / "_drafts" / "泄露草稿.md").write_text(
            "---\ntitle: 泄露草稿\nstatus: draft\n---\n原始路径见 /Users/someone/tmp\n",
            encoding="utf-8",
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0)
        self.assertIn("privacy-warn", result.stdout)

    def test_version_line_drift_is_error(self) -> None:
        manifest = self.workspace / "vault" / "00-系统" / "manifest.yaml"
        text = __import__("re").sub(
            r'starter_version:\s*"[^"]+"', 'starter_version: "9.9.9"', manifest.read_text(encoding="utf-8")
        )
        manifest.write_text(text, encoding="utf-8")
        result = self.run_validate()
        self.assertEqual(result.returncode, 2)
        self.assertIn("version-error", result.stdout)

    def test_active_with_superseded_by_is_warned(self) -> None:
        (self.knowledge / "被取代页.md").write_text(
            "---\ntitle: 被取代页\nstatus: active\nsuperseded_by: [[新页]]\n---\n正文\n",
            encoding="utf-8",
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0)  # WARN 不产生 ERROR
        self.assertIn("supersede-warn", result.stdout)
        self.assertIn("status=active 却带 superseded_by", result.stdout)

    def test_superseded_by_broken_link_is_warned(self) -> None:
        (self.knowledge / "旧页.md").write_text(
            "---\ntitle: 旧页\nstatus: frozen\nsuperseded_by: [[不存在的页]]\n---\n正文\n",
            encoding="utf-8",
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0)
        self.assertIn("supersede-warn", result.stdout)
        self.assertIn("指向页不存在", result.stdout)

    def test_frozen_without_superseded_by_is_silent_by_default(self) -> None:
        (self.knowledge / "冻结页.md").write_text(
            "---\ntitle: 冻结页\nstatus: frozen\n---\n正文\n",
            encoding="utf-8",
        )
        result = self.run_validate()
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("supersede-note", result.stdout)

    def test_frozen_without_superseded_by_shown_in_verbose(self) -> None:
        (self.knowledge / "冻结页.md").write_text(
            "---\ntitle: 冻结页\nstatus: frozen\n---\n正文\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["STARTER_ROOT"] = str(self.workspace)
        result = subprocess.run(
            [sys.executable, str(VALIDATE), "--verbose"],
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("supersede-note", result.stdout)


if __name__ == "__main__":
    unittest.main()
