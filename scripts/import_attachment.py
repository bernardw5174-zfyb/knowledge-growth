#!/usr/bin/env python3
"""Byte-copy one runtime-provided chat attachment into one confirmed domain.
Never overwrite an existing Raw file with different bytes.
Usage: python3 scripts/import_attachment.py <attachment-path> <domain>

Set STARTER_ROOT only for automated tests. Normal use derives the root
from this script's parent directory.
"""
from datetime import datetime
from pathlib import Path
import filecmp
import hashlib
import os
import re
import shutil
import sys


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python3 scripts/import_attachment.py <attachment-path> <domain>")
        return 2

    src = Path(sys.argv[1])
    domain = sys.argv[2].strip()
    if not src.is_file():
        print("ERROR: attachment path is not a readable file")
        return 2
    if not domain or len(domain) > 40 or re.search(r"[\\/\x00|]", domain):
        print("ERROR: invalid domain")
        return 2

    root = workspace_root()
    domain_dir = root / "vault" / domain
    raw_dir = domain_dir / "00-raw"
    drafts_dir = domain_dir / "01-知识" / "_drafts"
    if not raw_dir.is_dir() or not drafts_dir.is_dir():
        print(f"ERROR: domain not initialized: vault/{domain}; run create_domain.py first")
        return 2

    dest = raw_dir / src.name
    source_hash = sha256(src)
    if dest.exists():
        if sha256(dest) == source_hash:
            print(f"raw-path: {dest.relative_to(root)}")
            print("byte-identical: YES")
            print("raw-status: existing-identical")
            return 0
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = raw_dir / f"{src.stem}-{stamp}{src.suffix}"

    shutil.copy2(src, dest)
    identical = filecmp.cmp(src, dest, shallow=False)
    print(f"raw-path: {dest.relative_to(root)}")
    print(f"byte-identical: {'YES' if identical else 'NO'}")
    print("raw-status: copied-new" if identical else "raw-status: copy-mismatch")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
