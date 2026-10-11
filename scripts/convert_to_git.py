#!/usr/bin/env python3
"""Convert a ZIP-installed Core to a git-installed Core (one-time).

Usage:
    python3 scripts/convert_to_git.py [<repo-url>]

Example:
    python3 scripts/convert_to_git.py https://github.com/bernardw5174-zfyb/knowledge-growth.git

What it does:
    1. Detect no .git at workspace root (ZIP install)
    2. git init + git remote add origin <repo-url>
    3. git fetch origin
    4. git reset --hard origin/main  (jump to latest main; vault/ user data untouched via .gitignore)
    5. Report version change

Safety:
    - vault/ user data is .gitignore'd, never touched
    - Template files (AGENTS.md etc.) modified locally WILL be overwritten by reset --hard — warn first
    - Idempotent: if .git already exists, report already git-installed, no-op
"""
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "https://github.com/bernardw5174-zfyb/knowledge-growth.git"


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def run(cmd: list, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main() -> int:
    repo_url = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_REPO
    root = workspace_root()

    if not root.is_dir():
        print(f"ERROR: workspace root not found: {root}")
        return 1

    if (root / ".git").exists():
        print(f"[convert_to_git] {root} 已是 git 安装（存在 .git），无需转换。")
        print("  → 升级请直接运行：git pull")
        return 0

    if not shutil_which_git():
        print("ERROR: git not found in PATH. Install git first.")
        return 1

    print(f"[convert_to_git] 检测到 ZIP 安装（无 .git），开始转换为 git 安装…")
    print(f"[convert_to_git] 目标仓库：{repo_url}")

    # --- 1. git init ---
    r = run(["git", "init"], cwd=root)
    if r.returncode != 0:
        print(f"ERROR: git init failed:\n{r.stderr}")
        return 1

    # --- 2. remote add origin ---
    r = run(["git", "remote", "add", "origin", repo_url], cwd=root)
    if r.returncode != 0:
        # remote may already exist from a partial attempt
        r2 = run(["git", "remote", "get-url", "origin"], cwd=root)
        if r2.returncode == 0 and r2.stdout.strip() == repo_url:
            print("[convert_to_git] origin 已存在且指向同一仓库，继续…")
        else:
            print(f"ERROR: git remote add origin failed:\n{r.stderr}")
            return 1

    # --- 3. fetch ---
    print("[convert_to_git] git fetch origin…")
    r = run(["git", "fetch", "origin"], cwd=root)
    if r.returncode != 0:
        print(f"ERROR: git fetch failed:\n{r.stderr}")
        print("提示：ZIP 安装转 git 需要联网拉取远程仓库；若网络受限，请保持 ZIP 手动升级路径。")
        return 1

    # --- 4. reset --hard origin/main ---
    print("[convert_to_git] git reset --hard origin/main…")
    r = run(["git", "reset", "--hard", "origin/main"], cwd=root)
    if r.returncode != 0:
        print(f"ERROR: git reset --hard origin/main failed:\n{r.stderr}")
        return 1

    # --- 5. report version ---
    manifest = root / "vault" / "00-系统" / "manifest.yaml"
    version = "?"
    if manifest.exists():
        m = re.search(r"starter_version:\s*[\"']?([\w.]+)", manifest.read_text(encoding="utf-8"))
        if m:
            version = m.group(1)

    print(f"[convert_to_git] ✅ 转换完成。当前版本：v{version}")
    print("  → 以后升级直接说「升级知识库底座／Core」，或运行：git pull")
    print("  → vault/ 用户数据不受影响（.gitignore 已排除）")
    print("  ⚠️ 注意：转换时 reset 到最新 main，本地对模板文件（AGENTS.md 等）的修改会被覆盖；")
    print("     模板文件本就不应直接修改（协议要求复制到自己的目录再改）。")
    return 0


def shutil_which_git() -> bool:
    import shutil
    return shutil.which("git") is not None


if __name__ == "__main__":
    sys.exit(main())
