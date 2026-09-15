#!/usr/bin/env python3
"""Validate core invariants of a 知识生长 Starter workspace.

Checks (aligns with AGENTS.md 最终汇报协议; run before reporting completion):

1. Privacy (WARN): 持久化文件中出现本机绝对路径 / 用户名 / 临时下载路径。
   命中输出为「待复核」而非硬失败——草稿正文可能正当地讨论路径模式。
2. Promotion audit (WARN): `01-知识/` 顶层的 `status: active` 页须有
   `confirmed_at`（机器可读晋升留痕，schema 字段）+ `_drafts/` 同名前身。
   缺失说明晋升无据可查（审计语义，不是机械拦截）。
3. Version lines (ERROR): manifest `starter_version`（产品线）与
   schema.md 头部「随产品 vX 发布」标注、README「当前版本」一致；
   schema.md 头部 `schema_version`（协议线）必须存在。
   双版本线不一致不是漂移；但三处产品线互相打架是漂移。
4. Supersede temporal consistency (WARN): `status: active` 却带
   `superseded_by` → WARN（自相矛盾）；`superseded_by` 指向的页不存在 → WARN
   （断链）；`status: frozen|archived` 但无 `superseded_by` → 降噪提示
   （仅 --verbose 显示；早期库「冻结等替代页」是常态）。

Usage: python3 scripts/validate.py
Set STARTER_ROOT only for automated tests. Normal use derives the root
from this script's parent directory.

Exit code: 0 = pass (WARN allowed), 2 = at least one ERROR.
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import sys


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


# --- Privacy patterns -------------------------------------------------------

# 显式写死的路径/用户名特征；命中只报 WARN（标记待复核），不硬失败。
_ABSOLUTE_PATH_MARKERS = [
    "/Users/",           # macOS 家目录
    "/home/",            # Linux 家目录
    r"C:\\Users\\",      # Windows 家目录（字面反斜杠）
    "/tmp/",
    "/var/folders/",     # macOS 临时目录
    "/private/",
    "/Volumes/",
    "/AppData/Local/Temp/",
]
_TEMP_DOWNLOAD_MARKERS = ["Downloads", "AppData\\Local\\Temp"]


def _username_hints() -> list[str]:
    """返回可能暴露本机用户名的字符串（家目录 basename + 登录名）。

    太短的常见词（user/admin/win 等）跳过，避免把普通内容误报成用户名。
    """
    hints: list[str] = []
    home = Path.home()
    if home.name and len(home.name) >= 4:
        hints.append(home.name)
    try:
        login = getpass.getuser()
    except Exception:
        login = ""
    if login and login != home.name and len(login) >= 4:
        hints.append(login)
    return hints


def _privacy_hits(text: str, rel_path: str, username_hints: list[str]) -> list[str]:
    hits: list[str] = []
    for marker in _ABSOLUTE_PATH_MARKERS:
        if marker in text:
            hits.append(f"绝对路径特征 {marker!r}")
            break  # 一个文件报一条类别即可，避免刷屏
    for hint in username_hints:
        if hint in text:
            hits.append(f"用户名 {hint!r}")
            break
    for marker in _TEMP_DOWNLOAD_MARKERS:
        if marker in text:
            hits.append(f"下载/临时目录特征 {marker!r}")
            break
    return hits


# --- Frontmatter helpers ----------------------------------------------------

_FM_KEY_RE = {
    "status": re.compile(r"^status\s*:\s*(\w+)", re.M),
    "confirmed_at": re.compile(r"^confirmed_at\s*:\s*(\d{4}-\d{2}-\d{2})", re.M),
    "schema_version": re.compile(r"schema_version\s*:\s*([0-9][0-9.]*)"),
    "released_with": re.compile(r"随产品 v([0-9][0-9.]*) 发布"),
    "superseded_by": re.compile(r"^superseded_by\s*:\s*(.+)$", re.M),
}


def _fm_value(text: str, key: str) -> str | None:
    m = _FM_KEY_RE[key].search(text)
    return m.group(1) if m else None


# --- Check 2: promotion audit -----------------------------------------------

def _check_promotion(root: Path, warns: list[str]) -> None:
    vault = root / "vault"
    if not vault.is_dir():
        return
    for domain_dir in sorted(p for p in vault.iterdir() if p.is_dir()):
        knowledge_dir = domain_dir / "01-知识"
        if not knowledge_dir.is_dir():
            continue
        drafts_dir = knowledge_dir / "_drafts"
        # 顶层正式页（不含 _drafts/）
        for page in sorted(p for p in knowledge_dir.iterdir() if p.is_file() and p.suffix == ".md"):
            rel = page.relative_to(root)
            text = page.read_text(encoding="utf-8")
            status = _fm_value(text, "status")
            if status == "active":
                if _fm_value(text, "confirmed_at") is None:
                    warns.append(f"promotion-warn: {rel}: status=active 但缺 confirmed_at（疑似未经用户确认晋升，或旧版未留痕）")
                if not drafts_dir.is_dir() or not (drafts_dir / page.name).exists():
                    warns.append(f"promotion-warn: {rel}: 在 _drafts/ 未见同名前身（晋升审计弱检查，仅提示）")
            elif status == "draft":
                # 草稿不应有 confirmed_at（schema：晋升动作才写入）
                if _fm_value(text, "confirmed_at") is not None:
                    warns.append(f"promotion-warn: {rel}: status=draft 却带 confirmed_at（草稿不填，晋升时才写）")


# --- Check 3: version lines -------------------------------------------------

def _check_versions(root: Path, errors: list[str]) -> None:
    manifest_path = root / "vault" / "00-系统" / "manifest.yaml"
    schema_path = root / "vault" / "00-系统" / "schema.md"
    readme_path = root / "README.md"

    if manifest_path.is_file():
        manifest_text = manifest_path.read_text(encoding="utf-8")
        m = re.search(r"^starter_version\s*:\s*[\"']?([0-9][0-9.]*)", manifest_text, re.M)
        starter_version = m.group(1) if m else None
    else:
        starter_version = None
    if schema_path.is_file():
        schema_text = schema_path.read_text(encoding="utf-8")
        schema_version = _fm_value(schema_text, "schema_version")
        released_with = _fm_value(schema_text, "released_with")
    else:
        schema_version = None
        released_with = None
    readme_version = None
    if readme_path.is_file():
        m = re.search(r"当前版本\*\*：v([0-9][0-9.]*)", readme_path.read_text(encoding="utf-8"))
        readme_version = m.group(1) if m else None

    if schema_version is None:
        errors.append("version-error: vault/00-系统/schema.md: 头部缺 schema_version 声明（协议线必须存在）")

    # 产品线：manifest == schema「随产品发布」标注 == README「当前版本」
    product_line = {"manifest starter_version": starter_version,
                    "schema 随产品发布标注": released_with,
                    "README 当前版本": readme_version}
    present = {k: v for k, v in product_line.items() if v is not None}
    values = set(present.values())
    if len(values) > 1:
        details = "；".join(f"{k}={v}" for k, v in product_line.items() if v is not None)
        errors.append(f"version-error: 产品版本线不一致（双版本线下 schema_version 可不同，但产品线三处必须一致）：{details}")
    elif not present:
        errors.append("version-error: 无法读取任何产品版本声明（manifest/schema/README 至少一处）")


# --- Check 4: supersede temporal consistency --------------------------------

def _supersede_target_exists(root: Path, page: Path, raw_target: str) -> bool:
    """superseded_by 取值支持 裸文件名 / [[文件名]] / [[路径|别名]] 三种形态。"""
    t = raw_target.strip()
    if t.startswith("[["):
        t = t[2:]
    if t.endswith("]]"):
        t = t[:-2]
    t = t.split("|")[0].strip()
    if not t:
        return True  # 空目标不判断链
    if not t.endswith(".md"):
        t += ".md"
    if (page.parent / t).exists():
        return True
    # 兜底：vault 任意位置存在同名页也算可解析
    for p in (root / "vault").rglob(t):
        return True
    return False


def _check_supersede(root: Path, warns: list[str], verbose: bool = False) -> None:
    """Check 4: superseded_by 时态一致性（规则 1/2 走 WARN；规则 3 降噪）。

    Rule 1: status=active 却带 superseded_by → WARN（自相矛盾）。
    Rule 2: superseded_by 指向的页在库内不存在 → WARN（断链）。
    Rule 3: status=frozen|archived 但无 superseded_by → 仅 verbose 提示
    （早期库「冻结等替代页」是常态，不做豁免标记字段）。
    """
    vault = root / "vault"
    if not vault.is_dir():
        return
    for domain_dir in sorted(p for p in vault.iterdir() if p.is_dir()):
        for sub in ("01-知识", "02-框架"):
            top = domain_dir / sub
            if not top.is_dir():
                continue
            for page in sorted(p for p in top.iterdir() if p.is_file() and p.suffix == ".md"):
                rel = page.relative_to(root)
                text = page.read_text(encoding="utf-8")
                status = _fm_value(text, "status")
                superseded = _fm_value(text, "superseded_by")
                if superseded is None:
                    if status in ("frozen", "archived") and verbose:
                        warns.append(
                            f"supersede-note: {rel}: status={status} 但无 superseded_by"
                            "（可能只是手工归档/冻结；不要求一定有替代页）"
                        )
                    continue
                if status == "active":
                    warns.append(
                        f"supersede-warn: {rel}: status=active 却带 superseded_by"
                        "（自相矛盾：active 表示现行，superseded_by 表示被取代）"
                    )
                if not _supersede_target_exists(root, page, superseded):
                    warns.append(f"supersede-warn: {rel}: superseded_by 指向页不存在（断链）")


# --- main -------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="校验知识生长 Starter 工作区核心不变量")
    parser.add_argument("--verbose", action="store_true", help="显示降噪级提示（如 supersede-note）")
    args = parser.parse_args()

    root = workspace_root()
    warns: list[str] = []
    errors: list[str] = []

    username_hints = _username_hints()

    # Check 1: privacy（扫描 vault 下全部 md/yaml 持久化文本；跳过 .git 等）
    vault = root / "vault"
    if vault.is_dir():
        scanned = 0
        for path in sorted(vault.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".yaml", ".yml"}:
                continue
            if ".git" in path.parts or ".pytest_cache" in path.parts:
                continue
            rel = path.relative_to(root)
            text = path.read_text(encoding="utf-8", errors="replace")
            scanned += 1
            for hit in _privacy_hits(text, str(rel), username_hints):
                warns.append(f"privacy-warn: {rel}: {hit}（标记待复核，非硬失败；确属泄露则修正）")
        if scanned == 0:
            warns.append("privacy-warn: vault/ 下未扫描到 md/yaml 文件（工作区为空？）")
    else:
        errors.append("version-error: vault/ 目录缺失，不是有效的 Starter 工作区")

    # Check 2: promotion
    _check_promotion(root, warns)

    # Check 3: versions
    _check_versions(root, errors)

    # Check 4: supersede temporal consistency
    _check_supersede(root, warns, verbose=args.verbose)

    for w in warns:
        print(f"validate: {w}")
    for e in errors:
        print(f"validate: {e}")

    if errors:
        print(f"validate: FAIL ({len(errors)} error(s), {len(warns)} warn(s))")
        return 2
    if warns:
        print(f"validate: PASS-WITH-WARN ({len(warns)} warn(s))")
        return 0
    print("validate: OK (no errors, no warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
