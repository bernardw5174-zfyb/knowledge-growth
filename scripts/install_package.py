#!/usr/bin/env python3
"""Install a vertical pack into the Core vault (_packages/ + domain workspace).

Usage:
    python3 scripts/install_package.py <repo-url> [<package-name>]

Example:
    python3 scripts/install_package.py https://github.com/bernardw5174-zfyb/job-search-bw.git

What it does:
    1. git clone <repo-url> into vault/_packages/<package_name> (read-only reference area)
    2. Validate manifest.yaml exists and package_name/domain fields are present
    3. Create the domain workspace vault/<domain>/ (00-raw..04-复盘) via create_domain.py
    4. Register the domain in vault/00-系统/manifest.yaml active_domains

Safety:
    - Never writes into _packages/<package_name>/ (read-only reference area)
    - Never touches user data outside vault/<domain>/
    - Idempotent: if package already installed, offers git pull instead of re-clone
"""
from datetime import date
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def run(cmd: list, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def parse_manifest(manifest_path: Path) -> dict:
    """Minimal YAML-ish parse: pull package_name / domain / version / mount_path."""
    info = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z_]+):\s*(.+)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"\'')
            if key in ("package_name", "domain", "version", "mount_path", "package_type"):
                info[key] = val
    return info


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    repo_url = sys.argv[1]
    root = workspace_root()
    vault = root / "vault"
    packages_dir = vault / "_packages"

    # --- 1. clone ---
    if not shutil.which("git"):
        print("ERROR: git not found in PATH. Install git first.")
        return 1

    # Determine package name: explicit arg > repo URL basename
    if len(sys.argv) >= 3:
        package_name = sys.argv[2]
    else:
        base = repo_url.rstrip("/").split("/")[-1]
        package_name = base[:-4] if base.endswith(".git") else base

    packages_dir.mkdir(parents=True, exist_ok=True)
    target = packages_dir / package_name

    if target.exists():
        print(f"[install_package] '{package_name}' already exists at {target}")
        print("  → 运行 git pull 升级：")
        print(f"    cd {target} && git pull")
        print("  → 或先删除旧目录再重装（确认无本地改动后）：")
        print(f"    rm -rf {target}")
        return 0

    print(f"[install_package] cloning {repo_url} → {target}")
    r = run(["git", "clone", repo_url, str(target)])
    if r.returncode != 0:
        print(f"ERROR: git clone failed:\n{r.stderr}")
        return 1

    # --- 2. validate manifest ---
    manifest_path = target / "manifest.yaml"
    if not manifest_path.exists():
        print(f"ERROR: {manifest_path} not found — not a valid vertical pack.")
        return 1

    info = parse_manifest(manifest_path)
    missing = [k for k in ("package_name", "domain") if k not in info]
    if missing:
        print(f"ERROR: manifest.yaml missing required fields: {', '.join(missing)}")
        return 1

    if info.get("package_name") != package_name:
        print(f"WARN: manifest.package_name='{info.get('package_name')}' != dir name '{package_name}'")
        print("  → 目录名应等于 manifest.package_name（包发现靠读 manifest，不靠目录名）")
        print("  → 建议重命名为：")
        print(f"    mv {target} {packages_dir / info['package_name']}")
        # 不自动改名，提示用户；继续用 manifest 的 package_name 建领域

    domain = info["domain"]
    print(f"[install_package] manifest OK: package={info.get('package_name')} domain={domain} version={info.get('version', '?')}")

    # --- 3. create domain workspace ---
    create_script = root / "scripts" / "create_domain.py"
    if create_script.exists():
        print(f"[install_package] creating domain workspace: vault/{domain}/")
        r = run([sys.executable, str(create_script), domain])
        if r.returncode != 0:
            print(f"WARN: create_domain.py failed:\n{r.stdout}\n{r.stderr}")
            print("  → 领域工作区未创建；可稍后手动运行：")
            print(f"    python3 scripts/create_domain.py {domain}")
        else:
            print(r.stdout.strip() if r.stdout.strip() else f"  → vault/{domain}/ created")
    else:
        print(f"WARN: scripts/create_domain.py not found — skipping domain workspace creation.")
        print(f"  → 手动创建：python3 scripts/create_domain.py {domain}")

    # --- 4. register domain in manifest active_domains ---
    core_manifest = vault / "00-系统" / "manifest.yaml"
    if core_manifest.exists():
        text = core_manifest.read_text(encoding="utf-8")
        if f"- {domain}" not in text:
            # 简单追加：active_domains: [] → 多行列表
            new_text = text.replace(
                "active_domains: []",
                "active_domains:\n" + f"  - {domain}",
                1,
            )
            if new_text == text:
                # 已是多行列表：在第一个 - item 前插入
                lines = text.splitlines()
                out = []
                inserted = False
                for line in lines:
                    if not inserted and line.strip().startswith("active_domains:"):
                        out.append(line)
                        out.append(f"  - {domain}")
                        inserted = True
                    else:
                        out.append(line)
                new_text = "\n".join(out)
            core_manifest.write_text(new_text, encoding="utf-8")
            print(f"[install_package] registered domain '{domain}' in vault/00-系统/manifest.yaml active_domains")
        else:
            print(f"[install_package] domain '{domain}' already in active_domains")

    # --- 5. summary ---
    print()
    print("=" * 60)
    print(f"✅ 垂直包安装完成：{info.get('package_name')} v{info.get('version', '?')}")
    print(f"   包位置（只读）：vault/_packages/{package_name}/")
    print(f"   领域工作区：vault/{domain}/")
    print()
    print("下一步：在 Agent 里说「我要开始" + domain + "」")
    print("  → Agent 会扫描 _packages/*/manifest.yaml 按 domain 匹配，读包内 skills/ 执行任务")
    print()
    print("升级：cd vault/_packages/" + package_name + " && git pull")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
