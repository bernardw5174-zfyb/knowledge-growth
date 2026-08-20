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


if __name__ == "__main__":
    unittest.main(verbosity=2)
