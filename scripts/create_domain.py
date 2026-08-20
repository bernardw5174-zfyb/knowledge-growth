#!/usr/bin/env python3
"""Create one confirmed domain using the Starter's domain-first structure.
Usage: python3 scripts/create_domain.py <domain>

Set STARTER_ROOT only for automated tests. Normal use derives the root
from this script's parent directory.
"""
from datetime import date
import os
from pathlib import Path
import re
import sys


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 scripts/create_domain.py <domain>")
        return 2

    domain = sys.argv[1].strip()
    if not domain or len(domain) > 40 or re.search(r"[\\/\x00|]", domain):
        print(f"ERROR: invalid domain: {domain!r}")
        return 2
    if domain in {"00-系统", "_templates", "scripts", "结果", "tests"}:
        print(f"ERROR: reserved domain name: {domain}")
        return 2

    root = workspace_root()
    system_dir = root / "vault" / "00-系统"
    if not system_dir.is_dir():
        print("ERROR: starter system directory is missing")
        return 2

    domain_dir = root / "vault" / domain
    folders = [
        domain_dir / "00-raw",
        domain_dir / "01-知识" / "_drafts",
        domain_dir / "02-框架",
        domain_dir / "03-实战",
        domain_dir / "04-复盘",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    readmes = {
        domain_dir / "00-raw" / "README.md": "# 原始材料\n\n本领域原始材料的字节级副本。只进不改。\n",
        domain_dir / "01-知识" / "README.md": "# 知识\n\n只放用户明确确认过的知识页。\n",
        domain_dir / "01-知识" / "_drafts" / "README.md": "# 知识草稿\n\nAgent 生成、等待用户确认的草稿。未经确认不得晋升。\n",
        domain_dir / "02-框架" / "README.md": "# 框架\n\n只放用户确认过、可跨问题复用的判断规则。\n",
        domain_dir / "03-实战" / "README.md": "# 实战\n\n只放用户明确要记录的判断、行动与验证点。\n",
        domain_dir / "04-复盘" / "README.md": "# 复盘\n\n记录结果、修正与经验。\n",
    }
    for path, content in readmes.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    index_path = system_dir / "index.md"
    if index_path.exists():
        index = index_path.read_text(encoding="utf-8")
        marker = f"| {domain} |"
        if marker not in index:
            placeholder = "| （尚无） |  |  |"
            entry = f"| {domain} | {date.today().isoformat()} | 用户确认后由 Starter 创建 |"
            if placeholder in index:
                index = index.replace(placeholder, entry)
            else:
                index = index.rstrip() + "\n" + entry + "\n"
            index_path.write_text(index, encoding="utf-8")

    print(f"domain-ready: vault/{domain}")
    for folder in folders:
        print(f"  {folder.relative_to(root)}")
    print("index-updated: vault/00-系统/index.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
